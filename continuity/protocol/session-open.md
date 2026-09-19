# Session Open Protocol

Use this procedure at every Continuity-enabled session start.

1. Accept the host-provided session ID as the exact session identity. Do not invent a replacement ID when the host already supplied one.
2. Restore the Continuity context injected by the SessionStart hook.
3. Check for a lease conflict. If another session still owns the project, do not silently take ownership. Reconcile or use `continuity recover --expected-owner <id>` only when explicit recovery is intended.
4. Run `continuity orient` when the injected context is insufficient or ambiguous.
5. If a previous handoff exists, verify project root, branch, HEAD, working tree, and relevant files against current source.
6. If a newer mechanical freeze exists than the latest semantic handoff, treat the freeze as evidence that the prior session may have lost context before completing a semantic checkpoint.
7. Continue from the first unresolved next step only after verification.

Never describe historical memory or a handoff as current truth when the source tree disagrees.
