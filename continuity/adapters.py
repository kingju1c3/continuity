from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def detect() -> dict[str, bool]:
    return {"graft": shutil.which("graft") is not None, "graphify": shutil.which("graphify") is not None}


def structural_query(root: Path, question: str) -> tuple[str, str] | None:
    if shutil.which("graft"):
        p = subprocess.run(["graft", "ask", question], cwd=root, capture_output=True, text=True, timeout=45)
        if p.returncode == 0 and p.stdout.strip():
            return "graft", p.stdout.strip()
    if shutil.which("graphify") and (root / "graphify-out" / "graph.json").exists():
        p = subprocess.run(["graphify", "query", question], cwd=root, capture_output=True, text=True, timeout=45)
        if p.returncode == 0 and p.stdout.strip():
            return "graphify", p.stdout.strip()
    return None
