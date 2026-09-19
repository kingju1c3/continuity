#!/usr/bin/env python3
"""Command line interface. Python 3.10+ and SQLite FTS5; no network calls."""
import argparse
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

from continuity_core import __version__
from continuity_core.store import Store, source, canonical
from continuity_core.graph import index, graph_query, graph_path, markdown_map
from continuity_core.adapters import import_graph, import_engram, import_second_brain


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--store", default=os.environ.get("CONTINUITY_STORE"), help="Private durable store directory (or CONTINUITY_STORE)")
    p.add_argument("--scope", required=True, help="Exact project or user scope; never automatically merged")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("doctor")
    sub.add_parser("audit")
    sub.add_parser("checkpoint-show")
    remember = sub.add_parser("remember")
    remember.add_argument("--title", required=True)
    b = remember.add_mutually_exclusive_group(required=True)
    b.add_argument("--text")
    b.add_argument("--file")
    remember.add_argument("--topic", default="")
    remember.add_argument("--kind", default="observation")
    remember.add_argument("--class", dest="epistemic", choices=["A", "B", "C"], default="C")
    remember.add_argument("--confidence", default="unassessed")
    remember.add_argument("--source", action="append", default=[])
    remember.add_argument("--source-label", action="append", default=[])
    remember.add_argument("--supersedes")
    remember.add_argument("--review-after")
    search = sub.add_parser("search")
    search.add_argument("query", nargs="?", default="")
    search.add_argument("--limit", type=int, default=8)
    search.add_argument("--include-inactive", action="store_true")
    for name in ("get", "retire"):
        sub.add_parser(name).add_argument("id")
    sub.add_parser("timeline").add_argument("topic")
    sub.add_parser("checkpoint").add_argument("file")
    resume = sub.add_parser("resume")
    resume.add_argument("query", nargs="?", default="")
    resume.add_argument("--budget", type=int, default=6000, help="Maximum output characters, not tokens")
    sub.add_parser("index").add_argument("root")
    graph = sub.add_parser("graph")
    graph.add_argument("query", nargs="?", default="")
    graph.add_argument("--limit", type=int, default=12)
    path = sub.add_parser("path")
    path.add_argument("origin")
    path.add_argument("start")
    path.add_argument("end")
    sub.add_parser("map")
    imp = sub.add_parser("import")
    imp.add_argument("engine", choices=["second-brain", "graft", "graphify", "engram"])
    imp.add_argument("path")
    imp.add_argument("--project", help="Required source project for an Engram export")
    sub.add_parser("export").add_argument("file")
    sub.add_parser("restore").add_argument("file")
    return p


def private_write(path, content):
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    # No overwrite: snapshots are dated/versioned by their caller.
    with path.open("x", encoding="utf-8") as f:
        os.chmod(path, 0o600)
        f.write(content)
    return str(path)


def run(args):
    if not args.store:
        raise ValueError("Choose --store or CONTINUITY_STORE on durable private storage")
    s = Store(args.store, args.scope)
    try:
        c = args.command
        if c == "init":
            return {"scope": s.scope, "store": str(s.directory), "version": __version__}
        if c == "doctor":
            return {"core": __version__, "python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version, "fts5": True, "scope": s.scope, "store": str(s.directory), "executables": {x: bool(shutil.which(x)) for x in ("git", "node", "npm", "go", "graphify", "graft", "engram")}, "audit": s.audit(), "durability": "Directory existence cannot establish that the host retains it across sessions."}
        if c == "remember":
            body = Path(args.file).read_text() if args.file else args.text
            sources = [source(p) for p in args.source] + [{"label": x, "type": "reported"} for x in args.source_label]
            return s.remember(args.title, body, args.topic, args.kind, args.epistemic, args.confidence, sources, args.supersedes, args.review_after)
        if c == "search":
            return s.search(args.query, args.limit, args.include_inactive)
        if c == "get":
            return s.get(args.id)
        if c == "timeline":
            return s.timeline(args.topic)
        if c == "retire":
            return s.retire(args.id)
        if c == "checkpoint":
            return s.checkpoint(json.loads(Path(args.file).read_text()))
        if c == "checkpoint-show":
            row = s.db.execute("SELECT data FROM checkpoints WHERE scope=? ORDER BY created DESC LIMIT 1", (s.scope,)).fetchone()
            return json.loads(row[0]) if row else {"checkpoint": None}
        if c == "resume":
            return s.resume(args.query, args.budget)
        if c == "audit":
            return s.audit()
        if c == "index":
            return index(s, args.root)
        if c == "graph":
            return graph_query(s, args.query, args.limit)
        if c == "path":
            return graph_path(s, args.origin, args.start, args.end)
        if c == "map":
            return markdown_map(s)
        if c == "import":
            if args.engine in {"graft", "graphify"}:
                return import_graph(s, args.engine, args.path)
            if args.engine == "engram":
                if not args.project:
                    raise ValueError("Engram import requires --project to prevent cross-project mixing")
                return import_engram(s, args.path, args.project)
            return import_second_brain(s, args.path)
        if c == "export":
            return {"snapshot": private_write(args.file, json.dumps(s.snapshot(), indent=2, ensure_ascii=False))}
        if c == "restore":
            return s.restore(json.loads(Path(args.file).read_text()))
    finally:
        s.close()


def main():
    try:
        result = run(parser().parse_args())
        print(result if isinstance(result, str) else json.dumps(result, indent=2, ensure_ascii=False))
        if isinstance(result, dict) and result.get("ok") is False:
            return 1
        return 0
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
