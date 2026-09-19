from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

MARKER_START = "<!-- continuity:start -->"
MARKER_END = "<!-- continuity:end -->"
AGENT_BLOCK = (
    MARKER_START
    + "\n## Continuity\n"
    + "This project uses the /continuity protocol. At session start, restore Continuity context before editing. "
      "Search durable project memory before repeating prior work. Prefer structural orientation before broad raw-file reads. "
      "Before compaction, session end, or explicit handoff, create a semantic Continuity checkpoint that records goal, "
      "constraints, discoveries, accomplished work, ordered next steps, relevant files, and verification.\n"
    + MARKER_END
    + "\n"
)

OWN_TOKEN = "continuity hook --host"


class InstallError(RuntimeError):
    pass


def _read_json_object(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InstallError(f"refusing to overwrite unparseable JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise InstallError(f"expected JSON object in {path}")
    return value


def _backup(root: Path, path: Path) -> Path | None:
    if not path.exists():
        return None
    bdir = root / ".continuity" / "backups"
    bdir.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time())
    target = bdir / f"{path.name}.{stamp}.bak"
    shutil.copy2(path, target)
    return target


def _upsert_block_text(old: str, block: str) -> str:
    if MARKER_START in old and MARKER_END in old:
        a = old.index(MARKER_START)
        b = old.index(MARKER_END, a) + len(MARKER_END)
        return (old[:a] + block.rstrip() + old[b:]).rstrip() + "\n"
    return old.rstrip() + ("\n\n" if old.strip() else "") + block.rstrip() + "\n"


def _remove_block_text(old: str) -> str:
    if MARKER_START not in old or MARKER_END not in old:
        return old
    a = old.index(MARKER_START)
    b = old.index(MARKER_END, a) + len(MARKER_END)
    new = (old[:a] + old[b:]).strip()
    return new + ("\n" if new else "")


def _skill_text() -> str:
    p = Path(__file__).resolve().parent / "SKILL.md"
    if p.exists():
        return p.read_text(encoding="utf-8")
    raise InstallError("packaged continuity/SKILL.md is missing")


def _install_skill_bundle(target: Path) -> None:
    package_root = Path(__file__).resolve().parent
    target.mkdir(parents=True, exist_ok=True)
    (target / "SKILL.md").write_text(_skill_text(), encoding="utf-8")
    for name in ("protocol", "schemas"):
        src = package_root / name
        if src.is_dir():
            shutil.copytree(src, target / name, dirs_exist_ok=True)


def _ours(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    hooks = entry.get("hooks")
    if not isinstance(hooks, list):
        return False
    return any(
        isinstance(h, dict) and OWN_TOKEN in str(h.get("command", ""))
        for h in hooks
    )


def _merge_hook(data: dict, event: str, entry: dict) -> None:
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise InstallError("hooks must be a JSON object")
    prior = hooks.get(event, [])
    if not isinstance(prior, list):
        raise InstallError(f"hooks.{event} must be a JSON array")
    hooks[event] = [x for x in prior if not _ours(x)] + [entry]


def _remove_our_hooks(data: dict) -> None:
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return
    for event in list(hooks):
        prior = hooks.get(event)
        if isinstance(prior, list):
            kept = [x for x in prior if not _ours(x)]
            if kept:
                hooks[event] = kept
            else:
                del hooks[event]


def _command(host: str) -> str:
    return f'"{sys.executable}" -m continuity hook --host {host}'


def _handler(host: str, *, timeout: int = 10, context_limit: int | None = None) -> dict:
    h: dict = {
        "type": "command",
        "command": _command(host),
        "timeout": timeout,
    }
    if context_limit is not None:
        h["additionalContextLimit"] = context_limit
    return h


def _claude_entries() -> dict[str, dict]:
    return {
        "SessionStart": {
            "matcher": "startup|resume|clear|compact",
            "hooks": [_handler("claude", timeout=10)],
        },
        "UserPromptSubmit": {"hooks": [_handler("claude", timeout=10)]},
        "PostToolUse": {
            "matcher": "Write|Edit|MultiEdit|NotebookEdit|Bash",
            "hooks": [_handler("claude", timeout=10)],
        },
        "PreCompact": {"hooks": [_handler("claude", timeout=10)]},
        "PostCompact": {"hooks": [_handler("claude", timeout=10)]},
        "Stop": {"hooks": [_handler("claude", timeout=10)]},
        "SessionEnd": {"hooks": [_handler("claude", timeout=3)]},
    }


def _codex_entries() -> dict[str, dict]:
    return {
        "SessionStart": {
            "matcher": "startup|resume|clear|compact",
            "hooks": [_handler("codex", timeout=10, context_limit=5000)],
        },
        "UserPromptSubmit": {
            "hooks": [_handler("codex", timeout=10, context_limit=3500)],
        },
        "PostToolUse": {
            "matcher": "apply_patch|Write|Edit|MultiEdit|Bash|Shell|shell",
            "hooks": [_handler("codex", timeout=10, context_limit=1200)],
        },
        "PreCompact": {"hooks": [_handler("codex", timeout=10)]},
        "PostCompact": {"hooks": [_handler("codex", timeout=10)]},
        "Stop": {"hooks": [_handler("codex", timeout=10, context_limit=1200)]},
        "SessionEnd": {"hooks": [_handler("codex", timeout=3)]},
    }


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _enable(root: Path) -> Path:
    p = root / ".continuity" / "enabled.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "schema": 1,
                "enabled": True,
                "installed_at": int(time.time()),
                "python": sys.executable,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return p


def install_repo(root: Path, agents: list[str], *, dry_run: bool = False) -> list[str]:
    root = root.resolve()
    plan: list[str] = [str(root / ".continuity" / "enabled.json")]

    claude_settings = root / ".claude" / "settings.json"
    codex_cfg = Path.home() / ".codex" / "hooks.json"

    # Validate every existing config before writing anything.
    claude_data = _read_json_object(claude_settings) if "claude" in agents else None
    codex_data = (
        _read_json_object(codex_cfg)
        if "codex" in agents and Path.home().joinpath(".codex").exists()
        else None
    )

    if "claude" in agents:
        plan.extend(
            [
                str(root / ".claude" / "skills" / "continuity" / "SKILL.md"),
                str(claude_settings),
            ]
        )
    if "codex" in agents:
        plan.extend(
            [
                str(root / ".agents" / "skills" / "continuity" / "SKILL.md"),
                str(root / "AGENTS.md"),
            ]
        )
        if codex_data is not None:
            plan.append(str(codex_cfg))
    plan.append(str(root / ".continuity" / ".gitignore"))

    if dry_run:
        return plan

    _enable(root)

    if "claude" in agents:
        p = root / ".claude" / "skills" / "continuity"
        _install_skill_bundle(p)
        assert claude_data is not None
        _backup(root, claude_settings)
        for event, entry in _claude_entries().items():
            _merge_hook(claude_data, event, entry)
        _write_json(claude_settings, claude_data)

    if "codex" in agents:
        p = root / ".agents" / "skills" / "continuity"
        _install_skill_bundle(p)

        agents_md = root / "AGENTS.md"
        old = agents_md.read_text(encoding="utf-8") if agents_md.exists() else ""
        if agents_md.exists():
            _backup(root, agents_md)
        agents_md.write_text(_upsert_block_text(old, AGENT_BLOCK), encoding="utf-8")

        if codex_data is not None:
            _backup(root, codex_cfg)
            for event, entry in _codex_entries().items():
                _merge_hook(codex_data, event, entry)
            _write_json(codex_cfg, codex_data)

    c = root / ".continuity" / ".gitignore"
    c.parent.mkdir(parents=True, exist_ok=True)
    c.write_text("*\n!.gitignore\n", encoding="utf-8")
    return plan


def uninstall_repo(root: Path, agents: list[str], *, dry_run: bool = False) -> list[str]:
    root = root.resolve()
    plan: list[str] = []
    if "claude" in agents:
        plan.extend(
            [
                str(root / ".claude" / "skills" / "continuity" / "SKILL.md"),
                str(root / ".claude" / "settings.json"),
            ]
        )
    if "codex" in agents:
        plan.extend(
            [
                str(root / ".agents" / "skills" / "continuity" / "SKILL.md"),
                str(root / "AGENTS.md"),
            ]
        )
        if Path.home().joinpath(".codex", "hooks.json").exists():
            plan.append(str(Path.home() / ".codex" / "hooks.json"))
    plan.append(str(root / ".continuity" / "enabled.json"))
    if dry_run:
        return plan

    if "claude" in agents:
        skill = root / ".claude" / "skills" / "continuity"
        if skill.exists():
            shutil.rmtree(skill)
        settings = root / ".claude" / "settings.json"
        if settings.exists():
            data = _read_json_object(settings)
            _backup(root, settings)
            _remove_our_hooks(data)
            _write_json(settings, data)

    if "codex" in agents:
        skill = root / ".agents" / "skills" / "continuity"
        if skill.exists():
            shutil.rmtree(skill)
        agents_md = root / "AGENTS.md"
        if agents_md.exists():
            _backup(root, agents_md)
            agents_md.write_text(
                _remove_block_text(agents_md.read_text(encoding="utf-8")),
                encoding="utf-8",
            )
        codex_cfg = Path.home() / ".codex" / "hooks.json"
        if codex_cfg.exists():
            data = _read_json_object(codex_cfg)
            _backup(root, codex_cfg)
            _remove_our_hooks(data)
            _write_json(codex_cfg, data)

    enabled = root / ".continuity" / "enabled.json"
    if enabled.exists():
        enabled.unlink()
    return plan
