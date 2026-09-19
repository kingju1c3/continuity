import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from continuity.hooks import run_hook
from continuity.project import identity
from continuity.store import Store


class HookTests(unittest.TestCase):
    def enabled_project(self, root: Path):
        d = root / ".continuity"
        d.mkdir(parents=True, exist_ok=True)
        (d / "enabled.json").write_text('{"schema":1,"enabled":true}')

    def run_event(self, root: Path, event: dict, host="claude"):
        event = {"cwd": str(root), **event}
        out, err = io.StringIO(), io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(event))), redirect_stdout(out), redirect_stderr(err):
            code = run_hook(host)
        return code, out.getvalue(), err.getvalue()

    def test_session_start_injects_real_context_and_acquires_lease(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            self.enabled_project(root)
            with patch.dict(os.environ, {"HOME": home}):
                code, out, err = self.run_event(
                    root,
                    {"hook_event_name": "SessionStart", "session_id": "s1", "source": "startup"},
                )
                self.assertEqual(code, 0)
                payload = json.loads(out)
                self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "SessionStart")
                self.assertIn("CONTINUITY PROJECT CONTEXT", payload["hookSpecificOutput"]["additionalContext"])
                st = Store.default()
                ident = identity(root)
                lease = st.active_lease(ident.key)
                self.assertEqual(lease["session_id"], "s1")
                st.close()

    def test_disabled_project_is_noop(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            with patch.dict(os.environ, {"HOME": home}):
                code, out, err = self.run_event(
                    Path(project),
                    {"hook_event_name": "SessionStart", "session_id": "s1", "source": "startup"},
                )
                self.assertEqual(code, 0)
                self.assertEqual(out, "")

    def test_malformed_input_does_not_mutate(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            self.enabled_project(root)
            out, err = io.StringIO(), io.StringIO()
            with patch.dict(os.environ, {"HOME": home}), patch("sys.stdin", io.StringIO("{bad")), redirect_stdout(out), redirect_stderr(err):
                code = run_hook("claude")
            self.assertEqual(code, 0)
            self.assertEqual(out.getvalue(), "")
            self.assertIn("ignored malformed", err.getvalue())

    def test_edit_marks_dirty_and_stop_feedback_is_one_shot(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            self.enabled_project(root)
            with patch.dict(os.environ, {"HOME": home}):
                self.run_event(
                    root,
                    {"hook_event_name": "SessionStart", "session_id": "s1", "source": "startup"},
                )
                _, edit_out, _ = self.run_event(
                    root,
                    {
                        "hook_event_name": "PostToolUse",
                        "session_id": "s1",
                        "tool_name": "Edit",
                        "tool_input": {"file_path": str(root / "a.py")},
                    },
                )
                self.assertIn("PostToolUse", edit_out)
                _, stop1, _ = self.run_event(
                    root, {"hook_event_name": "Stop", "session_id": "s1"}
                )
                _, stop2, _ = self.run_event(
                    root, {"hook_event_name": "Stop", "session_id": "s1"}
                )
                self.assertIn("continuity checkpoint", stop1)
                self.assertEqual(stop2, "")

    def test_postcompact_persists_host_summary(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            self.enabled_project(root)
            with patch.dict(os.environ, {"HOME": home}):
                self.run_event(
                    root,
                    {"hook_event_name": "PostCompact", "session_id": "s1", "trigger": "auto", "compact_summary": "important summary"},
                )
                st = Store.default()
                freeze = st.latest_freeze(identity(root).key)
                self.assertEqual(freeze["compact_summary"], "important summary")
                st.close()
