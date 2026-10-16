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

    def arm(self, root: Path, home: str, sid="s1", host="claude", auto=True, background=True):
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
                background_successor=background,
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
                    "continuity.boundary._spawn_background",
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

    def test_default_successor_is_a_visible_sidebar_clone_not_claude_bg(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            self.enabled_project(root)
            with patch.dict(os.environ, {"HOME": home}):
                self.run_event(root, {"hook_event_name": "SessionStart", "session_id": "s1", "source": "startup"})
                self.arm(root, home, background=False)
                with patch("continuity.boundary.shutil.which", return_value=None), patch(
                    "continuity.boundary._spawn_background") as spawn:
                    _, out, _ = self.run_event(root, {"hook_event_name": "PreCompact", "session_id": "s1", "trigger": "auto"})
                spawn.assert_not_called()
                reason = json.loads(out)["reason"]
                self.assertIn("mcp__ccd_session__start_session", reason)
                self.assertIn('"use_worktree": false', reason)
                self.assertNotIn("permission_mode\"", reason)
                self.assertIn("Never use `claude --bg`", reason)
                st = Store.default()
                ident = identity(root)
                # Nothing has started yet: the predecessor must NOT be transferred and must keep its lease
                # (2026-10-16: a refused start left "transferred" sessions blocked with no successor).
                self.assertEqual(get_arm(st, ident.key, "s1")["status"], "successor_starting")
                pending = st.get_state(ident.key, "successor_pending")
                self.assertEqual(pending["status"], "pending")  # the successor inherits it when it arms
                self.assertTrue(pending["visible"])
                self.assertEqual(pending["start"]["args"]["initiation"], "user_asked")
                self.assertEqual(st.active_lease(ident.key)["session_id"], "s1")
                st.close()

    def _prepare_visible(self, root: Path, home: str):
        self.enabled_project(root)
        self.run_event(root, {"hook_event_name": "SessionStart", "session_id": "s1", "source": "startup"})
        self.arm(root, home, background=False)
        with patch("continuity.boundary.shutil.which", return_value=None):
            self.run_event(root, {"hook_event_name": "PreCompact", "session_id": "s1", "trigger": "auto"})

    def test_unstarted_successor_never_blocks_the_predecessor(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            with patch.dict(os.environ, {"HOME": home}):
                self._prepare_visible(root, home)
                _, out, _ = self.run_event(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "next?"})
                payload = json.loads(out)
                self.assertNotEqual(payload.get("decision"), "block")
                ctx = payload["hookSpecificOutput"]["additionalContext"]
                self.assertIn("NOT confirmed started", ctx)
                self.assertIn("start it now", ctx)
                self.assertIn("confirm-successor", ctx)

    def test_message_triggered_turn_is_told_not_to_start(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            with patch.dict(os.environ, {"HOME": home}):
                self._prepare_visible(root, home)
                prompt = '<cross-session-message from="x">hi</cross-session-message>'
                _, out, _ = self.run_event(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": prompt})
                ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
                self.assertIn("will refuse a start now", ctx)
                self.assertNotIn("start it now", ctx)

    def test_confirm_successor_completes_the_transfer(self):
        from continuity.boundary import confirm_successor
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            with patch.dict(os.environ, {"HOME": home}):
                self._prepare_visible(root, home)
                st = Store.default()
                ident = identity(root)
                state = confirm_successor(st, ident.key, "s1", successor_session="local_abc")
                self.assertEqual(state["status"], "transferred")
                self.assertEqual(state["successor_session"], "local_abc")
                self.assertIsNone(st.active_lease(ident.key))
                self.assertEqual(st.get_state(ident.key, "successor_pending")["status"], "launched")
                self.assertIsNone(confirm_successor(st, ident.key, "nope"))
                st.close()
                _, out, _ = self.run_event(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "x"})
                self.assertEqual(json.loads(out)["decision"], "block")

    def test_waiting_handover_does_not_expire_and_can_be_cancelled(self):
        from continuity.boundary import cancel_handover, pending_successor
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            with patch.dict(os.environ, {"HOME": home}):
                self._prepare_visible(root, home)
                st = Store.default()
                ident = identity(root)
                p = st.get_state(ident.key, "successor_pending")
                st.set_state(ident.key, "successor_pending", {**p, "created_at": 1})  # long ago
                self.assertIsNotNone(pending_successor(st, ident.key))  # a waiting hand-over never expires
                state = cancel_handover(st, ident.key, "s1")
                self.assertEqual(state["status"], "armed")
                self.assertTrue(state["handover_declined"])
                self.assertIsNone(pending_successor(st, ident.key))  # cancelled: can no longer retire s1
                self.assertEqual(st.active_lease(ident.key)["session_id"], "s1")
                st.close()

    def test_manual_staging_keeps_predecessor_owner_until_successor_starts_here(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            self.enabled_project(root)
            with patch.dict(os.environ, {"HOME": home}):
                self.run_event(root, {"hook_event_name": "SessionStart", "session_id": "s1", "source": "startup"})
                self.arm(root, home, auto=False)
                self.run_event(root, {"hook_event_name": "PreCompact", "session_id": "s1", "trigger": "auto"})
                st = Store.default()
                ident = identity(root)
                self.assertEqual(get_arm(st, ident.key, "s1")["status"], "successor_starting")
                self.assertEqual(st.active_lease(ident.key)["session_id"], "s1")
                st.close()
                _, out, _ = self.run_event(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "hi"})
                self.assertIn("This hand-over is manual", json.loads(out)["hookSpecificOutput"]["additionalContext"])
                # The successor opens in the same folder: no lease conflict; it retires the predecessor.
                _, out2, _ = self.run_event(root, {"hook_event_name": "SessionStart", "session_id": "s2", "source": "startup"})
                self.assertNotIn("LEASE CONFLICT", out2)
                st = Store.default()
                self.assertEqual(get_arm(st, ident.key, "s1")["status"], "transferred")
                self.assertEqual(st.active_lease(ident.key)["session_id"], "s2")
                st.close()

    def test_second_session_in_predecessor_folder_does_not_steal_worktree_handover(self):
        from continuity.boundary import take_over_from_waiting_predecessor
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            with patch.dict(os.environ, {"HOME": home}):
                self._prepare_visible(root, home)
                st = Store.default()
                ident = identity(root)
                p = st.get_state(ident.key, "successor_pending")
                st.set_state(ident.key, "successor_pending", {**p, "worktree": str(root / ".claude" / "worktrees" / "x")})
                self.assertFalse(take_over_from_waiting_predecessor(st, ident.key, root, "intruder"))
                self.assertEqual(get_arm(st, ident.key, "s1")["status"], "successor_starting")
                st.close()

    def test_pasted_marker_mid_prompt_is_still_a_user_turn(self):
        from continuity.hooks import _turn_from_another_session
        self.assertTrue(_turn_from_another_session({"prompt": "<cross-session-message from=x>hi</cross-session-message>"}))
        self.assertFalse(_turn_from_another_session({"prompt": "start it. " + "log line\n" * 60 + "<task-notification> pasted"}))

    def test_precompact_holds_once_while_successor_starting(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            with patch.dict(os.environ, {"HOME": home}):
                self._prepare_visible(root, home)
                _, out, _ = self.run_event(root, {"hook_event_name": "PreCompact", "session_id": "s1", "trigger": "auto"})
                self.assertIn("prepared but NOT started", json.loads(out)["reason"])
                _, out2, _ = self.run_event(root, {"hook_event_name": "PreCompact", "session_id": "s1", "trigger": "auto"})
                self.assertEqual(out2, "")  # only once: compaction then proceeds, the session stays the owner

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
                    "continuity.boundary._spawn_background",
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
                with patch("continuity.boundary.shutil.which", return_value="/usr/bin/codex"), patch(
                    "continuity.boundary._spawn_codex_exec",
                    return_value=SimpleNamespace(pid=5151),
                ), patch(
                    "continuity.boundary._thread_id_from_log",
                    return_value="thread-123",
                ):
                    _, out, _ = self.run_event(
                        root,
                        {"hook_event_name": "PreCompact", "session_id": "c1", "trigger": "auto"},
                        host="codex",
                    )
                alert = json.loads(out)
                self.assertFalse(alert["continue"])
                self.assertIn("fresh read-only Codex successor bootstrap thread", alert["stopReason"])
                self.assertIn("codex resume thread-123", alert["stopReason"])

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

    def test_no_auto_successor_codex_stages_without_spawn(self):
        with TemporaryDirectory() as home, TemporaryDirectory() as project:
            root = Path(project)
            self.enabled_project(root)
            with patch.dict(os.environ, {"HOME": home}):
                self.run_event(
                    root,
                    {"hook_event_name": "SessionStart", "session_id": "c1", "source": "startup"},
                    host="codex",
                )
                self.arm(root, home, sid="c1", host="codex", auto=False)
                with patch("continuity.boundary._spawn_codex_exec") as spawn:
                    _, out, _ = self.run_event(
                        root,
                        {"hook_event_name": "PreCompact", "session_id": "c1", "trigger": "auto"},
                        host="codex",
                    )
                spawn.assert_not_called()
                payload = json.loads(out)
                self.assertFalse(payload["continue"])
                self.assertIn("detailed handoff was captured", payload["stopReason"])
                st = Store.default()
                pending = st.get_state(identity(root).key, "successor_pending")
                self.assertEqual(pending["status"], "pending")
                self.assertEqual(pending["host"], "codex")
                st.close()

    def test_successor_session_end_marks_ready_and_preserves_arm(self):
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
                with patch("continuity.boundary.shutil.which", return_value=None):
                    self.run_event(
                        root,
                        {"hook_event_name": "PreCompact", "session_id": "c1", "trigger": "auto"},
                        host="codex",
                    )
                self.run_event(
                    root,
                    {"hook_event_name": "SessionStart", "session_id": "c2", "source": "startup"},
                    host="codex",
                )
                self.run_event(
                    root,
                    {"hook_event_name": "SessionEnd", "session_id": "c2", "reason": "logout"},
                    host="codex",
                )
                st = Store.default()
                ident = identity(root)
                pending = st.get_state(ident.key, "successor_pending")
                self.assertEqual(pending["status"], "ready")
                self.assertEqual(pending["successor_session"], "c2")
                self.assertEqual(get_arm(st, ident.key, "c2")["status"], "armed")
                self.assertIsNone(st.active_lease(ident.key))
                st.close()

    def test_unstarted_codex_successor_never_stops_the_predecessor(self):
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
                with patch("continuity.boundary.shutil.which", return_value=None):
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
                # No Codex successor was started (no executable), so the predecessor must NOT be stopped: it stays
                # the owner until a successor arms (it used to be blocked with nothing to continue in).
                self.assertEqual(out, "")
                st = Store.default()
                self.assertEqual(get_arm(st, identity(root).key, "c1")["status"], "successor_starting")
                st.close()

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
