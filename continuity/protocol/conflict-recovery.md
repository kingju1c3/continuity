# Conflict and Recovery Protocol

## Active session ownership

Continuity keeps one active lease per project.

A second session must not silently steal ownership while the first lease is live.

If the previous owner is abandoned or stopped and automatic release did not occur, recover explicitly:

```bash
continuity recover --host codex --expected-owner <old-session-id>
```

The expected owner check prevents an accidental takeover of a different live session.

## Lease conflicts

When SessionStart detects another active owner, the injected context contains a LEASE CONFLICT warning. Treat that as a coordination problem, not permission to continue destructive work.

## Handoff drift

`continuity resume` validates:
- project root;
- branch;
- HEAD;
- working-tree status;
- relevant file existence.

Drift does not necessarily mean the handoff is wrong; it means it must be reconciled with current source.

## Crash recovery

PreCompact, PostCompact, and SessionEnd mechanical freezes exist to preserve objective state even when a semantic handoff was not successfully completed.
