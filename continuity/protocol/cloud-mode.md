# Cloud mode (full protocol)

Loaded from SKILL.md when there is no local runtime. The handoff format is in SKILL.md ("Handoff format"), shared by both modes.


Cloud mode exists because local mode depends on a local runtime (`continuity` CLI), an exact host session ID, and a PreCompact hook, none of which exist in the Claude app or cloud workspaces. Cloud mode keeps the parts of the protocol that don't need them: a durable, lossless, verified handoff and a labelled fresh session that resumes from it.

It cannot capture at the exact compaction instant: there is no hook. It transfers **before** compaction instead, as soon as the conversation is long enough that fidelity is at risk. Say so once, when invoked. Never claim a measured context percentage the host did not expose.

### On invocation

1. Check for the runtime in this session's own shell (`command -v continuity`). If it is present AND the host exposes an exact session id (Claude Code, terminal or desktop app, exports `CLAUDE_CODE_SESSION_ID`), tell the user to use `/continuity` instead and stop: it arms without any prior install, hands over early on measured context usage, and keeps the PreCompact hook as backstop. A CLI installed on a linked remote computer does not count: hooks and session identity belong to the host running this conversation. Never invent a session ID.
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

0. **Measured usage ≥ 75%**, where it can be measured. Claude Code (including on the web) writes this session's transcript under `~/.claude/projects/`; check it at every milestone and roughly every 20 tool calls:
   ```bash
   python3 - <<'PY'
   import glob, json, os
   sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
   f = (glob.glob(os.path.expanduser(f"~/.claude/projects/*/{sid}.jsonl")) if sid else []) or sorted(glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")), key=os.path.getmtime)[-1:]
   used = 0
   for line in open(f[0]) if f else []:
       try: v = json.loads(line)
       except ValueError: continue
       u = (v.get("message") or {}).get("usage") if v.get("type") == "assistant" and not v.get("isSidechain") else None
       if u: used = sum(u.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
   print(f"context used: {used} tokens", f[0] if f else "(no transcript)")
   PY
   ```
   Compare against the model's window (the user or the host tells you; otherwise assume 200k, which errs early). Report the number as measured and the window as assumed or known.
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

**Same environment, same folders.** The successor's worktree is created in the environment the predecessor runs in: the same machine or container, inside the same main checkout, at `<main checkout>/.claude/worktrees/continuity-<name-slug>-session-<next>`. Never in a fresh clone, a temp directory, or another container. The successor works in that folder, in that environment, so it inherits the checkout, `node_modules`, caches, running test output and local tooling exactly as the predecessor left them. Starting the successor somewhere else (a new cloud container, another chat) is a fallback, used only when no same-environment launch is possible. Say that it is a fallback and why, and give the pushed branch so the other environment can reproduce the folder.

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
3. **Start the new session** labelled `Session <Name> 1.2`, **in this environment, in the worktree folder `$W`** (see *Same environment, same folders*):
   - Default: the successor runs **visibly, in this environment, in `$W`, with the same permissions and settings as this session** (Hard rules 3 and 7). When `mcp__ccd_session__start_session` exists (the Claude desktop app), call it yourself: `initiation: "user_asked"`, `title: "Session <Name> 1.2"`, `context: "fresh"`, `cwd: "$W"`, `use_worktree: false`, the bootstrap `prompt`, a short `background`, and no `permission_mode`/`model`/`effort` so it inherits this session's. It then shows in the sidebar as a clone. Otherwise give the user the folder path and the bootstrap prompt to paste into a new session opened on `$W`. Do **not** use `claude --bg` unless the user explicitly asks for a background session. A background session is invisible to the desktop app and the user's phone.
   - Only if no same-environment launch is possible, fall back to the options below, and tell the user it is a fallback that runs in a different environment, fetching branch `continuity/<name-slug>-session-1.2`:
   - If a session-creation tool exists (e.g. `create_session` in Claude Code on the web), create it on the same repository at branch `continuity/<name-slug>-session-1.2`, with title `Session <Name> 1.2` and the bootstrap prompt below. Report the new session's ID or link exactly as the tool returned it.
   - In the Claude desktop app's Code tab without the runtime, use the app's background-task tool if present (`spawn_task`): it opens a new session in its own fresh worktree from the base branch, so the bootstrap prompt must tell it to `git fetch` and check out `continuity/<name-slug>-session-1.2` (or apply the saved patch). Report the task id the tool returned.
   - If no such tool exists (Claude app chats), give the user the bootstrap prompt in a copyable block and ask them to start a new chat (same Project, if any) and paste it. Suggest naming that chat `Session <Name> 1.2`.
   - Never say a session was started unless the tool returned it.
   - If even the fallback is unavailable or the user asks you to stand down, create the worktree anyway and stop. The worktree in this environment is the handoff, and the user starts `Session <Name> 1.2` in it.
4. **Bootstrap prompt** for the new session (fill in every field):
   > You are **Session <Name> 1.2**. You are picking up exactly where **Session <Name> 1.1** left off: it reached its context limit and handed its work to you before compaction. Continue its goal; do not start over. Goal: … Handoff: `<path or doc name>` (read it fully). Code: worktree folder `<main checkout>/.claude/worktrees/continuity-<name-slug>-session-1.2` in this same environment, on branch `continuity/<name-slug>-session-1.2` (the previous session's uncommitted work is committed there; the original branch was `<branch>` at `<HEAD>`). Work in that folder; only if it is missing (a different environment), fetch the branch. Invoke `/continuity` (it will pick cloud mode), verify the handoff against live state, then tell the user in one line that Session <Name> 1.2 is continuing session 1.1's work, and report readiness before changing anything.
5. **Close out here, once the new session is confirmed running** (the tool returned its id, or the user says it's open). Until then you are still the owner: keep the work safe and say plainly that the hand-over isn't done. Tell the user in one or two lines: the new session's label (and link/ID if created), the branch holding the work, the handoff's name, and that further work should happen in the new session. Don't keep editing in the predecessor after the hand-over.

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
