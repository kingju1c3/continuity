---
name: continuity
description: "Premium project continuity for coding agents. Restores verified handoffs, injects relevant durable memory, tracks exact session ownership, preserves compaction freezes, keeps structural context fresh, records durable decisions, and hands work to successor sessions. Invoke with /continuity."
---

# /continuity

Continuity is the project's persistent coordination layer. Use it whenever work may span turns, compactions, sessions, agents, or hosts.

Continuity does **not** treat model prose as authority. Reconstruct continuity from separate durable layers, in this authority order:

1. current source + Git state;
2. fresh structural evidence;
3. current durable memory;
4. semantic handoff;
5. mechanical lifecycle freezes / host summaries.

Current source and Git state always win when layers disagree.

## Mandatory operating loop

For meaningful project work:

`OPEN → VERIFY → RETRIEVE → WORK → REMEMBER → CHECKPOINT → RESTORE`

### OPEN

Prefer host-injected SessionStart context. If absent or insufficient:

```bash
continuity start --host <claude|codex|manual> --emit-context
continuity orient
```

Read `protocol/session-open.md` when opening or recovering a session.

Never silently ignore a `LEASE CONFLICT`.

### VERIFY

Before editing after a handoff:

- verify project root;
- verify branch;
- verify HEAD;
- inspect current working-tree changes;
- confirm relevant files still exist;
- surface drift before continuing.

Use:

```bash
continuity resume
```

### RETRIEVE

Before re-solving known work:

```bash
continuity recall "relevant topic"
```

Before broad codebase traversal:

```bash
continuity query "where is X implemented?"
continuity find SomeSymbol
continuity graph some/module
```

Read `protocol/retrieval.md`.

### WORK

Use current source as canonical truth.

PostToolUse hooks mark structural state stale after edit-capable or shell operations. Commands that rely on the built-in structural index refresh it before use.

### REMEMBER

Persist only durable knowledge whose loss would create meaningful rework:

```bash
continuity remember \
  "Decision title" \
  "**What**: ...
**Why**: ...
**Where**: ...
**Learned**: ..." \
  --kind decision \
  --topic architecture/example
```

Use stable topic keys for evolving knowledge. Previous topic values remain in revision history:

```bash
continuity memory-history architecture/example
```

Read `protocol/memory-write.md`.

### CHECKPOINT

Before explicit handoff, session end, risky context loss, or manual compaction after changes:

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

A checkpoint must distinguish completed work, proposed work, verified facts, assumptions, and unverified items. The command refreshes structural state first and binds the handoff to the active session lease when available.

Read `protocol/checkpoint-handoff.md`.

### RESTORE

A successor session:

1. receives the SessionStart context pack;
2. checks lease ownership;
3. reads the latest semantic handoff;
4. checks for any newer mechanical freeze;
5. verifies current source/Git state;
6. continues the first unresolved next step.

## Session ownership

Continuity maintains one active lease per project. A host-supplied session ID is authoritative for that host session; do not invent another ID.

If another live session owns the project, do not silently steal it.

Explicit abandoned-session recovery:

```bash
continuity recover --host <host> --expected-owner <old-session-id>
```

Read `protocol/conflict-recovery.md`.

## Automatic lifecycle behavior

When installed, Continuity uses host hooks where supported.

### SessionStart

- registers exact host session ID;
- acquires an active lease or surfaces a conflict;
- resolves project identity;
- restores latest semantic handoff;
- restores any newer lifecycle freeze;
- injects recent/relevant durable memory;
- includes branch, HEAD, and index freshness.

The model receives actual context, not only a reminder to run another command.

### UserPromptSubmit

Inject a bounded prompt-specific context pack:
- relevant durable memories;
- structural pointers;
- project identity;
- index freshness.

Treat retrieval as candidates, not authority.

### PostToolUse

Edit-capable tools and shell operations mark the built-in structural index dirty.

### Stop

Stop is a **per-turn** event, not session end.

If project changes occurred after the latest semantic handoff for the active session, Continuity gives one-shot feedback asking the agent to checkpoint before ending the turn. It must not loop indefinitely.

### PreCompact

