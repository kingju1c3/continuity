<!--
  Continuity
  Persistent project context for coding agents
-->

<p align="center">
  <img
    src="https://d2ol7oe51mr4n9.cloudfront.net/user_311XgUsRBKFoeOtsydaPHNvNFQv/e98b7dae-0925-4566-af97-02f99d95f2bf.jpg"
    alt="Continuity — persistent context for coding agents"
    width="100%"
  />
</p>

<h1 align="center">Continuity</h1>

<p align="center">
  <strong>Persistent project continuity for Claude Code, Codex, and other coding agents.</strong>
</p>

<p align="center">
  Memory · Structure · Handoffs · Recovery
</p>

<p align="center">
  <a href="https://github.com/kingju1c3/continuity/actions/workflows/test.yml"><img alt="Tests" src="https://img.shields.io/github/actions/workflow/status/kingju1c3/continuity/test.yml?branch=main&style=flat-square&label=tests"></a>
  <a href="https://www.python.org/"><img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white"></a>
  <a href="LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/license-MIT-2ea44f?style=flat-square"></a>
  <img alt="Local first" src="https://img.shields.io/badge/storage-local--first-7c3aed?style=flat-square">
  <img alt="SQLite + FTS5" src="https://img.shields.io/badge/memory-SQLite%20%2B%20FTS5-0f766e?style=flat-square">
  <img alt="Claude Code" src="https://img.shields.io/badge/Claude%20Code-supported-D97757?style=flat-square">
  <img alt="Codex" src="https://img.shields.io/badge/Codex-supported-111827?style=flat-square">
</p>

---

## What is Continuity?

Coding agents are powerful inside a session, but sessions end, contexts compact, terminals restart, branches move, and the next agent often has to reconstruct work from scratch.

**Continuity is a local-first continuity layer for coding agents.** It gives a project a durable record of the things that should survive between sessions without pretending that a transcript is the same thing as memory or that a summary is the same thing as source truth.

Continuity separates project context into four different layers:

| Layer | Question it answers | Backing state |
| --- | --- | --- |
| **Durable memory** | “What did we decide or learn?” | SQLite + FTS5 |
| **Structural context** | “Where is this implemented and how is it connected?” | Local code index, optionally Graft / Graphify |
| **Handoff state** | “What was done, what remains, and what should the successor do next?” | Semantic checkpoint + Git evidence |
| **Current truth** | “What is actually true right now?” | Current source tree + Git |

The goal is not to manufacture artificial “perfect memory.” The goal is to make session-to-session recovery **fast, explicit, inspectable, and evidence-backed**.

> **Current source and Git state always outrank stale memory.**

---

## Why Continuity exists

A normal coding-agent workflow tends to break in predictable ways:

- the next session does not know what the previous session already tried;
- decisions get rediscovered repeatedly;
- context compaction drops details that mattered;
- summaries claim work is finished when the tree says otherwise;
- a new agent reads half the repository before finding the relevant files;
- raw transcripts grow forever but become worse at retrieval;
- architecture knowledge, user preferences, implementation details, and session state are mixed into one undifferentiated blob.

Continuity addresses those failures by giving each kind of state a different lifetime and authority.

```text
                            ┌────────────────────────────┐
                            │       CURRENT SOURCE       │
                            │        + Git state         │
                            │     highest authority      │
                            └─────────────┬──────────────┘
                                          │
                              verify / reconcile
                                          │
             ┌────────────────────────────┼────────────────────────────┐
             │                            │                            │
             ▼                            ▼                            ▼
    ┌────────────────┐          ┌──────────────────┐        ┌──────────────────┐
    │ DURABLE MEMORY │          │ STRUCTURAL INDEX │        │ SESSION HANDOFF  │
    │ SQLite + FTS5  │          │ symbols + edges  │        │ semantic + Git   │
    └────────────────┘          └──────────────────┘        └──────────────────┘
             │                            │                            │
             └────────────────────────────┴────────────────────────────┘
                                          │
                                          ▼
                                ┌──────────────────┐
                                │  NEXT AI SESSION │
                                │ orient → verify  │
                                │ → continue       │
                                └──────────────────┘
```

---

## Premium continuity runtime — v0.3

Continuity v0.3 changes the operating model from **active per-turn assistance** to **arm once, stay passive, transfer at the compaction boundary**.

Invoke `/continuity` once in the session. The skill arms the exact current host session, then gets out of the way.

