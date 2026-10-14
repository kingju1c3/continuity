---
name: continuity
description: "Session continuity for coding agents, local or cloud, in one skill. Invoke once. Local mode (Claude Code terminal/desktop or Codex with the continuity runtime) stays quiet until the real pre-compaction hook, then captures a lossless handoff and starts a fresh successor in a new git worktree labelled with a unique sequential identifier ('Session FE 1.1', '1.2'…) Cloud mode (Claude Code on the web, cloud workspaces, Claude app) writes verified handoffs at milestones and, on concrete triggers, alerts 'Compaction is imminent' and hands over to the next sequential session (1.1, 1.2…) on a new worktree branch named for that version (e.g. continuity/fe-session-1.1). Use whenever the user wants continuity, a handoff, a fresh session that picks up where this one left off, or protection against losing work to compaction."
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
HOST SIGNALS PRECOMPACT
    ↓
ALERT USER BEFORE COMPACTION
    ↓
CAPTURE DETAILED, LOSSLESS HANDOFF (incl. uncommitted work)
    ↓
START FRESH SUCCESSOR IN A NEW GIT WORKTREE
labelled "Session <name> 1.1" (then 1.2, 1.3 …)
    ↓
SUCCESSOR IS TOLD IT CONTINUES "Session <name> 1.0"
    ↓
SUCCESSOR VERIFIES SOURCE + RESUMES
```

The skill must not continuously interrupt the session, repeatedly inject memory, or create a checkpoint after every turn.

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
  --label "<short name for this line of work, e.g. SiteBooked>"
```

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

The runtime waits for a **documented host boundary**, not a guessed token percentage.

### Why PreCompact is the trigger

The supported hosts do not expose one portable, stable live field saying “the session is exactly N% from compaction” on every turn.

Therefore Continuity uses the host's **PreCompact** lifecycle event: the reliable point immediately before compaction.

Do not claim an earlier warning was measured if the host did not expose such telemetry.

## Boundary alert

When an armed session reaches PreCompact, Continuity must alert the user before compaction proceeds.

The alert should communicate:

> COMPACTION IMMINENT — Continuity handoff boundary reached: compaction is about to occur. A detailed handoff was captured, a new git worktree was created as the handoff (branch `continuity/<label-slug>-session-<N>.<M+1>`), and work is transferring to the fresh successor `Session <Name> <N>.<M+1>`.

Where supported, the hook also emits a terminal notification/bell.

The first armed PreCompact is blocked so the current context is not compacted before the transfer is captured.

The predecessor must not enter an infinite block loop. Once ownership is transferred, it is marked `transferred`; subsequent work should occur in the successor.

Read `continuity/protocol/compaction.md`.

## Automatic boundary handoff

At PreCompact, Continuity creates an **automatic-boundary handoff**.

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

Before compaction (at the PreCompact boundary), Continuity always:

