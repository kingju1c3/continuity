# Passive Mode Protocol

Invoking /continuity arms one exact host session. After arming, Continuity should become quiet.

## Arm

The agent's first action after invocation is:

```bash
continuity arm --host auto --goal "..." --instructions "..."
```

Arm state is session-scoped and durable. It records the exact session ID, host, active goal, critical instructions, whether automatic successor launch is enabled, and activation time.

## During normal work

An armed session should not create recurring user-visible chatter.

- UserPromptSubmit: no context injection in normal armed work.
- PostToolUse: edit-capable operations silently mark the structural index stale.
- Stop: no checkpoint nag.
- Memory retrieval: explicit/on-demand.
- Current source and Git remain authoritative.

## Trigger

The reliable trigger is the host PreCompact lifecycle event.

Continuity does not infer a fake "percent until compaction" when the host does not expose such telemetry. PreCompact is the documented boundary immediately before compaction.

## Disarm

```bash
continuity disarm
```

A disarmed session no longer performs automatic boundary transfer.