```text
/continuity
    │
    ▼
arm exact session
    │
    ├──────── normal prompts/tools ────────┐
    │             silent                  │
    │                                     │
    └───────────────┬─────────────────────┘
                    ▼
              host PreCompact
                    │
          alert user BEFORE loss
                    │
          durable boundary handoff
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
 Claude local             Codex local
 background named         background persisted
 successor session        codex exec thread
        │                       │
        └───────────┬───────────┘
                    ▼
           successor verifies
          source/Git + resumes
```

### What “passive” means

After arming:

- no memory dump on every prompt;
- no checkpoint nag after every turn;
- no visible PostToolUse chatter;
- edits silently mark structural state stale;
- durable memory remains available on demand;
- the runtime waits for the host's documented **PreCompact** event.

The host APIs do not expose one portable, stable live “N% until compaction” field on every turn, so Continuity does **not** fabricate one. PreCompact is the reliable lifecycle boundary immediately before compaction.

### Boundary alert and handoff

At an armed PreCompact event, Continuity:

1. alerts the user that compaction is about to occur;
2. emits a terminal notification/bell where supported;
3. writes a mechanical freeze;
4. rebuilds structural state;
5. writes an `automatic-boundary` handoff;
6. records branch, HEAD, worktree, diffstat, changed files, arm goal/instructions, bounded durable memory, and a bounded best-effort transcript tail;
7. redacts common secret patterns from transcript evidence;
8. persists `.continuity/LATEST.md` and `.continuity/LATEST.json`;
9. transfers ownership only after the handoff is durable;
10. blocks that compaction attempt so the predecessor context is not destroyed first.

### Automatic successor creation

**Claude Code:** when the local Claude CLI is available, Continuity starts a fresh named background session and tells you exactly how to attach:

```bash
claude --resume <continuity-successor-name>
```

**Codex:** when the local Codex CLI is available, Continuity starts a fresh persisted **read-only background bootstrap thread** with `codex exec --json`, captures its `thread.started` ID when available, and tells you how to attach interactively:

```bash
codex resume <successor-thread-id>
```

The Codex bootstrap only verifies the handoff/source; it is not launched with workspace-write permissions.

If either executable is unavailable, Continuity preserves the handoff and falls back safely rather than claiming a successor was created.

### Arm/disarm controls

```bash
continuity arm \
  --host auto \
  --goal "Finish retry-safe upload handling" \
  --instructions "Preserve the public API"

continuity status
continuity disarm
```

Use `--no-auto-successor` to keep the boundary alert/handoff while requiring a manual fresh-session launch.

### Ownership safety

Continuity keeps one active project lease. A successful transfer marks the predecessor `transferred`; later prompts in that predecessor can be blocked so two sessions do not unknowingly continue the same chain.

Arm state survives an ordinary session exit/resume. The lease is released on exit, while the saved session remains armed when resumed.


---

## Core capabilities

### 1. Curated persistent memory

Continuity stores reusable project knowledge in a local SQLite database with FTS5 full-text search.

Good memories include:

- architecture decisions;
- user-confirmed conventions;
- non-obvious bug root causes;
- configuration decisions;
- known gotchas;
- implementation constraints;
- decisions that would be expensive to rediscover.

Continuity is deliberately **not** a transcript sink. Save knowledge that has future value, not every interaction.

Stable topic keys make evolving knowledge update in place:

```bash
continuity remember \
  "Authentication model" \
  "**What**: Session cookies replace JWT access tokens.
**Why**: Server-side revocation is required.
**Where**: src/auth/, middleware/session.py
**Learned**: Mobile clients still use the refresh endpoint." \
  --kind architecture \
  --topic architecture/auth-model
```

Calling `remember` later with the same `--topic` updates that topic instead of creating competing copies.

---

### 2. Structural code orientation

Continuity includes a dependency-free local project index.

The built-in index:

- walks supported source/text files;
- uses Python AST parsing for Python symbols and imports;
- uses conservative patterns for symbols/imports in common languages;
- records file metadata, symbols, and import relationships;
- keeps project indexes scoped to the detected project identity.

Supported file extensions currently include:

```text
.py  .js  .jsx  .ts  .tsx  .go  .rs  .java  .kt
.rb  .php .md   .toml .yaml .yml .json
```

Build or refresh the local index:

```bash
continuity index
```

Find a symbol:

```bash
continuity find "RetryPolicy"
```

Inspect structural neighbors:

```bash
continuity graph "src/upload.py"
```

