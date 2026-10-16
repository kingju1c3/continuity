from __future__ import annotations

import json
import os
import shlex
import sys
import time
from pathlib import Path

from .boundary import (
    _slug,
    automatic_boundary_handoff,
    default_label,
    get_arm,
    handoff_due,
    inherit_pending_successor,
    launch_claude_successor,
    take_over_from_waiting_predecessor,
    visible_start_instructions,
    next_generation,
    session_label,
    set_arm_status,
    stage_codex_successor,
    stage_manual_successor,
)
from .context import build_context_pack, mechanical_freeze
from .project import identity
from .store import LeaseConflict, Store

MAX_INPUT = 2 * 1024 * 1024


def _read_event() -> dict | None:
    try:
        raw = sys.stdin.read(MAX_INPUT + 1)
    except Exception:
        return None
    if not raw.strip() or len(raw) > MAX_INPUT:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _enabled(root: Path) -> bool:
    return (root / ".continuity" / "enabled.json").is_file()


def _emit_context(event_name: str, additional_context: str, *, system_message: str | None = None) -> None:
    payload: dict = {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": additional_context,
        }
    }
    if system_message:
        payload["systemMessage"] = system_message
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))


def _alert_and_block(host: str, reason: str) -> None:
    if host == "codex":
        payload = {
            "continue": False,
            "stopReason": reason,
            "systemMessage": reason,
        }
    else:
        payload = {
            "decision": "block",
            "reason": reason,
            "terminalSequence": "\u0007",
        }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))


# Turns the user did not type: the Claude desktop app refuses mcp__ccd_session__start_session on them, so a
# hand-over that tries to start the successor there fails (BE 1.4→1.5 and 1.5→1.6, 2026-10-16).
_NOT_USER_TURN_MARKERS = ("<cross-session-message", "Another Claude session sent a message", "<side-sessions-event",
                          "<task-notification", "[SYSTEM NOTIFICATION", "<ci-monitor-event")


def _turn_from_another_session(event: dict) -> bool:
    prompt = event.get("prompt")
    # Anchored to the start of the prompt: the host wraps these turns at the top, while a user who pastes such
    # text usually writes something first.
    return isinstance(prompt, str) and any(m in prompt.lstrip()[:400] for m in _NOT_USER_TURN_MARKERS)


def _successor_starting_reminder(event: dict, arm: dict) -> None:
    """The predecessor prepared a successor that hasn't been confirmed started: it is STILL the owner."""
    name = arm.get("successor_name") or "the successor"
    start = arm.get("start") or {}
    if arm.get("manual_command"):
        how = (f"This hand-over is manual: the user starts the successor with `{arm.get('manual_command')}` and runs "
               "/continuity there; its arming completes the transfer. Remind them once, then keep working.")
    elif _turn_from_another_session(event):
        how = ("This turn was started by another session or an automated event, so the app will refuse a start now. "
               "Do not try it here. Make sure the user knows the successor is prepared but not started, with the folder "
               f"{start.get('folder')} and the start prompt as a copy-paste block; it starts on their next message.")
    else:
        how = (f"This is a user turn, so start it now: call {start.get('tool')} with exactly {json.dumps(start.get('args'))}, "
               "then run `continuity confirm-successor --successor-session <returned id>`.")
    _emit_context(
        "UserPromptSubmit",
        f"CONTINUITY: {name} is prepared but NOT confirmed started. You are still the owner of this work: keep working "
        f"and never tell the user you handed over until the start is confirmed. {how}",
        system_message=f"Continuity: {name} is prepared but not started yet.",
    )


def _block_transferred(host: str, reason: str) -> None:
    if host == "codex":
        sys.stdout.write(json.dumps({"continue": False, "stopReason": reason, "systemMessage": reason}))
    else:
        sys.stdout.write(json.dumps({"decision": "block", "reason": reason}))


def _edit_path(event: dict, root: Path) -> str | None:
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    direct = tool_input.get("file_path") or tool_input.get("path")
    if isinstance(direct, str) and direct.strip():
        try:
            return str(Path(direct).resolve().relative_to(root))
        except Exception:
            return direct
    command = tool_input.get("command")
    if isinstance(command, str):
        for line in command.splitlines():
            line = line.strip()
            if line.startswith("*** Update File:") or line.startswith("*** Add File:"):
                return line.split(":", 1)[1].strip()
    return None


def _freeze(store: Store, ident, host: str, sid: str | None, event_name: str, event: dict) -> dict:
    payload = mechanical_freeze(ident.root, host=host, session_id=sid, event=event_name)
    if event_name == "PostCompact":
        summary = event.get("compact_summary")
        if isinstance(summary, str) and summary.strip():
            payload["compact_summary"] = summary[:20000]
        trigger = event.get("trigger")
        if isinstance(trigger, str):
            payload["trigger"] = trigger
    store.add_freeze(ident.key, sid, event_name, payload)
    return payload


