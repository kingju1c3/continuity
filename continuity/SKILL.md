---
name: continuity
description: "Use for persistent project continuity across sessions and compactions. Restores prior handoffs, searches curated memory, orients in the codebase before broad reads, records durable decisions, and creates successor-ready checkpoints. Invoke with /continuity."
---

# /continuity

Continuity is the project's continuity layer. It creates an evidence-backed approximation of continuity from durable state: curated memory, source structure, Git state, and explicit handoffs.

## Session opening

At the beginning of project work:

1. Run continuity start --host <claude|codex|other> --emit-context.
2. Read the recovered handoff completely before modifying files.
3. Run continuity orient.
4. If the task refers to past decisions, bugs, conventions, or prior work, use continuity recall "keywords" before rediscovering them.
5. For architecture/code questions, prefer continuity query, continuity find, or continuity graph before broad raw-file traversal.
6. If the index is absent or stale, run continuity index.

Never claim recovery of facts that are not present in durable state or current source.

## Durable memory protocol

Save significant reusable knowledge, not every turn and not raw tool output. Good candidates: architecture decisions, confirmed conventions, non-obvious bug root causes, configuration decisions, user constraints, and discoveries that prevent future rework.

Use stable --topic keys for knowledge that evolves. That topic is updated rather than duplicated.

## Structural orientation protocol

Use the cheapest reliable source in this order:

1. Exact current source when the location is already known.
2. Continuity local symbol/edge index.
3. Graft adapter for code orientation when installed.
4. Graphify adapter for graph/path/concept questions when installed and indexed.
5. Raw repository-wide search/read as fallback.

After meaningful code changes, refresh with continuity index before producing an architecture handoff.

## Checkpoint and handoff

Before ending a session, before compaction, or when ownership will move to another agent/session, create a semantic checkpoint. It must state:

- goal;
- active instructions/constraints;
- discoveries and assumptions;
- accomplished work;
- exact next steps;
- relevant files;
- verification already performed and what remains unverified.

Continuity automatically adds Git branch, HEAD, working-tree status, and diffstat. Checkpoints are stored in SQLite and mirrored under .continuity/ for inspectability.

## Successor protocol

A successor session must:

1. run continuity start --emit-context;
2. run continuity resume if a handoff exists;
3. verify that project root, branch, HEAD, and relevant files still match the checkpoint;
4. state any mismatch before continuing;
5. continue from the first unresolved next step rather than repeating completed work.

## Automatic hooks

continuity install --agents claude,codex wires repository-local skill/instruction files and lifecycle hooks where the host supports them. Hooks are fail-soft: they inject restoration/checkpoint instructions but never fabricate a completed semantic handoff. A host that cannot programmatically create a brand-new chat/session still gets automatic session registration plus restoration on the next session.

## Integrity rules

- Current source and Git state outrank stale memories.
- Search hits are candidates; inspect enough evidence before relying on them.
- Do not store secrets, credentials, or raw private transcripts.
- Do not silently cross project boundaries.
- If continuity data is missing, stale, ambiguous, or inconsistent, say so and rebuild/reconcile it.
