from __future__ import annotations

import json
import os
import sys
from pathlib import Path

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


def _emit(event_name: str, additional_context: str, *, system_message: str | None = None) -> None:
    payload: dict = {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": additional_context,
        }
    }
    if system_message:
        payload["systemMessage"] = system_message
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))


def _emit_block(reason: str) -> None:
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))


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
            if not sid:
                print("continuity: SessionStart missing session_id; refusing lease mutation", file=sys.stderr)
                return 0
            store.start_session(
                sid,
                ident.key,
                host,
                str(ident.root),
                {"event": event_name, "source": event.get("source")},
            )
            conflict = None
            try:
                store.acquire_lease(ident.key, sid, host)
            except LeaseConflict as exc:
                conflict = str(exc)
            context = build_context_pack(
                store, ident, prompt="", max_chars=8500, include_handoff=True, memory_limit=8
            )
            prefix = [
                f"Continuity session id: {sid}",
                f"Session source: {event.get('source') or 'unknown'}",
            ]
            if conflict:
                prefix.append(
                    "LEASE CONFLICT: " + conflict +
                    ". Do not assume ownership; reconcile the active session before destructive work."
                )
            _emit(
                "SessionStart",
                "\n".join(prefix) + "\n\n" + context,
                system_message="Continuity restored project context.",
            )
            return 0

        if sid:
            store.touch_lease(ident.key, sid)

        if event_name == "UserPromptSubmit":
            prompt = event.get("prompt")
            if not isinstance(prompt, str) or len(prompt.strip()) < 3:
                return 0
            context = build_context_pack(
                store,
                ident,
                prompt=prompt,
                max_chars=5000,
                include_handoff=False,
                memory_limit=5,
                structural_limit=6,
            )
            _emit("UserPromptSubmit", context)
            return 0

        if event_name == "PostToolUse":
            tool_name = str(event.get("tool_name") or "")
            edit_tools = {"Write", "Edit", "MultiEdit", "NotebookEdit", "apply_patch"}
            shell_tools = {"Bash", "Shell", "shell"}
            if tool_name in edit_tools | shell_tools:
                path = _edit_path(event, ident.root)
                store.mark_index_dirty(ident.key, path)
                if path:
                    _emit(
                        "PostToolUse",
                        f"Continuity marked the structural index stale after editing {path}. "
                        "A semantic checkpoint should be written before this work is handed off.",
                    )
            return 0

        if event_name == "PreCompact":
            _freeze(store, ident, host, sid, "PreCompact", event)
            idx = store.index_state(ident.key)
            trigger = str(event.get("trigger") or "")
            if host == "claude" and trigger == "manual" and idx.get("dirty"):
                _emit_block(
                    "Continuity detected uncheckpointed project changes. "
                    "Create a semantic continuity checkpoint first, then run /compact again."
                )
            return 0

        if event_name == "PostCompact":
            _freeze(store, ident, host, sid, "PostCompact", event)
            return 0

        if event_name == "Stop":
            idx = store.index_state(ident.key)
            dirty_at = idx.get("dirty_at") if idx.get("dirty") else None
            handoff_at = store.latest_handoff_time(ident.key, sid) if sid else None
            handoff_is_stale = bool(
                dirty_at
                and (
                    handoff_at is None
                    or (handoff_at * 1_000_000_000) < int(dirty_at)
                )
            )
            if sid and handoff_is_stale:
                marker_key = f"stop-feedback:{sid}"
                prior = store.get_state(ident.key, marker_key)
                if prior != dirty_at:
                    store.set_state(ident.key, marker_key, dirty_at)
                    _emit(
                        "Stop",
                        "Continuity detected project changes newer than this session's latest semantic handoff. "
                        "Before ending this turn, run continuity checkpoint with the goal, constraints, "
                        "discoveries, accomplished work, exact next steps, relevant files, and verification. "
                        "The checkpoint command refreshes the structural index and binds the handoff to the active session.",
                    )
            return 0

        if event_name == "SessionEnd":
            _freeze(store, ident, host, sid, "SessionEnd", event)
            if sid:
                store.end_session(sid)
                store.release_lease(ident.key, sid)
            return 0

        return 0
    finally:
        store.close()
