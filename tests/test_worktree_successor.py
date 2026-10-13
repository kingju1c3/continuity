import io
import json
import os
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from continuity.boundary import arm_session, get_arm, next_generation
from continuity.handoff import validate_handoff
from continuity.hooks import run_hook
from continuity.project import identity
from continuity.store import Store


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


class WorktreeSuccessorTests(unittest.TestCase):
    """At the compaction boundary the successor starts in a new git worktree with the predecessor's
    uncommitted work, is labelled "Session <label> N.M+1", and is told it continues the predecessor."""

    def run_event(self, root: Path, event: dict):
        event = {"cwd": str(root), **event}
        out, err = io.StringIO(), io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(event))), redirect_stdout(out), redirect_stderr(err):
            run_hook("claude")
        return out.getvalue()

    def repo(self, base: Path) -> Path:
        root = base / "shop"
        root.mkdir()
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.email", "t@example.com")
        git(root, "config", "user.name", "T")
        (root / ".gitignore").write_text(".continuity/\n")
        (root / "app.py").write_text("print('v1')\n")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "init")
        (root / ".continuity").mkdir()
        (root / ".continuity" / "enabled.json").write_text('{"schema":1,"enabled":true}')
        return root

    def precompact(self, root: Path, sid: str):
        with patch("continuity.boundary.shutil.which", return_value="/usr/bin/claude"), patch(
            "continuity.boundary._spawn_background", return_value=SimpleNamespace(pid=4242)
        ) as popen:
            out = self.run_event(root, {"hook_event_name": "PreCompact", "session_id": sid, "trigger": "auto"})
        return json.loads(out), popen

    def test_generation_numbers(self):
        self.assertEqual(next_generation("1.0"), "1.1")
        self.assertEqual(next_generation("1.9"), "1.10")
        self.assertEqual(next_generation(None), "1.1")

    def test_successor_gets_worktree_with_work_in_progress_label_and_handoff(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as base, patch.dict(os.environ, {"HOME": home, "CLAUDE_CODE_REMOTE": ""}):
            root = self.repo(Path(base))
            self.run_event(root, {"hook_event_name": "SessionStart", "session_id": "s1", "source": "startup"})
            st = Store.default()
            arm_session(st, identity(root).key, "s1", "claude", goal="ship the booking chat", instructions="no PRs", label="SiteBooked")
            st.close()
            # Uncommitted work the successor must not lose: a tracked edit and a new file.
            (root / "app.py").write_text("print('v2 in progress')\n")
            (root / "notes.md").write_text("half-written plan\n")

            payload, popen = self.precompact(root, "s1")
            self.assertEqual(payload["decision"], "block")
            argv, cwd = popen.call_args.args
            name = argv[argv.index("--name") + 1]
            self.assertEqual(name, "Session SiteBooked 1.1")
            wt = root / ".claude" / "worktrees" / "continuity-sitebooked-1-1"
            self.assertEqual(Path(cwd).resolve(), wt.resolve())
            self.assertIn(str(wt), payload["reason"])
            self.assertIn("Session SiteBooked 1.1", payload["reason"])
            prompt = argv[-1]
            self.assertIn("You are Session SiteBooked 1.1. You are picking up exactly where Session SiteBooked 1.0 (session id s1) left off", prompt)
            self.assertIn("Goal: ship the booking chat", prompt)
            self.assertIn("uncommitted changes: applied", prompt)

            # The worktree has the predecessor's HEAD plus its uncommitted work; the predecessor's tree is untouched.
            self.assertEqual((wt / "app.py").read_text(), "print('v2 in progress')\n")
            self.assertEqual((wt / "notes.md").read_text(), "half-written plan\n")
            self.assertEqual((root / "app.py").read_text(), "print('v2 in progress')\n")
            branch = subprocess.run(["git", "-C", str(wt), "branch", "--show-current"], capture_output=True, text=True).stdout.strip()
            self.assertEqual(branch, "continuity/sitebooked-1-1")
            latest = (wt / ".continuity" / "LATEST.md").read_text()
            self.assertIn("Session label: Session SiteBooked 1.0", latest)
            self.assertIn("Work In Progress (lossless)", latest)
            self.assertIn("notes.md", latest)
            data = json.loads((wt / ".continuity" / "LATEST.json").read_text())
            self.assertEqual(validate_handoff(wt, data)[0].startswith("running in the successor worktree"), True)
            self.assertFalse(any(w.startswith("branch changed") or w.startswith("project root mismatch") for w in validate_handoff(wt, data)))

            st = Store.default()
            self.assertEqual(get_arm(st, identity(root).key, "s1")["status"], "transferred")
            self.assertIsNotNone(st.latest_handoff(identity(wt).key))  # `continuity resume` works in the worktree
            st.close()

            # The successor's own SessionStart (in the worktree, with its name) inherits the chain as 1.1 ...
            out = self.run_event(wt, {"hook_event_name": "SessionStart", "session_id": "s2", "source": "startup", "session_title": name})
            self.assertIn("designated successor", out)
            st = Store.default()
            arm2 = get_arm(st, identity(wt).key, "s2")
            st.close()
            self.assertEqual((arm2["label"], arm2["generation"], arm2["goal"]), ("SiteBooked", "1.1", "ship the booking chat"))
            # ... and its own boundary hands off to 1.2.
            payload, popen = self.precompact(wt, "s2")
            argv, cwd = popen.call_args.args
            self.assertEqual(argv[argv.index("--name") + 1], "Session SiteBooked 1.2")
            self.assertIn("picking up exactly where Session SiteBooked 1.1", argv[-1])

    def test_not_a_git_repo_falls_back_to_project_root(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project, patch.dict(os.environ, {"HOME": home, "CLAUDE_CODE_REMOTE": ""}):
            root = Path(project)
            (root / ".continuity").mkdir()
            (root / ".continuity" / "enabled.json").write_text('{"schema":1,"enabled":true}')
            self.run_event(root, {"hook_event_name": "SessionStart", "session_id": "s1", "source": "startup"})
            st = Store.default()
            arm_session(st, identity(root).key, "s1", "claude", goal="g")
            st.close()
            payload, popen = self.precompact(root, "s1")
            argv, cwd = popen.call_args.args
            self.assertEqual(Path(cwd), root.resolve())
            self.assertIn(f"Session {root.resolve().name} 1.1", payload["reason"])
            self.assertIn("No separate worktree was created", argv[-1])


if __name__ == "__main__":
    unittest.main()


class SpawnBackgroundTests(unittest.TestCase):
    def test_confirms_a_real_backgrounded_session(self):
        from continuity.boundary import _spawn_background
        with TemporaryDirectory() as d:
            got = _spawn_background(["sh", "-c", "echo 'backgrounded · 11844f29 · Session demo 1.1'"], Path(d))
            self.assertEqual(got.pid, "11844f29")

    def test_untrusted_workspace_is_a_failure_not_a_launch(self):
        from continuity.boundary import _spawn_background
        with TemporaryDirectory() as d:
            with self.assertRaises(OSError) as ctx:
                _spawn_background(["sh", "-c", "echo 'Workspace not trusted. Run claude once' >&2; exit 1"], Path(d))
            self.assertIn("Workspace not trusted", str(ctx.exception))
