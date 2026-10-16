---
name: continuity
description: "Session continuity for coding agents, local or cloud, in one skill. Invoke once. Local mode (Claude Code terminal/desktop or Codex with the continuity runtime) stays quiet until measured context nears the limit, then alerts 'Compaction is imminent', has the agent write a lossless handoff, and starts a fresh successor BEFORE compaction in a new git worktree inside the same checkout, labelled with a unique sequential identifier ('Session FE 1.1', '1.2'…); the PreCompact hook is the backstop. Cloud mode (Claude Code on the web, cloud workspaces, Claude app) writes verified handoffs at milestones and, on concrete triggers, alerts 'Compaction is imminent' and hands over to the next sequential session (1.1, 1.2…) on a new worktree branch named for that version (e.g. continuity/fe-session-1.1). Use whenever the user wants continuity, a handoff, a fresh session that picks up where this one left off, or protection against losing work to compaction."
hooks:
  UserPromptSubmit:
    - hooks:
        - type: command
          command: "if command -v continuity >/dev/null 2>&1; then continuity hook --host claude; fi"
          timeout: 10
  PostToolUse:
    - matcher: "Write|Edit|MultiEdit|NotebookEdit|Bash|PowerShell"
      hooks:
        - type: command
          command: "if command -v continuity >/dev/null 2>&1; then continuity hook --host claude; fi"
          timeout: 10
  PreCompact:
    - matcher: "manual|auto"
      hooks:
        - type: command
          command: "if command -v continuity >/dev/null 2>&1; then continuity hook --host claude; fi"
          timeout: 25
          statusMessage: "Continuity: COMPACTION IMMINENT — creating the successor worktree as the handoff…"
  PostCompact:
    - matcher: "manual|auto"
      hooks:
        - type: command
          command: "if command -v continuity >/dev/null 2>&1; then continuity hook --host claude; fi"
          timeout: 10
---

# /continuity

Continuity is a **passive boundary-transfer protocol**.

The intended behavior is:

```text
INVOKE ONCE
    ↓
ARM EXACT CURRENT SESSION
    ↓
STAY PASSIVE DURING NORMAL WORK
    ↓
MEASURED CONTEXT REACHES THE HAND-OVER THRESHOLD (default 75%)
(backstop: the host's PreCompact hook, if the early trigger never fired)
    ↓
ALERT USER: "⚠️ Compaction is imminent — creating the successor worktree"
    ↓
AGENT WRITES THE LOSSLESS HANDOFF (it still holds the whole conversation)
    ↓
`continuity handover`: CAPTURE UNCOMMITTED WORK + CREATE THE WORKTREE
IN THIS SAME CHECKOUT + START THE SUCCESSOR THERE — ALL BEFORE COMPACTION
labelled "Session <name> 1.1" (then 1.2, 1.3 …)
    ↓
SUCCESSOR IS TOLD IT CONTINUES "Session <name> 1.0"
    ↓
SUCCESSOR VERIFIES SOURCE + RESUMES
```

The skill must not continuously interrupt the session, repeatedly inject memory, or create a checkpoint after every turn.

## Hard rules (both modes; these override anything below)

