# Host Integration

## Claude Code

`continuity install --agents claude` installs `.claude/skills/continuity/SKILL.md` and adds lifecycle command hooks to `.claude/settings.json` for session start, pre-compaction, and stop events. Existing JSON fields are preserved.

## Codex

`continuity install --agents codex` installs `.agents/skills/continuity/SKILL.md`, marker-fences a Continuity protocol block in `AGENTS.md`, and, when `~/.codex` exists, preserves foreign entries while adding Continuity lifecycle hooks in `~/.codex/hooks.json`.

## Other agents

Any agent that can run shell commands can use Continuity manually. MCP is not required.
