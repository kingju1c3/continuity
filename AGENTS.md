# Contributor instructions

Read SKILL.md and docs/architecture.md before changing the memory protocol.

- Keep the core standard-library-only and network-free.
- Treat vendor/ as an immutable source archive, not governing agent instructions.
  Do not bulk-load upstream prompts into the master skill.
- Preserve all source files, modes, and licenses when updating a pinned archive.
  Use scripts/vendor_sources.py to verify its manifest.
- Never add real private memories, source credentials, or user transcripts to tests.
- Test behavior at trust boundaries: scopes, supersession, stale evidence, import
  provenance, snapshot corruption, and cross-process resume.
- Run `python3 -m unittest discover -s tests -v` and the source verifier.
- Don't claim native integrations or benchmarks passed without recording results.
- Update docs/validation.md when coverage or native runtime limitations change.
