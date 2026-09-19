# Architecture

Continuity separates state by lifetime and authority.

## Project identity

The canonical project root is the Git toplevel when available, otherwise the current directory. A stable project key hashes the canonical root plus configured origin URL. Every memory, session, index row, and handoff is project-scoped.

## Curated memory

SQLite + FTS5 stores only durable observations. `topic_key` provides an upsert identity for evolving topics so the system does not accumulate competing copies of the same architectural fact.

Memory is useful historical context; it never outranks current source or Git state.

## Session state and handoff

A handoff stores semantic fields supplied by the agent plus a mechanical Git snapshot captured by Continuity. Prose records predecessor understanding; Git evidence lets the successor verify it.

The mirrored `.continuity/LATEST.md` is inspectable and disposable. SQLite is the durable local record.

## Project structure

The built-in index walks bounded text/code files, extracts Python AST symbols/imports, and applies conservative symbol/import patterns to common languages.

When Graft is installed, Continuity may delegate code-orientation queries to Graft. When Graphify is installed and its graph exists, Continuity may delegate graph queries to Graphify. External adapters enhance rather than define the system.

## Retrieval ladder

1. Known exact source location.
2. Local Continuity index.
3. Specialized adapter (Graft / Graphify).
4. Raw broad search/read.

## Lifecycle

`start` registers a session and emits the latest handoff. Host hooks can call the same path automatically. Pre-compaction/stop events inject a checkpoint requirement. The semantic checkpoint still belongs to the agent because a lifecycle hook cannot reliably infer hidden task state from process metadata alone.

## Failure behavior

Continuity is fail-soft on lifecycle hooks and fail-closed on project identity. It never silently restores a handoff from another project.
