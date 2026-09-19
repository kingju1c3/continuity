from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .handoff import render_markdown
from .project import ProjectIdentity, git_snapshot
from .store import Store

WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_./:-]{2,}")
STOP = {
    "the","and","for","with","this","that","from","into","where","what","when","how","why",
    "are","was","were","have","has","had","does","did","can","could","should","would","please",
    "implement","implemented","implementation","project","code","file","files",
}


def query_terms(text: str, limit: int = 8) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for raw in WORD_RE.findall(text or ""):
        term = raw.lower().strip("./:-")
        if len(term) < 3 or term in STOP or term in seen:
            continue
        seen.add(term)
        terms.append(term)
        if len(terms) >= limit:
            break
    return terms


def fts_query(text: str) -> str:
    terms = query_terms(text)
    return " OR ".join(f'"{t}"' for t in terms)


def _trim(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 80)].rstrip() + "\n… [Continuity context truncated]"


def build_context_pack(
    store: Store,
    ident: ProjectIdentity,
    *,
    prompt: str = "",
    max_chars: int = 7000,
    include_handoff: bool = True,
    memory_limit: int = 6,
    structural_limit: int = 8,
) -> str:
    lines: list[str] = [
        "CONTINUITY PROJECT CONTEXT",
        f"Project: {ident.root}",
        f"Branch: {ident.branch or '(unknown)'}",
        f"HEAD: {ident.git_head or '(unknown)'}",
    ]

    lease = store.active_lease(ident.key)
    if lease:
        lines.append(
            f"Active session: {lease['session_id']} ({lease['host']}); "
            f"heartbeat={lease['heartbeat_at']}"
        )

    idx = store.index_state(ident.key)
    if idx:
        state = "DIRTY/STALE" if idx.get("dirty") else "fresh"
        lines.append(f"Structural index: {state}; last_file={idx.get('last_file') or '-'}")
    else:
        lines.append("Structural index: not built")

    if include_handoff:
        handoff = store.latest_handoff(ident.key)
        if handoff:
            lines.extend(["", "LATEST HANDOFF", render_markdown(handoff).strip()])
        freeze = store.latest_freeze(ident.key)
        if freeze and (not handoff or freeze.get("_created_at", 0) > handoff.get("_created_at", 0)):
            lines.extend(
                [
                    "",
                    "NEWER MECHANICAL FREEZE",
                    f"Event: {freeze.get('_event')}",
                    f"Created: {freeze.get('_created_at')}",
                    f"Git: {json.dumps(freeze.get('git') or {}, sort_keys=True)}",
                    "A semantic checkpoint may be missing after this freeze; verify current source before continuing.",
                ]
            )

    q = fts_query(prompt)
    memories = store.search_memory(ident.key, q if q else "", memory_limit)
    if memories:
        lines.extend(["", "RELEVANT DURABLE MEMORY"])
        for row in memories:
            topic = row["topic_key"] or "-"
            lines.append(
                f"- [{row['kind']}] {row['title']} (topic={topic})\n  {str(row['content']).strip()}"
            )

    terms = query_terms(prompt)
    structural = []
    seen = set()
    for term in terms[:4]:
        for row in store.search_symbols(ident.key, term, structural_limit):
            key = (row["path"], row["line"], row["symbol"])
            if key in seen:
                continue
            seen.add(key)
            structural.append(row)
            if len(structural) >= structural_limit:
                break
        if len(structural) >= structural_limit:
            break
    if structural:
        lines.extend(["", "STRUCTURAL POINTERS"])
        for row in structural:
            lines.append(f"- {row['path']}:{row['line']} {row['kind']} {row['symbol']}")

    lines.extend(
        [
            "",
            "INTEGRITY",
            "- Current source and Git state outrank this historical context.",
            "- If branch/HEAD/files disagree with the handoff, surface the mismatch before editing.",
            "- Do not repeat completed work unless current evidence requires it.",
        ]
    )
    return _trim("\n".join(lines).strip() + "\n", max_chars)


def mechanical_freeze(root: Path, *, host: str, session_id: str | None, event: str) -> dict:
    return {
        "version": 1,
        "created_at": int(time.time()),
        "root": str(root),
        "host": host,
        "session_id": session_id,
        "event": event,
        "git": git_snapshot(root),
    }
