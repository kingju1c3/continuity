# Successor Transfer Protocol

The objective is a **fresh context** that resumes from durable evidence rather than carrying the predecessor transcript forward.

## Claude Code

When a local Claude executable is available and automatic successor launch is enabled, Continuity launches a named background session:

```text
claude --bg --name <continuity-name> <bootstrap prompt>
```

The bootstrap prompt invokes /continuity and requires verification before file edits.

The predecessor receives the attach command:

```bash
claude --resume <continuity-name>
```

A pending successor record binds predecessor session, successor name, handoff ID/path, goal/instructions, and creation time.

A matching successor SessionStart consumes that record and inherits arm state. If the new Claude process starts before the parent hook finishes updating launch metadata, the consumed claim wins; launch metadata must not overwrite it.

If launch fails, the predecessor lease is reacquired.

## Codex

A hook process cannot safely manufacture an interactive TUI window because it has no controlling terminal. Continuity therefore separates **creating the successor thread** from **attaching the user's terminal**.

When the local Codex executable is available, Continuity automatically starts a fresh persisted read-only bootstrap thread with:

```text
codex exec --json <verification prompt>
```

The JSONL stream exposes a `thread.started` event. Continuity polls briefly for that thread ID and stores it in the pending-successor state.

The bootstrap is deliberately read-only and instructed to:

1. read .continuity/LATEST.md;
2. run Continuity restore/orientation commands;
3. verify project root, branch, HEAD, working tree, and relevant source;
4. report readiness;
5. avoid project-file edits.

The user can then attach interactively to the saved successor:

```bash
codex resume <thread-id>
```

If the thread ID has not appeared by the time the PreCompact alert returns, inspect:

```bash
continuity status
```

The background JSONL log path and any later thread ID are kept in successor state.

If the Codex executable is unavailable or automatic bootstrap cannot be started, Continuity falls back to staging a pending successor and tells the user to start a fresh `codex` session in the project. The next fresh session consumes the pending handoff.

## Ownership

The predecessor lease is released only after the handoff is durably written.

If successor launch fails before a new session is established, predecessor ownership is restored.

A transferred predecessor is blocked from continuing ordinary prompts so two sessions do not unknowingly work the same continuity chain.

## Resume semantics

Arm state survives an ordinary SessionEnd/resume. The lease is released on exit but the durable arm state remains, so resuming the same saved successor continues passive boundary monitoring.

## Verification

Every successor must verify root, branch, HEAD, worktree, and relevant files before continuing.

A handoff is historical evidence, not current authority.
