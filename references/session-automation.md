# Automatic session opening and handoff (v0.2)

The lifecycle bridge turns Continuity into an active Claude Code/Codex CLI handoff
system. It restores context at startup, requests a complete checkpoint at turn end,
opens a fresh native CLI session when rotation is due, and verifies the successor
before transferring writing ownership. This supplements the scoped memory core.

## What was adopted from session-handoff

Reviewed source: `kingju1c3/session-handoff`, commit
`5b55592b8c946e9e74c772258ccbd687d9743779` (MIT, copyright KingJu1c3).
The complete source is pinned as the fifth component in the full distribution.
The new Python bridge independently implements its useful lifecycle principles;
the upstream JavaScript engine and tests remain available unchanged.

| Strong upstream behavior | Continuity implementation |
| --- | --- |
| Complete checkpoint before creation | Immutable JSON envelope, source hashes, readback before reservation |
| Same mission, permissions, worktree | Exact scope/root, preserved goal and permission record, observed mode comparison |
| Read-only bootstrap | Candidate nonce bound to actual SessionStart; required file reads before accept |
| One writer | SQLite reservation/transfer; predecessor fenced by supported PreToolUse hooks |
| Ambiguous launch is not absence | No blind retries; pending reservation persists through process restarts |
| Persistent rotation cap | Five launch attempts by default; recovery does not reset the counter |
| Early context check | Optional exact-session measurement and two-turn reserve gate |
| Degraded recovery | Preserve prior valid packet; mark missing/failing checkpoint rather than inventing it |

A summary, a new window, a successful launcher exit, or a stored file is not proof
of successor comprehension or readiness. `accept` records the assistant's explicit
readback and rechecks artifact hashes; it does not read the model's hidden state.

## Enable on the actual computer running the CLI

First install the skill, or keep a stable clone path. The following are macOS
examples for Claude Code. Replace `/absolute/path/to/project` and the script path
with actual paths. Pick one host per mission chain; give concurrently independent
missions separate project/worktree directories and scopes.

```bash
python3 /path/to/continuity/scripts/continuity_session.py \
  --store "$HOME/.local/share/continuity/vault" \
  --scope project:my-project --project /absolute/path/to/project \
  configure --host claude --launcher terminal --auto --max-turns 8 --max-launches 5

python3 /path/to/continuity/scripts/continuity_session.py \
  --store "$HOME/.local/share/continuity/vault" \
  --scope project:my-project --project /absolute/path/to/project \
  install-hooks --host claude --execute
```

For Codex, replace both `--host claude` values with `--host codex`. Start Codex in
that project and review the exact hook definitions with `/hooks`. The installer
never trusts hooks for you or passes a trust/permission bypass flag. Hook definitions
awaiting review are configured but inactive. Claude Code may also require the host's
normal project trust/reload process. Start a new session after installation.

For Linux or a tmux workflow on macOS, use `--launcher tmux` and run the CLI inside
an existing tmux session. The bridge opens a new visible tmux window. The macOS
`terminal` launcher uses the documented Terminal application scripting interface;
macOS may request Automation permission. No Windows launcher is supplied in v0.2.
`--launcher manual` supports checkpoint/recovery without automatic process opening.
The native `claude` or `codex` executable must be on the launch environment's PATH.

The installer merges project-local hooks, makes a private backup before changing
existing JSON under the private vault (outside the repository), and preserves foreign handlers even in the same group. Repeating
installation is idempotent. It does not edit permission settings or trust hashes.
A malformed configuration is rejected rather than overwritten.

## Runtime sequence

1. `SessionStart` observes the real host session ID, project, and permission mode.
   The first session becomes the owner. Startup feedback points to the full skill
   and the last complete lifecycle checkpoint, if any.
2. `UserPromptSubmit` counts an ordinary user turn. Other tool activity marks the
   prior packet stale. The scheduled rotation default is eight user turns. This
   is a configurable operational budget, **not a context-window measurement**.
3. `Stop` requests one checkpoint-writing continuation if needed. The agent follows
   `assets/handoff.example.json`, fills actual state, stops background writers, and
   calls `checkpoint --session <observed-id> --file <private-json>`.
4. If the current packet is valid and rotation is due, the bridge verifies its
   digest, required artifact fingerprints and Git HEAD, reserves exactly one launch,
   freezes predecessor mission writes, and opens a fresh native CLI window.
5. The successor's `SessionStart` binds its actual ID to the launch nonce. It reads
   the complete checkpoint with `bootstrap`, reads each required file with
   `read-artifact --path relative/file.py` (or a permitted read-only host viewer), then calls
   `accept --session <actual-id> --digest <digest> --first-action <exact-first-action>
   --artifacts-read '["relative/file.py"]'` using the common store/scope/project flags.
