# Retrieval Protocol

Continuity uses the smallest sufficient source.

## Order of operations

1. Known exact current source location.
2. Continuity structural index.
3. Optional Graft adapter.
4. Optional Graphify adapter.
5. Broad repository search/read.

## Automatic prompt context

UserPromptSubmit hooks may inject:
- relevant durable memories;
- structural pointers;
- index freshness state;
- project/branch/HEAD identity.

Treat injected context as retrieval candidates, not authority.

## Freshness

PostToolUse marks the structural index dirty after edit-capable tools and shell operations. Commands that rely on the built-in structural index refresh it before using it. Checkpoints also refresh the index before recording the handoff.

If an adapter or index appears stale, inspect current source directly.
