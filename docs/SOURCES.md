# Source Synthesis and Attribution

Continuity was designed after reviewing these projects. It independently implements the combined architecture rather than vendoring their code.

## Second Brain — henrydaum/second-brain

Adopted concepts:
- slash-command / modular capability mindset;
- local-first agent runtime philosophy;
- background-maintained memory as a separate capability;
- path/task/event separation as an architectural cue.

License observed during review: MIT (2026 Henry Daum).

## Graft — trailhq/Graft

Adopted concepts:
- orient from a compact project graph before broad file traversal;
- multi-host installation that owns only its own skill/rule sections;
- code graph as regenerable cache rather than canonical truth;
- bounded host integration instead of overwriting user instructions.

License observed during review: MIT (2026 Context Graph Engine contributors).

## Graphify — Graphify-Labs/graphify

Adopted concepts:
- query/path/explain style graph-first exploration;
- evidence-bearing relationships;
- graph output separated from source truth;
- update structural indexes after code changes.

Continuity does not copy Graphify source code.

## session-handoff — kingju1c3/session-handoff

Adopted concepts:
- explicit predecessor/successor contract;
- checkpoint before context loss rather than after it;
- exact project/session identity checks;
- mechanical Git evidence alongside prose;
- fail visibly when automatic handoff timing cannot be verified.

License observed during review: MIT (2026 KingJu1c3).

## Engram — Gentleman-Programming/engram

Adopted concepts:
- SQLite + FTS5 local persistent memory;
- curated observations instead of transcript sink;
- stable topic keys for evolving knowledge;
- project-scoped memory;
- structured session summaries and search-before-repeat behavior.

License observed during review: MIT (2026 Alan Buscaglia).

## Principle of synthesis

- memory answers “what did we decide/learn?”
- structural index answers “where/how is this implemented?”
- Git/source answers “what is true now?”
- handoff answers “what should the successor do next?”
