# Successor Transfer Protocol

The objective is a **fresh context** that resumes from durable evidence.

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

A pending successor record binds:

- predecessor session;
- successor name;
- handoff ID/path;
- goal/instructions;
- creation time.

A matching successor SessionStart consumes that pending record and inherits arm state.

If launch fails, the predecessor lease is reacquired.

## Codex

A command hook must not pretend it can open an interactive Codex TUI without a controlling terminal.

Continuity therefore:

1. captures the durable handoff;
2. stores a pending Codex successor;
3. releases predecessor ownership;
4. alerts the user with a fresh-session command;
5. lets the next fresh Codex session consume the pending record and inherit the arm state.

Typical command:

```bash
cd /path/to/project && codex
```

This deliberately favors a fresh context over transcript duplication.

## Verification

Every successor must verify root, branch, HEAD, worktree, and relevant files before continuing. A handoff is historical evidence, not current authority.