Ask a structural question:

```bash
continuity query "where is retry policy implemented?"
```

If Graft or Graphify are available, Continuity can delegate deeper structural queries to them. Otherwise it falls back to its built-in index.

---

### 3. Evidence-backed session handoffs

A handoff is not just a prose summary.

Continuity captures both:

**Semantic state**
- goal;
- instructions and constraints;
- discoveries;
- accomplished work;
- next steps;
- relevant files;
- verification status.

**Mechanical Git state**
- project root;
- current branch;
- HEAD commit;
- working-tree status;
- diffstat.

Example:

```bash
continuity checkpoint \
  --host codex \
  --goal "Finish retry-safe upload handling" \
  --instructions "Preserve backwards-compatible API behavior" \
  --discoveries "Duplicate rows occur when client retries race" \
  --accomplished "Added request-id idempotency guard and unit tests" \
  --next-steps "Run integration suite; inspect concurrent retry path" \
  --relevant-files "src/upload.py tests/test_upload.py" \
  --verification "Unit tests pass; integration suite not yet run"
```

Continuity writes the handoff to the local database and mirrors an inspectable copy under:

```text
.continuity/
├── LATEST.md
├── LATEST.json
└── handoffs/
    └── <timestamp>-<session>.md
```

The installer makes that repository-local continuity state gitignored by default.

---

### 4. Session restoration

Installed host hooks register exact session identity automatically. The preferred successor flow is therefore:

```bash
continuity resume
continuity orient
continuity status
```

A successor created/staged by the passive boundary protocol also inherits the pending goal and constraints. It must still verify the handoff against current source and Git state before making edits.

`continuity start --emit-context` remains available for manual or unsupported-host workflows, but it is not required for normal installed Claude/Codex sessions.

---

### 5. Claude Code and Codex lifecycle integration

Install host integration:

```bash
continuity install --agents claude,codex
```

#### Claude Code

Claude receives only minimal project-global bookkeeping hooks:

- `SessionStart` — exact session identity + lease bookkeeping;
- `SessionEnd` — objective freeze + lease release.

The expensive/session-specific hooks live in the installed `/continuity` skill itself. After the skill is invoked, its hook set remains active for that session:

- `UserPromptSubmit` — normally silent; blocks a transferred predecessor;
- `PostToolUse` — silently marks structure stale;
- `PreCompact` — alert, capture handoff, launch/transfer successor;
- `PostCompact` — recovery evidence if compaction still occurs.

The installer rewrites the skill hook command to the exact Python interpreter that installed Continuity, avoiding PATH-dependent hook failures.

#### Codex

Codex lifecycle dispatch hooks are installed in `~/.codex/hooks.json` when available, but expensive behavior is **arm-gated**. Unarmed project sessions are effectively no-op beyond session bookkeeping.

Installed dispatchers include:

- `SessionStart`;
- `UserPromptSubmit`;
- `PostToolUse`;
- `PreCompact`;
- `PostCompact`;
- `SessionEnd`.

There is intentionally no per-turn Stop nag.

At the boundary, Continuity can automatically create a persisted non-interactive Codex successor thread without pretending that a hook can open an interactive terminal window.


---

## Quick start

### Requirements

- Python **3.11+**
- Git is strongly recommended because project identity and handoff verification use Git when available.

No database server, Docker daemon, Node runtime, vector database, cloud account, or API key is required for the core runtime.

### Option A — install directly from GitHub

```bash
python3 -m pip install "git+https://github.com/kingju1c3/continuity.git"
```

### Option B — clone for development

```bash
git clone https://github.com/kingju1c3/continuity.git
cd continuity

python3 -m venv .venv
source .venv/bin/activate      # macOS / Linux
# .venv\Scripts\activate     # Windows PowerShell

python -m pip install -e .
```

### Wire Continuity into a project

After installing the CLI, change into the project where you want continuity:

```bash
cd /path/to/your/project
continuity install --agents claude,codex
continuity index
continuity doctor
```

For only one host:

```bash
continuity install --agents claude
```

or:

```bash
continuity install --agents codex
```

### First armed session

In Claude Code or Codex, invoke:

```text
/continuity
```

The skill's first action arms the exact host session. For manual use:

```bash
continuity arm --host auto --goal "Current objective" --instructions "Critical constraints"
```

Then work normally. Continuity stays passive until PreCompact. Use `continuity status` at any time to inspect arm/lease/successor state.

### Intentional early handoff

