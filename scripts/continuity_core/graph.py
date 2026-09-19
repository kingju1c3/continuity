"""Small deterministic source map; optional engines add richer graphs."""
import ast
import json
import os
import re
import subprocess
from collections import deque
from pathlib import Path

from .store import canonical, digest, now, freshness

EXCLUDED = {".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__", "vendor", "upstream", "dist", "build", ".continuity"}
EXTENSIONS = {".py", ".md", ".txt", ".rst", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".c", ".h", ".cpp", ".json", ".yaml", ".yml", ".toml"}


def files(root):
    root = Path(root).resolve()
    try:
        found_root = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], check=True, capture_output=True, text=True).stdout.strip()
        # Subdirectory indexing uses the fallback walk; never walk outside root.
        if Path(found_root).resolve() != root:
            raise ValueError("subdirectory")
        paths = subprocess.run(["git", "-C", str(root), "ls-files", "-c", "-o", "--exclude-standard", "-z"], check=True, capture_output=True).stdout.decode().split("\0")
    except (OSError, ValueError, subprocess.CalledProcessError):
        paths = []
        for parent, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not d.startswith("."))
            paths.extend(str((Path(parent) / name).relative_to(root)) for name in names)
    for rel in sorted(set(paths)):
        p = root / rel
        if not rel or any(x in EXCLUDED or x.startswith(".") for x in Path(rel).parts):
            continue
        if p.suffix.lower() not in EXTENSIONS or p.is_symlink() or not p.is_file():
            continue
        if any(x in p.name.lower() for x in ("credential", "secret", "private-key")):
            continue
        if not p.resolve().is_relative_to(root) or p.stat().st_size > 1_000_000:
            continue
        yield p, rel


def extract(rel, text, file_hash):
    fid = rel
    nodes = [{"id": fid, "label": rel, "kind": "file", "path": rel, "line": 1, "sha256": file_hash}]
    edges = []

    def edge(src, dst, relation, line):
        edges.append({"source": src, "target": dst, "relation": relation, "confidence": "EXTRACTED", "evidence": {"path": rel, "line": line, "sha256": file_hash}, "meaning": "syntactic relationship; does not prove runtime behavior"})

    if rel.endswith(".py"):
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            nodes[0]["parse_error"] = str(exc)
            return nodes, edges

        def walk(parent, owner, qual=""):
            for child in ast.iter_child_nodes(parent):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    name = f"{qual}.{child.name}".strip(".")
                    nid = f"{rel}#{name}@{child.lineno}"
                    nodes.append({"id": nid, "label": name, "kind": type(child).__name__, "path": rel, "line": child.lineno, "sha256": file_hash})
                    edge(owner, nid, "contains", child.lineno)
                    walk(child, nid, name)
                elif isinstance(child, (ast.Import, ast.ImportFrom)):
                    names = [a.name for a in child.names] if isinstance(child, ast.Import) else [("." * child.level) + (child.module or "")]
                    for name in names:
                        nid = "module:" + name
                        if not any(n["id"] == nid for n in nodes):
                            nodes.append({"id": nid, "label": name, "kind": "unresolved_module"})
                        edge(owner, nid, "imports", child.lineno)
                else:
                    walk(child, owner, qual)
        walk(tree, fid)
    elif rel.endswith(".md"):
        for line, value in enumerate(text.splitlines(), 1):
            m = re.match(r"^(#{1,6})\s+(.+)", value)
            if m:
                nid = f"{rel}#heading@{line}"
                nodes.append({"id": nid, "label": m[2], "kind": "heading", "path": rel, "line": line, "sha256": file_hash})
                edge(fid, nid, "contains", line)
            for target in re.findall(r"\[[^\]]*\]\(([^)\s]+)\)", value):
                if ":" in target or target.startswith("/"):
                    continue
                clean = os.path.normpath(str(Path(rel).parent / target.split("#")[0]))
                if clean.startswith("../"):
                    continue
                edge(fid, clean, "links", line)
    return nodes, edges