1. **Captures a detailed, lossless handoff.** On top of goal, instructions, Git branch/HEAD, working tree, diffstat, changed files, index, durable memories and transcript tail, it stores the **work in progress**: a full binary patch of every uncommitted tracked change against HEAD (`.continuity/handoffs/<stamp>-<session>.patch`), the list of untracked files, and the recent commits. Nothing in the predecessor's tree is staged, stashed or committed.
2. **Creates a new git worktree for the successor** at `<main checkout>/.claude/worktrees/continuity-<label-slug>-session-<N>.<M+1>` (where Claude Code and the desktop app keep worktrees; a chain of successors stays side by side, never nested; the folder is added to `.git/info/exclude` if not already ignored), on branch `continuity/<label-slug>-session-<N>.<M+1>` (the successor's own version, written with its dot: `continuity/sitebooked-session-1.1`, then `-session-1.2`, `-session-1.3`), from the predecessor's HEAD. It applies the patch there, copies the untracked files (up to 10 MB each, 100 MB total; anything skipped is named), and copies `.continuity/enabled.json` and the handoff (`LATEST.md`/`LATEST.json`) into it. The predecessor's own tree is untouched; merge the successor branch back when the work is done.
3. **Starts the successor in that worktree**, named **`Session <label> <N>.<M+1>`** (Claude Code: `claude --bg --name "Session <label> 1.1"`), with a bootstrap prompt that says, in substance:

   > You are `Session <label> 1.1`. You are picking up exactly where `Session <label> 1.0` (session id …) left off: it reached its context limit and handed its work to you just before compaction. Continue its goal; do not start over. Goal: … You are in a new git worktree at … on branch …; the predecessor's uncommitted changes were applied (or: how to apply them). Read the handoff fully, run `continuity resume` and `continuity orient`, verify, then tell the user in one line that `Session <label> 1.1` is continuing `Session <label> 1.0`'s work, and report readiness.

4. **Tells the user** in the boundary alert: the successor's label, its worktree path and branch, whether the uncommitted work was applied, and how to attach (`claude --resume "Session <label> 1.1"` or `claude agents`).

**Workspace trust.** `claude --bg` refuses to start in a workspace the user has never trusted. A worktree inherits trust from its repository, so this works for any repo the user has opened in Claude before; in a never-opened repo the launch fails with Claude's own message. Continuity confirms the launch from `claude --bg`'s output (`backgrounded · <id>`); if that line is missing it reports the failure verbatim, keeps the handoff and the worktree, and restores the predecessor's lease. It never announces a successor that did not start.

If the project isn't a Git repository with at least one commit, or the worktree can't be created, the successor starts in the project root instead and the alert and prompt say why. If the patch doesn't apply cleanly, the successor is told the exact `git apply` command for the saved patch. Never claim a worktree, an applied patch or a launched successor that the runtime did not report.

## Successor behavior

### Claude Code

When all of these are true:

- current host is local Claude Code;
- Continuity is armed;
- automatic successor is enabled;
- the `claude` executable is available;
- the environment is not marked remote;

Continuity attempts to launch a **fresh named background Claude session in a new git worktree** at the boundary (see *Session chain and worktree successor*).

The successor receives a bootstrap prompt instructing it to:

1. invoke `/continuity`;
2. know that it is `Session <label> <N>.<M+1>` continuing `Session <label> <N>.<M>`;
3. read the handoff (`.continuity/LATEST.md` in its worktree);
4. run `continuity resume`;
5. run `continuity orient`;
6. verify project root, branch, HEAD, working tree, and relevant source;
7. tell the user it is continuing the predecessor's work, and report readiness before modifying files.

The predecessor alert includes the successor name and the command to attach:

```bash
claude --resume "Session <label> 1.1"
```

If background launch fails, Continuity preserves the handoff and restores predecessor ownership rather than pretending a successor exists.

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

Once a predecessor successfully transfers, that predecessor is marked `transferred`. New prompts in it may be blocked so two sessions do not continue modifying the same project under one continuity chain.

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
- Claude launch failure → handoff remains durable and predecessor lease is restored;
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

Cloud mode exists because local mode depends on a local runtime (`continuity` CLI), an exact host session ID, and a PreCompact hook, none of which exist in the Claude app or cloud workspaces. Cloud mode keeps the parts of the protocol that don't need them: a durable, lossless, verified handoff and a labelled fresh session that resumes from it.

It cannot capture at the exact compaction instant: there is no hook. It transfers **before** compaction instead, as soon as the conversation is long enough that fidelity is at risk. Say so once, when invoked. Never claim a measured context percentage the host did not expose.

### On invocation

1. Check for the runtime in this session's own shell (`command -v continuity`). If it is present AND the host exposes an exact session id (Claude Code, terminal or desktop app, exports `CLAUDE_CODE_SESSION_ID`), tell the user to use `/continuity` instead and stop: it arms without any prior install and hands over at the real PreCompact hook. A CLI installed on a linked remote computer does not count: hooks and session identity belong to the host running this conversation. Never invent a session ID.
2. Tell the user in one line that cloud mode is active: there is no compaction hook here, so handoffs are written at milestones and the hand-over to a new session happens before compaction, not at it.
3. **Work out this session's label.** Sessions in one line of work form a chain: **`Session <Name> 1.0`**, then **`1.1`**, **`1.2`**, **`1.3`** … If the session was started by a predecessor, its first message names it ("You are Session SiteBooked 1.2 …"): keep that label. Otherwise it is a new instance: `<Name>` is the project or topic (ask only if it's genuinely unclear), and its number is the next one never used before under that name. Check the existing handoffs and session or chat titles for `Session <Name> …`, and take the number after the highest one found (`Session <Name> 1.0` only if none exists). Identifiers are never reused, so two sessions never share one. State the label in that same line.
4. Find the latest existing handoff. If a Project is attached, search its docs for `Handoff`; otherwise check the working directory. Read it and note its version.
5. Verify it against live state (Git branch/HEAD/working tree, deployed version, open PRs/CI). Surface drift.
6. Write a fresh handoff now if none exists for the current work or the latest is stale.

