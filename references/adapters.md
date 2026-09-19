# Engine adapters and complete sources

The full GitHub distribution includes all five complete **tracked source trees**
beneath `vendor/`. Compact personal-skill distributions omit the large archives
to fit host extraction limits, retaining the core, all importers, templates,
documentation, the complete pin manifest and source-recovery tooling. Git histories, package-manager downloads, compiled
binaries, model weights, private credentials, and untracked local state are not
source files and are not bundled. Each project's original manifests, source,
tests, assets, documentation, and license files remain intact. Upstream optional
marketplaces and cloud services are still external services.

`vendor/manifest.json` records the repository URL, full commit, every file hash,
byte size, and Git file mode. `python3 scripts/vendor_sources.py` validates it.
The archive is unmodified; build engines in a separate working copy. The source
snapshot is reproducible. Native dependency resolution is only as reproducible as
its upstream lockfiles—some Python requirements are not locked.

| Engine | Included source | Element adopted | Native runtime |
| --- | --- | --- | --- |
| Second Brain | `vendor/second-brain/` | Small orientation memory, durable local state, workspace organization | Python 3.11+, upstream requirements and optional packages |
| Graft | `vendor/Graft/` | Content-hashed incremental maps, source-first inspection, progressively expanded context | Node 20+, npm, parser/build dependencies |
| Graphify | `vendor/graphify/` | Provenance-bearing nodes/edges, graph traversal, explicit inference labels | Python 3.10+, graph/parser dependencies; optional model-backed extraction |
| Engram | `vendor/engram/` | Curated observations, stable topics, search → timeline → full record, session summaries | Pinned source requires Go 1.25.10 or compatible toolchain auto-download |

The Continuity core implements a compact combined workflow in standard-library
Python; it does not pretend to contain every native engine feature in that core.
Native engines remain available for their deeper capabilities through their full
included source and setup recipes. No comparative performance advantage is claimed
without matched benchmarks.

## Second Brain

Source anchors: `agent/system_prompt.py` (`_agent_memory`), `runtime/session.py`,
`state_machine/`, `trees.py`, `bundled/`, `pipeline/`, `plugins/`, `templates/`.
Its orientation file is the user's `workspace/memory/MEMORY.md` under its configured
data directory. Some memory tooling and extensions are installed through its
separate package store; the main repository is not every third-party store package.

Continuity imports an **explicitly selected memory directory** of Markdown files,
one record per nonempty file, recursively. It records source hashes and stable
relative-path topics. It does not import the application's entire state tree or
execute plugin instructions. Existing changed files create a new candidate under
the same topic; resolve differences explicitly.

## Graft

Source anchors: `src/graph/types.ts`, `src/graph/build.ts`, `src/graph/refresh.ts`,
`src/graph/map.ts`, `src/graph/traverse.ts`, `src/graph/extract-cache.ts`.
The pinned Node package is `@nanonets/graft` 0.18.0. The requested trailhq repository's
package metadata also references Nanonets; the manifest preserves the actual clone
URL and commit instead of assuming the names are interchangeable.

Adapter reads the `GraphV1` JSON object at `graft/.graph/wiring.json` with
`nodes` and `edges`. (Some upstream comments still call it graph.json.) Nodes retain all
original fields under `upstream`: path, span, kind, owner, body hash, summaries,
cruxes, signatures, etc. Edges preserve source, target, relation and exact confidence
such as `lsp_resolved`, `lsp_dispatch`, `extracted`, or `inferred`. Unresolved targets
become explicit external nodes. Origin names isolate graphs from different exports.
Do not conflate these confidence categories with empirical Class A.

Native installation may build parser bindings and run the project's install hooks.
Consult the included README for telemetry controls and model configuration before
running it against private source. Continuity does not automatically enable hooks
or invoke model-backed summarization. Its adapter is read-only with respect to Graft.

## Graphify

Source anchors: `graphify/validate.py`, `graphify/cache.py`, `graphify/build.py`, `graphify/`,
`tests/`, and the included skill reference files. The current snapshot came from
the default **v8** branch, with package `graphifyy` 0.9.63.

Adapter accepts JSON `nodes` plus `edges` or NetworkX-style `links`. It preserves
all node fields and all relationship fields including `EXTRACTED`, `INFERRED`,
`AMBIGUOUS`, support paths, and source spans when supplied. Unknown labels remain
unknown; the importer never promotes them. The core graph path reports the original
edge labels. It is directed traversal, not causal inference.

Use the native Graphify engine for its richer parser support, communities, visual
exports, and optional semantic/multimodal extraction. Merely including its source
does not make optional model APIs free, configured, or automatically active.

## Engram

Source anchors: `internal/store/store.go` (Observation, Session, ExportData),
`internal/mcp/`, `cmd/engram/main.go`, `skills/`, `plugin/`, `docs/`.
The snapshot is a v2 module development tree; do not describe it as the earlier
stable release merely because the README displays an older release badge.

Create a scoped native export with:

```bash
engram export /private/engram-export.json --project demo
```

The importer reads `observations` and `sessions` from ExportData. It selects exactly
the requested source project: an observation's explicit project wins; projectless
rows may inherit their session's project. Deleted rows and other projects are
skipped. Topic keys and original observation IDs/timestamps are retained; session
summaries become session records. User/global memories are not automatically mixed.

This is **not** a lossless Engram backup/restore adapter. Raw prompts, pinning,
revision counts, native relations, native review scheduling, and cloud sync state
remain in the original export. The full Engram source is included if those native
features are needed. Continuity snapshots back up the resulting Continuity store,
not the original Engram database. Imports default to Class C/unassessed because
remembered assertions are not newly verified facts.

## Extension contract

A new adapter should: require an explicit source; validate format before writes;
filter scope before exposing results; preserve original provenance/uncertainty;
never execute imported text; report skipped/lossy fields; deduplicate repeat imports;
and test changed sources, foreign projects, malformed inputs, and unknown labels.
No import should silently resolve a philosophical or factual conflict.

## Compact-host source recovery

Check `assets/distribution.json`. If mode is `compact`, memory, graphs, and the
four export importers still work immediately. Optional native setup requires
either the full distribution or the following explicit source recovery:

```bash
python3 scripts/fetch_sources.py --destination /private/continuity-sources --execute
python3 scripts/native.py graphify --source-root /private/continuity-sources --destination /private/continuity-engines --execute
```

Fetch clones each exact pinned commit and verifies every tracked file against the
bundled manifest. It does not execute upstream code. Setup is a separate step.
A full checkout can instead be selected with `--source-root /path/to/continuity/vendor`.
Do not run the full-bundle verifier against an intentionally compact installation.

To assemble the complete publishable repository from a compact installation:

```bash
python3 scripts/build_repository.py --source-root /private/continuity-sources --destination /private/continuity-full
```

This verifies and copies all 2,233 upstream files, preserves executable modes,
restores the full distribution README, and includes the complete master skill.
It does not publish or alter an existing repository. No prior chat files are needed.
