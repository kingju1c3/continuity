# Host Integration

## Claude Code

`continuity install --agents claude` installs the complete skill bundle under:

```text
.claude/skills/continuity/
```

Project-global hooks are intentionally minimal:

- `SessionStart` — exact session registration and lease bookkeeping;
- `SessionEnd` — objective lifecycle freeze and lease release.

The `/continuity` skill itself declares session-scoped hooks for:

- `UserPromptSubmit`;
- `PostToolUse`;
- `PreCompact`;
- `PostCompact`.

Those hooks become relevant after the skill is invoked. The first skill action arms the exact current session, then normal operation is passive until PreCompact.

At an armed boundary, local Claude can create a named background successor and report the `claude --resume <name>` attach command.

The installer pins skill hook commands to the Python interpreter that installed Continuity instead of relying on ambient PATH.

## Codex

`continuity install --agents codex` installs:

```text
.agents/skills/continuity/
AGENTS.md
```

When `~/.codex` exists, Continuity preserves foreign entries while adding lifecycle dispatch hooks in `~/.codex/hooks.json`.

Codex dispatchers cover:

- `SessionStart`;
- `UserPromptSubmit`;
- `PostToolUse`;
- `PreCompact`;
- `PostCompact`;
- `SessionEnd`.

Expensive behavior is arm-gated. An unarmed project session is effectively passive beyond exact session bookkeeping.

At an armed PreCompact boundary, Continuity can create a fresh persisted read-only `codex exec --json` bootstrap thread and record its thread ID. The hook cannot create an interactive terminal window; the user attaches to the saved successor using the resume path reported by Continuity.

## Other agents

Any agent that can run shell commands can use Continuity manually. Without a documented PreCompact-equivalent lifecycle hook, automatic boundary timing cannot be claimed; use explicit checkpoints/transfers instead.

MCP is not required.
