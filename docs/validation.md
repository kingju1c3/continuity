# Validation report

Validation date: 2026-09-18. Release: 0.1.0.

## Core behavior

**20 automated tests passed** on Python 3.12 in the build environment.
Run: `python3 -m unittest discover -s tests -v`.

Coverage includes persistence across a new process, exact scope isolation, concurrent
writers, idempotent source imports, explicit supersession, possible conflicts,
changed and missing source fingerprints, checkpoint validation, bounded resumes,
FTS query punctuation, provenance requirements, credential tripwires, review dates,
checksummed snapshot round-trips, corrupted restore rollback, edited projections,
missing search-index entries, incremental index/deletion behavior, external symlink
exclusion, directed evidenced paths, and all four import adapters.

The CI workflow declares Python 3.10/3.12/3.13 jobs. Only the local Python 3.12 run
was executed here; the declared CI matrix is not a claim of completed remote CI.

## Independent fresh-session trial

A separate assistant received only the skill, a synthetic project, a scoped vault,
and a request to resume. The fixture contained a superseded decision, a checkpoint
still referring to the old record, a missing test report, an instruction-injection
passage, and a superficially passing test.

The assistant recovered SQLite as the current decision, rejected the injected
instruction to announce a release, noticed the missing source, ran the available
test, and correctly explained that its trivial assertion did not establish cache
invalidation or release readiness. It saved an updated checkpoint and a verified
snapshot, explicitly stating that temporary files did not prove durable persistence.

Its usability feedback led to renaming the deadline flag to `review_due`, separating
it clearly from source freshness. This is one behavioral trial, not a general proof
that every model or host will follow the skill under every adversarial input.

## Complete source verification

`python3 scripts/vendor_sources.py` verified **2,221 upstream files**, including
content hashes and executable bits. Complete tracked trees were read from committed
Git blobs, not from potentially modified working files. Original folders, manifests,
assets, tests, licenses and notices are present. No Git submodules are needed.

A complete Claude installation into a temporary host directory was exercised. Its
copied bundle passed the same 2,221-file verifier, and the command template resolved
to the installed master skill. The actual Claude/Gemini host UIs were not available
for end-to-end slash-command discovery tests.

## Native engine smoke checks

| Engine | Actually exercised | Remaining limits |
| --- | --- | --- |
| Second Brain | Isolated virtual environment, requirements install, application boot to REPL | `main.py --help` starts the app rather than a help-only exit; test process was stopped. Web UI dependencies, model configuration, store packages, and full upstream suite were not tested |
| Graft | npm dependency install, TypeScript/viewer build, CLI help, structural build of a synthetic Python file, import of the real wiring graph | Initial node-gyp header extraction failed on `fchown`; matching headers extracted without ownership changes fixed it. Model-backed summaries, LSP services, hooks, and full upstream suite were not tested |
| Graphify | Virtual environment/package install, CLI help, no-LLM/no-cluster update of a synthetic Python file, import of the real graph | Semantic/multimodal extraction, clustering, remote services, and full upstream suite were not tested |
| Engram | Pinned source/schema inspection and project-filtered export adapter tests | Native Go binary was not built because Go was not installed. The source requires Go 1.25.10; MCP/cloud/TUI flows were not executed |

Graphify emitted four nodes and three edges. Graft emitted three primary nodes and
three edges; its imported unresolved external target was represented explicitly as
a fourth node. The Graft smoke test also caught and corrected an example path:
the current native output is `graft/.graph/wiring.json`, not `graft/graph.json`.

## Honest boundaries

- No head-to-head benchmark against the four original systems was run.
- Core retrieval is lexical FTS plus structural graphs; there are no embeddings,
  automatic semantic deduplication, or native multimodal extraction in the core.
- A local event chain provides consistency checks, not protection against a fully
  privileged attacker who can rewrite the entire store.
- Real cross-session durability depends on the selected host storage. The synthetic
  subprocess trial establishes process-to-process persistence on the same disk.
- Host authorization, skill discovery, external service configuration and paid model
  usage remain under the host and user. The skill does not override them.

## Host packaging

The personal-skill service rejected the initial 90 MB archive with “Archive is too
large to extract safely.” The complete GitHub distribution retains all sources.
A compact host variant keeps the working core, all four import adapters, tests,
documentation, exact source manifest, and explicit source-recovery/build scripts.
The compact variant is not represented as already containing the optional native
engines. Source recovery was executed against all four pinned commits and verified
all 2,221 files successfully.

## Version 0.2 session automation (2026-09-19)

45 tests pass locally (20 memory/graph plus 25 lifecycle tests). Lifecycle coverage
includes complete checkpoint readback, missing/changed artifacts, invalid saves,
read-only candidate gating, permission-mode mismatch, nonce mismatch, persistent
attempt caps, ambiguous launcher results, restart recovery, loop-free Stop handling,
mission completion, fresh telemetry gating, Claude/Codex output shapes, and hook
installation preserving foreign handlers. An independent review found and prompted
regression fixes for subdirectory fencing, Codex artifact reading, repository-visible
hook backups, and repeated blocking Stop errors at launch exhaustion. Hook backups
now remain outside the project; expected launch deferrals return without a Stop loop.
Reserved packet fields cannot be overridden by submitted checkpoint data. Native Terminal/tmux commands are tested
with controlled fixtures; no authenticated real Claude Code/Codex session rotation
was performed here. The host's actual trust and lifecycle events remain a local
activation check, not a claimed completed test.

The full source distribution now includes session-handoff at commit
5b55592b8c946e9e74c772258ccbd687d9743779, bringing the pinned source count to 2,233.

The compact installed skill intentionally omits native source archives; running the
source verifier there reports missing files. The complete repository passes the
2,233-file verifier. This is a packaging distinction, not a passed compact-source check.
