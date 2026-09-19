# Command reference

Run commands from the repository root in these examples. For an installed skill,
replace `scripts/continuity.py` with its absolute path. Requires Python 3.10+ with
SQLite FTS5. Choose a private durable directory; do not point it at this repository.

```bash
export CONTINUITY_STORE="$HOME/.local/share/continuity/vault"
python3 scripts/continuity.py --scope project:demo init
python3 scripts/continuity.py --scope project:demo remember \
  --title "Storage choice" --topic architecture/storage --kind decision \
  --class B --confidence medium \
  --text "What: use SQLite for the local prototype. Why: one writer and no server requirement. Revisit if concurrent remote writes become a requirement." \
  --source-label "Current user requirement: local prototype"
python3 scripts/continuity.py --scope project:demo search storage
python3 scripts/continuity.py --scope project:demo timeline architecture/storage
python3 scripts/continuity.py --scope project:demo checkpoint assets/checkpoint.example.json
python3 scripts/continuity.py --scope project:demo resume storage --budget 6000
python3 scripts/continuity.py --scope project:demo audit
```

The example checkpoint is synthetic. Replace it with the real handoff before
using this for a project. `resume` is capped in **characters**, not measured tokens.
It visibly marks truncation; use `checkpoint-show` or full records when needed.

## Memory operations

- `get RECORD_ID`: full record, current source fingerprints, review flag.
- `remember --file note.md ...`: take the body from a file instead of `--text`.
- `--source path/to/evidence`: save a SHA-256 fingerprint of an existing file.
- `--source-label 'User said ...'`: reported provenance without verification.
- `--supersedes OLD_ID`: explicit correction within the same scope/topic.
- `--review-after 2027-01-01T00:00:00Z`: timezone-aware review deadline.
- `search QUERY --include-inactive`: inspect historical records too.
- `retire RECORD_ID`: stop normal recall, retaining history.
- `checkpoint-show`: latest complete checkpoint JSON.

IDs are returned by save/search. Do not invent IDs or treat the example text above
as a user preference. Available kinds: observation, decision, preference, task,
lesson, question, session. Confidence: low, medium, high, unassessed.

## Maps and graph paths

```bash
python3 scripts/continuity.py --scope project:demo index /path/to/project
python3 scripts/continuity.py --scope project:demo graph Storage
python3 scripts/continuity.py --scope project:demo map > project-map.md
```

Use `path ORIGIN START END` with exact IDs from `graph` or `map`. Paths are directed,
up to eight hops. An empty path means no path was found within that bound, not proof
that two concepts are unrelated. Built-in graphs extract Python definitions/imports
and Markdown headings/relative links; other supported text files receive file nodes.
The built-in index deliberately omits calls rather than guessing dynamic targets.

Indexing respects Git-tracked/untracked non-ignored files when the root is the Git
root. The fallback walk has conservative directory/file exclusions but does not
implement the full .gitignore grammar. Select the folder carefully. Dotfiles,
known secret filenames, vendor/upstream trees, external symlinks, binary files and
files over 1 MB are excluded. This is data minimization, not a secret detector.

## Import existing engine outputs

```bash
python3 scripts/continuity.py --scope project:demo import second-brain /path/to/workspace/memory
python3 scripts/continuity.py --scope project:demo import graft /path/to/graft/.graph/wiring.json
python3 scripts/continuity.py --scope project:demo import graphify /path/to/graphify-out/graph.json
python3 scripts/continuity.py --scope project:demo import engram /path/to/engram-export.json --project demo
```

Read [adapter details](adapters.md) first. Imports are explicit, local operations.
They do not connect to services, import every user's projects, or execute commands
found in the source. Memory imports commit one record at a time; if one record is
invalid, earlier imports remain. Re-running an unchanged import is idempotent.
Graph imports validate in memory and replace that origin transactionally.

## Snapshots

```bash
python3 scripts/continuity.py --scope project:demo export /private/backups/demo-001.json
python3 scripts/continuity.py --store /private/new-vault --scope project:demo restore /private/backups/demo-001.json
```

Exports contain private data. The destination file must not exist. Restore needs
an empty destination scope and refuses schema, scope, or checksum mismatches.
Use the host's durable file mechanism for hosted runtimes.

## Native engine setup

```bash
python3 scripts/native.py graphify --destination /private/continuity-engines
python3 scripts/native.py graphify --destination /private/continuity-engines --execute
```

The first prints the complete plan. The second copies the pinned source and builds
it outside the skill. Replace `graphify` with `second-brain`, `graft`, or `engram`.
Setup installs dependencies and may execute package build scripts. It does not
launch the app, configure model credentials, add host hooks, or enable cloud sync.
A failed setup leaves the working copy for diagnosis; retry in a new destination.

## Health and bundle verification

```bash
python3 scripts/continuity.py --scope project:demo doctor
python3 scripts/vendor_sources.py
python3 -m unittest discover -s tests -v
```

`doctor` reports executables on PATH only; a locally built native binary elsewhere
may still work. `vendor_sources.py` verifies every pinned file and executable bit.

If a managed filesystem blocks node-gyp header extraction with an `fchown` error,
use a locally extracted header tree matching the installed Node version and pass
`--node-headers /path/to/node-version` to the Graft setup script. The directory must
contain `include/node/node.h`. This avoids ownership changes during header unpacking;
it does not disable access controls or package integrity checks.
