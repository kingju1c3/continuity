#!/usr/bin/env python3
"""Recover the exact full source trees for a compact host installation."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', required=True, type=Path, help='New private source-cache directory')
    parser.add_argument('--execute', action='store_true', help='Without this flag, print the exact clone plan only')
    args = parser.parse_args()
    destination = args.destination.expanduser().resolve()
    manifest = json.loads((ROOT / 'vendor/manifest.json').read_text())
    plan = {name: {'url': row['url'], 'commit': row['commit'], 'destination': str(destination / name)} for name, row in manifest['sources'].items()}
    print(json.dumps(plan, indent=2), flush=True)
    if not args.execute:
        return
    if destination.exists() or destination.is_relative_to(ROOT):
        raise ValueError('Choose a new source cache outside the installed skill')
    destination.mkdir(parents=True)
    for name, row in manifest['sources'].items():
        target = destination / name
        subprocess.run(['git', 'init', '--quiet', str(target)], check=True, timeout=30)
        subprocess.run(['git', '-C', str(target), 'remote', 'add', 'origin', row['url']], check=True, timeout=30)
        subprocess.run(['git', '-C', str(target), 'fetch', '--depth', '1', 'origin', row['commit']], check=True, timeout=600)
        subprocess.run(['git', '-C', str(target), 'checkout', '--detach', row['commit']], check=True, timeout=600)
        names = set(subprocess.check_output(['git', '-C', str(target), 'ls-files', '-z']).decode().strip('\0').split('\0'))
        if names != set(row['files']):
            raise ValueError('Tracked file set does not match pin: ' + name)
        for rel, expected in row['files'].items():
            p = target / rel
            if not p.is_file() or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest() != expected['sha256']:
                raise ValueError('Source verification failed: ' + name + '/' + rel)
        print('Verified', name, row['file_count'], 'files', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        raise SystemExit(str(exc))
