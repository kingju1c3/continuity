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

from continuity.boundary import arm_session, context_usage, get_arm, handoff_due
from continuity.cli import build_parser
from continuity.hooks import run_hook
from continuity.project import identity
from continuity.store import Store


def transcript(path: Path, used: int, model: str = "claude-opus-5-5") -> str:
    rows = [
        {"type": "user", "message": {"content": "hi"}},
        {"type": "assistant", "message": {"model": model, "usage": {"input_tokens": 2, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": used - 1002, "output_tokens": 50}}},
        # A sub-agent turn must not count toward the main thread's context.
        {"type": "assistant", "isSidechain": True, "message": {"model": model, "usage": {"input_tokens": 5}}},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return str(path)


class EarlyHandoverTests(unittest.TestCase):
    def setup_project(self, root: Path, home: str, sid="s1", **arm_extra):
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init"], check=True)
        d = root / ".continuity"
        d.mkdir(parents=True, exist_ok=True)
        (d / "enabled.json").write_text('{"schema":1,"enabled":true}')
        with patch.dict(os.environ, {"HOME": home}):
            st = Store.default()
            ident = identity(root)
            st.ensure_project(ident.key, str(ident.root))
            st.acquire_lease(ident.key, sid, "claude")
            arm_session(st, ident.key, sid, "claude", goal="ship it", label="FE", generation="1.1",
                        background_successor=arm_extra.pop("background_successor", True))
            if arm_extra:
                from continuity.boundary import set_arm_status
                set_arm_status(st, ident.key, sid, "armed", **arm_extra)
            st.close()

    def hook(self, root: Path, event: dict) -> dict | None:
        out = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps({"cwd": str(root), **event}))), redirect_stdout(out), redirect_stderr(io.StringIO()):
            run_hook("claude")
        return json.loads(out.getvalue()) if out.getvalue() else None

    def test_usage_is_measured_from_main_thread_turn(self):
        with TemporaryDirectory() as d:
            u = context_usage(transcript(Path(d) / "t.jsonl", 150_000))
            self.assertEqual(u["used"], 150_000)
            self.assertIsNone(context_usage(str(Path(d) / "missing.jsonl")))

    def test_threshold_and_window_settings(self):
        with TemporaryDirectory() as d:
            t = transcript(Path(d) / "t.jsonl", 150_000)
            self.assertEqual(handoff_due(t, {})["ratio"], 0.75)  # 200k default window, 0.75 threshold
            self.assertIsNone(handoff_due(t, {"context_window": 1_000_000}))
            self.assertIsNone(handoff_due(transcript(Path(d) / "u.jsonl", 100_000), {}))

    def test_hook_alerts_user_and_agent_once_then_per_prompt(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project, TemporaryDirectory() as td:
            root = Path(project)
            self.setup_project(root, home)
            t = transcript(Path(td) / "t.jsonl", 170_000)
            with patch.dict(os.environ, {"HOME": home}):
                first = self.hook(root, {"hook_event_name": "PostToolUse", "session_id": "s1", "tool_name": "Bash", "transcript_path": t})
                self.assertIn("Compaction is imminent", first["systemMessage"])
                self.assertIn("continuity/fe-session-1.2", first["systemMessage"])
                self.assertIn("Session FE 1.2", first["systemMessage"])
                ctx = first["hookSpecificOutput"]["additionalContext"]
                self.assertIn("continuity handover --handoff-file .continuity/HANDOFF.md", ctx)
                # Not on every tool call after the first alert...
                self.assertIsNone(self.hook(root, {"hook_event_name": "PostToolUse", "session_id": "s1", "tool_name": "Bash", "transcript_path": t}))
                # ...but on every user turn until the hand-over happens.
                again = self.hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "transcript_path": t})
                self.assertIn("Compaction is imminent", again["systemMessage"])

    def test_below_threshold_stays_silent(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project, TemporaryDirectory() as td:
            root = Path(project)
            self.setup_project(root, home)
            t = transcript(Path(td) / "t.jsonl", 50_000)
            with patch.dict(os.environ, {"HOME": home}):
                self.assertIsNone(self.hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "transcript_path": t}))

    def test_handover_embeds_narrative_and_launches_successor_in_same_checkout(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project).resolve()
            self.setup_project(root, home)
            (root / "wip.txt").write_text("unsaved work\n")
            hf = root / ".continuity" / "HANDOFF.md"
            hf.write_text("Decision: keep pull-in-place, because it survives a hub restart.\n")
            args = build_parser().parse_args(["--path", str(root), "handover", "--handoff-file", str(hf)])
            out = io.StringIO()
            with patch.dict(os.environ, {"HOME": home, "CLAUDE_CODE_SESSION_ID": "s1"}), patch(
                "continuity.boundary.shutil.which", return_value="/usr/bin/claude"
            ), patch("continuity.boundary._spawn_background", return_value=SimpleNamespace(pid=7)) as spawn, redirect_stdout(out):
                code = args.fn(args)
                self.assertEqual(code, 0)
                result = json.loads(out.getvalue())
                self.assertEqual(result["successor_name"], "Session FE 1.2")
                self.assertEqual(result["worktree_branch"], "continuity/fe-session-1.2")
                self.assertTrue(result["worktree"].startswith(str(root / ".claude" / "worktrees")))
                self.assertEqual(spawn.call_args.args[1], Path(result["worktree"]))
                latest = (root / ".continuity" / "LATEST.md").read_text()
                self.assertIn("## Agent Handoff", latest)
                self.assertIn("keep pull-in-place", latest)
                self.assertTrue((Path(result["worktree"]) / "wip.txt").is_file())
                st = Store.default()
                self.assertEqual(get_arm(st, identity(root).key, "s1")["status"], "transferred")
                st.close()


    def test_message_triggered_early_warning_says_start_will_be_refused(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project, TemporaryDirectory() as td:
            root = Path(project)
            self.setup_project(root, home)
            t = transcript(Path(td) / "t.jsonl", 170_000)
            with patch.dict(os.environ, {"HOME": home}):
                out = self.hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "transcript_path": t,
                                       "prompt": "Another Claude session sent a message:\n<cross-session-message>x</cross-session-message>"})
                ctx = out["hookSpecificOutput"]["additionalContext"]
                self.assertIn("the app will refuse the start here", ctx)
                self.assertIn("You remain the owner", ctx)
                plain = self.hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "transcript_path": t, "prompt": "go on"})
                self.assertNotIn("refuse the start here", plain["hookSpecificOutput"]["additionalContext"])

    def test_visible_handover_retires_predecessor_only_when_successor_arms(self):
        """The full visible flow: handover prepares (predecessor still owner), a re-run re-issues the same start,
        and the successor arming in its worktree, by tool call or by hand, completes the transfer."""
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project).resolve()
            self.setup_project(root, home, background_successor=False)
            hf = root / ".continuity" / "HANDOFF.md"
            hf.write_text("Decision: x.\n")
            env = {"HOME": home, "CLAUDE_CODE_SESSION_ID": "s1"}
            with patch.dict(os.environ, env):
                a = build_parser().parse_args(["--path", str(root), "handover", "--handoff-file", str(hf)])
                out = io.StringIO()
                with redirect_stdout(out):
                    self.assertEqual(a.fn(a), 0)
                first = json.loads(out.getvalue())
                self.assertTrue(first["visible"])
                self.assertIn("confirm-successor", first["next"])
                self.assertIn("you are STILL the owner", first["next"])
                st = Store.default()
                key = identity(root).key
                self.assertEqual(get_arm(st, key, "s1")["status"], "successor_starting")
                self.assertEqual(st.active_lease(key)["session_id"], "s1")
                st.close()
                # A re-run (e.g. after a refused start) re-issues the SAME start, no second worktree or number.
                out2 = io.StringIO()
                with redirect_stdout(out2):
                    self.assertEqual(a.fn(a), 0)
                again = json.loads(out2.getvalue())
                self.assertEqual(again["start"], first["start"])
                self.assertEqual(again["successor_name"], first["successor_name"])
            wt = Path(first["worktree"])
            with patch.dict(os.environ, {"HOME": home, "CLAUDE_CODE_SESSION_ID": "s2"}):
                arm2 = build_parser().parse_args(["--path", str(wt), "arm", "--host", "auto", "--goal", "g"])
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(arm2.fn(arm2), 0)
                st = Store.default()
                prev = get_arm(st, identity(root).key, "s1")
                self.assertEqual(prev["status"], "transferred")
                self.assertEqual(prev["successor_session"], "s2")
                self.assertIsNone(st.active_lease(identity(root).key))
                self.assertEqual(get_arm(st, identity(wt).key, "s2")["generation"], "1.2")
                st.close()

    def test_arm_generation_continues_a_chain_started_elsewhere(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project).resolve()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            with patch.dict(os.environ, {"HOME": home, "CLAUDE_CODE_SESSION_ID": "s9"}), redirect_stdout(io.StringIO()):
                for argv in (["arm", "--label", "FE"], ["arm", "--label", "FE", "--generation", "1.2"]):
                    a = build_parser().parse_args(["--path", str(root), *argv])
                    self.assertEqual(a.fn(a), 0)
                st = Store.default()
                self.assertEqual(get_arm(st, identity(root).key, "s9")["generation"], "1.2")
                st.close()


if __name__ == "__main__":
    unittest.main()