1. **Hand over BEFORE compaction, never after.** The successor worktree is created and the successor started while this session still holds its full context. A hand-over after compaction works from a lossy summary; it is a recovery, not continuity.
2. **Alert the user first, in plain words.** The first line the user sees is: `⚠️ Compaction is imminent. I'm creating a new git worktree (continuity/<slug>-session-<next>) in this same checkout and handing the work to Session <Name> <next>.` Then do it, in the same turn, without waiting for a reply.
3. **Same environment, same folders, same permissions: a clone of the predecessor.** The PREDECESSOR creates the successor's worktree itself, in the exact same folder and environment it is running in: `<main checkout>/.claude/worktrees/continuity-<slug>-session-<next>`, on the same machine or container, inside the same main checkout, next to its own worktree. The successor runs with the same permissions, permission mode, settings, environment variables, tools, MCP servers, plugins, skills, hooks and folder access as the predecessor, as its clone. Only the context is fresh. The successor is started in that folder. Never a fresh clone, a temp dir, another machine or another container, except as an announced fallback when no same-environment launch exists.
4. **Lossless.** The handoff lets a session with no access to this conversation continue without asking anything. It contains the goal and done condition; the user's instructions and standing preferences, quoted; every decision with its reason; every open thread; failed attempts and why they failed; verified vs. assumed state with exact SHAs, paths, commands, IDs, URLs and test counts; and the single next action. Every uncommitted and untracked change goes into the worktree. Nothing is summarised away to save space.
5. **Report only what happened.** Name the worktree path, branch, successor label and launch id exactly as the runtime or tool returned them. Never announce a worktree, an applied patch or a started session that was not confirmed.
6. **One owner, and ownership moves only on proof.** This session stays the owner (it keeps its lease and keeps working) until the successor is **confirmed started**: the start tool returned a session id and you ran `continuity confirm-successor --successor-session <id>`, or the successor armed in its worktree (which confirms automatically, however it was started). Only then do you stop and point the user at it. Saying "I handed over" and going quiet while no successor runs is the failure this rule exists to prevent: on 2026-10-16 two sessions did exactly that and the user had to rescue the work by hand.
7. **The successor is a visible sidebar clone, created automatically.** Since v0.8 the runtime never starts `claude --bg` unless the session was armed with `--background-successor`. `continuity handover` (and the PreCompact backstop) prepares the clone: the worktree, the carried-over work and the handoff. It then prints a `start` block and a `next` instruction. In the Claude desktop app you then **call `mcp__ccd_session__start_session` with exactly the printed `start.args`**: `initiation: "user_asked"` (arming /continuity is the user's standing request for the successor), `title: "Session <label> <next>"`, `context: "fresh"`, `cwd: <the new worktree>`, `use_worktree: false`, and the bootstrap `prompt`. **Do not pass `permission_mode`, `model` or `effort`**, so the app gives the successor this session's own permissions and settings. The successor then appears in the app's sidebar (and on the user's phone) in the new worktree, as a clone. Report the session id the tool returns, then run `continuity confirm-successor --successor-session <id>`. **The app refuses starts on a turn that another session's message or an automated event began** (a cross-session message, a side-session note, a task notification). On such a turn, prepare everything, tell the user the successor is prepared but not started (folder + prompt as a copy-paste block), and ask them to reply so you can start it on their turn. You remain the owner meanwhile. Only when that tool doesn't exist (a plain terminal) do you give the user the folder and a copy-paste start message instead. A background session does not appear in the sidebar and can't be reached from the phone; on 2026-10-14 a lead session ran for hours that the user could not talk to. If a background successor exists anyway (an older runtime, or `--background-successor`), say so in the same turn and stop it (`claude stop <id>`) or tell the user how to reach it (`claude attach <id>`, then `/remote-control`). Never leave two owners running.

## Pick the mode first (one skill, two modes)

Decide before anything else, from this session's own shell:

```bash
command -v continuity && echo "session=${CLAUDE_CODE_SESSION_ID:-none} remote=${CLAUDE_CODE_REMOTE:-0}"
```

- **Local mode**: the `continuity` command exists, a session id is present, and `CLAUDE_CODE_REMOTE` is not set (Claude Code in a terminal or the desktop app on your own machine), or the host is Codex with the runtime installed. Follow the rest of this file: arm once, stay passive, transfer at the real PreCompact hook into a new worktree.
- **Cloud mode**: anything else, such as Claude Code on the web, a cloud workspace, a claude.ai chat, or a machine without the runtime. Follow **Cloud mode** at the end of this file: verified handoffs at milestones, and a hand-over to a new session *before* compaction, because there is no hook to catch the exact moment.

Tell the user in one line which mode is active and why. A runtime installed on some other machine does not count: hooks and session identity belong to the host running this conversation. To get local mode on a machine, install the runtime: `pipx install git+https://github.com/kingju1c3/continuity.git`.

## Host invocation syntax

Use the host's native explicit skill syntax:

- **Claude Code:** `/continuity`
- **Codex:** `$continuity`

Current Codex skill documentation defines explicit skill invocation with `$<skill-name>`. Do not depend on deprecated custom-prompt slash aliases to fake `/continuity` in Codex. The protocol and runtime remain the same after either host-native invocation.

