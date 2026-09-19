from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .boundary import (
    automatic_boundary_handoff,
    get_arm,
    inherit_pending_successor,
    launch_claude_successor,
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
            "terminalSequence": "\u0007",
        }
    else:
        payload = {
            "decision": "block",
            "reason": reason,
            "terminalSequence": "\u0007",
        }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))


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

    inherited = inherit_pending_successor(store, ident, host=host, session_id=sid, event=event)
    conflict = None
    try:
        store.acquire_lease(ident.key, sid, host)
    except LeaseConflict as exc:
        conflict = str(exc)

    arm = inherited or get_arm(store, ident.key, sid)
    if conflict:
        _emit_context(
            "SessionStart",
            "LEASE CONFLICT: " + conflict + ". Do not modify project state until ownership is reconciled.",
            system_message="Continuity detected a session ownership conflict.",
        )
        return 0

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


def _precompact(store: Store, ident, host: str, sid: str | None, event: dict) -> int:
    if not sid:
        return 0
    arm = get_arm(store, ident.key, sid)
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
        if transfer.get("ok"):
            reason = (
                "Continuity handoff boundary reached: compaction is about to occur. "
                "A detailed handoff was captured and a fresh Claude successor session was started in the background. "
                f"Successor name: {transfer.get('successor_name')}. "
                f"Attach with: claude --resume {transfer.get('successor_name')}. "
                "This predecessor is now transferred; continue in the successor."
            )
        else:
            set_arm_status(store, ident.key, sid, "armed", launch_error=transfer.get("reason"))
            reason = (
                "Continuity handoff boundary reached: compaction is about to occur. "
                f"The detailed handoff was captured at {handoff_path}, but automatic Claude successor launch failed: "
                f"{transfer.get('reason')}. Start a fresh Claude session in this project and invoke /continuity."
            )
        _alert_and_block(host, reason)
        return 0

    if host == "codex":
        transfer = stage_codex_successor(
            store,
            ident,
            predecessor_session=sid,
            arm=arm,
            handoff_id=handoff_id,
            handoff_path=handoff_path,
        )
        reason = (
            "Continuity handoff boundary reached: compaction is about to occur. "
            "A detailed handoff was captured and a fresh Codex successor is staged. "
            "Codex hooks cannot safely open an interactive TUI from this no-terminal hook. "
            f"Start the fresh session with: {transfer.get('command')}. "
            "The next fresh Codex session will inherit the staged handoff automatically."
        )
        _alert_and_block(host, reason)
        return 0

    command = f'cd "{ident.root}" && claude' if host == "claude" else f'cd "{ident.root}"'
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
        "Continuity handoff boundary reached: compaction is about to occur. "
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

        if event_name == "PostToolUse":
            if arm and arm.get("status") == "armed":
                tool_name = str(event.get("tool_name") or "")
                edit_tools = {"Write", "Edit", "MultiEdit", "NotebookEdit", "apply_patch"}
                shell_tools = {"Bash", "PowerShell", "Shell", "shell"}
                if tool_name in edit_tools | shell_tools:
                    store.mark_index_dirty(ident.key, _edit_path(event, ident.root))
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
                if arm and arm.get("status") == "armed":
                    set_arm_status(store, ident.key, sid, "disarmed", ended=True)
            return 0

        return 0
    finally:
        store.close()
