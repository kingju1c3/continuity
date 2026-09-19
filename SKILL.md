---
name: continuity
description: "Use for persistent project continuity across sessions and compactions. Restores prior handoffs, searches curated memory, orients in the codebase before broad reads, records durable decisions, and creates successor-ready checkpoints. Invoke with /continuity."
---

# /continuity

At session start, run `continuity start --host <host> --emit-context`, read any recovered handoff in full, then run `continuity orient`. Search durable memory before repeating prior work. Prefer structural queries before broad file traversal.

Save significant reusable knowledge with `continuity remember`, using stable topic keys for evolving decisions. Do not save raw transcripts, secrets, or ephemeral terminal output.

Before stop, compaction, or ownership transfer, create a semantic checkpoint with `continuity checkpoint` covering goal, constraints, discoveries, accomplished work, exact next steps, relevant files, and verification. Continuity adds Git branch, HEAD, working tree, and diffstat.

A successor must run `continuity resume`, verify project identity and Git state, disclose mismatches, and continue from the first unresolved next step.

Current source and Git state outrank stale memory. Missing or ambiguous continuity data must be surfaced, not guessed.