## Invocation contract

When this skill is invoked, **the first operational action** is to arm the exact current session:

```bash
continuity arm \
  --host auto \
  --goal "<current user objective in one concise sentence>" \
  --instructions "<critical constraints that must survive the handoff>" \
  --label "<short name for this line of work, e.g. SiteBooked>" \
  [--context-window <tokens>] [--handoff-at 0.75] [--generation 1.2]
```

Pass `--generation` when this session continues a chain that started elsewhere (a cloud session, a hand-started successor): it is told its label, e.g. "You are Session FE 1.2", so arm with `--label FE --generation 1.2` and its successor becomes 1.3.

Pass `--context-window` when the host's real context window is known (for example `1000000` for a 1M-context model). Without it the runtime uses `CONTINUITY_CONTEXT_WINDOW` if set, otherwise 1M when the model id says `[1m]` or measured usage has already passed 200k, otherwise 200k. A window that is too small hands over early, which is the safe direction. `--handoff-at` is the fraction of the window at which the hand-over starts (default 0.75).

Do this before substantive new work. `--label` names the session chain: this session is **`Session <label> 1.0`**, its successors **`Session <label> 1.1`**, **`1.2`**, **`1.3`** and so on. Without `--label` the project folder name is used. A successor inherits the label and the next number automatically; never re-label it by hand. Every instance gets a unique identifier in sequential order: a number issued under a label is never reused in this project, so a second chain armed as `FE`, or `FE` armed again later, continues at the next free number (`Session FE 1.3`, `1.4` …), never a second `1.0`.

If the `continuity` console command is unavailable, read `.continuity/enabled.json` and use the recorded `python` interpreter to invoke the same runtime:

```bash
"<recorded-python>" -m continuity arm \
  --host auto \
  --goal "<current user objective>" \
  --instructions "<critical constraints>"
```

Do not guess an interpreter path. If the enable marker is missing or its interpreter no longer exists, report that host integration needs repair.

Then tell the user, briefly, that Continuity is armed and will remain passive until a compaction/transfer boundary.

Do **not** keep invoking the skill manually each turn. The host hooks remain registered for the session where supported, and the runtime arm state is durable.

In Claude Code (terminal or the desktop app) arming works even when no SessionStart hook ran: the runtime takes the exact session id Claude Code exports as `CLAUDE_CODE_SESSION_ID` (the same id every hook receives), takes the project lease, and writes `.continuity/enabled.json` plus a `.continuity/.gitignore` so the skill's hooks act on this project and handoffs never get committed. Arming is the opt-in; nothing else enables a project silently.

If arming fails because no exact host session identity exists, report the failure instead of inventing a session ID. Run:

```bash
continuity doctor
continuity status
```

and repair host integration if necessary.

## Passive mode

Once armed:

- ordinary prompts: no Continuity commentary;
- ordinary tool calls: no Continuity commentary;
- edits/shell operations: silently mark structural state stale;
- ordinary Stop/turn boundaries: no checkpoint nag;
- durable memory is available on demand, not injected every turn;
- source and Git remain canonical.

### Two triggers: measured early hand-over, PreCompact backstop

**1. Early hand-over (primary, Claude Code).** On every user prompt and every edit/shell tool call, the hook reads the session's own transcript and takes the **measured** context size: the prompt tokens (`input + cache_creation + cache_read`) of the last main-thread assistant turn. When that reaches the threshold (default 75% of the window), the hook:

- shows the user `⚠️ Compaction is imminent — context is at <used> of ~<window> tokens (<pct>). Continuity is creating a new git worktree (<branch>) in this same checkout and handing the work to Session <Name> <next> before compaction.`
- tells the agent to hand over now. On the first crossing it fires at once; after that it repeats on every user turn until the hand-over happens.

When you (the agent) receive `CONTINUITY: COMPACTION IS IMMINENT`, do exactly this, in this turn, before any other work:

