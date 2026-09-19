from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from .handoff import checkpoint_payload, write_checkpoint
from .indexer import build_index
from .project import git_snapshot
from .store import Store

PENDING_TTL_SECONDS = 15 * 60
MAX_TRANSCRIPT_BYTES = 768 * 1024
MAX_TRANSCRIPT_CHARS = 18000


def arm_key(session_id: str) -> str:
    return f"armed:{session_id}"


def arm_session(store: Store, project_key: str, session_id: str, host: str, *, goal: str = "", instructions: str = "", auto_successor: bool = True, inherited_from: str | None = None) -> dict:
    state = {
        "schema": 1,
        "status": "armed",
        "session_id": session_id,
        "host": host,
        "goal": goal,
        "instructions": instructions,
        "auto_successor": bool(auto_successor),
        "armed_at": int(time.time()),
        "inherited_from": inherited_from,
    }
    store.set_state(project_key, arm_key(session_id), state)
    return state


def get_arm(store: Store, project_key: str, session_id: str | None) -> dict | None:
    if not session_id:
        return None
    value = store.get_state(project_key, arm_key(session_id))
    return value if isinstance(value, dict) else None


def set_arm_status(store: Store, project_key: str, session_id: str, status: str, **extra) -> dict:
    state = get_arm(store, project_key, session_id) or {
        "schema": 1,
        "session_id": session_id,
        "host": extra.get("host", "unknown"),
        "goal": "",
        "instructions": "",
        "auto_successor": True,
        "armed_at": int(time.time()),
    }
    state = {**state, "status": status, **extra, "updated_at": int(time.time())}
    store.set_state(project_key, arm_key(session_id), state)
    return state


def disarm_session(store: Store, project_key: str, session_id: str) -> dict:
    return set_arm_status(store, project_key, session_id, "disarmed")


def pending_successor(store: Store, project_key: str) -> dict | None:
    p = store.get_state(project_key, "successor_pending")
    if not isinstance(p, dict):
        return None
    created = int(p.get("created_at") or 0)
    if not created or int(time.time()) - created > PENDING_TTL_SECONDS:
        return None
    if p.get("status") not in {"pending", "launched"}:
        return None
    return p


def _extract_strings(value, out: list[str], depth: int = 0) -> None:
    if depth > 6 or sum(len(x) for x in out) >= MAX_TRANSCRIPT_CHARS:
        return
    if isinstance(value, str):
        text = value.strip()
        if text and len(text) > 2:
            out.append(text)
        return
    if isinstance(value, list):
        for item in value[-20:]:
            _extract_strings(item, out, depth + 1)
        return
    if isinstance(value, dict):
        for key in ("role", "type", "text", "content", "message", "prompt", "tool_name"):
            if key in value:
                _extract_strings(value[key], out, depth + 1)


def transcript_tail(path_value: object) -> dict:
    if not isinstance(path_value, str) or not path_value.strip():
        return {"available": False, "reason": "host transcript path unavailable"}
    path = Path(path_value).expanduser()
    try:
        with path.open("rb") as f:
            try:
                f.seek(-MAX_TRANSCRIPT_BYTES, os.SEEK_END)
            except OSError:
                f.seek(0)
            raw = f.read(MAX_TRANSCRIPT_BYTES)
    except OSError as exc:
        return {"available": False, "reason": f"transcript unreadable: {exc}"}

    text = raw.decode("utf-8", errors="replace")
    extracted: list[str] = []
    for line in text.splitlines()[-250:]:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        _extract_strings(value, extracted)
        if sum(len(x) for x in extracted) >= MAX_TRANSCRIPT_CHARS:
            break
    if not extracted:
        return {"available": False, "reason": "transcript tail contained no parseable structured text", "bytes_read": len(raw)}
    joined = "\n".join(extracted)
    return {
        "available": True,
        "bytes_read": len(raw),
        "text": joined[-MAX_TRANSCRIPT_CHARS:],
        "warning": "Best-effort host transcript evidence; format is not treated as a stable API.",
    }


def _changed_files(root: Path, index_state: dict) -> list[str]:
    snap = git_snapshot(root)
    found: list[str] = []
    for line in str(snap.get("status") or "").splitlines():
        body = line[3:].strip() if len(line) > 3 else line.strip()
        if " -> " in body:
            body = body.split(" -> ", 1)[1].strip()
        if body and body not in found:
            found.append(body)
    last = index_state.get("last_file")
    if isinstance(last, str) and last and last not in found:
        found.append(last)
    return found[:100]


