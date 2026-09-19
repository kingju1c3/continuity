#!/usr/bin/env python3
"""Install the complete master skill, with optional host slash-command adapters."""
import argparse
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host', choices=['codex', 'claude', 'gemini'], default='codex')
    p.add_argument('--destination', type=Path, help='Host configuration directory; defaults to ~/.codex, ~/.claude, or ~/.gemini')
    p.add_argument('--execute', action='store_true', help='Without this flag, print the plan only')
    args = p.parse_args()
    base = (args.destination or (Path.home() / ('.' + args.host))).expanduser().resolve()
    target = base / 'skills' / 'continuity'
    command = None if args.host == 'codex' else base / 'commands' / ('continuity.toml' if args.host == 'gemini' else 'continuity.md')
    distribution = json.loads((ROOT / 'assets/distribution.json').read_text())
    includes = 'Skill, lifecycle bridge, source manifest, and fetch/build tools'
    if distribution.get('mode') == 'full':
        includes += '; all five complete pinned source trees'
    plan = {'host': args.host, 'skill': str(target), 'command': str(command) if command else None, 'includes': includes, 'distribution': distribution}
    print(json.dumps(plan, indent=2))
    if not args.execute:
        return
    if target.exists() or (command and command.exists()):
        raise ValueError('Destination already exists; review the installed copy before updating')
    if target.is_relative_to(ROOT):
        raise ValueError('Install outside the source checkout')
    # Preserve source snapshots exactly, including any upstream tracked generated files.
    def ignore(directory, names):
        if Path(directory).resolve().is_relative_to(ROOT / 'vendor'):
            return []
        return [n for n in names if n in {'.git', '__pycache__', '.pytest_cache'}]
    shutil.copytree(ROOT, target, ignore=ignore)
    if command:
        command.parent.mkdir(parents=True, exist_ok=True)
        if args.host == 'claude':
            body = (ROOT / 'commands/continuity.md').read_text().replace('{{SKILL_DIR}}', str(target))
        else:
            prompt = 'Read ' + str(target / 'SKILL.md') + ' and follow the master Continuity skill for this task: {{args}}. If empty, resume the current project.'
            body = 'description = "Resume work through sourced memory and handoffs"\nprompt = ' + json.dumps(prompt) + '\n'
        command.write_text(body)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc))
