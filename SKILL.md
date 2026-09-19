---
name: continuity
description: "Passive session continuity for coding agents. Invoke once to arm the current session; Continuity stays quiet until the host reaches the reliable pre-compaction boundary, then alerts the user, captures a detailed verified handoff, and transfers work to a fresh successor session when the host supports safe launch."
hooks:
  UserPromptSubmit:
    - hooks:
        - type: command
          command: "continuity hook --host claude"
          timeout: 10
  PostToolUse:
    - matcher: "Write|Edit|MultiEdit|NotebookEdit|Bash|PowerShell"
      hooks:
        - type: command
          command: "continuity hook --host claude"
          timeout: 10
  PreCompact:
    - matcher: "manual|auto"
      hooks:
        - type: command
          command: "continuity hook --host claude"
          timeout: 25
          statusMessage: "Continuity: compaction boundary reached — preparing successor handoff…"
  PostCompact:
    - matcher: "manual|auto"
      hooks:
        - type: command
          command: "continuity hook --host claude"
          timeout: 10
---

# /continuity

Continuity is a **passive boundary-transfer protocol**.

The intended behavior is:

```text
INVOKE ONCE
    ↓
ARM EXACT CURRENT SESSION
    ↓
STAY PASSIVE DURING NORMAL WORK
    ↓
HOST SIGNALS PRECOMPACT
    ↓
ALERT USER BEFORE COMPACTION
    ↓
CAPTURE DETAILED HANDOFF
    ↓
TRANSFER TO FRESH SUCCESSOR
    ↓
SUCCESSOR VERIFIES SOURCE + RESUMES
```

The skill must not continuously interrupt the session, repeatedly inject memory, or create a checkpoint after every turn.

## Host invocation syntax

Use the host's native explicit skill syntax:

- **Claude Code:** `/continuity`
- **Codex:** `$continuity`

Current Codex skill documentation defines explicit skill invocation with `$<skill-name>`. Do not depend on deprecated custom-prompt slash aliases to fake `/continuity` in Codex. The protocol and runtime remain the same after either host-native invocation.

## Invocation contract

When this skill is invoked, **the first operational action** is to arm the exact current session:

```bash
continuity arm \
  --host auto \
  --goal "<current user objective in one concise sentence>" \
  --instructions "<critical constraints that must survive the handoff>"
```

Do this before substantive new work.

If the `continuity` console command is unavailable, read `.continuity/enabled.json` and use the recorded `python` interpreter to invoke the same runtime:

```bash
"<recorded-python>" -m continuity arm \
  --host auto \
  --goal "<current user objective>" \
  --instructions "<critical constraints>"
```

Do not guess an interpreter path. If the enable marker is missing or its interpreter no longer exists, report that host integration needs repair.

Then tell the user, briefly, that Continuity is armed and will remain passive until a compaction/transfer boundary.

Do **not** keep invoking the skill manually each turn. The host hooks remain registered for the session where supported, and the runtime arm state is durable.

If arming fails because no exact host session identity exists, report the failure instead of inventing a session ID. Run:

```bash
continuity doctor
continuity status
```

and repair host integration if necessary.

## Passive mode

Once armed:

- ordinary prompts: no Continuity commentary;
- ordinary tool calls: no Continuity commentary;
- edits/shell operations: silently mark structural state stale;
- ordinary Stop/turn boundaries: no checkpoint nag;
- durable memory is available on demand, not injected every turn;
- source and Git remain canonical.

The runtime waits for a **documented host boundary**, not a guessed token percentage.

### Why PreCompact is the trigger

The supported hosts do not expose one portable, stable live field saying “the session is exactly N% from compaction” on every turn.

Therefore Continuity uses the host's **PreCompact** lifecycle event: the reliable point immediately before compaction.

Do not claim an earlier warning was measured if the host did not expose such telemetry.

## Boundary alert

When an armed session reaches PreCompact, Continuity must alert the user before compaction proceeds.

The alert should communicate:

> Continuity handoff boundary reached: compaction is about to occur. A detailed handoff is being captured and work is transferring to a fresh successor session.