You do **not** need a checkpoint at every ordinary session turn or stop. If you want to transfer intentionally before PreCompact, create a richer semantic checkpoint:

```bash
continuity checkpoint \
  --host codex \
  --goal "Implement account lockout" \
  --accomplished "Added lockout state and unit tests" \
  --next-steps "Wire metrics and run full auth integration tests" \
  --relevant-files "src/auth/lockout.py tests/test_lockout.py" \
  --verification "Unit tests passing"
```

### Successor session

The boundary alert gives the attach/resume command. Once attached, verify:

```bash
continuity resume
continuity orient
continuity status
```

Then continue from the first unresolved next step only after reconciling the handoff with the current tree.

---

## Recommended daily workflow

A normal armed workflow is intentionally quiet.

### Arm once

In Claude Code or Codex:

```text
/continuity
```

The skill immediately binds itself to the exact current host session. Manual equivalent:

```bash
continuity arm \
  --host auto \
  --goal "Current objective" \
  --instructions "Constraints that must survive transfer"
```

Confirm when useful:

```bash
continuity status
```

### Work normally

Continuity should not narrate itself during ordinary turns. It silently records edit freshness while armed.

Use durable memory only when it saves future rediscovery:

```bash
continuity recall "rate limiting"

continuity remember \
  "Use exponential backoff for billing retries" \
  "**What**: Retry schedule is 1s, 2s, 4s, 8s with jitter.
**Why**: Reduce synchronized retries against provider.
**Where**: billing/retry.py
**Learned**: Provider Retry-After wins when present." \
  --kind decision \
  --topic billing/retry-policy
```

Use structural retrieval when needed:

```bash
continuity query "where does billing retry logic live?"
continuity find "BillingRetry"
continuity graph "billing"
```

### At the compaction boundary

No manual polling is required. When the host emits `PreCompact`, an **armed** session automatically:

1. alerts you before compaction;
2. captures the durable automatic-boundary handoff;
3. refreshes structural state;
4. transfers ownership;
5. creates or stages a fresh successor;
6. blocks the predecessor compaction attempt so the transfer happens before context loss.

For Claude, attach to the named successor shown in the alert:

```bash
claude --resume <continuity-successor-name>
```

For Codex, attach to the persisted successor thread shown in the alert:

```bash
codex resume <successor-thread-id>
```

### Optional explicit transfer

If you intentionally want to hand off **before** compaction, create a richer semantic checkpoint:

```bash
continuity checkpoint \
  --goal "..." \
  --instructions "..." \
  --discoveries "..." \
  --accomplished "..." \
  --next-steps "..." \
  --relevant-files "..." \
  --verification "..."
```

Disable passive transfer at any time:

```bash
continuity disarm
```

The operating model is:

```text
INVOKE → ARM → WORK QUIETLY → PRECOMPACT ALERT → CAPTURE → FRESH SUCCESSOR → VERIFY → CONTINUE
```

---

## Installation in detail

### Installing into the Python environment

The package name is `continuity-ai`; the CLI command is `continuity`.

Check that the executable is available:

```bash
continuity --help
```

If your shell cannot find it, confirm the Python environment that received the installation:

```bash
python3 -m pip show continuity-ai
python3 -m continuity --help
```

The module entrypoint works even when the console-script directory is not on `PATH`:

```bash
python3 -m continuity doctor
```

### Project-scoped installation

Run host installation **from the target project root**, not from the Continuity repository unless the Continuity repository itself is the project you want to wire.

```bash
cd ~/code/my-project
continuity install --agents claude,codex
```

Continuity resolves the Git toplevel when possible, so calling it from a nested project directory still scopes operations to the repository root.

### Pointing at another project explicitly

Every command accepts a global `--path` option. Because it is a global argument, place it **before** the subcommand:

```bash
continuity --path ../another-project orient
continuity --path ../another-project index
continuity --path ../another-project recall "auth"
```

### Upgrading

Direct GitHub install:

```bash
python3 -m pip install --upgrade "git+https://github.com/kingju1c3/continuity.git"
```

Editable clone:

```bash
cd /path/to/continuity
git pull
python3 -m pip install -e .
```

After upgrading the package, rerun host installation inside projects where you want copied skill text / hooks refreshed:

```bash
cd /path/to/project
continuity install --agents claude,codex
```

---

## Command reference

The CLI is intentionally small and composable.

### `continuity arm`

Arm passive compaction-boundary continuity for the exact active host session.

