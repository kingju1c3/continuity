# Durable Memory Protocol

Persist knowledge only when losing it would impose meaningful rediscovery cost.

## Save
Good candidates:
- architecture decisions;
- root causes;
- project conventions;
- non-obvious constraints;
- user-approved choices;
- durable implementation patterns;
- important failed approaches.

Do not store:
- credentials or secrets;
- raw transcripts;
- temporary shell output;
- trivial facts cheaper to read from source;
- unsupported guesses.

## Structure

Prefer:
- **What** — the durable fact or decision.
- **Why** — why it matters.
- **Where** — files/components involved.
- **Learned** — non-obvious edge cases.

## Topic keys

Use stable topic keys for evolving knowledge, such as `architecture/auth-model`.

Updating a topic preserves prior revisions in memory history. Use `continuity memory-history <topic>` when a change needs audit or reconciliation.

## Conflicts

A memory update is not automatically proof that the old value was wrong. When two states could both be valid because of branches, environments, or concurrent sessions, preserve the distinction in the content or choose separate topic keys.
