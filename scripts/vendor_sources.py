#!/usr/bin/env python3
"""Bundle every tracked upstream file; or verify the existing pinned bundle."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "session-handoff": "https://github.com/kingju1c3/session-handoff",
    "second-brain": "https://github.com/henrydaum/second-brain",
    "Graft": "https://github.com/trailhq/Graft",
    "graphify": "https://github.com/Graphify-Labs/graphify",
    "engram": "https://github.com/Gentleman-Programming/engram",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bundle(directory):
    manifest = {"schema": 1, "sources": {}}
    for name, url in SOURCES.items():
        src = Path(directory).resolve() / name
        dst = ROOT / "vendor" / name
        if dst.exists():
            raise ValueError(f"Refusing to overwrite an existing snapshot: {dst}")
        commit = subprocess.check_output(["git", "-C", str(src), "rev-parse", "HEAD"], text=True).strip()
        entries = subprocess.check_output(["git", "-C", str(src), "ls-tree", "-rz", "HEAD"]).split(b"\0")
        files = {}
        for entry in entries:
            if not entry:
                continue
            metadata, raw_path = entry.split(b"\t", 1)
            mode, kind, object_id = metadata.decode().split()
            rel = raw_path.decode()
            if kind != "blob" or mode == "120000":
                raise ValueError("Review submodules/symlinks explicitly before bundling: " + rel)
            target = dst / rel
            if not target.resolve().is_relative_to(dst.resolve()):
                raise ValueError("Unsafe upstream path")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(subprocess.check_output(["git", "-C", str(src), "cat-file", "blob", object_id]))
            os.chmod(target, 0o755 if mode == "100755" else 0o644)
            files[rel] = {"sha256": sha(target), "bytes": target.stat().st_size, "mode": mode}
        manifest["sources"][name] = {"url": url, "commit": commit, "files": files, "file_count": len(files)}
    (ROOT / "vendor/manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return {name: {"commit": data["commit"], "files": data["file_count"]} for name, data in manifest["sources"].items()}


def verify():
    manifest = json.loads((ROOT / "vendor/manifest.json").read_text())
    errors = []
    total = 0
    for name, data in manifest["sources"].items():
        directory = ROOT / "vendor" / name
        present = {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file() or p.is_symlink()}
        if present != set(data["files"]):
            errors.append({"source": name, "missing": sorted(set(data["files"])-present), "extra": sorted(present-set(data["files"]))})
        for rel, expected in data["files"].items():
            p = directory / rel
            if not p.is_file() or p.is_symlink() or sha(p) != expected["sha256"]:
                errors.append({"source": name, "mismatch": rel})
            elif os.name != "nt" and bool(p.stat().st_mode & 0o111) != (expected["mode"] == "100755"):
                errors.append({"source": name, "mode_mismatch": rel})
            total += 1
    return {"ok": not errors, "files_checked": total, "errors": errors}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--from-directory", help="Existing clones; reads committed blobs, never downloads")
    args = p.parse_args()
    result = bundle(args.from_directory) if args.from_directory else verify()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result.get("ok", True) else 1)
