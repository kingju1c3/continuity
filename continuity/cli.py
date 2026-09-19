from __future__ import annotations

import argparse
import json
import os
import sys
import uuid

from .adapters import detect, structural_query
from .context import query_terms
from .handoff import checkpoint_payload, render_markdown, validate_handoff, write_checkpoint
from .hooks import run_hook
from .indexer import build_index
from .install import InstallError, install_repo, uninstall_repo
from .project import identity
from .store import LeaseConflict, Store


def _ctx(path: str | None = None):
    ident = identity(path)
    st = Store.default()
    st.ensure_project(ident.key, str(ident.root))
    return ident, st


def _ensure_index(ident, st: Store) -> dict:
    state = st.index_state(ident.key)
    if not state or state.get("dirty") or not state.get("indexed_at"):
        files, symbols, edges = build_index(ident.root)
        counts = st.replace_index(ident.key, files, symbols, edges)
        return {"refreshed": True, "files": counts[0], "symbols": counts[1], "edges": counts[2]}
    return {"refreshed": False, **state}


def _active_session(st: Store, project_key: str) -> tuple[str | None, str | None]:
    lease = st.active_lease(project_key)
    if not lease:
        return None, None
    return str(lease["session_id"]), str(lease["host"])


def cmd_start(a) -> int:
    ident, st = _ctx(a.path)
    sid = a.session or os.getenv("CONTINUITY_SESSION_ID") or f"{a.host}-{uuid.uuid4()}"
    st.start_session(sid, ident.key, a.host, str(ident.root), {"pid": os.getpid(), "manual": True})
    try:
        st.acquire_lease(ident.key, sid, a.host)
    except LeaseConflict as exc:
        print(f"LEASE CONFLICT: {exc}", file=sys.stderr)
        st.close()
        return 3

    h = st.latest_handoff(ident.key)
    if a.emit_context:
        print(f"CONTINUITY_SESSION_ID={sid}")
        print(f"Project: {ident.root}\nBranch: {ident.branch or '(unknown)'}\nHEAD: {ident.git_head or '(unknown)'}")
        if h:
            print("\nPrevious handoff:\n" + render_markdown(h))
            warnings = validate_handoff(ident.root, h)
            if warnings:
                print("\nHandoff drift:")
                for w in warnings:
                    print(f"- {w}")
        else:
            print("\nNo previous handoff recorded.")
    else:
        print(sid)
    st.close()
    return 0


def cmd_end(a) -> int:
    ident, st = _ctx(a.path)
    sid = a.session
    if not sid:
        sid, _ = _active_session(st, ident.key)
    if not sid:
        print("No active Continuity session.", file=sys.stderr)
        st.close()
        return 2
    st.end_session(sid)
    st.release_lease(ident.key, sid)
    print(f"released={sid}")
    st.close()
    return 0


def cmd_recover(a) -> int:
    ident, st = _ctx(a.path)
    sid = a.session or f"{a.host}-{uuid.uuid4()}"
    try:
        st.recover_lease(
            ident.key,
            sid,
            a.host,
            expected_owner=a.expected_owner,
        )
    except LeaseConflict as exc:
        print(f"RECOVERY REFUSED: {exc}", file=sys.stderr)
        st.close()
        return 3
    st.start_session(
        sid,
        ident.key,
        a.host,
        str(ident.root),
        {"manual": True, "recovered": True, "expected_owner": a.expected_owner},
    )
    print(f"recovered_session={sid}")
    st.close()
    return 0


def cmd_remember(a) -> int:
    ident, st = _ctx(a.path)
    content = a.content if a.content is not None else sys.stdin.read()
    sid = a.session
    if not sid:
        sid, _ = _active_session(st, ident.key)
    mid = st.save_memory(
        ident.key,
        a.title,
        content,
        a.kind,
        a.topic,
        sid,
        a.pin,
        reason=a.reason,
    )
    print(mid)
    st.close()
    return 0


def cmd_memory_history(a) -> int:
    ident, st = _ctx(a.path)
    rows = st.memory_history(ident.key, a.topic, a.limit)
    for r in rows:
        print(
            f"[{r['id']}] {r['recorded_at']} reason={r['reason']} "
            f"kind={r['kind']} title={r['title']}\n{r['content']}\n"
        )
    st.close()
    return 0


def cmd_recall(a) -> int:
    ident, st = _ctx(a.path)
    rows = st.search_memory(ident.key, a.query, a.limit)
    for r in rows:
        print(f"[{r['id']}] {r['kind']} {r['topic_key'] or '-'} — {r['title']}\n{r['content']}\n")
    st.close()
    return 0


