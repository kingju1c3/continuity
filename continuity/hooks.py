from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .context import build_context_pack, mechanical_freeze
from .project import identity
from .store import LeaseConflict, Store

MAX_INPUT = 2 * 1024 * 1024
CONTEXT_EVENTS = {"SessionStart", "UserPromptSubmit", "PostToolUse", "Stop"}


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
                target = line.split(":", 1)[1].strip()
                return target
    return None


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
            if tool_name in {"Write", "Edit", "MultiEdit", "NotebookEdit", "apply_patch"}:
                path = _edit_path(event, ident.root)
                store.mark_index_dirty(ident.key, path)
                if path:
                    _emit(
                        "PostToolUse",
                        f"Continuity marked the structural index stale after editing {path}. "
                        "Structural commands will refresh it before relying on indexed relationships.",
                    )
            return 0

        if event_name == "PreCompact":
            freeze = mechanical_freeze(
                ident.root, host=host, session_id=sid, event="PreCompact"
            )
            store.add_freeze(ident.key, sid, "PreCompact", freeze)
            # PreCompact output support differs by host/version. Persisting the freeze is
            # the durable guarantee; SessionStart(source=compact) hydrates it afterward.
            return 0

        if event_name == "Stop":
            # Stop is a per-turn event in both supported hosts, not a session end.
            # Never release ownership here.
            return 0

        if event_name == "SessionEnd":
            freeze = mechanical_freeze(
                ident.root, host=host, session_id=sid, event="SessionEnd"
            )
            store.add_freeze(ident.key, sid, "SessionEnd", freeze)
            if sid:
                store.end_session(sid)
                store.release_lease(ident.key, sid)
            return 0

        return 0
    finally:
        store.close()
