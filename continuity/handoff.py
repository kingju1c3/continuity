from __future__ import annotations

import json
import time
from pathlib import Path

from .project import git_snapshot


def checkpoint_payload(
    root: Path,
    *,
    session_id: str | None,
    host: str,
    goal: str = "",
    instructions: str = "",
    discoveries: str = "",
    accomplished: str = "",
    next_steps: str = "",
    relevant_files: str = "",
    verification: str = "",
) -> dict:
    return {
        "version": 2,
        "kind": "semantic",
        "created_at": int(time.time()),
        "session_id": session_id,
        "host": host,
        "root": str(root),
        "goal": goal,
        "instructions": instructions,
        "discoveries": discoveries,
        "accomplished": accomplished,
        "next_steps": next_steps,
        "relevant_files": relevant_files,
        "verification": verification,
        "git": git_snapshot(root),
    }


def render_markdown(p: dict) -> str:
    git = p.get("git") or {}

    def s(k: str) -> str:
        return str(p.get(k) or "(none recorded)")

    text = f"""# Continuity Handoff

- Created: {p.get('created_at')}
- Session label: {p.get('session_label') or '(none)'}
- Kind: {p.get('kind') or 'semantic'}
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
    boundary = p.get("automatic_boundary_context")
    if isinstance(boundary, dict):
        text += "\n## Automatic Boundary Context\n"
        text += "\nThis section is machine-captured evidence. Verify it against current source.\n"
        changed = boundary.get("changed_files") or []
        if changed:
            text += "\n### Changed Files\n" + "\n".join(f"- {x}" for x in changed) + "\n"
        memories = boundary.get("recent_memory") or []
        if memories:
            text += "\n### Recent Durable Memory\n"
            for item in memories:
                text += f"- [{item.get('kind')}] {item.get('title')} ({item.get('topic_key') or '-'})\n"
        wip = boundary.get("work_in_progress") or {}
        if wip.get("available"):
            text += "\n### Work In Progress (lossless)\n"
            text += f"- Uncommitted tracked changes: {wip.get('patch_bytes', 0)} bytes" + (f", full binary patch at `{wip.get('patch_path')}`" if wip.get("patch_path") else " (none)") + "\n"
            untracked = wip.get("untracked_files") or []
            text += f"- Untracked files ({len(untracked)}): " + (", ".join(untracked[:50]) or "none") + ("…" if len(untracked) > 50 else "") + "\n"
            if wip.get("recent_commits"):
                text += "\nRecent commits:\n```\n" + str(wip["recent_commits"]) + "\n```\n"
        transcript = boundary.get("transcript_tail") or {}
        text += "\n### Transcript Tail\n"
        if transcript.get("available"):
            text += str(transcript.get("text") or "") + "\n"
            text += "\n_" + str(transcript.get("warning") or "Best-effort transcript evidence.") + "_\n"
        else:
            text += "(unavailable: " + str(transcript.get("reason") or "unknown") + ")\n"
    return text


def ensure_state_dir(root: Path) -> Path:
    """Create .continuity/ and keep it out of Git: handoffs hold transcript tails and must never be committed."""
    d = root / ".continuity"
    d.mkdir(parents=True, exist_ok=True)
    ignore = d / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n", encoding="utf-8")
    return d


def write_checkpoint(root: Path, payload: dict) -> Path:
    d = ensure_state_dir(root) / "handoffs"
    d.mkdir(parents=True, exist_ok=True)
    sid = (payload.get("session_id") or "session").replace("/", "-")[:80]
    path = d / f"{int(payload['created_at'])}-{sid}.md"
    n = 1
    while path.exists():  # two checkpoints in one second must not overwrite each other
        n += 1
        path = d / f"{int(payload['created_at'])}-{sid}-{n}.md"
    text = render_markdown(payload)
    path.write_text(text, encoding="utf-8")
    (root / ".continuity" / "LATEST.md").write_text(text, encoding="utf-8")
    (root / ".continuity" / "LATEST.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    return path


def validate_handoff(root: Path, payload: dict) -> list[str]:
    warnings: list[str] = []
    target_root = Path(str(payload.get("root") or ".")).expanduser().resolve()
    successor_roots = {str(x) for x in payload.get("successor_roots") or []}
    in_successor_worktree = str(root.resolve()) in successor_roots
    if in_successor_worktree:
        warnings.append(f"running in the successor worktree {root.resolve()} (handoff captured in {payload.get('root')}); branch differs by design")
    elif str(root.resolve()) != str(target_root):
        warnings.append(
            f"project root mismatch: handoff={payload.get('root')} current={root.resolve()}"
        )

    old = payload.get("git") or {}
    current = git_snapshot(root)

    if old.get("branch") and current.get("branch") and old["branch"] != current["branch"] and not in_successor_worktree:
        warnings.append(
            f"branch changed: handoff={old['branch']} current={current['branch']}"
        )
    if old.get("head") and current.get("head") and old["head"] != current["head"]:
        warnings.append(
            f"HEAD changed: handoff={old['head']} current={current['head']}"
        )
    if (old.get("status") or "") != (current.get("status") or ""):
        warnings.append("working-tree status differs from the recorded handoff")

    raw_files = str(payload.get("relevant_files") or "")
    for token in raw_files.replace(",", " ").split():
        if token.startswith("-"):
            continue
        candidate = token.strip(chr(96) + "'\"")
        if not candidate or candidate.startswith(("http://", "https://")):
            continue
        p = root / candidate
        if "/" in candidate or "." in Path(candidate).name:
            if not p.exists():
                warnings.append(f"relevant file no longer exists: {candidate}")
    return warnings
