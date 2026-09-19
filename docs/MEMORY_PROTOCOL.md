# Memory Protocol

Save knowledge only when future sessions would otherwise pay a meaningful rediscovery cost.

Recommended structure:

```markdown
**What**: What changed or was learned.
**Why**: Why it matters or why this choice was made.
**Where**: Files, components, commands, or systems involved.
**Learned**: Non-obvious gotchas or constraints.
```

Use stable topic keys for evolving state, for example `architecture/auth-model` or `config/test-runner`. Distinct decisions should not share a topic key merely because they are related.

Do not store raw terminal dumps, entire conversations, secrets, credentials, ephemeral status, or facts that are cheaper to read from source.