Where supported, the hook also emits a terminal notification/bell.

The first armed PreCompact is blocked so the current context is not compacted before the transfer is captured.

The predecessor must not enter an infinite block loop. Once ownership is transferred, it is marked `transferred`; subsequent work should occur in the successor.

Read `continuity/protocol/compaction.md`.

## Automatic boundary handoff

At PreCompact, Continuity creates an **automatic-boundary handoff**.

It captures, mechanically:

- exact project root;
- exact host;
- predecessor session ID;
- active goal and surviving instructions from arm state;
- Git branch;
- Git HEAD;
- working-tree status;
- diffstat;
- changed-file candidates;
- fresh structural index state;
- recent durable project memories, bounded in size;
- a bounded best-effort tail of the host transcript when a transcript path is exposed;
- verification warnings and provenance labels.

Transcript material is evidence, not source-of-truth. Host transcript formats are not treated as a stable API.

The handoff is mirrored to:

```text
.continuity/LATEST.md
.continuity/LATEST.json
.continuity/handoffs/
```

and stored in the Continuity database.

Read `continuity/protocol/checkpoint-handoff.md`.

## Successor behavior

### Claude Code

When all of these are true:

- current host is local Claude Code;
- Continuity is armed;
- automatic successor is enabled;
- the `claude` executable is available;
- the environment is not marked remote;

Continuity attempts to launch a **fresh named background Claude session** at the boundary.

The successor receives a bootstrap prompt instructing it to:

1. invoke `/continuity`;
2. read `.continuity/LATEST.md`;
3. run `continuity resume`;
4. run `continuity orient`;
5. verify project root, branch, HEAD, working tree, and relevant source;
6. report readiness before modifying files.

The predecessor alert includes the successor name and the command to attach:

```bash
claude --resume <successor-name>
```

If background launch fails, Continuity preserves the handoff and restores predecessor ownership rather than pretending a successor exists.

### Codex

Continuity captures the same detailed handoff and, when the local Codex CLI is available, automatically creates a **fresh persisted background Codex bootstrap thread** using non-interactive `codex exec --json`.

The bootstrap runs read-only by default and is instructed only to verify the handoff/source and report readiness. Continuity captures the emitted `thread.started` ID when available.

The user alert then gives the resume path:

```bash
codex resume <successor-thread-id>
```

A command hook still cannot safely open an interactive TUI window by itself. The distinction matters: Continuity can create the fresh resumable Codex thread automatically, while attaching an interactive terminal to that saved thread remains a user/host UI action.

If the Codex executable is unavailable, Continuity falls back to staging a pending successor and tells the user to start `codex` from the project. The first fresh session inherits that pending handoff.

A transcript fork is not preferred because the purpose is fresh context with durable state, not a duplicate of the predecessor transcript.

Read `continuity/protocol/successor-transfer.md`.

## Successor verification

A successor is not allowed to treat the handoff as current truth without verification.

Authority order:

1. current source + Git state;
2. fresh structural evidence;
3. current durable memory;
4. semantic/automatic handoff;
5. mechanical freezes and host summaries.

Before editing, successor must verify:

- project root;
- branch;
- HEAD;
- working-tree status;
- relevant files;
- whether another session owns the project.

Use:

```bash
continuity resume
continuity orient
continuity status
```

Surface drift before continuing.

Read `continuity/protocol/session-open.md`.

## Manual control

### Inspect arm state

```bash
continuity status
```

### Disable passive boundary transfer

```bash
continuity disarm
```

### Arm without automatic successor launch

```bash
continuity arm \
  --host auto \
  --goal "..." \
  --instructions "..." \
  --no-auto-successor
```

This still captures and alerts at the boundary, but stages a manual fresh-session transfer.

### Explicit semantic checkpoint

Automatic boundary capture is designed for context-loss prevention. For an intentional transfer before compaction, a richer semantic checkpoint is still useful:

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

## Durable memory

Memory is available when needed:

```bash
continuity recall "topic"
continuity remember "Title" "Durable content" --kind decision --topic architecture/example
continuity memory-history architecture/example
```

Save only expensive-to-rediscover knowledge:

