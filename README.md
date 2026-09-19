# Continuity

**Persistent project continuity for Claude Code, Codex, and other coding agents.**

Continuity combines four ideas into one standalone, local-first skill:

- **Curated durable memory** — SQLite + FTS5, stable topic keys, deliberate saves instead of transcript hoarding.
- **Structural orientation** — a zero-dependency local code index with optional Graft/Graphify adapters for deeper code graphs.
- **Verified handoffs** — semantic checkpoints plus Git branch/HEAD/status/diffstat so a successor can distinguish what was said from what is actually in the tree.
- **Lifecycle restoration** — session-start, pre-compaction, and stop hooks where the host exposes them, plus `/continuity` as the operating protocol.

It is inspired by the strongest concepts in Second Brain, Graft, Graphify, session-handoff, and Engram while remaining independently implemented and usable without installing any of them.

## Architecture

A transcript is not memory. A code graph is not a handoff. A summary is not source truth. Continuity stores each kind of context separately and retrieves it according to the question.

```text
Agent session
   │
   ├─ /continuity protocol
   ├─ curated memory ─────── SQLite + FTS5 (~/.continuity/continuity.db)
   ├─ session/handoff ───── semantic checkpoint + Git evidence
   └─ project structure ─── local symbol/import graph
               ├─ optional Graft adapter
               └─ optional Graphify adapter
```

## Install

```bash
git clone https://github.com/kingju1c3/continuity
cd continuity
python3 -m pip install -e .
continuity install --agents claude,codex
continuity doctor
```

Python 3.11+ is the only required runtime dependency.

## Use

Inside a coding project:

```bash
continuity start --host codex --emit-context
continuity orient
continuity index
continuity recall "authentication decision"
continuity query "where is retry policy implemented?"
```

Save durable knowledge:

```bash
continuity remember   "Chose request-id idempotency"   "**What**: Reuse request id as idempotency key. **Why**: Prevent duplicate writes on retry. **Where**: upload handler. **Learned**: retries can race."   --kind decision   --topic architecture/idempotency
```

Before compaction or session end:

```bash
continuity checkpoint   --host codex   --goal "Finish upload retry hardening"   --accomplished "Added idempotency check and tests"   --next-steps "Run integration suite, inspect race path"   --relevant-files "src/upload.py tests/test_upload.py"   --verification "Unit tests pass; integration suite not yet run"
```

Next session:

```bash
continuity start --host codex --emit-context
continuity resume
```

## Commands

| Command | Purpose |
|---|---|
| `start` | Register a session and emit the previous handoff |
| `orient` | Project identity + latest handoff + recent durable memory |
| `remember` | Save/upsert curated memory |
| `recall` | FTS5 memory search |
| `index` | Rebuild local symbol/import graph |
| `find` | Find symbols/files |
| `graph` | Show neighboring import relationships |
| `query` | Prefer Graft/Graphify when available, else local structural search |
| `checkpoint` | Create semantic + Git-evidenced handoff |
| `resume` | Print the latest handoff in full |
| `install` | Wire Claude/Codex project integration |
| `doctor` | Verify store, adapters, and host wiring |
| `hook` | Lifecycle hook entry point used by integrations |

## Automatic continuity

Continuity can automatically register a session, recover the last handoff on a new session, and request a checkpoint on host lifecycle events. It cannot guarantee that every host can spawn a brand-new chat/session on its own, because that requires a host-specific supported control surface. Where no such control exists, Continuity performs the strongest portable behavior: checkpoint early, persist exact project state, and restore it automatically when the next session starts.

That distinction is intentional. Continuity never claims more continuity than the host can actually provide.

## Optional adapters

Continuity remains standalone. If either is installed, `continuity query` can use it:

- **Graft** for fast codebase orientation and code-specific context graphs.
- **Graphify** for persistent graph/path/concept queries, including richer cross-file relationships.

If neither exists, the built-in Python/regex index handles symbols and imports with no external dependency.

## Security and privacy

- Local by default; no network service is required.
- The database lives at `~/.continuity/continuity.db`.
- Repository mirrors under `.continuity/` are gitignored by the installer.
- Do not save credentials, secrets, API keys, or raw private transcripts as durable memories.

## Source synthesis

See `docs/SOURCES.md` for the concepts adopted from each source project and license notes.

## License

MIT.
