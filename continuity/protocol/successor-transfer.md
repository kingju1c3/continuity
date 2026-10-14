# Successor Transfer Protocol

The objective is a **fresh context** that resumes from durable evidence rather than carrying the predecessor transcript forward.

## Claude Code

By default (v0.8) the successor is a **visible sidebar clone**. Continuity prepares the worktree, carries the work over, writes the handoff, releases the predecessor's lease, and returns a `start` block:

```json
{"tool": "mcp__ccd_session__start_session",
 "args": {"initiation": "user_asked", "title": "Session <label> <next>", "context": "fresh",
          "cwd": "<main checkout>/.claude/worktrees/continuity-<slug>-session-<next>",
          "use_worktree": false, "prompt": "<bootstrap prompt>", "background": "..."}}
```

The agent makes that call in the Claude desktop app. `permission_mode`, `model` and `effort` are left out on purpose so the successor inherits the predecessor's. The successor's title matches `successor_name`, so its SessionStart hook inherits the chain. In a plain terminal the user opens the folder and pastes the prompt.

The bootstrap prompt invokes /continuity and requires verification before file edits.

Opt-in only (`continuity arm --background-successor`): the old background launch, `claude --bg --name <continuity-name> <bootstrap prompt>`, attached with `claude --resume <continuity-name>`. Background sessions don't appear in the desktop app's sidebar or on the phone.

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


## Worktree successor and session chain (v0.4)

At the PreCompact boundary the Claude successor is started in a **new git worktree** (`<project>-continuity/<label-slug>-<N>-<M>`, branch `continuity/<label-slug>-<N>-<M>`) created from the predecessor's HEAD, with the predecessor's uncommitted work applied from the lossless patch and its untracked files copied. Sessions in one chain are labelled `Session <label> 1.0`, `1.1`, `1.2`, …; the label comes from `continuity arm --label` (default: the project folder name) and the successor inherits it with the next number. The bootstrap prompt tells the successor it is picking up exactly where the named predecessor left off. Without a Git repository the successor starts in the project root, and the alert says so.

### Same environment, same folders (v0.6.0)

Worktree creation happens in the predecessor's own environment: the same machine or container, inside the same main checkout, at `<main checkout>/.claude/worktrees/continuity-<label-slug>-session-<N>.<M+1>`. Never in a fresh clone, a temporary directory or another container. The successor is launched there too, so it inherits the checkout, installed dependencies, caches and in-flight test output. This applies in cloud mode as well: when the `claude` CLI is present, the successor is launched with `claude --bg` from the worktree folder. A new container (`create_session`), a desktop background task (`spawn_task`) or a new chat is a fallback, used only when no same-environment launch is possible, and the user is told it is a fallback.