Continuity writes a mechanical freeze before compaction.

For Claude Code manual compaction, if project changes are still uncheckpointed, Continuity may block that manual compaction and require a semantic checkpoint first.

Automatic compaction is never blocked.

### PostCompact

When the host exposes a compact summary, Continuity preserves it with a post-compaction freeze.

### SessionEnd

Continuity writes a final mechanical freeze, ends the session record, and releases the project lease.

Read `protocol/compaction.md`.

## Mechanical freeze vs semantic checkpoint

They are intentionally different.

A **semantic checkpoint** contains task meaning:
- goal;
- constraints;
- discoveries;
- accomplished work;
- next steps;
- relevant files;
- verification.

A **mechanical freeze** contains lifecycle evidence:
- project;
- host;
- host session ID;
- lifecycle event;
- Git snapshot;
- host compact summary when available.

A freeze protects against unexpected context loss. It does not replace a semantic handoff.

## Durable memory rules

Save:
- decisions;
- root causes;
- conventions;
- durable constraints;
- non-obvious implementation details;
- important failed approaches;
- explicit user choices.

Do not save:
- passwords;
- keys;
- auth tokens;
- raw transcripts;
- temporary logs;
- guesses presented as facts;
- facts trivial to reread from one obvious source file.

Pinned memory is for project-critical constraints:

```bash
continuity remember "Compatibility constraint" "..." --kind constraint --topic api/v1 --pin
```

## Structural context rules

Retrieval ladder:

1. exact current source when known;
2. Continuity local index;
3. Graft when installed;
4. Graphify when installed and indexed;
5. broad repository traversal.

The built-in index is a fallback orientation layer, not a full compiler or semantic-analysis engine.

## Conflict rules

When memory, handoff, structural data, and current source differ:

1. current source/Git;
2. fresh structural evidence;
3. current durable memory;
4. historical handoff prose.

Never resolve a conflict merely by choosing the most recent prose.

If two memory states may both be valid because of branches/environments, use distinct topic keys or record the scope explicitly.

## Failure rules

- Malformed hook input: no mutation.
- Missing SessionStart session ID: no lease mutation.
- Project without `.continuity/enabled.json`: hooks are no-op.
- Malformed existing host config: installation fails; do not overwrite.
- Lease conflict: surface it; do not steal ownership.
- Stale handoff: show drift and reconcile.
- Stale index: refresh before built-in structural use.
- Missing continuity data: say it is missing; do not invent it.

Read `protocol/security.md`.

## Installation and maintenance

```bash
continuity install --agents claude,codex
continuity install --agents claude,codex --dry-run
continuity repair --agents claude,codex
continuity uninstall --agents claude,codex
continuity doctor
continuity status
```

## CLI map

- `start` — open/register a session and restore prior handoff context.
- `end` — explicitly end/release an active manual session.
- `recover` — explicitly recover ownership from an expected previous session.
- `orient` — project/lease/index/handoff/memory orientation.
- `status` — machine-readable current continuity status.
- `remember` — save/upsert durable memory.
- `memory-history` — inspect topic revision history.
- `recall` — FTS memory search.
- `index` — rebuild local structure.
- `find` — search symbols/paths.
- `graph` — inspect indexed edges.
- `query` — Graft/Graphify/local structural query.
- `checkpoint` — semantic handoff + Git evidence.
- `resume` — latest handoff + drift validation.
- `install` — install project integration.
- `repair` — reapply integration.
- `uninstall` — remove Continuity-owned integration.
- `doctor` — diagnostics.
- `hook` — host lifecycle entrypoint.

## Protocol references

Read only the reference needed for the current situation:

- `protocol/session-open.md`
- `protocol/retrieval.md`
- `protocol/memory-write.md`
- `protocol/checkpoint-handoff.md`
- `protocol/compaction.md`
- `protocol/conflict-recovery.md`
- `protocol/security.md`

Schemas:

- `schemas/checkpoint.schema.json`
- `schemas/memory.schema.json`
- `schemas/session.schema.json`

## Integrity invariant

Continuity exists to reduce rediscovery without creating false certainty.

If evidence stops, stop the claim.