- architectural decisions;
- root causes;
- durable constraints;
- non-obvious conventions;
- important failed approaches;
- explicit user choices.

Do not save:

- credentials;
- auth tokens;
- private keys;
- raw full transcripts;
- temporary logs;
- unsupported guesses.

Read `continuity/protocol/memory-write.md`.

## Structural context

Use the smallest sufficient source:

1. exact current source;
2. Continuity built-in index;
3. Graft when installed;
4. Graphify when installed/indexed;
5. broad repository traversal.

Commands:

```bash
continuity query "where is X implemented?"
continuity find SomeSymbol
continuity graph module/name
continuity index
```

Armed PostToolUse hooks silently mark structural state stale. Boundary capture rebuilds the local structural index before writing its handoff.

Read `continuity/protocol/retrieval.md`.

## Session ownership

Continuity keeps one active lease per project.

Never silently steal a live lease.

Explicit abandoned-owner recovery:

```bash
continuity recover --host <host> --expected-owner <old-session-id>
```

Once a predecessor successfully transfers, that predecessor is marked `transferred`. New prompts in it may be blocked so two sessions do not continue modifying the same project under one continuity chain.

Read `continuity/protocol/conflict-recovery.md`.

## Host lifecycle model

### Global host integration

Global hooks should do only what must happen before the skill is invoked:

- SessionStart: exact session registration/lease bookkeeping;
- SessionEnd: objective freeze/end/release.

### Claude skill-scoped hooks

After `/continuity` is invoked, this skill's hooks remain active for the session:

- UserPromptSubmit — normally silent; blocks a transferred predecessor;
- PostToolUse — silently marks structure dirty;
- PreCompact — alert, capture, transfer;
- PostCompact — preserve compact state only if compaction actually occurs.

### Codex dispatch hooks

Codex lifecycle dispatchers may be installed globally, but expensive behavior is gated by the durable arm state. An unarmed session is effectively a no-op beyond exact session bookkeeping.

## Failure behavior

Fail closed around identity and ownership:

- malformed hook input → no mutation;
- missing SessionStart ID → no lease mutation;
- unarmed session → no PreCompact transfer;
- lease conflict → surface, do not steal;
- Claude launch failure → handoff remains durable and predecessor lease is restored;
- unreadable transcript → record unavailable, do not crash;
- stale handoff → show drift;
- missing source evidence → say unknown;
- host cannot open a fresh interactive successor → stage transfer and tell the user exactly what remains manual.

Read `continuity/protocol/security.md`.

## Installation / repair

```bash
continuity install --agents claude,codex
continuity install --agents claude,codex --dry-run
continuity repair --agents claude,codex
continuity doctor
continuity status
```

Remove only Continuity-owned integration:

```bash
continuity uninstall --agents claude,codex
```

## CLI map

- `arm` — activate passive boundary continuity for exact current session.
- `disarm` — disable it.
- `status` — inspect lease, arm state, pending successor, handoff, index.
- `start` — manual session registration.
- `end` — explicit manual session release.
- `recover` — expected-owner recovery.
- `remember` / `recall` / `memory-history` — durable memory.
- `index` / `find` / `graph` / `query` — structural retrieval.
- `checkpoint` — explicit semantic handoff.
- `resume` / `orient` — restore and verify.
- `install` / `repair` / `uninstall` / `doctor` — integration maintenance.
- `hook` — host lifecycle dispatcher.

## Protocol references

Read only what is relevant:

- `continuity/protocol/passive-mode.md`
- `continuity/protocol/compaction.md`
- `continuity/protocol/successor-transfer.md`
- `continuity/protocol/session-open.md`
- `continuity/protocol/checkpoint-handoff.md`
- `continuity/protocol/retrieval.md`
- `continuity/protocol/memory-write.md`
- `continuity/protocol/conflict-recovery.md`
- `continuity/protocol/security.md`

## Integrity invariant

Continuity is a durable coordination protocol, not literal model identity persistence.

It exists to make a fresh agent capable of continuing verified work with minimal rediscovery.

**Fresh source beats old narrative. Evidence beats continuity theater.**
