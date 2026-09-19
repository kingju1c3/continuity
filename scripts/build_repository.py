#!/usr/bin/env python3
"""Assemble the complete GitHub-ready distribution from a compact installation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--destination', required=True, type=Path, help='New output directory')
    p.add_argument('--source-root', required=True, type=Path, help='Full vendor directory or verified fetch_sources output')
    args = p.parse_args()
    destination = args.destination.expanduser().resolve()
    source_root = args.source_root.expanduser().resolve()
    if destination.exists() or destination.is_relative_to(ROOT):
        raise ValueError('Choose a new directory outside this skill')
    manifest = json.loads((ROOT / 'vendor/manifest.json').read_text())
    # Validate every required source before writing the output.
    for name, row in manifest['sources'].items():
        for rel, meta in row['files'].items():
            src = source_root / name / rel
            if not src.is_file() or src.is_symlink() or hashlib.sha256(src.read_bytes()).hexdigest() != meta['sha256']:
                raise ValueError('Source verification failed: ' + name + '/' + rel)
    def ignore(directory, names):
        skip = {'.git', '__pycache__', '.pytest_cache'}
        if Path(directory).resolve() == ROOT:
            skip.add('vendor')
        return [n for n in names if n in skip]
    shutil.copytree(ROOT, destination, ignore=ignore)
    (destination / 'vendor').mkdir()
    shutil.copy2(ROOT / 'vendor/manifest.json', destination / 'vendor/manifest.json')
    count = 0
    for name, row in manifest['sources'].items():
        for rel, meta in row['files'].items():
            dst = destination / 'vendor' / name / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_root / name / rel, dst)
            os.chmod(dst, 0o755 if meta['mode'] == '100755' else 0o644)
            count += 1
    shutil.copy2(ROOT / 'assets/repository-readme.md', destination / 'README.md')
    (destination / 'assets/distribution.json').write_text(json.dumps({'mode': 'full', 'upstream_files': count}, indent=2) + '\n')
    print(json.dumps({'repository': str(destination), 'upstream_files': count, 'published': False}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc))