```bash
continuity arm \
  [--host auto|claude|codex|manual] \
  [--session SESSION_ID] \
  [--goal TEXT] \
  [--instructions TEXT] \
  [--no-auto-successor]
```

`--host auto` is preferred inside an installed host because it derives the host from the active session lease. A mismatched host/session is rejected rather than silently rebound.

After arming, ordinary turns are passive. `--no-auto-successor` preserves the boundary alert and handoff but stages a manual fresh-session transfer.

---

### `continuity disarm`

Disable passive boundary transfer for the active session.

```bash
continuity disarm [--session SESSION_ID]
```

---
### `continuity start`

Manually register a session and optionally print restoration context. Installed Claude/Codex workflows normally get exact session identity from host hooks, so this is a fallback/manual command rather than the preferred way to arm `/continuity`.

```bash
continuity start [--host HOST] [--session SESSION_ID] [--emit-context]
```

Examples:

```bash
continuity start --host claude --emit-context
continuity start --host codex --session my-session --emit-context
```

If `--session` is omitted, Continuity uses `CONTINUITY_SESSION_ID` when present or creates a generated ID.

---

### `continuity orient`

Show the current project identity and high-value continuity state.

```bash
continuity orient
```

Output includes:

- detected project root;
- branch;
- HEAD;
- latest handoff when available;
- recent durable memories;
- optional adapter detection.

Use this near the beginning of a session.

---

### `continuity remember`

Save durable project knowledge.

```bash
continuity remember TITLE [CONTENT] \
  [--kind KIND] \
  [--topic TOPIC_KEY] \
  [--session SESSION_ID] \
  [--pin]
```

Example:

```bash
continuity remember \
  "Chose Postgres advisory locks" \
  "**What**: Use transaction-scoped advisory locks for settlement.
**Why**: Settlement workers can race across processes.
**Where**: settlement/worker.py
**Learned**: Lock key must be stable across retries." \
  --kind architecture \
  --topic settlement/concurrency
```

If content is omitted, Continuity reads it from stdin:

```bash
cat decision.md | continuity remember "Settlement concurrency" --kind decision
```

#### Suggested `--kind` values

The CLI accepts a string rather than a closed enum, but these conventions work well:

```text
decision
architecture
bugfix
discovery
pattern
config
preference
constraint
```

---

### `continuity recall`

Search durable memory using FTS5.

```bash
continuity recall [QUERY] [--limit N]
```

Examples:

```bash
continuity recall "authentication"
continuity recall "retry policy" --limit 12
```

An empty query returns recent memories.

Search results are historical evidence, not current source truth.

---

### `continuity index`

Rebuild the project's local structural index.

```bash
continuity index
```

The command prints counts for indexed files, symbols, and edges.

Run it:

- after initial installation;
- after meaningful source restructuring;
- before creating an architecture-heavy handoff;
- when structural search appears stale.

---

### `continuity find`

Find indexed symbols or symbol-associated paths.

```bash
continuity find TERM [--limit N]
```

Example:

```bash
continuity find "SessionManager"
```

---

### `continuity graph`

Show import relationships neighboring a node/path/module substring.

```bash
continuity graph NODE [--limit N]
```

Example:

```bash
continuity graph "auth"
```

Output format:

```text
src/file.py -[imports]-> package.module (src/file.py:12)
```

---

### `continuity query`

Ask a structural question.

```bash
continuity query "QUESTION" [--limit N]
```

Example:

```bash
continuity query "where is token refresh implemented?"
```

Resolution order:

1. Graft, when the `graft` executable is available;
2. Graphify, when `graphify` is available and `graphify-out/graph.json` exists;
3. Continuity's built-in structural index.

The adapters are optional. Continuity remains functional without them.

---

### `continuity checkpoint`

Create a successor-ready handoff.

```bash
continuity checkpoint \
  [--session SESSION_ID] \
  [--host HOST] \
  [--goal TEXT] \
  [--instructions TEXT] \
  [--discoveries TEXT] \
  [--accomplished TEXT] \
  [--next-steps TEXT] \
  [--relevant-files TEXT] \
  [--verification TEXT]
```

Recommended example:

```bash
continuity checkpoint \
  --host claude \
  --goal "Replace synchronous export path with queued jobs" \
  --instructions "Keep current API response schema stable" \
  --discoveries "Large exports time out behind the reverse proxy" \
  --accomplished "Added queue model, worker, and unit tests" \
  --next-steps "Add migration; run integration suite; verify cancellation" \
  --relevant-files "src/export/jobs.py src/export/worker.py tests/export/" \
  --verification "New unit tests pass; migration not tested"
```

