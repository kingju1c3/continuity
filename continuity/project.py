from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectIdentity:
    root: Path
    key: str
    git_head: str | None
    branch: str | None


def _git(root: Path, *args: str) -> str | None:
    try:
        p = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if p.returncode != 0:
        return None
    return p.stdout.strip() or None


def find_root(start: str | os.PathLike[str] | None = None) -> Path:
    p = Path(start or os.getcwd()).expanduser().resolve()
    if p.is_file():
        p = p.parent
    git = _git(p, "rev-parse", "--show-toplevel")
    return Path(git).resolve() if git else p


def identity(start: str | os.PathLike[str] | None = None) -> ProjectIdentity:
    root = find_root(start)
    remote = _git(root, "config", "--get", "remote.origin.url") or ""
    canonical = f"{root}\n{remote}".encode()
    key = hashlib.sha256(canonical).hexdigest()[:20]
    return ProjectIdentity(root=root, key=key, git_head=_git(root, "rev-parse", "HEAD"), branch=_git(root, "branch", "--show-current"))


def git_snapshot(root: Path) -> dict[str, str | None]:
    return {
        "head": _git(root, "rev-parse", "HEAD"),
        "branch": _git(root, "branch", "--show-current"),
        "status": _git(root, "status", "--short"),
        "diffstat": _git(root, "diff", "--stat"),
    }