def _session_start(store: Store, ident, host: str, sid: str | None, event: dict) -> int:
    if not sid:
        print("continuity: SessionStart missing session_id; refusing lease mutation", file=sys.stderr)
        return 0

    store.start_session(
        sid,
        ident.key,
        host,
        str(ident.root),
        {"event": "SessionStart", "source": event.get("source")},
    )

    conflict = None
    # A same-folder successor of a predecessor still waiting on its hand-over takes over instead of conflicting.
    take_over_from_waiting_predecessor(store, ident.key, ident.root, sid)
    try:
        store.acquire_lease(ident.key, sid, host)
    except LeaseConflict as exc:
        conflict = str(exc)

    if conflict:
        _emit_context(
            "SessionStart",
            "LEASE CONFLICT: " + conflict + ". Do not modify project state until ownership is reconciled.",
            system_message="Continuity detected a session ownership conflict.",
        )
        return 0

    # Claim pending transfer only after this exact session successfully owns the project.
    inherited = inherit_pending_successor(store, ident, host=host, session_id=sid, event=event)
    arm = inherited or get_arm(store, ident.key, sid)

    # Normal sessions remain silent. Only armed/inherited sessions receive continuity context.
    if arm and arm.get("status") == "armed":
        context = build_context_pack(
            store,
            ident,
            prompt="",
            max_chars=9000,
            include_handoff=True,
            memory_limit=8,
        )
        prefix = [
            "Continuity is ARMED for this session and will remain passive until a compaction/transfer boundary.",
            f"Continuity session id: {sid}",
            f"Session source: {event.get('source') or 'unknown'}",
        ]
        if inherited:
            prefix.append("This is the designated successor session; predecessor state has been inherited.")
        _emit_context(
            "SessionStart",
            "\n".join(prefix) + "\n\n" + context,
            system_message="Continuity restored the armed session handoff.",
        )
    return 0


def _early_warning(store: Store, ident, host: str, sid: str | None, arm: dict | None, event: dict, event_name: str) -> bool:
    """Measured context crossed the hand-over threshold: alert the user and make the agent hand over now,
    while it still holds the whole conversation. The PreCompact hook stays armed as the backstop."""
    if host != "claude" or not sid or not arm or arm.get("status") != "armed" or arm.get("handover_declined"):
        return False
    due = handoff_due(event.get("transcript_path"), arm)
    if not due:
        return False
    first = not arm.get("early_warning")
    if not first and event_name != "UserPromptSubmit":
        return False  # first crossing alerts at once; after that, remind once per user turn, not per tool call
    set_arm_status(store, ident.key, sid, "armed", early_warning={**due, "at": int(time.time())})
    label = str(arm.get("label") or default_label(ident.root))
    nxt = next_generation(str(arm.get("generation") or "1.0"))
    name = session_label(label, nxt)
    branch = f"continuity/{_slug(label)}-session-{nxt}"
    pct = f"{due['used']:,} of ~{due['window']:,} tokens ({due['ratio']:.0%})"
    user_msg = (
        f"⚠️ Compaction is imminent — context is at {pct}. Continuity is creating a new git worktree "
        f"({branch}) in this same checkout and handing the work to {name} before compaction."
    )
    agent_msg = (
        f"CONTINUITY: COMPACTION IS IMMINENT. Measured context: {pct}; hand-over threshold {due['threshold']:.0%}. "
        "Hand over NOW, before compaction, while you still hold the full conversation. Do this before any other work, in this turn:\n"
        f"1. Tell the user, as the first line of your reply: \"⚠️ Compaction is imminent. I'm creating a new git worktree "
        f"({branch}) in this same checkout and handing the work to {name}.\"\n"
        "2. Finish or safely pause the step in flight (never leave a half-written file or a half-pushed branch).\n"
        "3. Write the lossless handoff to .continuity/HANDOFF.md, per the skill's handoff format: goal and done condition, "
        "the user's exact instructions and standing preferences (quoted), every decision with its reason, every open thread, "
        "failed attempts, verified vs. assumed state with exact SHAs/paths/commands/IDs/URLs/test counts, and the single next action.\n"
        "4. Run: continuity handover --handoff-file .continuity/HANDOFF.md\n"
        "   It creates the successor worktree in THIS environment (<main checkout>/.claude/worktrees/), carries over every "
        "uncommitted and untracked change, and prints a `start` block and a `next` instruction.\n"
        "5. Start the successor VISIBLY, as its `next` says: in the Claude desktop app call mcp__ccd_session__start_session "
        "with the printed `start.args` (a sidebar session in the new worktree, with this session's permissions and settings), "
        "then run `continuity confirm-successor --successor-session <returned id>`. Never `claude --bg`. "
        "In a terminal, give the user the folder and the prompt instead.\n"
        + ("   THIS TURN WAS STARTED BY ANOTHER SESSION'S MESSAGE OR AN AUTOMATED EVENT: the app will refuse the start here. "
           "Do steps 1-4 now, then tell the user the successor is prepared and ask them to reply so you can start it on "
           "their turn. You remain the owner until then.\n" if _turn_from_another_session(event) else "")
        + "6. Report the real result (worktree path, branch, successor name, session id). Stop working in this session "
        "ONLY after the start is confirmed; if it was refused, you are still the owner, so say so and keep working."
    )
    _emit_context(event_name, agent_msg, system_message=user_msg)
    return True


