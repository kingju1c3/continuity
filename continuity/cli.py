from __future__ import annotations

import argparse
import json
import os
import sys
import uuid

from .adapters import detect, structural_query
from .handoff import checkpoint_payload, render_markdown, write_checkpoint
from .hooks import run_hook
from .indexer import build_index
from .install import install_repo
from .project import identity
from .store import Store

def _ctx(path: str | None = None):
    ident = identity(path)
    st = Store.default()
    st.ensure_project(ident.key, str(ident.root))
    return ident, st

def cmd_start(a) -> int:
    ident, st = _ctx(a.path)
    sid = a.session or os.getenv("CONTINUITY_SESSION_ID") or f"{a.host}-{uuid.uuid4()}"
    st.start_session(sid, ident.key, a.host, str(ident.root), {"pid": os.getpid()})
    h = st.latest_handoff(ident.key)
    if a.emit_context:
        print(f"CONTINUITY_SESSION_ID={sid}")
        print(f"Project: {ident.root}\nBranch: {ident.branch or '(unknown)'}\nHEAD: {ident.git_head or '(unknown)'}")
        if h:
            print("\nPrevious handoff:\n" + render_markdown(h))
        else:
            print("\nNo previous handoff recorded.")
    else:
        print(sid)
    st.close()
    return 0

def cmd_remember(a) -> int:
    ident, st = _ctx(a.path)
    content = a.content or sys.stdin.read()
    mid = st.save_memory(ident.key, a.title, content, a.kind, a.topic, a.session, a.pin)
    print(mid)
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
    p = checkpoint_payload(
        ident.root, session_id=a.session, host=a.host,
        goal=a.goal or "", instructions=a.instructions or "", discoveries=a.discoveries or "",
        accomplished=a.accomplished or "", next_steps=a.next_steps or "",
        relevant_files=a.relevant_files or "", verification=a.verification or "",
    )
    hid = st.add_handoff(ident.key, a.session, p)
    path = write_checkpoint(ident.root, p)
    print(f"handoff={hid}\nfile={path}")
    st.close()
    return 0

def cmd_resume(a) -> int:
    ident, st = _ctx(a.path)
    h = st.latest_handoff(ident.key)
    print(render_markdown(h) if h else "No prior handoff.")
    st.close()
    return 0

def cmd_index(a) -> int:
    ident, st = _ctx(a.path)
    files, symbols, edges = build_index(ident.root)
    st.replace_index(ident.key, files, symbols, edges)
    print(json.dumps({"files": len(files), "symbols": len(symbols), "edges": len(edges)}, indent=2))
    st.close()
    return 0

def cmd_find(a) -> int:
    ident, st = _ctx(a.path)
    for r in st.search_symbols(ident.key, a.term, a.limit):
        print(f"{r['path']}:{r['line']} {r['kind']} {r['symbol']}")
    st.close()
    return 0

def cmd_graph(a) -> int:
    ident, st = _ctx(a.path)
    for r in st.neighbors(ident.key, a.node, a.limit):
        print(f"{r['src']} -[{r['kind']}]-> {r['dst']} ({r['evidence']})")
    st.close()
    return 0

def cmd_query(a) -> int:
    ident, st = _ctx(a.path)
    ext = structural_query(ident.root, a.question)
    if ext:
        print(f"[{ext[0]}]\n{ext[1]}")
    else:
        rows = st.search_symbols(ident.key, a.question, a.limit)
        if not rows:
            print("No structural match. Run continuity index or install Graft/Graphify for deeper graph queries.")
        for r in rows:
            print(f"{r['path']}:{r['line']} {r['kind']} {r['symbol']}")
    st.close()
    return 0

def cmd_orient(a) -> int:
    ident, st = _ctx(a.path)
    print(f"Project: {ident.root}\nBranch: {ident.branch or '(unknown)'}\nHEAD: {ident.git_head or '(unknown)'}")
    h = st.latest_handoff(ident.key)
    if h:
        print("\nLatest handoff:\n" + render_markdown(h))
    print("\nRecent durable memory:")
    for r in st.search_memory(ident.key, "", 6):
        print(f"- {r['kind']}: {r['title']} ({r['topic_key'] or 'untagged'})")
    print("\nAdapters: " + json.dumps(detect()))
    st.close()
    return 0

def cmd_doctor(a) -> int:
    ident, st = _ctx(a.path)
    checks = {
        "python": sys.version.split()[0],
        "project": str(ident.root),
        "database": str(st.path),
        "sqlite_fts5": True,
        "graft": detect()["graft"],
        "graphify": detect()["graphify"],
        "claude_skill": (ident.root / ".claude/skills/continuity/SKILL.md").exists(),
        "codex_skill": (ident.root / ".agents/skills/continuity/SKILL.md").exists(),
        "agents_md": (ident.root / "AGENTS.md").exists(),
    }
    try:
        st.db.execute("SELECT count(*) FROM memories_fts").fetchone()
    except Exception:
        checks["sqlite_fts5"] = False
    print(json.dumps(checks, indent=2))
    st.close()
    return 0

def cmd_install(a) -> int:
    root = identity(a.path).root
    agents = [x.strip() for x in a.agents.split(",") if x.strip()]
    for p in install_repo(root, agents):
        print(p)
    return 0

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="continuity", description="Persistent project continuity for coding agents")
    p.add_argument("--path", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)
    s=sub.add_parser("start"); s.add_argument("--host",default="manual"); s.add_argument("--session"); s.add_argument("--emit-context",action="store_true"); s.set_defaults(fn=cmd_start)
    s=sub.add_parser("remember"); s.add_argument("title"); s.add_argument("content",nargs="?"); s.add_argument("--kind",default="discovery"); s.add_argument("--topic"); s.add_argument("--session"); s.add_argument("--pin",action="store_true"); s.set_defaults(fn=cmd_remember)
    s=sub.add_parser("recall"); s.add_argument("query",nargs="?",default=""); s.add_argument("--limit",type=int,default=8); s.set_defaults(fn=cmd_recall)
    s=sub.add_parser("checkpoint"); s.add_argument("--session"); s.add_argument("--host",default="manual"); s.add_argument("--goal"); s.add_argument("--instructions"); s.add_argument("--discoveries"); s.add_argument("--accomplished"); s.add_argument("--next-steps"); s.add_argument("--relevant-files"); s.add_argument("--verification"); s.set_defaults(fn=cmd_checkpoint)
    s=sub.add_parser("resume"); s.set_defaults(fn=cmd_resume)
    s=sub.add_parser("index"); s.set_defaults(fn=cmd_index)
    s=sub.add_parser("find"); s.add_argument("term"); s.add_argument("--limit",type=int,default=15); s.set_defaults(fn=cmd_find)
    s=sub.add_parser("graph"); s.add_argument("node"); s.add_argument("--limit",type=int,default=30); s.set_defaults(fn=cmd_graph)
    s=sub.add_parser("query"); s.add_argument("question"); s.add_argument("--limit",type=int,default=15); s.set_defaults(fn=cmd_query)
    s=sub.add_parser("orient"); s.set_defaults(fn=cmd_orient)
    s=sub.add_parser("doctor"); s.set_defaults(fn=cmd_doctor)
    s=sub.add_parser("install"); s.add_argument("--agents",default="claude,codex"); s.set_defaults(fn=cmd_install)
    s=sub.add_parser("hook"); s.add_argument("--host",required=True); s.set_defaults(fn=lambda a: run_hook(a.host))
    return p

def main() -> None:
    p = build_parser()
    a = p.parse_args()
    raise SystemExit(a.fn(a))

if __name__ == "__main__":
    main()