def automatic_boundary_handoff(store: Store, ident, *, host: str, session_id: str, arm: dict, event: dict, boundary: str = "PreCompact") -> tuple[int, Path, dict]:
    files, symbols, edges = build_index(ident.root)
    store.replace_index(ident.key, files, symbols, edges)
    idx = store.index_state(ident.key)
    changed = _changed_files(ident.root, idx)
    memories = store.search_memory(ident.key, "", 8)
    transcript = transcript_tail(event.get("transcript_path"))

    payload = checkpoint_payload(
        ident.root,
        session_id=session_id,
        host=host,
        goal=str(arm.get("goal") or ""),
        instructions=str(arm.get("instructions") or ""),
        discoveries="Automatically captured at a compaction boundary. Verify against current source.",
        accomplished="See Git working tree/diffstat and machine-captured boundary evidence below.",
        next_steps="Successor must verify current source, restore Continuity, then continue the active goal.",
        relevant_files=" ".join(changed),
        verification="Automatic boundary capture only; semantic verification must be performed by the successor.",
    )
    payload["kind"] = "automatic-boundary"
    payload["boundary"] = boundary
    payload["automatic_boundary_context"] = {
        "arm": {"goal": arm.get("goal"), "instructions": arm.get("instructions"), "armed_at": arm.get("armed_at")},
        "index": idx,
        "changed_files": changed,
        "recent_memory": [
            {"kind": row["kind"], "topic_key": row["topic_key"], "title": row["title"], "content": str(row["content"])[:1200]}
            for row in memories
        ],
        "transcript_tail": transcript,
    }
    hid = store.add_handoff(ident.key, session_id, payload)
    path = write_checkpoint(ident.root, payload)
    return hid, path, payload


def _safe_name(session_id: str) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    stem = "".join(ch for ch in session_id if ch.isalnum() or ch in "-_")[:16] or "session"
    return f"continuity-{stamp}-{stem}"


def launch_claude_successor(store: Store, ident, *, predecessor_session: str, arm: dict, handoff_id: int, handoff_path: Path) -> dict:
    exe = shutil.which("claude")
    if not exe:
        return {"ok": False, "reason": "claude executable not found"}
    if str(os.getenv("CLAUDE_CODE_REMOTE", "")).lower() in {"1", "true", "yes"}:
        return {"ok": False, "reason": "remote Claude environment; local background launch disabled"}

    name = _safe_name(predecessor_session)
    prompt = (
        "/continuity\n"
        "You are the fresh successor session for a Continuity transfer. "
        "Read .continuity/LATEST.md, run continuity resume and continuity orient, "
        "verify project root/branch/HEAD/current source against the handoff, and report readiness. "
        "Do not modify project files until verification is complete."
    )
    pending = {
        "schema": 1, "status": "pending", "host": "claude",
        "predecessor_session": predecessor_session, "successor_name": name,
        "handoff_id": handoff_id, "handoff_path": str(handoff_path),
        "goal": arm.get("goal", ""), "instructions": arm.get("instructions", ""),
        "auto_successor": bool(arm.get("auto_successor", True)), "created_at": int(time.time()),
    }
    store.set_state(ident.key, "successor_pending", pending)
    store.release_lease(ident.key, predecessor_session)

    try:
        proc = subprocess.Popen(
            [exe, "--bg", "--name", name, prompt],
            cwd=str(ident.root), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
        )
    except OSError as exc:
        store.acquire_lease(ident.key, predecessor_session, "claude")
        pending.update({"status": "failed", "reason": str(exc)})
        store.set_state(ident.key, "successor_pending", pending)
        return {"ok": False, "reason": str(exc)}

    pending.update({"status": "launched", "pid": proc.pid})
    store.set_state(ident.key, "successor_pending", pending)
    set_arm_status(store, ident.key, predecessor_session, "transferred", successor_name=name)
    return {"ok": True, "successor_name": name, "pid": proc.pid}


def stage_manual_successor(store: Store, ident, *, host: str, predecessor_session: str, arm: dict, handoff_id: int, handoff_path: Path, command: str) -> dict:
    pending = {
        "schema": 1, "status": "pending", "host": host,
        "predecessor_session": predecessor_session, "handoff_id": handoff_id,
        "handoff_path": str(handoff_path), "goal": arm.get("goal", ""),
        "instructions": arm.get("instructions", ""),
        "auto_successor": bool(arm.get("auto_successor", True)), "created_at": int(time.time()),
    }
    store.set_state(ident.key, "successor_pending", pending)
    store.release_lease(ident.key, predecessor_session)
    set_arm_status(store, ident.key, predecessor_session, "transferred")
    return {"ok": True, "manual_start": True, "command": command}


def stage_codex_successor(store: Store, ident, *, predecessor_session: str, arm: dict, handoff_id: int, handoff_path: Path) -> dict:
    return stage_manual_successor(
        store, ident, host="codex", predecessor_session=predecessor_session,
        arm=arm, handoff_id=handoff_id, handoff_path=handoff_path,
        command=f'cd "{ident.root}" && codex',
    )


def inherit_pending_successor(store: Store, ident, *, host: str, session_id: str, event: dict) -> dict | None:
    pending = pending_successor(store, ident.key)
    if not pending or pending.get("host") != host:
        return None

    if host == "claude":
        expected = pending.get("successor_name")
        title = event.get("session_title") or event.get("sessionTitle")
        if expected and str(title or "") != str(expected):
            return None

    inherited = arm_session(
        store, ident.key, session_id, host,
        goal=str(pending.get("goal") or ""), instructions=str(pending.get("instructions") or ""),
        auto_successor=bool(pending.get("auto_successor", True)),
        inherited_from=str(pending.get("predecessor_session") or ""),
    )
    pending.update({"status": "consumed", "successor_session": session_id, "consumed_at": int(time.time())})
    store.set_state(ident.key, "successor_pending", pending)
    return inherited
