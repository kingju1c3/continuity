# Compaction Protocol

Compaction is a continuity-risk boundary.

## PreCompact

Continuity writes a mechanical freeze before compaction. The freeze captures:
- exact project;
- host session ID when provided;
- host;
- event;
- current Git snapshot.

For Claude Code manual compaction, Continuity blocks the operation when the structural index is dirty, requiring a semantic checkpoint first. Automatic compaction is never blocked because doing so near a hard context limit can cause request failure.

## PostCompact

When the host exposes a generated compact summary, Continuity stores it with a PostCompact freeze. On the next SessionStart with compact source, that information is rehydrated alongside the latest semantic handoff.

A compact summary is supporting evidence, not a substitute for current source or a structured semantic checkpoint.