### Passive otherwise

No commentary on ordinary turns. Write or update the handoff only at a milestone:

- merge, push, deploy, release, or another state change on a shared system;
- a discovered blocker or changed plan;
- before the user steps away or before handing off to scheduled/unattended work;
- when the user asks;
- **before compaction**: see **Pre-compaction hand-over is mandatory** below. Before degradation, never after.

### Pre-compaction hand-over is mandatory

A cloud host compacts without warning, so waiting for "it feels long" fails: the context is summarized and the successor never exists. Treat the hand-over as a hard rule with concrete triggers.

**Triggers.** Hand over as soon as ANY of these is true. Count from invocation, or from the last hand-over:

1. The host shows any notice about context, conversation length or compaction.
2. About **120 tool calls**, or about **40 user turns**.
3. About **25 large tool outputs** (full logs, whole files, test-suite dumps over ~200 lines each).
4. The user says they are stepping away while long work continues (CI watching, long test runs).

These numbers are conservative defaults, not measurements. The host exposes no context percentage, so never claim one. When in doubt, hand over early: a spare hand-over costs minutes, and a missed one loses the session.

**Safety net (do it at invocation and at every milestone).** Commit and push work in progress so a surprise compaction loses nothing. If the project uses a feature branch, pushing it is enough. Otherwise use the successor branch `continuity/<name-slug>-session-<next>`. Update the handoff doc at the same time.

**Alert first, in exactly this form, before any hand-over step:**

> ⚠️ **Compaction is imminent.** I'm creating a new git worktree as the handoff: branch `continuity/<name-slug>-session-<next>` (for example `continuity/fe-session-1.1`). It holds every uncommitted change and the handoff `<handoff file name>`. **Session <Name> <next>** will continue from it. Please don't start new work in this session after this.

Then run **Hand-over to a new session** below, in the same turn, without waiting for a reply.

**Version labels.** The successor's version is the next sequential number after this session's: 1.0 → 1.1 → 1.2 → 1.3. The same number appears in three places: the session title (`Session FE 1.1`), the branch (`continuity/fe-session-1.1`) and the worktree folder (`.claude/worktrees/continuity-fe-session-1.1`). Never skip a number, and never reuse one (see *On invocation*, step 3).

**If compaction already happened** (the conversation opens with a summary that says it was continued from an earlier, longer one): tell the user in the first line that compaction occurred before a hand-over, then run the alert and the hand-over above before taking on new work. Finishing a step already in flight (a push, a CI fix) is fine.

### Hand-over to a new session (before compaction)

Do all of it in one go, in this order, and report each step's real result.

