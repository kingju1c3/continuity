# Conflict and Recovery Protocol

## Active session ownership

Continuity keeps one active lease per project.

A second session must not silently steal ownership while the first lease is live.

If the previous owner is abandoned and automatic release did not occur, recover explicitly:

```bash
continuity recover --host codex --expected-owner <old-session-id>
```

The expected-owner check prevents accidental takeover of a different live session.

## Lease conflicts

When SessionStart detects another active owner, Continuity surfaces a LEASE CONFLICT. Treat that as a coordination problem, not permission to continue destructive work.

Pending successor state is consumed only after the new session successfully acquires project ownership.

## Transferred predecessors

After a successful boundary transfer, the predecessor is marked `transferred`.

Further prompts in that predecessor may be blocked so the predecessor and successor do not unknowingly diverge on the same continuity chain.

If automatic successor creation fails before transfer is established, the predecessor lease is restored.

## Resume semantics

An ordinary SessionEnd releases the active lease but does not erase an armed session's durable arm state. Resuming that saved session can therefore continue passive boundary monitoring.

Explicit `continuity end` is different: it releases the manual session and disarms its Continuity state.

## Handoff drift

`continuity resume` validates:

- project root;
- branch;
- HEAD;
- working-tree status;
- relevant file existence.

Drift does not necessarily mean the handoff is wrong; it means it must be reconciled with current source.

## Crash recovery

PreCompact, PostCompact, and SessionEnd mechanical freezes preserve objective lifecycle evidence even when a semantic handoff is incomplete.

Automatic-boundary handoffs add a stronger transfer snapshot at the PreCompact boundary, but the successor still verifies current source before editing.