def _precompact(store: Store, ident, host: str, sid: str | None, event: dict) -> int:
    if not sid:
        return 0
    arm = get_arm(store, ident.key, sid)
    if arm and arm.get("status") == "successor_starting" and not arm.get("precompact_reminded"):
        # The successor was prepared but never confirmed started: hold compaction ONCE so the agent can still start
        # it with the full conversation; after that, compaction proceeds and this session stays the owner.
        set_arm_status(store, ident.key, sid, "successor_starting", precompact_reminded=int(time.time()))
        how = (f"Start it with `{arm.get('manual_command')}` and run /continuity there." if arm.get("manual_command")
               else visible_start_instructions({"successor_name": arm.get("successor_name"), "start": arm.get("start") or {}}))
        _alert_and_block(host, "COMPACTION IMMINENT — the Continuity successor is prepared but NOT started. " + how)
        return 0
    if not arm or arm.get("status") != "armed":
        return 0

    _freeze(store, ident, host, sid, "PreCompact", event)
    handoff_id, handoff_path, _ = automatic_boundary_handoff(
        store,
        ident,
        host=host,
        session_id=sid,
        arm=arm,
        event=event,
        boundary="PreCompact",
    )
    set_arm_status(
        store,
        ident.key,
        sid,
        "handoff_pending",
        handoff_id=handoff_id,
        handoff_path=str(handoff_path),
    )

    auto = bool(arm.get("auto_successor", True))
    if host == "claude" and auto:
        transfer = launch_claude_successor(
            store,
            ident,
            predecessor_session=sid,
            arm=arm,
            handoff_id=handoff_id,
            handoff_path=handoff_path,
        )
        if transfer.get("ok") and transfer.get("visible"):
            reason = (
                "COMPACTION IMMINENT — Continuity handoff boundary reached: compaction is about to occur. "
                f"A detailed handoff was captured and a new git worktree was created for {transfer.get('successor_name')} "
                + (f"at {transfer.get('worktree')} (branch {transfer.get('worktree_branch')}; {transfer.get('worktree_note')}). " if transfer.get("worktree") else f"in the project root ({transfer.get('worktree_note')}). ")
                + visible_start_instructions(transfer)
            )
        elif transfer.get("ok"):
            reason = (
                "COMPACTION IMMINENT — Continuity handoff boundary reached: compaction is about to occur. "
                "A detailed handoff was captured, a new git worktree was created as the handoff, and a fresh Claude successor session was started in the background"
                + (f", in its own git worktree at {transfer.get('worktree')} (branch {transfer.get('worktree_branch')}; {transfer.get('worktree_note')})" if transfer.get("worktree") else f" in the project root ({transfer.get('worktree_note')})")
                + ". It has been told it is picking up where this session left off. "
                f"Successor: {transfer.get('successor_name')}. "
                f"Attach with: claude --resume \"{transfer.get('successor_name')}\" (or claude agents). "
                "This predecessor is now transferred; continue in the successor."
            )
        else:
            set_arm_status(store, ident.key, sid, "armed", launch_error=transfer.get("reason"))
            reason = (
                "COMPACTION IMMINENT — Continuity handoff boundary reached: compaction is about to occur. "
                f"The detailed handoff was captured at {handoff_path}, but automatic Claude successor launch failed: "
                f"{transfer.get('reason')}. Start a fresh Claude session in this project and invoke /continuity."
            )
        _alert_and_block(host, reason)
        return 0

    if host == "codex":
        transfer = (
            stage_codex_successor(
                store,
                ident,
                predecessor_session=sid,
                arm=arm,
                handoff_id=handoff_id,
                handoff_path=handoff_path,
            )
            if auto
            else stage_manual_successor(
                store,
                ident,
                host="codex",
                predecessor_session=sid,
                arm=arm,
                handoff_id=handoff_id,
                handoff_path=handoff_path,
                command=f"cd {shlex.quote(str(ident.root))} && codex",
            )
        )
        if not transfer.get("ok"):
            reason = (
                "COMPACTION IMMINENT — Continuity handoff boundary reached: compaction is about to occur. "
                f"The detailed handoff was captured at {handoff_path}, but automatic Codex successor launch failed: "
                f"{transfer.get('reason')}. Predecessor ownership was restored."
            )
        elif transfer.get("automatic"):
            tid = transfer.get("thread_id")
            thread_text = f" Successor thread: {tid}." if tid else ""
            reason = (
                "COMPACTION IMMINENT — Continuity handoff boundary reached: compaction is about to occur. "
                "A detailed handoff was captured and a fresh read-only Codex successor bootstrap thread was launched "
                "in the background." + thread_text + " "
                f"Resume it interactively with: {transfer.get('resume_command')}. "
                "The successor must verify source before editing."
            )
        else:
            reason = (
                "COMPACTION IMMINENT — Continuity handoff boundary reached: compaction is about to occur. "
                "A detailed handoff was captured. The Codex executable was not available for automatic bootstrap. "
                f"Start the fresh session with: {transfer.get('command')}. "
                "The next fresh Codex session will inherit the staged handoff automatically."
            )
        _alert_and_block(host, reason)
        return 0

    command = (
        f"cd {shlex.quote(str(ident.root))} && claude"
        if host == "claude"
        else f"cd {shlex.quote(str(ident.root))}"
    )
    transfer = stage_manual_successor(
        store,
        ident,
        host=host,
        predecessor_session=sid,
        arm=arm,
        handoff_id=handoff_id,
        handoff_path=handoff_path,
        command=command,
    )
    reason = (
        "COMPACTION IMMINENT — Continuity handoff boundary reached: compaction is about to occur. "
        f"A detailed handoff was captured at {handoff_path}. "
        f"Start a fresh successor session from the project: {transfer.get('command')}."
    )
    _alert_and_block(host, reason)
    return 0


