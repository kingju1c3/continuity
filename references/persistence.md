# Persistence and privacy

## Local durable hosts

Use a private folder outside the repository, for example
`~/.local/share/continuity/vault`, and an exact scope such as `project:owner/repo`.
Set `CONTINUITY_STORE` to reuse that folder. SQLite uses WAL, a busy timeout,
transactional writes, and a scope-specific event chain. Directory permissions are
private on creation; the database is restricted where the OS supports it. This
is not encryption or access control between mutually untrusted local processes.
Scopes prevent accidental retrieval mixing, not access by somebody who owns the
underlying database file. Use OS permissions, encrypted disks, and separate vaults
where the threat model requires it.

The core does not upload anything, start a server, or call an LLM. It does not
install a background hook. Checkpoints must be saved by the calling assistant or
an explicitly configured host integration.

## Ephemeral hosted sessions

A successful SQLite commit to scratch does **not** prove cross-session durability.
Use the host's durable files capability. In ChatGPT Work, invoke the installed
Library skill to find, download, and save the user's private continuity snapshot.
Do not assume a Library API signature or invent a persistence result.

1. Find the latest snapshot for the exact scope and verify its identity and version.
2. Download it to a new temporary vault, then run `restore`. Never restore over a
   populated scope. The snapshot includes schema, scope and SHA-256 checksum.
3. Perform retrieval and authorized work. Revalidate local source paths after a
   move; a source unavailable on this host is `missing`, not automatically false.
4. Export a new uniquely named snapshot after changes. Persist it to the same
   durable destination using its actual available skill/tools. Read back metadata
   or content to verify success. Retain the prior revision until the new save is
   confirmed.
5. Record which snapshot is current in the durable destination, if supported.
   If concurrent sessions made divergent revisions, stop automatic merging and
   reconcile records explicitly; this release is not a distributed CRDT.

If no durable destination is accessible, perform useful work and clearly report
that the current vault is temporary. Do not claim continuity survived a reset.

## Export, restore, and integrity

`export` writes a scope-only JSON snapshot to a new path and refuses overwrite.
It includes records (including retired ones), checkpoints, graph data, and event
history. Graph maps and resume text are lossy projections, not backups. `restore`
requires the correct scope and an empty destination scope, validates the checksum,
and audits projections against the event history before committing.

The event chain detects accidental edits and mismatches between history and current
records. It is not a signed audit log: an actor with full write access can rewrite
both history and its hashes. The schema is versioned; unknown schemas are rejected.
This release has no migration from hypothetical future schema versions.

## Deletion and sharing

`retire` retains data in history and exported backups. For actual removal, inventory
the vault, snapshots, durable file revisions, and external engine stores and delete
them under the user's explicit deletion request using host-supported mechanisms.
There is no misleading “forget everywhere” button. Do not publish private stores,
exports, source paths, or checkpoints to the public Continuity repository.