def cmd_checkpoint(a) -> int:
    ident, st = _ctx(a.path)
    refresh = _ensure_index(ident, st)
    sid = a.session
    host = a.host
    if not sid:
        active_sid, active_host = _active_session(st, ident.key)
        sid = active_sid
        if host == "manual" and active_host:
            host = active_host
    payload = checkpoint_payload(
        ident.root,
        session_id=sid,
        host=host,
        goal=a.goal or "",
        instructions=a.instructions or "",
        discoveries=a.discoveries or "",
        accomplished=a.accomplished or "",
        next_steps=a.next_steps or "",
        relevant_files=a.relevant_files or "",
        verification=a.verification or "",
    )
    hid = st.add_handoff(ident.key, sid, payload)
    path = write_checkpoint(ident.root, payload)
    print(
        f"handoff={hid}\nfile={path}\nsession={sid or '(none)'}"
        f"\nindex_refreshed={str(bool(refresh.get('refreshed'))).lower()}"
    )
    st.close()
    return 0


def cmd_resume(a) -> int:
    ident, st = _ctx(a.path)
    h = st.latest_handoff(ident.key)
    if not h:
        print("No prior handoff.")
        st.close()
        return 0
    print(render_markdown(h))
    warnings = validate_handoff(ident.root, h)
    if warnings:
        print("\n# Drift / Verification Warnings")
        for warning in warnings:
            print(f"- {warning}")
    else:
        print("\n# Verification\n- Handoff project/branch/HEAD/working-tree evidence matches current state.")
    st.close()
    return 0


def cmd_index(a) -> int:
    ident, st = _ctx(a.path)
    files, symbols, edges = build_index(ident.root)
    counts = st.replace_index(ident.key, files, symbols, edges)
    print(json.dumps({"files": counts[0], "symbols": counts[1], "edges": counts[2]}, indent=2))
    st.close()
    return 0


def cmd_find(a) -> int:
    ident, st = _ctx(a.path)
    _ensure_index(ident, st)
    for r in st.search_symbols(ident.key, a.term, a.limit):
        print(f"{r['path']}:{r['line']} {r['kind']} {r['symbol']}")
    st.close()
    return 0


def cmd_graph(a) -> int:
    ident, st = _ctx(a.path)
    _ensure_index(ident, st)
    for r in st.neighbors(ident.key, a.node, a.limit):
        print(f"{r['src']} -[{r['kind']}]-> {r['dst']} ({r['evidence']})")
    st.close()
    return 0


def cmd_query(a) -> int:
    ident, st = _ctx(a.path)
    ext = structural_query(ident.root, a.question)
    if ext:
        print(f"[{ext[0]}]\n{ext[1]}")
        st.close()
        return 0

    _ensure_index(ident, st)
    terms = query_terms(a.question)
    seen = set()
    found = 0
    for term in terms or [a.question]:
        for r in st.search_symbols(ident.key, term, a.limit):
            key = (r["path"], r["line"], r["symbol"])
            if key in seen:
                continue
            seen.add(key)
            print(f"{r['path']}:{r['line']} {r['kind']} {r['symbol']}")
            found += 1
            if found >= a.limit:
                break
        if found >= a.limit:
            break
    if not found:
        print("No structural match. Inspect current source or install Graft/Graphify for deeper graph queries.")
    st.close()
    return 0


def cmd_orient(a) -> int:
    ident, st = _ctx(a.path)
    print(f"Project: {ident.root}\nBranch: {ident.branch or '(unknown)'}\nHEAD: {ident.git_head or '(unknown)'}")
    lease = st.active_lease(ident.key)
    if lease:
        print(f"Active session: {lease['session_id']} ({lease['host']})")
    else:
        print("Active session: none")

    idx = st.index_state(ident.key)
    print("Index: " + json.dumps(idx or {"built": False}, sort_keys=True))

    h = st.latest_handoff(ident.key)
    if h:
        print("\nLatest handoff:\n" + render_markdown(h))
        warnings = validate_handoff(ident.root, h)
        if warnings:
            print("\nDrift:")
            for w in warnings:
                print(f"- {w}")

    freeze = st.latest_freeze(ident.key)
    if freeze and (not h or freeze.get("_created_at", 0) > h.get("_created_at", 0)):
        print(
            f"\nNewer mechanical freeze: event={freeze.get('_event')} "
            f"created={freeze.get('_created_at')}"
        )

    print("\nRecent durable memory:")
    for r in st.search_memory(ident.key, "", 6):
        print(f"- {r['kind']}: {r['title']} ({r['topic_key'] or 'untagged'})")
    print("\nAdapters: " + json.dumps(detect()))
    st.close()
    return 0


def cmd_status(a) -> int:
    ident, st = _ctx(a.path)
    lease = st.active_lease(ident.key)
    handoff = st.latest_handoff(ident.key)
    freeze = st.latest_freeze(ident.key)
    result = {
        "project": str(ident.root),
        "branch": ident.branch,
        "head": ident.git_head,
        "enabled": (ident.root / ".continuity" / "enabled.json").exists(),
        "lease": dict(lease) if lease else None,
        "index": st.index_state(ident.key),
        "latest_handoff": {
            "id": handoff.get("_id"),
            "created_at": handoff.get("_created_at"),
            "session_id": handoff.get("session_id"),
        } if handoff else None,
        "latest_freeze": {
            "id": freeze.get("_id"),
            "created_at": freeze.get("_created_at"),
            "event": freeze.get("_event"),
        } if freeze else None,
    }
    print(json.dumps(result, indent=2, default=str))
    st.close()
    return 0


