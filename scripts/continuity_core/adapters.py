"""Read explicit upstream exports without running their code or treating it as authority."""
import json
from pathlib import Path
from .store import source, digest, canonical


def import_graph(store, engine, path):
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict) or not isinstance(data.get("nodes"), list):
        raise ValueError("Expected a graph object with a nodes list")
    raw_edges = data.get("edges", data.get("links", []))
    if not isinstance(raw_edges, list):
        raise ValueError("Graph edges must be a list")
    nodes = []
    seen = set()
    for n in data["nodes"]:
        nid = str(n["id"])
        if nid in seen:
            raise ValueError("Duplicate graph node id")
        seen.add(nid)
        nodes.append({"id": nid, "label": n.get("label", n.get("name", nid)), "kind": n.get("kind", n.get("file_type", "node")), "upstream": n})
    edges = []
    for e in raw_edges:
        a, b = str(e["source"]), str(e["target"])
        for nid in (a, b):
            if nid not in seen:
                seen.add(nid)
                nodes.append({"id": nid, "label": nid, "kind": "unresolved_external"})
        edges.append({"source": a, "target": b, "relation": e.get("relation", "related"), "confidence": e.get("confidence", "UNASSESSED"), "engine": engine, "upstream": e})
    provenance = source(path)
    origin = f"{engine}:{Path(path).resolve()}"
    store.save_graph(origin, {"nodes": nodes, "edges": edges, "provenance": provenance, "engine": engine})
    return {"origin": origin, "nodes": len(nodes), "edges": len(edges)}


def import_engram(store, path, project):
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict) or not isinstance(data.get("observations"), list):
        raise ValueError("Expected Engram ExportData with observations")
    sessions = {s["id"]: s for s in data.get("sessions", [])}
    ids, skipped = [], 0
    provenance = source(path)
    for o in data["observations"]:
        owner = o.get("project") or sessions.get(o.get("session_id"), {}).get("project")
        # User/global or another project's memories require a separate explicit import.
        if owner != project or o.get("deleted_at") or o.get("scope", "project") not in (None, "", "project"):
            skipped += 1
            continue
        imported = {**provenance, "engine": "engram", "observation_id": o.get("id"), "upstream_created_at": o.get("created_at"), "upstream_updated_at": o.get("updated_at"), "upstream_review_after": o.get("review_after"), "upstream_scope": o.get("scope")}
        ids.append(store.remember(o.get("title") or "Engram observation", o["content"], topic=o.get("topic_key") or f"engram/{project}/{o.get('sync_id') or o['id']}", sources=[imported])["id"])
    for s in sessions.values():
        if s.get("project") == project and s.get("summary"):
            ids.append(store.remember("Engram session " + s["id"], s["summary"], topic="engram/session/" + s["id"], kind="session", sources=[provenance])["id"])
    return {"imported": len(ids), "record_ids": ids, "skipped": skipped, "note": "Observations and session summaries only. Prompts and native memory relations stay in the source export. Review timestamps are preserved as provenance and must be reviewed; imports are Class C/unassessed."}


def import_second_brain(store, path):
    p = Path(path).resolve()
    if not p.is_dir():
        raise ValueError("Choose the explicit Second Brain workspace/memory directory")
    ids = []
    for f in sorted(p.rglob("*.md")):
        if f.is_symlink() or not f.resolve().is_relative_to(p) or f.stat().st_size > 1_000_000:
            continue
        content = f.read_text(encoding="utf-8")
        if content.strip():
            ids.append(store.remember(f.stem, content, topic="second-brain/" + f.relative_to(p).as_posix(), sources=[source(f)])["id"])
    return {"imported": len(ids), "record_ids": ids}
