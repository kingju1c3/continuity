from __future__ import annotations

import json
import time
from pathlib import Path

from .project import git_snapshot


def checkpoint_payload(root: Path, *, session_id: str | None, host: str, goal: str = "", instructions: str = "", discoveries: str = "", accomplished: str = "", next_steps: str = "", relevant_files: str = "", verification: str = "") -> dict:
    return {
        "version": 1, "created_at": int(time.time()), "session_id": session_id, "host": host, "root": str(root),
        "goal": goal, "instructions": instructions, "discoveries": discoveries, "accomplished": accomplished,
        "next_steps": next_steps, "relevant_files": relevant_files, "verification": verification, "git": git_snapshot(root),
    }


def render_markdown(p: dict) -> str:
    git = p.get("git") or {}
    def s(k: str) -> str:
        return str(p.get(k) or "(none recorded)")
    return f"""# Continuity Handoff

- Created: {p.get('created_at')}
- Host: {p.get('host')}
- Session: {p.get('session_id') or '(unknown)'}
- Project: {p.get('root')}
- Branch: {git.get('branch') or '(detached/unknown)'}
- HEAD: {git.get('head') or '(unknown)'}

## Goal
{s('goal')}

## Instructions / Constraints
{s('instructions')}

## Discoveries
{s('discoveries')}

## Accomplished
{s('accomplished')}

## Next Steps
{s('next_steps')}

## Relevant Files
{s('relevant_files')}

## Verification
{s('verification')}

## Working Tree
{git.get('status') or '(clean or unavailable)'}

## Diffstat
{git.get('diffstat') or '(none or unavailable)'}
"""


def write_checkpoint(root: Path, payload: dict) -> Path:
    d = root / ".continuity" / "handoffs"; d.mkdir(parents=True, exist_ok=True)
    sid = (payload.get("session_id") or "session").replace("/", "-")[:80]
    path = d / f"{int(payload['created_at'])}-{sid}.md"
    text = render_markdown(payload)
    path.write_text(text, encoding="utf-8")
    (root / ".continuity" / "LATEST.md").write_text(text, encoding="utf-8")
    (root / ".continuity" / "LATEST.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path
