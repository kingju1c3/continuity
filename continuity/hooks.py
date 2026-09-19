from __future__ import annotations

import json
import os
import sys
import uuid

from .project import identity
from .store import Store

def _read_event() -> dict:
    try:
        raw = sys.stdin.read(1_048_576)
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}

def run_hook(host: str) -> int:
    event = _read_event()
    cwd = event.get("cwd") or os.getcwd()
    ident = identity(cwd)
    store = Store.default()
    store.ensure_project(ident.key, str(ident.root))
    event_name = event.get("hook_event_name") or event.get("event") or "unknown"
    sid = str(event.get("session_id") or event.get("sessionId") or f"{host}-{uuid.uuid4()}")
    if event_name in {"SessionStart", "session_start", "unknown"}:
        store.start_session(sid, ident.key, host, str(ident.root), {"event": event_name})
        handoff = store.latest_handoff(ident.key)
        msg = "Continuity session opened."
        if handoff:
            msg += " Previous handoff recovered; run continuity resume for the full checkpoint before making project changes."
    elif event_name in {"PreCompact", "pre_compact"}:
        msg = "Continuity checkpoint required before compaction. Preserve goal, constraints, discoveries, accomplished work, next steps, relevant files, and verification with continuity checkpoint."
    elif event_name in {"Stop", "SessionEnd", "stop", "session_end"}:
        msg = "Continuity close protocol: write a semantic checkpoint before the session ends."
        store.end_session(sid)
    else:
        msg = "Continuity active."
    store.close()
    sys.stdout.write(json.dumps({"systemMessage": msg, "additionalContext": msg}))
    return 0
