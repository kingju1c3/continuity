#!/usr/bin/env python3
"""Plan or build an optional upstream engine in an isolated working copy."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ENGINES = {"second-brain": "second-brain", "graft": "Graft", "graphify": "graphify", "engram": "engram"}


def recipe(engine, destination):
    work = Path(destination).expanduser().resolve() / engine
    py = str(work / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
    if engine == "second-brain":
        setup = [[sys.executable, "-m", "venv", ".venv"], [py, "-m", "pip", "install", "-r", "requirements.txt"]]
        launch = [py, "main.py"]
    elif engine == "graphify":
        setup = [[sys.executable, "-m", "venv", ".venv"], [py, "-m", "pip", "install", "."]]
        launch = [str(work / ".venv" / ("Scripts/graphify.exe" if os.name == "nt" else "bin/graphify"))]
    elif engine == "graft":
        # Native tree-sitter bindings require dependency install scripts. This is opt-in.
        setup = [["npm", "ci"], ["npm", "run", "build"]]
        launch = ["node", str(work / "dist/cli.js")]
    else:
        setup = [["go", "build", "-o", "engram.exe" if os.name == "nt" else "engram", "./cmd/engram"]]
        launch = [str(work / ("engram.exe" if os.name == "nt" else "engram"))]
    return {"engine": engine, "source": str(ROOT / "vendor" / ENGINES[engine]), "working_copy": str(work), "setup": setup, "launch": launch, "requirements": {"second-brain": "Python >=3.11", "graphify": "Python >=3.10 plus pip-resolvable dependencies", "graft": "Node >=20, npm, native build toolchain", "engram": "Go >=1.25.10 or Go toolchain auto-download"}[engine], "note": "Setup downloads dependencies and executes their build/install scripts. Launch can start upstream services or require model credentials; it is printed, never automatically run."}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("engine", choices=list(ENGINES))
    p.add_argument("--destination", required=True, help="Private engine build directory outside the immutable skill")
    p.add_argument("--execute", action="store_true", help="Actually copy source and install/build; omit to print plan")
    p.add_argument("--node-headers", type=Path, help="Graft only: existing Node header root containing include/node/node.h")
    p.add_argument("--source-root", type=Path, help="Optional full source directory containing second-brain, Graft, graphify, engram; useful for compact installations")
    args = p.parse_args()
    plan = recipe(args.engine, args.destination)
    if args.source_root:
        plan["source"] = str(args.source_root.expanduser().resolve() / ENGINES[args.engine])
    if args.node_headers:
        headers = args.node_headers.expanduser().resolve()
        if args.engine != "graft" or not (headers / "include/node/node.h").is_file():
            raise ValueError("--node-headers requires Graft and a valid Node header root")
        plan["setup"][0].append("--nodedir=" + str(headers))
    print(json.dumps(plan, indent=2), flush=True)
    if not args.execute:
        return
    work = Path(plan["working_copy"])
    if work.is_relative_to(ROOT):
        raise ValueError("Build engines outside the installed skill")
    if work.exists():
        raise ValueError("Use a fresh destination; existing engine copies are not overwritten")
    if not Path(plan["source"]).is_dir():
        raise ValueError("Missing bundled source; install the complete repository")
    shutil.copytree(plan["source"], work, ignore=shutil.ignore_patterns(".git"))
    for command in plan["setup"]:
        subprocess.run(command, cwd=work, check=True, timeout=1800, shell=False)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
