import io
import json
import os
import subprocess
import unittest
from argparse import Namespace
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from continuity.boundary import get_arm
from continuity.cli import cmd_arm, cmd_status
from continuity.install import install_repo
from continuity.project import identity
from continuity.store import Store

# Host-exported session variables must not leak in from the shell running the
# tests (e.g. a Claude Code session), so every case sets them explicitly.
CLEAN = {"CLAUDE_CODE_SESSION_ID": "", "CONTINUITY_SESSION_ID": ""}


def arm_args(root: Path, **kw) -> Namespace:
    base = dict(path=str(root), session=None, host="auto", goal="g", instructions="i", no_auto_successor=True)
    base.update(kw)
    return Namespace(**base)


def scrub(env: dict) -> dict:
    return {k: v for k, v in env.items() if v}


class SessionEnvTests(unittest.TestCase):
    @contextmanager
    def run_env(self, home: str, extra: dict):
        env = {**CLEAN, "HOME": home, **extra}
        # patch.dict restores the WHOLE environment on exit, including keys
        # removed inside it.
        with patch.dict(os.environ, scrub(env)):
            for k in [k for k, v in env.items() if not v]:
                os.environ.pop(k, None)
            yield

    def test_arm_uses_claude_exported_session_without_a_lease(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            with self.run_env(home, {"CLAUDE_CODE_SESSION_ID": "claude-sess-1"}), redirect_stdout(io.StringIO()):
                self.assertEqual(cmd_arm(arm_args(root)), 0)
                st = Store.default()
                arm = get_arm(st, identity(root).key, "claude-sess-1")
                st.close()
            self.assertEqual(arm["status"], "armed")
            self.assertEqual(arm["host"], "claude")

    def test_arm_still_refuses_without_any_exact_identity(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            err = io.StringIO()
            with self.run_env(home, {}), redirect_stderr(err):
                self.assertEqual(cmd_arm(arm_args(Path(project))), 2)
            self.assertIn("CLAUDE_CODE_SESSION_ID", err.getvalue())

    def test_explicit_continuity_session_wins_over_claude_env(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            with self.run_env(home, {"CLAUDE_CODE_SESSION_ID": "c", "CONTINUITY_SESSION_ID": "explicit"}), redirect_stdout(io.StringIO()):
                self.assertEqual(cmd_arm(arm_args(root, host="claude")), 0)
                st = Store.default()
                self.assertIsNotNone(get_arm(st, identity(root).key, "explicit"))
                self.assertIsNone(get_arm(st, identity(root).key, "c"))
                st.close()

    def test_status_reports_the_exported_sessions_arm(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            with self.run_env(home, {"CLAUDE_CODE_SESSION_ID": "s-env"}):
                with redirect_stdout(io.StringIO()):
                    cmd_arm(arm_args(root))
                out = io.StringIO()
                with redirect_stdout(out):
                    cmd_status(Namespace(path=str(root), session=None))
            status = json.loads(out.getvalue())
            self.assertEqual(status["session"], "s-env")
            self.assertEqual(status["armed"]["status"], "armed")


class InstallExcludeTests(unittest.TestCase):
    def git(self, root: Path, *args: str) -> None:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)

    def test_installed_skill_copy_is_kept_out_of_commits(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            self.git(root, "init", "-q")
            with patch.dict(os.environ, {"HOME": home}):
                install_repo(root, ["claude"])
            status = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
                                    capture_output=True, text=True, check=True).stdout
            self.assertNotIn("skills/continuity", status)
            self.assertIn(".claude/skills/continuity/", (root / ".git" / "info" / "exclude").read_text())

    def test_a_tracked_skill_copy_is_left_alone(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            self.git(root, "init", "-q")
            self.git(root, "config", "user.email", "t@example.invalid")
            self.git(root, "config", "user.name", "t")
            with patch.dict(os.environ, {"HOME": home}):
                install_repo(root, ["claude"])
            exclude = root / ".git" / "info" / "exclude"
            exclude.write_text("")
            self.git(root, "add", "-f", ".claude/skills/continuity")
            self.git(root, "commit", "-qm", "track it")
            with patch.dict(os.environ, {"HOME": home}):
                install_repo(root, ["claude"])
            self.assertNotIn("skills/continuity", exclude.read_text())

    def test_outside_git_install_still_works(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            with patch.dict(os.environ, {"HOME": home, "GIT_CEILING_DIRECTORIES": str(root.parent)}):
                plan = install_repo(root, ["claude"])
            self.assertTrue((root / ".claude" / "skills" / "continuity").exists())
            self.assertFalse(any("exclude" in p for p in plan))


if __name__ == "__main__":
    unittest.main()
