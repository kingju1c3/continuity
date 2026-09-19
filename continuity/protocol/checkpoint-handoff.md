# Checkpoint and Handoff Protocol

Create a semantic checkpoint before:
- explicit session transfer;
- manual compaction when project state changed;
- ending a work session after meaningful changes;
- changing ownership between Claude Code and Codex;
- any operation where losing task state would cause expensive reconstruction.

A useful checkpoint records:
1. Goal.
2. Active instructions and constraints.
3. Discoveries and assumptions.
4. Accomplished work.
5. Ordered next steps.
6. Relevant files.
7. Verification already performed.
8. What remains unverified.

Continuity automatically adds Git branch, HEAD, working-tree status, and diffstat.

The checkpoint command refreshes the structural index first and binds the handoff to the active session lease when one exists.

A successor must verify the checkpoint against current source before relying on it.