1. **Write the lossless handoff** (format below), labelled for both sides: "from `Session <Name> 1.1` to `Session <Name> 1.2`". Lossless means a fresh session could continue with no access to this conversation: every decision and its reason, every open thread, exact file paths, commands, IDs, URLs, versions, test results with numbers, what was verified versus assumed, the user's standing preferences and corrections, and the exact next action.
2. **Preserve all work in progress on a new worktree branch** (Git projects). Never stage, stash, commit or reset in the current tree:
   ```bash
   N="<name-slug>-session-1.2"                          # the successor's version, dot kept: 1.1, 1.2, 1.3 …
   MAIN="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"   # main checkout, so worktrees never nest
   W="$MAIN/.claude/worktrees/continuity-$N"
   git check-ignore -q "$MAIN/.claude/worktrees/x" || echo ".claude/worktrees/" >> "$(git rev-parse --git-common-dir)/info/exclude"
   git worktree add -b "continuity/$N" "$W" HEAD
   git diff --binary HEAD > "/tmp/$N.patch"            # every uncommitted tracked change
   git -C "$W" apply --binary "/tmp/$N.patch"
   git ls-files --others --exclude-standard -z | tar --null -T - -cf - | tar -xf - -C "$W"   # untracked files (portable: GNU and BSD/macOS)
   git -C "$W" status --short                           # show the user what was carried over
   # put the handoff doc in the worktree too, then:
   git -C "$W" add -A
   git -C "$W" commit -m "continuity: work in progress handed to Session <Name> 1.2"
   git -C "$W" push -u origin "continuity/$N"
   ```
   A cloud session is a fresh checkout: anything not pushed is lost. If pushing isn't allowed, say so and attach the patch and handoff as files instead. Skip secrets and files that look like credentials, and name what you skipped.
3. **Start the new session** labelled `Session <Name> 1.2`:
   - If a session-creation tool exists (e.g. `create_session` in Claude Code on the web), create it on the same repository at branch `continuity/<name-slug>-session-1.2`, with title `Session <Name> 1.2` and the bootstrap prompt below. Report the new session's ID or link exactly as the tool returned it.
   - In the Claude desktop app's Code tab without the runtime, use the app's background-task tool if present (`spawn_task`): it opens a new session in its own fresh worktree from the base branch, so the bootstrap prompt must tell it to `git fetch` and check out `continuity/<name-slug>-session-1.2` (or apply the saved patch). Report the task id the tool returned.
   - If no such tool exists (Claude app chats), give the user the bootstrap prompt in a copyable block and ask them to start a new chat (same Project, if any) and paste it. Suggest naming that chat `Session <Name> 1.2`.
   - Never say a session was started unless the tool returned it.
4. **Bootstrap prompt** for the new session (fill in every field):
   > You are **Session <Name> 1.2**. You are picking up exactly where **Session <Name> 1.1** left off: it reached its context limit and handed its work to you before compaction. Continue its goal; do not start over. Goal: … Handoff: `<path or doc name>` (read it fully). Code: branch `continuity/<name-slug>-session-1.2` (the previous session's uncommitted work is committed there; the original branch was `<branch>` at `<HEAD>`). Invoke `/continuity` (it will pick cloud mode), verify the handoff against live state, then tell the user in one line that Session <Name> 1.2 is continuing session 1.1's work, and report readiness before changing anything.
5. **Close out here.** Tell the user in one or two lines: the new session's label (and link/ID if created), the branch holding the work, the handoff's name, and that further work should happen in the new session. Don't keep editing in the predecessor after the hand-over.

### Handoff format

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

### Where to save

1. Attached Project: `project_write` under `claude/`. A new version is a new file; don't overwrite the prior version.
2. No Project: working directory (and, at a hand-over, the worktree branch), then send it to the user as a file.
3. Tell the user the doc name in one line and remind them to upload it to their project files if they keep their own copy.

### Successor (fresh session)

A fresh session resumes by:

1. noting its label from the bootstrap prompt (`Session <Name> 1.2`) and telling the user it is continuing the named predecessor's work;
2. reading the latest handoff fully;
3. verifying project root, branch, HEAD, working tree, and live systems against it;
4. surfacing drift;
5. reporting readiness before modifying anything.

When it later hands over, the next session is `Session <Name> 1.3`, and so on.

Authority order: current source + Git state > fresh live-system evidence > durable memory > handoff doc > summaries.

**Fresh source beats old narrative. Evidence beats continuity theater.**