A strong checkpoint tells the successor not only **what happened**, but also **what is still uncertain**.

---

### `continuity resume`

Print the latest project handoff in full.

```bash
continuity resume
```

Use after a session transition, context reset, or handoff.

---

### `continuity install`

Install host-specific project integration.

```bash
continuity install --agents claude,codex
```

Examples:

```bash
continuity install --agents claude
continuity install --agents codex
continuity install --agents claude,codex
```

---

### `continuity doctor`

Inspect the active project and installation.

```bash
continuity doctor
```

It reports:

- Python version;
- detected project;
- database path;
- SQLite FTS5 availability;
- Graft detection;
- Graphify detection;
- Claude skill installation;
- Codex skill installation;
- `AGENTS.md` presence.

Use it as the first troubleshooting command.

---

### `continuity hook`

Internal lifecycle entrypoint used by host integrations.

```bash
continuity hook --host claude
continuity hook --host codex
```

Most users should not call this manually.

---

## Memory model

Continuity's memory model follows one rule:

> **Persist conclusions and durable context, not the entire path taken to reach them.**

### Strong memory

```markdown
**What**: Payment retries use provider Retry-After, otherwise exponential backoff.
**Why**: Avoid provider throttling and retry storms.
**Where**: src/payments/retry.py
**Learned**: Retry-After can be an HTTP date, not only integer seconds.
```

### Weak memory

```text
We looked at a bunch of files and then tried several things.
```

### Topic keys

Use topic keys when a fact can evolve:

```text
architecture/auth-model
billing/retry-policy
config/test-runner
deployment/runtime
ui/design-system
```

Use a new memory without a topic key for distinct historical events that should coexist.

### Pinning

Use `--pin` for especially important project constraints:

```bash
continuity remember \
  "Never break v1 response schema" \
  "Public clients still consume v1; additive changes only." \
  --kind constraint \
  --topic api/v1-compatibility \
  --pin
```

Pinned memories are prioritized in retrieval ordering.

---

## Handoff protocol

A Continuity handoff should let a competent successor resume without replaying the entire previous session.

### Minimum useful handoff

At minimum, capture:

1. **Goal** — what the session was trying to accomplish.
2. **Instructions / constraints** — requirements that must survive.
3. **Discoveries** — non-obvious facts discovered during work.
4. **Accomplished** — completed work, with enough specificity to verify it.
5. **Next steps** — ordered unresolved work.
6. **Relevant files** — files the successor should inspect first.
7. **Verification** — tests/checks actually run and anything still unverified.

Continuity adds Git evidence mechanically.

### Successor checklist

Before editing:

1. restore the latest handoff;
2. confirm the project root;
3. compare current branch and HEAD with the handoff;
4. inspect working-tree changes;
5. verify relevant files still exist and match expectations;
6. surface any mismatch;
7. continue from the first unresolved action.

This prevents a stale summary from silently overriding a changed repository.

---

## Project identity

Continuity resolves the current project as:

1. the Git repository toplevel when available;
2. otherwise the resolved working directory.

The project key is derived from the canonical root and configured `remote.origin.url`.

That means memories, sessions, handoffs, symbols, and edges are project-scoped rather than mixed globally.

---

## Storage layout

### User-level durable database

```text
~/.continuity/
└── continuity.db
```

The database contains:

- projects;
- sessions;
- durable memories;
- FTS5 index;
- handoff payloads;
- indexed files;
- symbols;
- structural edges.

### Repository-local handoff mirror

```text
<project>/.continuity/
├── .gitignore
├── LATEST.md
├── LATEST.json
├── handoffs/
└── successors/        # Codex bootstrap JSONL logs when used
```

The repository mirror is there for inspectability and local recovery. The installer configures it so generated continuity state is not committed by default.

---

## Optional adapters

Continuity is designed to stand alone, but it can use specialized structural systems when they are already installed.

### Graft

