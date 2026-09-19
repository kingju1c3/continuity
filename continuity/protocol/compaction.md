# Compaction Boundary Protocol

Compaction is treated as a transfer boundary, not merely a summarization event.

## Before compaction

For an **armed** session, PreCompact triggers this sequence:

1. ring/notify where the host supports a terminal sequence;
2. alert the user that compaction is about to happen;
3. write a mechanical PreCompact freeze;
4. rebuild the built-in structural index;
5. create an automatic-boundary handoff;
6. persist the handoff to SQLite and .continuity/LATEST.*;
7. prepare or launch a fresh successor;
8. release predecessor ownership only after durable handoff capture;
9. block the current compaction attempt so the original context is not destroyed first.

Unarmed sessions do not perform this sequence.

## Automatic-boundary evidence

The boundary handoff records:

- exact host/session/project;
- arm goal and instructions;
- Git branch and HEAD;
- working-tree status and diffstat;
- changed-file candidates;
- fresh index state;
- bounded durable memory candidates;
- bounded best-effort transcript tail when the host supplies a transcript path.

Transcript data is explicitly marked as best-effort evidence and must not outrank source.

## No infinite block

After a successful transfer the predecessor is marked transferred. It is not allowed to repeatedly recreate/block the same transfer boundary. Work should continue in the fresh successor.

If automatic successor launch fails, predecessor ownership is restored and the durable handoff remains available.

## PostCompact

PostCompact is a recovery path, not the preferred armed path. If compaction nevertheless occurs, Continuity may preserve the host's compact summary and mechanical state for restoration.
