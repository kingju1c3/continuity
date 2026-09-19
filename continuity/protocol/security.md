# Security and Integrity Protocol

Continuity is a context system, not an authorization system or secret manager.

1. Do not save credentials, private keys, tokens, passwords, or secret material in durable memory.
2. Existing malformed host configuration is never overwritten. Installation must fail visibly.
3. Installation preserves foreign hook entries and backs up host files before mutation.
4. Codex hooks are global at the user config level, but Continuity runtime behavior is project-gated by `.continuity/enabled.json`.
5. Malformed hook payloads cause no state mutation.
6. Missing host session IDs do not create ownership leases.
7. Current source and Git state outrank retrieved memories and handoffs.
8. Uninstall removes Continuity-owned integration while preserving unrelated host configuration.