1. Put the alert to the user as the first line of your reply (Hard rule 2).
2. Finish or safely pause the step in flight. Never leave a half-written file or a half-pushed branch.
3. Write the lossless handoff to `.continuity/HANDOFF.md` (format: **Handoff format** below, shared by both modes; Hard rule 4).
4. Run `continuity handover --handoff-file .continuity/HANDOFF.md`. It embeds your narrative at the top of the handoff, captures the work in progress, creates the successor worktree in this same checkout and environment (Hard rule 3), applies the uncommitted changes and copies the untracked files, and prints a `start` block plus a `next` instruction. This session stays the owner (status `successor_starting`, lease kept). It does **not** start a background session (Hard rule 7).
5. **Create the sidebar clone now**: call `mcp__ccd_session__start_session` with the printed `start.args`, unchanged (no `permission_mode`, `model` or `effort`; Hard rule 7). In a plain terminal, give the user the folder and the prompt as a copy-paste block instead.
6. **Confirm it**: run `continuity confirm-successor --successor-session <the returned id>`. Report the real state (worktree, branch, successor name, session id), then stop working in this session.

**If the start is refused or impossible** (a turn begun by another session's message, no tool, the user declines): you are still the owner. Say so plainly, give the folder and prompt, and keep working. On every later user turn the hook reminds you, with the exact start call; starting it then is allowed. Re-running `continuity handover` re-prints the same start (never a second worktree). If the user decides to keep working here, run `continuity handover --cancel`. If the successor is opened by hand, its arming retires this session automatically.

The usage number is measured; the window is configured or inferred. Say which one it is when you report it. If the transcript can't be read, the early trigger stays silent and the backstop applies.

**2. PreCompact (backstop).** If compaction arrives before the early hand-over happened, the host's PreCompact hook does the same transfer mechanically. That happens before compaction, but without your narrative, so it is less complete. Treat a backstop transfer as a sign that `--context-window` or `--handoff-at` should be lower.

## Boundary alert

At an armed PreCompact the hook blocks the first compaction, so the transfer is captured with full context, and tells the user plainly: compaction is imminent, a handoff was captured, a worktree was created (branch `continuity/<label-slug>-session-<N>.<M+1>`), and `Session <Name> <N>.<M+1>` is prepared. It blocks once per state, never in a loop. If a prepared successor still hasn't started, the next PreCompact holds compaction one more time with the start call, then lets compaction proceed with this session still the owner. Read `continuity/protocol/compaction.md`.

## Automatic boundary handoff

At the hand-over (`continuity handover`, kind `agent-handover`, with the agent's narrative first) or at PreCompact (kind `automatic-boundary`), Continuity creates a handoff.

It captures, mechanically:

- exact project root;
- exact host;
- predecessor session ID;
- active goal and surviving instructions from arm state;
- Git branch;
- Git HEAD;
- working-tree status;
- diffstat;
- changed-file candidates;
- fresh structural index state;
- recent durable project memories, bounded in size;
- a bounded best-effort tail of the host transcript when a transcript path is exposed;
- verification warnings and provenance labels.

Transcript material is evidence, not source-of-truth. Host transcript formats are not treated as a stable API.

The handoff is mirrored to:

```text
.continuity/LATEST.md
.continuity/LATEST.json
.continuity/handoffs/
```

and stored in the Continuity database.

Read `continuity/protocol/checkpoint-handoff.md`.

## Session chain and worktree successor

Before compaction (at `continuity handover`, or at the PreCompact boundary as backstop), Continuity always:

1. **Captures a detailed, lossless handoff.** On top of goal, instructions, Git branch/HEAD, working tree, diffstat, changed files, index, durable memories and transcript tail, it stores the **work in progress**: a full binary patch of every uncommitted tracked change against HEAD (`.continuity/handoffs/<stamp>-<session>.patch`), the list of untracked files, and the recent commits. Nothing in the predecessor's tree is staged, stashed or committed.
2. **Creates a new git worktree for the successor** at `<main checkout>/.claude/worktrees/continuity-<label-slug>-session-<N>.<M+1>` (where Claude Code and the desktop app keep worktrees; a chain of successors stays side by side, never nested; the folder is added to `.git/info/exclude` if not already ignored), in the same environment as the predecessor (same machine, same main checkout; never a fresh clone or another machine), on branch `continuity/<label-slug>-session-<N>.<M+1>` (the successor's own version, written with its dot: `continuity/sitebooked-session-1.1`, then `-session-1.2`, `-session-1.3`), from the predecessor's HEAD. It applies the patch there, copies the untracked files (up to 10 MB each, 100 MB total; anything skipped is named), and copies `.continuity/enabled.json` and the handoff (`LATEST.md`/`LATEST.json`) into it. The predecessor's own tree is untouched; merge the successor branch back when the work is done.
3. **Hands the agent the start of the successor as a sidebar clone** (Hard rules 3 and 7), named **`Session <label> <N>.<M+1>`**: the `start` block is a ready `mcp__ccd_session__start_session` call (cwd = the worktree, `use_worktree: false`, permission mode and settings inherited). The agent makes that call, so the successor appears in the desktop app's sidebar with the same permissions, permission mode, settings, env, tools, MCP servers, plugins, skills and folder access. Never as a background `claude --bg` session unless the session was armed with `--background-successor`. In a plain terminal the user opens the worktree folder and pastes the bootstrap prompt, which says, in substance:

   > You are `Session <label> 1.1`. You are picking up exactly where `Session <label> 1.0` (session id …) left off: it reached its context limit and handed its work to you just before compaction. Continue its goal; do not start over. Goal: … You are in a new git worktree at … on branch …; the predecessor's uncommitted changes were applied (or: how to apply them). Read the handoff fully, run `continuity resume` and `continuity orient`, verify, then tell the user in one line that `Session <label> 1.1` is continuing `Session <label> 1.0`'s work, and report readiness.

4. **Tells the user** in the boundary alert: the successor's label, its worktree path and branch, whether the uncommitted work was applied, and that it now appears in the sidebar (or which folder to open).

**Workspace trust (background mode only).** `claude --bg` refuses to start in a workspace the user has never trusted. A worktree inherits trust from its repository, so this works for any repo the user has opened in Claude before; in a never-opened repo the launch fails with Claude's own message. Continuity confirms the launch from `claude --bg`'s output (`backgrounded · <id>`); if that line is missing it reports the failure verbatim, keeps the handoff and the worktree, and restores the predecessor's lease. It never announces a successor that did not start.

If the project isn't a Git repository with at least one commit, or the worktree can't be created, the successor starts in the project root instead and the alert and prompt say why. If the patch doesn't apply cleanly, the successor is told the exact `git apply` command for the saved patch. Never claim a worktree, an applied patch or a launched successor that the runtime did not report.

## Successor behavior

### Claude Code

The runtime prepares a visible sidebar clone in the new worktree, and the agent starts it (Hard rules 6 and 7). `--background-successor` restores the old `claude --bg` launch; it needs the `claude` executable and a non-remote environment.

The successor's bootstrap prompt has it:
1. invoke `/continuity`, which **arms it in its worktree**. Arming from the prepared hand-over inherits the chain (label, next number, goal, instructions) and retires the predecessor. Don't skip it: the desktop app may not pass the session title to hooks, so arming is the reliable signal;
2. read `.continuity/LATEST.md`;
3. run `continuity resume` and `continuity orient`;
4. verify root, branch, HEAD, working tree and relevant source;
5. tell the user in one line that it continues the predecessor, and report readiness before modifying files.

### Codex

Continuity captures the same detailed handoff and, when the local Codex CLI is available, automatically creates a **fresh persisted background Codex bootstrap thread** using non-interactive `codex exec --json`.

The bootstrap runs read-only by default and is instructed only to verify the handoff/source and report readiness. Continuity captures the emitted `thread.started` ID when available.

The user alert then gives the resume path:

```bash
codex resume <successor-thread-id>
```

A command hook still cannot safely open an interactive TUI window by itself. The distinction matters: Continuity can create the fresh resumable Codex thread automatically, while attaching an interactive terminal to that saved thread remains a user/host UI action.

If the Codex executable is unavailable, Continuity falls back to staging a pending successor and tells the user to start `codex` from the project. The first fresh session inherits that pending handoff.

A transcript fork is not preferred because the purpose is fresh context with durable state, not a duplicate of the predecessor transcript.

Read `continuity/protocol/successor-transfer.md`.

## Successor verification

A successor is not allowed to treat the handoff as current truth without verification.

Authority order:

1. current source + Git state;
2. fresh structural evidence;
3. current durable memory;
4. semantic/automatic handoff;
5. mechanical freezes and host summaries.

Before editing, successor must verify:

- project root;
- branch;
- HEAD;
- working-tree status;
- relevant files;
- whether another session owns the project.

Use:

```bash
continuity resume
continuity orient
continuity status
```

Surface drift before continuing.

Read `continuity/protocol/session-open.md`.

## Manual control

### Inspect arm state

```bash
continuity status
```

### Disable passive boundary transfer

```bash
continuity disarm
```

### Opt back into a background successor (not recommended)

```bash
continuity arm --host auto --goal "..." --background-successor
```

The successor then starts with `claude --bg`: it is hidden from the desktop app's sidebar and the phone until someone runs `claude attach <id>`.

### Arm without automatic successor launch

```bash
continuity arm \
  --host auto \
  --goal "..." \
  --instructions "..." \
  --no-auto-successor
```

This still captures and alerts at the boundary, but stages a manual fresh-session transfer.

### Explicit semantic checkpoint

Automatic boundary capture is designed for context-loss prevention. For an intentional transfer before compaction, a richer semantic checkpoint is still useful:

```bash
continuity checkpoint \
  --goal "..." \
  --instructions "..." \
  --discoveries "..." \
  --accomplished "..." \
  --next-steps "..." \
  --relevant-files "..." \
  --verification "..."
```

## Durable memory

Memory is available when needed:

```bash
continuity recall "topic"
continuity remember "Title" "Durable content" --kind decision --topic architecture/example
continuity memory-history architecture/example
```

Save only expensive-to-rediscover knowledge:

- architectural decisions;
- root causes;
- durable constraints;
- non-obvious conventions;
- important failed approaches;
- explicit user choices.

Do not save:

- credentials;
- auth tokens;
- private keys;
- raw full transcripts;
- temporary logs;
- unsupported guesses.

Read `continuity/protocol/memory-write.md`.

## Structural context

Use the smallest sufficient source:

1. exact current source;
2. Continuity built-in index;
3. Graft when installed;
4. Graphify when installed/indexed;
5. broad repository traversal.

Commands:

```bash
continuity query "where is X implemented?"
continuity find SomeSymbol
continuity graph module/name
continuity index
```

Armed PostToolUse hooks silently mark structural state stale. Boundary capture rebuilds the local structural index before writing its handoff.

Read `continuity/protocol/retrieval.md`.

## Session ownership

Continuity keeps one active lease per project.

Never silently steal a live lease.

Explicit abandoned-owner recovery:

```bash
continuity recover --host <host> --expected-owner <old-session-id>
```

A predecessor is marked `transferred` only when its successor is confirmed (`continuity confirm-successor`, or the successor arming). From then on new prompts in it are blocked, so two sessions don't keep modifying the same work. While a successor is merely prepared (`successor_starting`), the predecessor is never blocked.

Read `continuity/protocol/conflict-recovery.md`.

## Host lifecycle model

### Global host integration

Global hooks should do only what must happen before the skill is invoked:

- SessionStart: exact session registration/lease bookkeeping;
- SessionEnd: objective freeze/end/release.

### Claude skill-scoped hooks

After `/continuity` is invoked, this skill's hooks remain active for the session:

- UserPromptSubmit — normally silent; blocks a transferred predecessor;
- PostToolUse — silently marks structure dirty;
- PreCompact — alert, capture, transfer;
- PostCompact — preserve compact state only if compaction actually occurs.

### Codex dispatch hooks

Codex lifecycle dispatchers may be installed globally, but expensive behavior is gated by the durable arm state. An unarmed session is effectively a no-op beyond exact session bookkeeping.

## Failure behavior

Fail closed around identity and ownership:

- malformed hook input → no mutation;
- missing SessionStart ID → no lease mutation;
- unarmed session → no PreCompact transfer;
- lease conflict → surface, do not steal;
- Claude launch failure, or a refused or never-made start → handoff and worktree remain durable, the predecessor stays the owner, and the hook keeps reminding it on user turns;
- unreadable transcript → record unavailable, do not crash;
- stale handoff → show drift;
- missing source evidence → say unknown;
- host cannot open a fresh interactive successor → stage transfer and tell the user exactly what remains manual.

Read `continuity/protocol/security.md`.

## Installation / repair

```bash
continuity install --agents claude,codex
continuity install --agents claude,codex --dry-run
continuity repair --agents claude,codex
continuity doctor
continuity status
```

Remove only Continuity-owned integration:

```bash
continuity uninstall --agents claude,codex
```

## CLI map

- `arm` — activate passive boundary continuity for exact current session (`--label` names the session chain).
- `handover [--handoff-file F]` — hand over now, before compaction: embed the agent's handoff and prepare the successor worktree in this checkout. It prints the start call; this session stays the owner until confirmed. Re-running it re-prints the same start.
- `handover --cancel` — the user chose to keep working here: undo a prepared hand-over (no more early-warning nags; PreCompact stays as backstop).
- `confirm-successor --successor-session ID` — the successor really started: only now is this session transferred.
- `disarm` — disable it.
- `status` — inspect lease, arm state, pending successor, handoff, index.
- `start` — manual session registration.
- `end` — explicit manual session release.
- `recover` — expected-owner recovery.
- `remember` / `recall` / `memory-history` — durable memory.
- `index` / `find` / `graph` / `query` — structural retrieval.
- `checkpoint` — explicit semantic handoff.
- `resume` / `orient` — restore and verify.
- `install` / `repair` / `uninstall` / `doctor` — integration maintenance.
- `hook` — host lifecycle dispatcher.

## Protocol references

Read only what is relevant:

- `continuity/protocol/passive-mode.md`
- `continuity/protocol/compaction.md`
- `continuity/protocol/successor-transfer.md`
- `continuity/protocol/cloud-mode.md`
- `continuity/protocol/session-open.md`
- `continuity/protocol/checkpoint-handoff.md`
- `continuity/protocol/retrieval.md`
- `continuity/protocol/memory-write.md`
- `continuity/protocol/conflict-recovery.md`
- `continuity/protocol/security.md`

## Integrity invariant

Continuity is a durable coordination protocol, not literal model identity persistence.

It exists to make a fresh agent capable of continuing verified work with minimal rediscovery.

**Fresh source beats old narrative. Evidence beats continuity theater.**

## Cloud mode

Use it when the runtime is absent or the host exposes no session id: Claude Code on the web, cloud workspaces, claude.ai chats. There is no compaction hook there, so:
- write verified handoffs at milestones (merge, push, deploy, blocker, stepping away);
- hand over to `Session <Name> <next>` BEFORE compaction, on concrete triggers: measured usage ≥ 75% where you can read the transcript, a host context notice, about 120 tool calls, about 40 user turns, or about 25 large outputs;
- commit and push work in progress at every milestone, so a surprise compaction loses nothing.

**Read `continuity/protocol/cloud-mode.md` before acting in cloud mode.** It has the exact alert, the worktree commands, the start options and the successor's steps. The same hard rules apply, including rule 6: you remain the owner until the new session is confirmed running.

## Handoff format

Filename: `<Project>-<Topic>-Handoff-<YYYY-MM-DD>-v<N>.md`, incrementing N from the previous handoff.

Required sections:

- **Session:** this session's label and, at a hand-over, the successor's label ("Session <Name> 1.1 → 1.2").
- **Supersedes:** exact name of the prior handoff, or "none".
- **Continuity mode:** cloud, and why `/continuity` was unavailable.
- **Goal and done condition.**
- **Verified state:** only facts backed by real tool output this session, with timestamps and SHAs/IDs/URLs.
- **Work in progress:** branch, HEAD, worktree branch holding uncommitted work, files changed, anything not carried over and why.
- **Locked decisions** (with reasons) and **Open decisions**.
- **User preferences and corrections** that must survive.
- **Next steps:** split into *Blocked on user* and *Ready (agent)*, each with exact commands and paths; mark the single next action.
- **Environment notes:** permission boundaries hit, tools that failed, where files live.

Never include credentials, tokens, private keys, or raw transcripts.