Repository: [trailhq/Graft](https://github.com/trailhq/Graft)

When `graft` is available, `continuity query` tries Graft first for code-oriented structural retrieval.

Continuity does not require Graft and does not vendor it.

### Graphify

Repository: [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify)

When `graphify` is available **and** the current repository contains:

```text
graphify-out/graph.json
```

Continuity can use `graphify query` for graph-first retrieval.

Again, Graphify is optional.

---

## Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                         CODING AGENT                            │
│             Claude Code · Codex · shell-capable agent          │
└──────────────┬──────────────────┬──────────────────┬────────────┘
               │                  │                  │
               ▼                  ▼                  ▼
        ┌────────────┐      ┌─────────────┐    ┌──────────────┐
        │  SESSION   │      │   MEMORY    │    │  STRUCTURE   │
        │ lifecycle  │      │ SQLite/FTS5 │    │ local index  │
        └──────┬─────┘      └──────┬──────┘    └──────┬───────┘
               │                   │                   │
               │                   │              ┌────┴─────┐
               │                   │              │ adapters │
               │                   │              │Graft/Graphify
               │                   │              └────┬─────┘
               └──────────────┬────┴───────────────────┘
                              ▼
                     ┌─────────────────┐
                     │    HANDOFF      │
                     │ semantic state  │
                     │ + Git evidence  │
                     └────────┬────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │ NEXT SESSION    │
                     │ restore/verify  │
                     └─────────────────┘
```

### Authority hierarchy

When two sources disagree, use this order:

1. **Current source and Git state**
2. **Fresh structural evidence**
3. **Durable project memory**
4. **Historical handoff prose**

The point of continuity is to reduce rediscovery, not freeze the repository in the past.

For a deeper explanation, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Security and privacy

Continuity is local-first.

Core operation does not require:

- an external API;
- cloud storage;
- telemetry service;
- vector database;
- hosted memory server.

Security guidelines:

- **Do not store secrets** in `continuity remember`.
- Do not persist API keys, credentials, auth cookies, private keys, or tokens.
- Automatic transcript-tail evidence applies common-pattern redaction, but redaction is best-effort; avoid putting secrets in prompts.
- Treat handoffs as project metadata that may contain sensitive implementation context.
- The user-level SQLite database inherits the security of the local user account and filesystem.
- Review host configuration changes when installing into shared machines or shared repositories.
- Current source remains authoritative; memory is not an execution policy.

---

## What Continuity does not claim

Continuity deliberately avoids several misleading claims.

It does **not** claim:

- perfect memory;
- model consciousness or identity persistence;
- lossless replay of every prior token;
- the ability to force every host UI to open a new interactive window;
- that historical memory is more authoritative than current code;
- that a machine-captured boundary handoff is equivalent to a human/agent-authored semantic checkpoint;
- that the built-in index is a full semantic code intelligence engine.

It provides a practical, inspectable approximation of continuity from durable state.

---

## Troubleshooting

### `continuity: command not found`

Check installation:

```bash
python3 -m pip show continuity-ai
python3 -m continuity --help
```

If the module command works but `continuity` does not, your Python scripts directory is probably not on `PATH`.

---

### FTS5 reports unavailable

Run:

```bash
continuity doctor
```

Continuity uses Python's SQLite build. Most standard Python distributions include FTS5, but some custom/minimal SQLite builds may not.

Memory search has a LIKE-based fallback for query failures, but full-text relevance requires FTS5.

---

### Structural search returns nothing

Refresh the index:

```bash
continuity index
```

Then inspect a known symbol:

```bash
continuity find "KnownSymbol"
```

Remember that the built-in index is intentionally conservative. Install/use Graft or Graphify if you need richer code-graph semantics.

---

### No previous handoff appears

Check:

```bash
continuity orient
continuity resume
```

If the result says no handoff exists, a semantic checkpoint was not recorded for that project yet.

---

### Claude/Codex integration does not appear active

Run:

```bash
continuity doctor
```

Then rerun installation from the project:

```bash
continuity install --agents claude,codex
```

Restart the coding agent after changing host configuration.

---

### Wrong project detected

Inspect the root:

```bash
git rev-parse --show-toplevel
continuity doctor
```

Or explicitly target the intended project:

```bash
continuity --path /absolute/path/to/project orient
```

---

## Development

Clone and install editable:

```bash
git clone https://github.com/kingju1c3/continuity.git
cd continuity

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Run the test suite:

```bash
python -m unittest discover -s tests -v
```

Compile-check the package:

```bash
python -m compileall -q continuity
```

CLI smoke test:

```bash
python -m continuity --path . index
python -m continuity --path . doctor
```

CI currently exercises supported Python versions through GitHub Actions.

---

## Repository layout

```text
continuity/
├── .github/
│   └── workflows/
│       └── test.yml
├── continuity/
│   ├── __init__.py
│   ├── __main__.py
│   ├── adapters.py
│   ├── boundary.py        # passive arm + boundary handoff + successor launch
│   ├── cli.py
│   ├── context.py
│   ├── handoff.py
│   ├── hooks.py
│   ├── indexer.py
│   ├── install.py
│   ├── project.py
│   ├── store.py
│   ├── SKILL.md
│   ├── protocol/
│   │   ├── passive-mode.md
│   │   ├── compaction.md
│   │   ├── successor-transfer.md
│   │   ├── session-open.md
│   │   ├── checkpoint-handoff.md
│   │   ├── retrieval.md
│   │   ├── memory-write.md
│   │   ├── conflict-recovery.md
│   │   └── security.md
│   └── schemas/
│       ├── arm.schema.json
│       ├── checkpoint.schema.json
│       ├── memory.schema.json
│       └── session.schema.json
├── docs/
│   ├── ARCHITECTURE.md
│   ├── HOSTS.md
│   ├── MEMORY_PROTOCOL.md
│   └── SOURCES.md
├── tests/
│   ├── test_arm_cli.py
│   ├── test_boundary.py
│   ├── test_handoff.py
│   ├── test_hooks.py
│   ├── test_indexer.py
│   ├── test_install.py
│   ├── test_premium.py
│   └── test_store.py
├── LICENSE
├── README.md
├── SKILL.md
└── pyproject.toml
```

---

## Design lineage

Continuity synthesizes architectural ideas from several strong projects while remaining independently implemented.

| Project | Idea Continuity draws from |
| --- | --- |
| [Second Brain](https://github.com/henrydaum/second-brain) | local-first modular agent architecture and separated capabilities |
| [Graft](https://github.com/trailhq/Graft) | compact codebase orientation and host-aware integration |
| [Graphify](https://github.com/Graphify-Labs/graphify) | graph-first structural exploration |
| [session-handoff](https://github.com/kingju1c3/session-handoff) | explicit predecessor/successor contracts and evidence-backed transfer |
| [Engram](https://github.com/Gentleman-Programming/engram) | curated persistent memory, SQLite/FTS5, stable topic keys |

The organizing principle is simple:

> **Memory answers what we learned. Structure answers where it lives. Git answers what is true now. Handoff answers what comes next.**

See [docs/SOURCES.md](docs/SOURCES.md) for attribution and synthesis notes.

---

## FAQ

### Is Continuity a vector database?

No. The core memory layer uses SQLite + FTS5. The built-in structure layer stores explicit symbols and import edges.

### Does it send my code to a cloud service?

Not for core operation. Optional external tools you independently install may have their own behavior and policies.

### Does it work without Graft or Graphify?

Yes. Both are optional adapters.

### Does it replace Git?

No. Git is part of the verification layer. Continuity complements Git with semantic session state and durable project memory.

### Does it replace an agent's native memory?

No. It gives the project an explicit, local, inspectable continuity substrate that does not depend on a single model provider's memory behavior.

### Can I use it with another coding agent?

Yes, manually, as long as that environment can execute shell commands. Automatic lifecycle wiring is currently implemented for Claude Code and Codex.

### Will it automatically create a fresh Claude/Codex successor before compaction?

When `/continuity` is armed and the local CLI is available, **yes at the reliable `PreCompact` boundary**: Claude gets a fresh named background session; Codex gets a fresh persisted read-only `codex exec --json` bootstrap thread. Continuity cannot force the host UI to open a new interactive window, so you attach to the prepared successor with the resume command shown in the alert. If the host executable is unavailable, the durable handoff is preserved and the successor is staged for manual launch.

### Why not store the full transcript?

Because transcript volume and durable knowledge are different problems. Continuity optimizes for future retrieval and verification, not archival completeness.

---

## Contributing

Contributions that preserve the project's core principles are welcome:

- local-first by default;
- explicit project boundaries;
- current source outranks memory;
- fail visibly instead of fabricating continuity;
- prefer small, inspectable durable state over transcript accumulation;
- keep host-specific integrations isolated from the core runtime.

For code changes:

```bash
python -m unittest discover -s tests -v
python -m compileall -q continuity
```

before opening a pull request.

---

## License

Continuity is released under the [MIT License](LICENSE).

---

<p align="center">
  <strong>Same project. New session. Keep building.</strong>
</p>

<p align="center">
  Built for the gap between “the model knew this” and “the project can prove it.”
</p>
