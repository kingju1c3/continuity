# Architecture

Continuity separates state by lifetime, authority, and lifecycle role.

## Project identity

The canonical project root is the Git toplevel when available, otherwise the current directory. A stable project key hashes the canonical root plus configured origin URL. Memory, sessions, arm state, indexes, freezes, handoffs, and successor-transfer state are project-scoped.

## Authority hierarchy

When state disagrees:

1. current source + Git state;
2. fresh structural evidence;
3. current durable memory;
4. semantic or automatic-boundary handoff;
5. lifecycle freezes / host summaries.

Continuity exists to reduce rediscovery, not to make historical text authoritative.

## Curated memory

SQLite + FTS5 stores durable observations. `topic_key` provides an upsert identity for evolving topics and revision history preserves superseded topic values.

Memory is useful historical context; it never outranks current source or Git state.

## Armed session state

Invoking `/continuity` arms the exact current host session. Arm state stores:

- exact session ID and host;
- active goal;
- critical surviving instructions;
- automatic-successor preference;
- predecessor relationship when inherited.

After arming, the normal mode is passive. Ordinary prompts do not receive large continuity injections and ordinary turn boundaries do not trigger checkpoint nags.

## Compaction boundary

The reliable automatic trigger is the host's `PreCompact` lifecycle event. Continuity does not pretend to know an earlier context percentage when the host does not expose one.

For an armed session, the boundary path is:

```text
PreCompact
  → alert
  → mechanical freeze
  → refresh structure
  → automatic-boundary handoff
  → durable write
  → successor creation/staging
  → ownership transfer
  → block predecessor compaction attempt
```

The automatic-boundary handoff contains mechanical state plus bounded evidence, including a bounded best-effort transcript tail when the host provides a transcript path. Transcript evidence is redacted for common secret patterns and remains lower authority than current source.

## Successor transfer

Claude Code can launch a fresh named background session when the local CLI supports it.

Codex can launch a fresh persisted non-interactive `codex exec --json` bootstrap thread and record its emitted thread ID. The bootstrap is verification-first and read-only by default; attaching a user's interactive TUI remains a host/user action.

If automatic launch is unavailable, the durable handoff is preserved and a pending manual successor is staged.

## Project structure

The built-in index walks bounded text/code files, extracts Python AST symbols/imports, and applies conservative symbol/import patterns to common languages.

When Graft is installed, Continuity may delegate code-orientation queries to Graft. When Graphify is installed and its graph exists, Continuity may delegate graph queries to Graphify. External adapters enhance rather than define the system.

## Retrieval ladder

1. Known exact current source location.
2. Local Continuity index.
3. Specialized adapter (Graft / Graphify).
4. Raw broad search/read.

## Failure behavior

Continuity fails closed around session identity and ownership, fails soft around optional transcript parsing, and never silently restores a handoff from another project.

A successor must verify current source before editing.
