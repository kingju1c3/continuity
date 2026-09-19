import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from continuity.boundary import arm_session, get_arm
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

    def arm(self, root: Path, home: str, sid="s1", host="claude", auto=True):
        with patch.dict(os.environ, {"HOME": home}):
            st = Store.default()
            ident = identity(root)
            arm_session(
                st,
                ident.key,
                sid,
                host,
                goal="finish the current feature",
                instructions="preserve current behavior",
                auto_successor=auto,
            )
            st.close()

    def test_unarmed_session_start_is_passive_but_acquires_lease(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            self.enabled_project(root)
            with patch.dict(os.environ, {"HOME": home}):
                code, out, err = self.run_event(
                    root,
                    {"hook_event_name": "SessionStart", "session_id": "s1", "source": "startup"},
                )
                self.assertEqual(code, 0)
                self.assertEqual(out, "")
                st = Store.default()
                lease = st.active_lease(identity(root).key)
                self.assertEqual(lease["session_id"], "s1")
                st.close()

    def test_disabled_project_is_noop(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            with patch.dict(os.environ, {"HOME": home}):
                code, out, _ = self.run_event(
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
            with patch.dict(os.environ, {"HOME": home}), patch(
                "sys.stdin", io.StringIO("{bad")
            ), redirect_stdout(out), redirect_stderr(err):
                code = run_hook("claude")
            self.assertEqual(code, 0)
            self.assertEqual(out.getvalue(), "")
            self.assertIn("ignored malformed", err.getvalue())

    def test_armed_posttooluse_marks_dirty_silently(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            self.enabled_project(root)
            with patch.dict(os.environ, {"HOME": home}):
                self.run_event(
                    root,
                    {"hook_event_name": "SessionStart", "session_id": "s1", "source": "startup"},
                )
                self.arm(root, home)
                _, out, _ = self.run_event(
                    root,
                    {
                        "hook_event_name": "PostToolUse",
                        "session_id": "s1",
                        "tool_name": "Edit",
                        "tool_input": {"file_path": str(root / "a.py")},
                    },
                )
                self.assertEqual(out, "")
                st = Store.default()
                state = st.index_state(identity(root).key)
                self.assertTrue(state["dirty"])
                self.assertEqual(state["last_file"], "a.py")
                st.close()

    def test_unarmed_precompact_is_noop(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            self.enabled_project(root)
            with patch.dict(os.environ, {"HOME": home}):
                self.run_event(
                    root,
                    {"hook_event_name": "SessionStart", "session_id": "s1", "source": "startup"},
                )
                _, out, _ = self.run_event(
                    root,
                    {"hook_event_name": "PreCompact", "session_id": "s1", "trigger": "auto"},
                )
                self.assertEqual(out, "")
                st = Store.default()
                self.assertIsNone(st.latest_handoff(identity(root).key))
                st.close()

    def test_armed_claude_precompact_alerts_captures_and_launches_successor(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            self.enabled_project(root)
            (root / "work.py").write_text("print('work')\n")
            with patch.dict(os.environ, {"HOME": home}):
                self.run_event(
                    root,
                    {"hook_event_name": "SessionStart", "session_id": "s1", "source": "startup"},
                )
                self.arm(root, home)
                with patch("continuity.boundary.shutil.which", return_value="/usr/bin/claude"), patch(
                    "continuity.boundary.subprocess.Popen",
                    return_value=SimpleNamespace(pid=4242),
                ) as popen:
                    _, out, _ = self.run_event(
                        root,
                        {
                            "hook_event_name": "PreCompact",
                            "session_id": "s1",
                            "trigger": "auto",
                        },
                    )
                payload = json.loads(out)
                self.assertEqual(payload["decision"], "block")
                self.assertIn("compaction is about to occur", payload["reason"])
                self.assertEqual(payload["terminalSequence"], "\u0007")
                argv = popen.call_args.args[0]
                self.assertIn("--bg", argv)
                self.assertIn("--name", argv)

                st = Store.default()
                ident = identity(root)
                h = st.latest_handoff(ident.key)
                self.assertEqual(h["kind"], "automatic-boundary")
                self.assertEqual(get_arm(st, ident.key, "s1")["status"], "transferred")
                pending = st.get_state(ident.key, "successor_pending")
                self.assertEqual(pending["status"], "launched")
                self.assertIsNone(st.active_lease(ident.key))
                st.close()

    def test_claude_launch_failure_restores_predecessor_ownership(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            self.enabled_project(root)
            with patch.dict(os.environ, {"HOME": home}):
                self.run_event(
                    root,
                    {"hook_event_name": "SessionStart", "session_id": "s1", "source": "startup"},
                )
                self.arm(root, home)
                with patch("continuity.boundary.shutil.which", return_value="/usr/bin/claude"), patch(
                    "continuity.boundary.subprocess.Popen",
                    side_effect=OSError("spawn failed"),
                ):
                    _, out, _ = self.run_event(
                        root,
                        {"hook_event_name": "PreCompact", "session_id": "s1", "trigger": "auto"},
                    )
                self.assertIn("automatic Claude successor launch failed", json.loads(out)["reason"])
                st = Store.default()
                ident = identity(root)
                self.assertEqual(st.active_lease(ident.key)["session_id"], "s1")
                self.assertEqual(get_arm(st, ident.key, "s1")["status"], "armed")
                st.close()

    def test_codex_precompact_stages_fresh_successor_and_next_session_inherits(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            self.enabled_project(root)
            with patch.dict(os.environ, {"HOME": home}):
                self.run_event(
                    root,
                    {"hook_event_name": "SessionStart", "session_id": "c1", "source": "startup"},
                    host="codex",
                )
                self.arm(root, home, sid="c1", host="codex")
                _, out, _ = self.run_event(
                    root,
                    {"hook_event_name": "PreCompact", "session_id": "c1", "trigger": "auto"},
                    host="codex",
                )
                alert = json.loads(out)
                self.assertFalse(alert["continue"])
                self.assertIn("fresh Codex successor is staged", alert["stopReason"])

                st = Store.default()
                ident = identity(root)
                self.assertIsNone(st.active_lease(ident.key))
                self.assertEqual(get_arm(st, ident.key, "c1")["status"], "transferred")
                st.close()

                _, start_out, _ = self.run_event(
                    root,
                    {"hook_event_name": "SessionStart", "session_id": "c2", "source": "startup"},
                    host="codex",
                )
                restored = json.loads(start_out)
                self.assertIn(
                    "designated successor",
                    restored["hookSpecificOutput"]["additionalContext"],
                )
                st = Store.default()
                self.assertEqual(st.active_lease(ident.key)["session_id"], "c2")
                self.assertEqual(get_arm(st, ident.key, "c2")["status"], "armed")
                st.close()

    def test_transferred_predecessor_blocks_further_prompt(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            self.enabled_project(root)
            with patch.dict(os.environ, {"HOME": home}):
                self.run_event(
                    root,
                    {"hook_event_name": "SessionStart", "session_id": "c1", "source": "startup"},
                    host="codex",
                )
                self.arm(root, home, sid="c1", host="codex")
                self.run_event(
                    root,
                    {"hook_event_name": "PreCompact", "session_id": "c1", "trigger": "auto"},
                    host="codex",
                )
                _, out, _ = self.run_event(
                    root,
                    {
                        "hook_event_name": "UserPromptSubmit",
                        "session_id": "c1",
                        "prompt": "keep editing here",
                    },
                    host="codex",
                )
                payload = json.loads(out)
                self.assertFalse(payload["continue"])
                self.assertIn("transferred", payload["stopReason"])

    def test_ordinary_stop_is_silent_when_armed(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            self.enabled_project(root)
            with patch.dict(os.environ, {"HOME": home}):
                self.run_event(
                    root,
                    {"hook_event_name": "SessionStart", "session_id": "s1", "source": "startup"},
                )
                self.arm(root, home)
                _, out, _ = self.run_event(
                    root, {"hook_event_name": "Stop", "session_id": "s1"}
                )
                self.assertEqual(out, "")