def run_hook(host: str) -> int:
    event = _read_event()
    if event is None:
        print("continuity: ignored malformed/empty hook event", file=sys.stderr)
        return 0

    event_name = event.get("hook_event_name") or event.get("event")
    cwd = event.get("cwd") or os.getcwd()
    if not isinstance(event_name, str) or not event_name:
        print("continuity: ignored hook event without event name", file=sys.stderr)
        return 0
    if not isinstance(cwd, str) or not cwd:
        return 0

    ident = identity(cwd)
    if not _enabled(ident.root):
        return 0

    sid_raw = event.get("session_id") or event.get("sessionId")
    sid = str(sid_raw) if sid_raw else None
    store = Store.default()
    try:
        store.ensure_project(ident.key, str(ident.root))

        if event_name == "SessionStart":
            return _session_start(store, ident, host, sid, event)

        arm = get_arm(store, ident.key, sid)

        if sid:
            store.touch_lease(ident.key, sid)

        if event_name == "UserPromptSubmit":
            if arm and arm.get("status") == "transferred":
                _block_transferred(
                    host,
                    "Continuity already transferred this predecessor session. Continue in the fresh successor session.",
                )
                return 0
            if arm and arm.get("status") == "successor_starting":
                if host == "claude":  # codex: never block; the predecessor simply stays the owner
                    _successor_starting_reminder(event, arm)
                return 0
            _early_warning(store, ident, host, sid, arm, event, event_name)
            return 0

        if event_name == "PostToolUse":
            if arm and arm.get("status") == "armed":
                tool_name = str(event.get("tool_name") or "")
                edit_tools = {"Write", "Edit", "MultiEdit", "NotebookEdit", "apply_patch"}
                shell_tools = {"Bash", "PowerShell", "Shell", "shell"}
                if tool_name in edit_tools | shell_tools:
                    store.mark_index_dirty(ident.key, _edit_path(event, ident.root))
                _early_warning(store, ident, host, sid, arm, event, event_name)
            return 0

        if event_name == "PreCompact":
            return _precompact(store, ident, host, sid, event)

        if event_name == "PostCompact":
            if arm and arm.get("status") in {"armed", "handoff_pending"}:
                _freeze(store, ident, host, sid, "PostCompact", event)
            return 0

        if event_name == "Stop":
            # Passive mode intentionally does nothing at ordinary turn boundaries.
            return 0

        if event_name == "SessionEnd":
            _freeze(store, ident, host, sid, "SessionEnd", event)
            if sid:
                store.end_session(sid)
                store.release_lease(ident.key, sid)
                # Keep arm state durable across ordinary exit/resume.
                pending = store.get_state(ident.key, "successor_pending")
                if (
                    isinstance(pending, dict)
                    and pending.get("successor_session") == sid
                    and pending.get("status") in {"consumed", "launched"}
                ):
                    pending.update({"status": "ready", "ready_at": time.time_ns()})
                    store.set_state(ident.key, "successor_pending", pending)
            return 0

        return 0
    finally:
        store.close()