def index(store, root):
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("Index root must be a directory")
    if root == Path(root.anchor) or root == Path.home():
        raise ValueError("Choose a project directory, not a filesystem or home root")
    origin = "local:" + str(root)
    prior = store.graphs().get(origin, {})
    old = prior.get("files", {}) if prior.get("extractor_version") == 1 else {}
    cache = {}
    changed = 0
    for p, rel in files(root):
        if p.resolve().is_relative_to(store.directory):
            continue
        content = p.read_bytes()
        h = digest(content)
        if old.get(rel, {}).get("sha256") == h:
            cache[rel] = old[rel]
            continue
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            continue
        nodes, edges = extract(rel, text, h)
        cache[rel] = {"sha256": h, "nodes": nodes, "edges": edges}
        changed += 1
    nodes = {n["id"]: n for c in cache.values() for n in c["nodes"]}
    edges = [e for c in cache.values() for e in c["edges"]]
    # Missing Markdown targets remain explicit unresolved nodes, never silently disappear.
    for e in edges:
        if e["target"] not in nodes:
            nodes[e["target"]] = {"id": e["target"], "label": e["target"], "kind": "unresolved_link"}
    graph = {"root": str(root), "indexed_at": now(), "extractor_version": 1, "files": cache, "nodes": list(nodes.values()), "edges": edges}
    store.save_graph(origin, graph)
    return {"origin": origin, "files": len(cache), "changed": changed, "removed": len(set(old)-set(cache)), "nodes": len(nodes), "edges": len(edges)}


def graph_query(store, query, limit=12):
    rows = []
    for origin, graph in store.graphs().items():
        for n in graph["nodes"]:
            if query.casefold() in (n.get("label", "") + " " + n["id"]).casefold():
                row = {"origin": origin, **n}
                if graph.get("root") and n.get("path") and n.get("sha256"):
                    p = Path(graph["root"]) / n["path"]
                    row["freshness"] = "missing" if not p.is_file() else ("current" if digest(p.read_bytes()) == n["sha256"] else "changed")
                else:
                    row["freshness"] = "imported-unverified"
                    if graph.get("provenance"):
                        row["export_source"] = freshness([graph["provenance"]])[0]
                rows.append(row)
    return rows[:max(1, min(100, limit))]


def graph_path(store, origin, start, end, max_hops=8):
    graphs = store.graphs()
    if origin not in graphs:
        raise ValueError("Unknown graph origin in this scope")
    graph = graphs[origin]
    nodes = {n["id"] for n in graph["nodes"]}
    if start not in nodes or end not in nodes:
        raise ValueError("Both endpoints must exist in this graph")
    adjacent = {}
    for e in graph["edges"]:
        adjacent.setdefault(e["source"], []).append(e)
    queue = deque([(start, [])])
    seen = {start}
    while queue:
        node, path = queue.popleft()
        if node == end:
            return {"found": True, "directed": True, "origin": origin, "path": path, "export_sources": freshness([graph["provenance"]]) if graph.get("provenance") else [], "note": "Edges retain their original evidence labels; a graph path is not causal proof. Recheck current source before relying on a cached path."}
        if len(path) >= max_hops:
            continue
        for e in adjacent.get(node, []):
            if e["target"] not in seen:
                seen.add(e["target"])
                queue.append((e["target"], path + [e]))
    return {"found": False, "directed": True, "path": [], "max_hops": max_hops}


def markdown_map(store):
    out = [f"# Project map: {store.scope}\n", "Generated projection. Read current source before relying on this map.\n"]
    for origin, graph in store.graphs().items():
        out.append(f"\n## {origin}\n")
        for n in graph["nodes"]:
            out.append(f"- `{n['id']}` — {n.get('label', n['id'])} ({n.get('kind', 'node')})\n")
        out.append("\n### Relationships\n")
        for e in graph["edges"]:
            out.append(f"- `{e['source']}` → `{e['target']}`: {e['relation']} [{e['confidence']}]\n")
    return "".join(out)