6. Acceptance rechecks the files and permission mode, records the acknowledgment,
   and transfers ownership transactionally. The successor continues the mission.
   The old window remains available for inspection but must not continue writing.
7. Mark `mission_complete: true` in the final handoff to stop automatic continuation.
   It is an agent/user declaration, not an automatic proof that the mission succeeded.

`Stop` asks at most once per turn and honors `stop_hook_active`; it cannot trap the
agent in a checkpoint loop. If the agent cannot produce a fresh complete packet,
automatic launch is deferred and the previous valid packet is retained. Missing
launchers, changed artifacts and exhausted launch caps are recorded in `last_issue`;
they do not cause repeated blocking Stop errors. The hook retries no more than once
per user turn. Explicit `rotate` still reports the actionable error directly.

## Early context and compaction

When an actual host integration exposes fresh resident-context telemetry, record it
using `telemetry --session <id> --file <measurement.json>`. Required fields:

```json
{
  "session_id": "actual-observed-session",
  "used_tokens": 10000,
  "boundary_tokens": 30000,
  "next_turn_bound": 4000,
  "handoff_reserve": 5000,
  "observed_at": 0,
  "source": "Name the actual measurement source"
}
```

These numbers are schema examples, not defaults. Replace `observed_at` with the
actual Unix timestamp and every value with supported evidence. Never infer the
boundary from a model name, cumulative billing totals, or a guessed percentage.
There is no bundled generic transcript parser pretending that unstable formats
are reliable telemetry. Measurements older than 60 seconds are unusable.

With valid exact-session evidence, `PreToolUse` requests handoff when
`used + 2 * next_turn_bound + handoff_reserve >= boundary`. It denies one ordinary
call in the turn and allows checkpoint/helper calls to prepare rotation. This is
cooperative prompting; do not retry the denied large operation as a workaround.
When telemetry is absent, the configured user-turn budget and early checkpoints
provide a disclosed best-effort fallback. They cannot guarantee two turns before
an unobservable compaction threshold.

`PreCompact` is a last-chance event: a fresh prepared packet can trigger rotation.
Codex supports stopping compaction; Claude's event cannot guarantee blocking it.
The bridge never opens a successor from a stale or missing packet merely to claim
that an automatic handoff occurred.

## Recovery, privacy, and limitations

`status` reports ownership, last issue, launch attempts, pending candidate and
observed hook events. A manually supplied fixture is not evidence that your real
host ran the hook. Validate a harmless startup/checkpoint/rotation on your machine
before relying on automatic behavior.

`disarm --session <owner>` stops automatic continuation but does not silently release
a pending candidate or erase ownership. After confirming all other mission sessions
and background writers have stopped, use `recover --session <actual-id> --reason
"what was verified" --all-other-sessions-stopped`. This is an explicit operator
attestation, not an OS process detector. It retains the launch counter. An ambiguous
launch must be investigated, never retried automatically. Start a new explicitly
configured mission scope when the prior mission is finished.

The coordinator is a cooperative single-writer guard, not a security sandbox.
Host hooks may not cover every specialized tool, and processes outside the host
can edit files. Existing jobs must actually be stopped before declaring
`writers_quiesced`. Required files are referenced in the same canonical worktree,
not copied to another provider. Nonce-bound startup prevents accidental duplicate
candidates; it is not authentication against somebody who controls the machine.

The lifecycle store lives under the private vault's `sessions/` folder, separately
from core semantic memory. Core JSON export/restore does not include live ownership
state. Back up closed lifecycle databases and immutable checkpoint files with the
vault; restoring them must require explicit recovery, not replaying a pending launch.
Do not put handoff state or hook configuration backups into a public repository.

The current bridge launches Claude Code and Codex **CLI** sessions. It does not
claim to open a ChatGPT web conversation or a Codex desktop task through private
APIs. Where documented native task tools are available, an agent can use the same
checkpoint/readback/one-owner protocol with those tools; that is a separate adapter.

## Primary interface references

- [Codex hooks](https://developers.openai.com/codex/hooks): lifecycle events, discovery, trust, blocking behavior.
- [Claude Code hooks](https://code.claude.com/docs/en/hooks): lifecycle input/output and stop-loop behavior.
- [Codex CLI](https://developers.openai.com/codex/cli/reference): native startup prompt.
- [Session Handoff source](https://github.com/kingju1c3/session-handoff/tree/5b55592b8c946e9e74c772258ccbd687d9743779): adopted lifecycle design.

These interfaces were checked on 2026-09-19. Real host operation and account
permissions must still be verified locally; unit fixtures do not establish that.