def cmd_doctor(a) -> int:
    ident, st = _ctx(a.path)
    checks = {
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "project": str(ident.root),
        "enabled": (ident.root / ".continuity" / "enabled.json").exists(),
        "database": str(st.path),
        "sqlite_fts5": True,
        "graft": detect()["graft"],
        "graphify": detect()["graphify"],
        "claude_skill": (ident.root / ".claude/skills/continuity/SKILL.md").exists(),
        "codex_skill": (ident.root / ".agents/skills/continuity/SKILL.md").exists(),
        "agents_md": (ident.root / "AGENTS.md").exists(),
        "index": st.index_state(ident.key),
        "active_lease": dict(st.active_lease(ident.key)) if st.active_lease(ident.key) else None,
    }
    try:
        st.db.execute("SELECT count(*) FROM memories_fts").fetchone()
    except Exception:
        checks["sqlite_fts5"] = False
    print(json.dumps(checks, indent=2, default=str))
    st.close()
    return 0


def _agents(value: str) -> list[str]:
    agents = [x.strip() for x in value.split(",") if x.strip()]
    unknown = sorted(set(agents) - {"claude", "codex"})
    if unknown:
        raise InstallError("unsupported agents: " + ", ".join(unknown))
    return agents


def cmd_install(a) -> int:
    root = identity(a.path).root
    try:
        plan = install_repo(root, _agents(a.agents), dry_run=a.dry_run)
    except InstallError as exc:
        print(f"continuity install: {exc}", file=sys.stderr)
        return 2
    for p in plan:
        print(p)
    return 0


def cmd_uninstall(a) -> int:
    root = identity(a.path).root
    try:
        plan = uninstall_repo(root, _agents(a.agents), dry_run=a.dry_run)
    except InstallError as exc:
        print(f"continuity uninstall: {exc}", file=sys.stderr)
        return 2
    for p in plan:
        print(p)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="continuity", description="Persistent project continuity for coding agents")
    p.add_argument("--path", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("start")
    s.add_argument("--host", default="manual")
    s.add_argument("--session")
    s.add_argument("--emit-context", action="store_true")
    s.set_defaults(fn=cmd_start)

    s = sub.add_parser("end")
    s.add_argument("--session")
    s.set_defaults(fn=cmd_end)

    s = sub.add_parser("recover")
    s.add_argument("--host", default="manual")
    s.add_argument("--session")
    s.add_argument("--expected-owner")
    s.set_defaults(fn=cmd_recover)

    s = sub.add_parser("remember")
    s.add_argument("title")
    s.add_argument("content", nargs="?")
    s.add_argument("--kind", default="discovery")
    s.add_argument("--topic")
    s.add_argument("--session")
    s.add_argument("--pin", action="store_true")
    s.add_argument("--reason", default="write")
    s.set_defaults(fn=cmd_remember)

    s = sub.add_parser("memory-history")
    s.add_argument("topic")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(fn=cmd_memory_history)

    s = sub.add_parser("recall")
    s.add_argument("query", nargs="?", default="")
    s.add_argument("--limit", type=int, default=8)
    s.set_defaults(fn=cmd_recall)

    s = sub.add_parser("checkpoint")
    s.add_argument("--session")
    s.add_argument("--host", default="manual")
    s.add_argument("--goal")
    s.add_argument("--instructions")
    s.add_argument("--discoveries")
    s.add_argument("--accomplished")
    s.add_argument("--next-steps")
    s.add_argument("--relevant-files")
    s.add_argument("--verification")
    s.set_defaults(fn=cmd_checkpoint)

    s = sub.add_parser("resume")
    s.set_defaults(fn=cmd_resume)

    s = sub.add_parser("index")
    s.set_defaults(fn=cmd_index)

    s = sub.add_parser("find")
    s.add_argument("term")
    s.add_argument("--limit", type=int, default=15)
    s.set_defaults(fn=cmd_find)

    s = sub.add_parser("graph")
    s.add_argument("node")
    s.add_argument("--limit", type=int, default=30)
    s.set_defaults(fn=cmd_graph)

    s = sub.add_parser("query")
    s.add_argument("question")
    s.add_argument("--limit", type=int, default=15)
    s.set_defaults(fn=cmd_query)

    s = sub.add_parser("orient")
    s.set_defaults(fn=cmd_orient)

    s = sub.add_parser("status")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("doctor")
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("install")
    s.add_argument("--agents", default="claude,codex")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_install)

    s = sub.add_parser("uninstall")
    s.add_argument("--agents", default="claude,codex")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_uninstall)

    s = sub.add_parser("repair")
    s.add_argument("--agents", default="claude,codex")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_install)

    s = sub.add_parser("hook")
    s.add_argument("--host", required=True)
    s.set_defaults(fn=lambda a: run_hook(a.host))
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.fn(args))


if __name__ == "__main__":
    main()
