from __future__ import annotations

import json
import sys
from pathlib import Path

MARKER_START = "<!-- continuity:start -->"
MARKER_END = "<!-- continuity:end -->"
AGENT_BLOCK = f"""{MARKER_START}
## Continuity
At session start, run continuity start --host codex --emit-context. Before ending, compaction, or handing work to another session, invoke /continuity and create a semantic checkpoint with continuity checkpoint. Search Continuity before repeating prior project work. Prefer structural orientation before broad raw-file reads.
{MARKER_END}
"""

def _upsert_block(path: Path, block: str) -> None:
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    if MARKER_START in old and MARKER_END in old:
        a = old.index(MARKER_START)
        b = old.index(MARKER_END, a) + len(MARKER_END)
        new = old[:a] + block.rstrip() + old[b:]
    else:
        new = old.rstrip() + ("\n\n" if old.strip() else "") + block
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new.rstrip() + "\n", encoding="utf-8")

def _skill_text() -> str:
    p = Path(__file__).resolve().parent / "SKILL.md"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return "---\nname: continuity\ndescription: Persistent project continuity.\n---\nRun continuity start --emit-context.\n"

def _install_codex_hooks() -> list[str]:
    base = Path.home() / ".codex"
    if not base.exists():
        return []
    cfg = base / "hooks.json"
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    else:
        data = {}
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        return []
    cmd = f'"{sys.executable}" -m continuity hook --host codex'
    desired = {
        "SessionStart": {"matcher": "startup|resume|compact", "hooks": [{"type": "command", "command": cmd, "timeout": 10000}]},
        "UserPromptSubmit": {"hooks": [{"type": "command", "command": cmd, "timeout": 10000}]},
        "PreCompact": {"hooks": [{"type": "command", "command": cmd, "timeout": 10000}]},
        "Stop": {"hooks": [{"type": "command", "command": cmd, "timeout": 10000}]},
    }
    def ours(entry: object) -> bool:
        try:
            return any("continuity hook --host codex" in str(h.get("command", "")) for h in entry.get("hooks", []))
        except Exception:
            return False
    for event, entry in desired.items():
        prior = hooks.get(event, [])
        if not isinstance(prior, list):
            return []
        hooks[event] = [x for x in prior if not ours(x)] + [entry]
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return [str(cfg)]

def install_repo(root: Path, agents: list[str]) -> list[str]:
    writes: list[str] = []
    skill = _skill_text()
    if "claude" in agents:
        p = root / ".claude" / "skills" / "continuity" / "SKILL.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(skill, encoding="utf-8")
        writes.append(str(p))
        settings = root / ".claude" / "settings.json"
        data = {}
        if settings.exists():
            try:
                data = json.loads(settings.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
        hooks = data.setdefault("hooks", {})
        cmd = f'"{sys.executable}" -m continuity hook --host claude'
        for event in ("SessionStart", "PreCompact", "Stop"):
            arr = hooks.setdefault(event, [])
            entry = {"hooks": [{"type": "command", "command": cmd}]}
            if entry not in arr:
                arr.append(entry)
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        writes.append(str(settings))
    if "codex" in agents:
        p = root / ".agents" / "skills" / "continuity" / "SKILL.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(skill, encoding="utf-8")
        writes.append(str(p))
        a = root / "AGENTS.md"
        _upsert_block(a, AGENT_BLOCK)
        writes.append(str(a))
        writes.extend(_install_codex_hooks())
    c = root / ".continuity" / ".gitignore"
    c.parent.mkdir(parents=True, exist_ok=True)
    c.write_text("*\n!.gitignore\n", encoding="utf-8")
    writes.append(str(c))
    return writes
