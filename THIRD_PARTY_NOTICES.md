# Third-party notices

The complete tracked source snapshots below are redistributed without modification.
All original copyright notices, license files, manifests, and nested attributions
are retained. The MIT license at the repository root applies only to Continuity's
original additions. Review source-level notices for incorporated dependencies.

| Project | Commit | License and attribution |
| --- | --- | --- |
| [Second Brain](https://github.com/henrydaum/second-brain) | `ab99eb5bca1561cba4cee9d4b64fbd87010d10ba` | MIT; copyright 2026 Henry Daum; `vendor/second-brain/LICENSE` |
| [Graft](https://github.com/trailhq/Graft) | `8c05769618d413041ea2c8891f82d566f0461b3c` | MIT; copyright 2026 Context Graph Engine contributors; `vendor/Graft/LICENSE` |
| [Graphify](https://github.com/Graphify-Labs/graphify) | `26b02b5e3430e4ab85dd7e72c7b98836d8e65c48` | Apache-2.0 with retained earlier MIT notices; `vendor/graphify/LICENSE`, `LICENSE-MIT`, `NOTICE` |
| [Engram](https://github.com/Gentleman-Programming/engram) | `3dd1f66ccec2bae42f5085ff984b1fbbcc421f0a` | MIT; copyright 2026 Alan Buscaglia; `vendor/engram/LICENSE` |

Graphify's NOTICE attributes the project to Safi Shamsi and the Graphify contributors
and preserves earlier MIT contributions. See the original files for full terms.
`vendor/manifest.json` records every file's SHA-256, byte size, and original Git mode.

No upstream source file was patched for this integration. Continuity adapters live
outside the source trees. Build dependencies downloaded by optional setup commands
have their own terms and are not part of these pinned source snapshots.

## Session Handoff

Complete unmodified source pinned at `5b55592b8c946e9e74c772258ccbd687d9743779`,
from https://github.com/kingju1c3/session-handoff. MIT, copyright 2026 KingJu1c3.
Its original LICENSE is retained at `vendor/session-handoff/LICENSE` in the full
bundle. Continuity's Python lifecycle adapter is an independently written
implementation informed by its checkpoint/readback/ownership protocol.
