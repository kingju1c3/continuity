# Checkpoint and Handoff Protocol

Continuity has two complementary handoff paths.

## Explicit semantic checkpoint

Use a semantic checkpoint for an intentional transfer before compaction or when a carefully authored task summary is valuable:

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

A strong semantic checkpoint records:

1. goal;
2. active instructions and constraints;
3. discoveries and assumptions;
4. accomplished work;
5. ordered next steps;
6. relevant files;
7. verification already performed;
8. what remains unverified.

Continuity automatically adds Git branch, HEAD, working-tree status, and diffstat. The checkpoint command refreshes the structural index first and binds the handoff to the active session lease when one exists.

## Automatic boundary handoff

When an **armed** session reaches PreCompact, Continuity automatically writes an `automatic-boundary` handoff before transferring ownership.

It mechanically records:

- exact project/host/predecessor session;
- arm goal and critical instructions;
- Git branch, HEAD, status, and diffstat;
- changed-file candidates;
- fresh structural index state;
- bounded recent durable-memory candidates;
- bounded best-effort transcript-tail evidence when available.

Common secret patterns are redacted from transcript evidence, but redaction is best effort.

An automatic boundary handoff must not imply tests passed, work was complete, or semantic claims were verified unless independent evidence supports that claim.

## Successor rule

Every successor verifies the handoff against current source before relying on it.

The automatic path protects against context loss; the semantic path provides richer human/agent-authored meaning. Neither outranks current source.
