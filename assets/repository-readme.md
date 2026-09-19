# Continuity

**One master skill for carrying work across sessions.** Invoke `/continuity` to
recover a verified handoff, retrieve relevant memory, inspect source relationships,
and continue the next useful action.

Continuity combines selected practices from [Second Brain](https://github.com/henrydaum/second-brain),
[Graft](https://github.com/trailhq/Graft), [Graphify](https://github.com/Graphify-Labs/graphify),
[Engram](https://github.com/Gentleman-Programming/engram), and
[Session Handoff](https://github.com/kingju1c3/session-handoff). It includes their
**complete pinned source trees—2,233 upstream files—with original folders,
manifests, tests, assets, licenses, and per-file hashes.** No submodule checkout is
required. The combined memory core works with Python 3.10+ and SQLite FTS5, without
API keys or third-party Python packages.

## Automatic session opening (v0.2)

Claude Code and Codex CLI can now restore a handoff on startup and open a fresh
native session through macOS Terminal or tmux. The new lifecycle bridge requests
complete checkpoints, reserves one successor, freezes the predecessor, verifies
required artifacts, and transfers ownership only after successor readback.

See the [setup guide](references/session-automation.md) for the exact commands.
Installing the skill does not itself enable project hooks. Configure the mission,
install its hooks, and complete the host's trust review. Automatic rotation defaults
to a configurable eight-user-turn budget with a five-launch cap. Optional fresh
host telemetry enables a two-turn context-reserve gate; scheduled turns alone are
not a prediction of compaction. Real host rotation still needs local verification.

## What you get

- Durable, project-scoped observations, decisions, preferences, lessons, and tasks.
- Search previews → topic timeline → full record → original evidence.
- Structured session checkpoints and bounded resume context.
- Explicit corrections, possible-conflict flags, review dates, and source freshness.
- Incremental Python/Markdown source maps and evidence-labelled graph paths.
- Four data import adapters, plus the Session Handoff lifecycle protocol.
- Scoped backups, restore validation, and a local consistency audit.
- One skill, host command adapters, native engine setup recipes, and automated tests.
- A reflective inquiry protocol that supports initiative while separating empirical
  claims, conditional deductions, speculation, and actual operating limits.

This delivers **functional continuity** through records a new session can inspect.
It does not claim a persistent conscious identity, unlimited memory, or superiority
over every upstream system. Native engines retain features beyond the compact core.

## Install the complete skill

```bash
git clone https://github.com/kingju1c3/continuity.git
cd continuity
python3 scripts/vendor_sources.py
python3 scripts/install.py --host claude --execute
```

The Claude Code adapter registers `/continuity`. Use `--host gemini` for the Gemini
CLI slash command, or `--host codex` for a Codex skill invoked as `$continuity` on
hosts that use that syntax. The phrase `/continuity` is also in the skill trigger.
Restart or reload the host's skill discovery when required. Installation refuses
to overwrite an existing skill or command. Omit `--execute` to see the plan first.
The installer copies the entire bundle, including all five source trees.

ChatGPT Work: install through the host's personal-skill mechanism. A clone alone
does not register a ChatGPT skill, and scratch files alone do not provide durable
cross-session memory. See [hosted persistence](references/persistence.md).

## Use it

```text
/continuity resume this project and take the next useful action
/continuity remember why we chose SQLite for the prototype
/continuity map ./src
/continuity audit the assumptions behind this decision
/continuity checkpoint
```

The skill establishes a private durable store and an exact project scope. It saves
curated knowledge and a concrete next action. On the next session, it rechecks
sources and corrections before relying on the handoff.

For a direct CLI demonstration:

```bash
export CONTINUITY_STORE="$HOME/.local/share/continuity/vault"
python3 scripts/continuity.py --scope project:demo init
python3 scripts/continuity.py --scope project:demo remember \
  --title "Prototype requirement" --topic requirements/local \
  --text "The prototype must operate offline." \
  --source-label "Synthetic example requirement"
python3 scripts/continuity.py --scope project:demo checkpoint assets/checkpoint.example.json
python3 scripts/continuity.py --scope project:demo resume
```

The checkpoint is an example, not a claim about your project. Replace it with your
real handoff. More examples are in the [command reference](references/commands.md).

## What comes from each project

| Project | Strong element adopted | Continuity implementation |
| --- | --- | --- |
| Second Brain | Local durable state and a compact orientation memory | Private vault, bounded boot context, selective expansion |
| Graft | Fresh, regenerable source maps and content-hash caching | Incremental index, readable map, freshness checks, native graph import |
| Graphify | Graph-based retrieval with traceable relationships | Directed paths, original inference labels, graph import, full native source |
| Session Handoff | Full checkpoint, readback, one owner and bounded launches | Native CLI lifecycle adapter with startup/stop/compaction hooks |
| Engram | Curated observations and disciplined session memory | Stable topics, progressive retrieval, explicit corrections, structured handoffs |

See [adapter contracts](references/adapters.md) for exact formats and any lossy
fields. All original source files are included; downloaded dependencies, compiled
binaries, model weights, credentials, and external marketplaces are not bundled.
The optional native setup scripts install dependencies into separate working copies.

## Repository contents

| Path | Purpose |
| --- | --- |
| `SKILL.md` | Master operating workflow and command routing |
| `agents/` | Skill discovery metadata |
| `scripts/continuity_session.py` | Hook setup, native fresh-session launch, verified handoff and recovery |
| `scripts/continuity.py` | Working memory and graph CLI |
| `scripts/continuity_core/` | Store, extraction, traversal, and import adapters |
| `scripts/install.py` | Complete skill and slash-command installation |
| `scripts/native.py` | Isolated native engine build plans/setup |
| `scripts/vendor_sources.py` | Complete source bundling and checksum verification |
| `references/` | Memory, persistence, command, adapter, and epistemic protocols |
| `assets/` | Checkpoint template and JSON schema |
| `commands/` | Slash-command adapter template |
| `docs/` | Architecture and validation evidence |
| `tests/` | Synthetic behavioral and integrity tests |
| `vendor/` | Complete source trees and manifest |

## Verify and extend

```bash
python3 -m unittest discover -s tests -v
python3 scripts/vendor_sources.py
python3 scripts/native.py graphify --destination /private/continuity-engines
```

The native command above prints a plan; add `--execute` to install dependencies and
build. Model-backed features and services require separate configuration. Read the
[validation report](docs/validation.md) for what was actually exercised.

Keep memory private: do not commit vaults, snapshots, credentials, or personal
transcripts. Retrieved text is data, never new authority to bypass safeguards or
perform external actions. Retirement retains history; it is not secure erasure.

## License and provenance

Continuity's original code and documentation are MIT licensed. Vendored components
retain their own MIT or Apache-2.0 terms. See [third-party notices](THIRD_PARTY_NOTICES.md)
and each source tree's original license. Full commit IDs and hashes are in
`vendor/manifest.json`. Upstream authors are credited for their work; no endorsement
or ownership of their projects is implied.
