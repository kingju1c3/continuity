---
name: "continuity-cloud"
description: "Use instead of /continuity in the Claude app or any cloud session with no local continuity runtime. Writes verified, versioned handoffs at milestones; before compaction it writes a detailed lossless handoff, pushes the work to a new worktree branch, and starts a fresh session labelled <name> session 1.1, 1.2, 1.3… that is told it is picking up where the last one left off."
---

# /continuity-cloud

Cloud-session companion to `/continuity`. The original skill depends on a local runtime (`continuity` CLI), an exact host session ID, and a PreCompact hook, none of which exist in the Claude app or cloud workspaces. This skill keeps the parts of the protocol that don't need them: a durable, lossless, verified handoff and a labelled fresh session that resumes from it.

It cannot capture at the exact compaction instant: there is no hook. It transfers **before** compaction instead, as soon as the conversation is long enough that fidelity is at risk. Say so once, when invoked. Never claim a measured context percentage the host did not expose.

## On invocation

1. Check for the runtime in this session's own shell (`command -v continuity`, `.continuity/enabled.json`). If it is present AND the host exposes a session ID, tell the user to use `/continuity` instead and stop. A CLI installed on a linked remote computer does not count: hooks and session identity belong to the host running this conversation. Never invent a session ID.
2. Tell the user in one line that cloud mode is active: there is no compaction hook here, so handoffs are written at milestones and the hand-over to a new session happens before compaction, not at it.
3. **Work out this session's label.** Sessions in one line of work form a chain: **`<Name> session 1.0`**, then **`1.1`**, **`1.2`**, **`1.3`** … If the session was started by a predecessor, its first message names it ("You are SiteBooked session 1.2 …"): keep that label. Otherwise this is `<Name> session 1.0`, where `<Name>` is the project or topic (ask only if it's genuinely unclear). State the label in that same line.
4. Find the latest existing handoff. If a Project is attached, search its docs for `Handoff`; otherwise check the working directory. Read it and note its version.
5. Verify it against live state (Git branch/HEAD/working tree, deployed version, open PRs/CI). Surface drift.
6. Write a fresh handoff now if none exists for the current work or the latest is stale.

## Passive otherwise

No commentary on ordinary turns. Write or update the handoff only at a milestone:

- merge, push, deploy, release, or another state change on a shared system;
- a discovered blocker or changed plan;
- before the user steps away or before handing off to scheduled/unattended work;
- when the user asks;
- **before compaction**: when the conversation has grown long enough that fidelity is at risk (many large tool outputs, many turns, repeated reconnects, a host warning about context). Warn the user, then run the **Hand-over** below. Before degradation, never after.

## Hand-over to a new session (before compaction)

Do all of it in one go, in this order, and report each step's real result.

1. **Write the lossless handoff** (format below), labelled for both sides: "from `<Name> session 1.1` to `<Name> session 1.2`". Lossless means a fresh session could continue with no access to this conversation: every decision and its reason, every open thread, exact file paths, commands, IDs, URLs, versions, test results with numbers, what was verified versus assumed, the user's standing preferences and corrections, and the exact next action.
2. **Preserve all work in progress on a new worktree branch** (Git projects). Never stage, stash, commit or reset in the current tree:
   ```bash
   N="<name-slug>-1-2"                                  # next label, dots → dashes
   git worktree add -b "continuity/$N" "../$(basename "$PWD")-continuity/$N" HEAD
   git diff --binary HEAD > "/tmp/$N.patch"            # every uncommitted tracked change
   git -C "../$(basename "$PWD")-continuity/$N" apply --binary "/tmp/$N.patch"
   git ls-files --others --exclude-standard -z | xargs -0 -I{} cp --parents {} "../$(basename "$PWD")-continuity/$N/"   # untracked files
   # put the handoff doc in the worktree too, then:
   git -C "../$(basename "$PWD")-continuity/$N" add -A
   git -C "../$(basename "$PWD")-continuity/$N" commit -m "continuity: work in progress handed to <Name> session 1.2"
   git -C "../$(basename "$PWD")-continuity/$N" push -u origin "continuity/$N"
   ```
   A cloud session is a fresh checkout: anything not pushed is lost. If pushing isn't allowed, say so and attach the patch and handoff as files instead. Skip secrets and files that look like credentials, and name what you skipped.
3. **Start the new session** labelled `<Name> session 1.2`:
   - If a session-creation tool exists (e.g. `create_session` in Claude Code on the web), create it on the same repository at branch `continuity/<name-slug>-1-2`, with title `<Name> session 1.2` and the bootstrap prompt below. Report the new session's ID or link exactly as the tool returned it.
   - If no such tool exists (Claude app chats), give the user the bootstrap prompt in a copyable block and ask them to start a new chat (same Project, if any) and paste it. Suggest naming that chat `<Name> session 1.2`.
   - Never say a session was started unless the tool returned it.
4. **Bootstrap prompt** for the new session (fill in every field):
   > You are **<Name> session 1.2**. You are picking up exactly where **<Name> session 1.1** left off: it reached its context limit and handed its work to you before compaction. Continue its goal; do not start over. Goal: … Handoff: `<path or doc name>` (read it fully). Code: branch `continuity/<name-slug>-1-2` (the previous session's uncommitted work is committed there; the original branch was `<branch>` at `<HEAD>`). Invoke `/continuity-cloud`, verify the handoff against live state, then tell the user in one line that <Name> session 1.2 is continuing session 1.1's work, and report readiness before changing anything.
5. **Close out here.** Tell the user in one or two lines: the new session's label (and link/ID if created), the branch holding the work, the handoff's name, and that further work should happen in the new session. Don't keep editing in the predecessor after the hand-over.

## Handoff format

Filename: `<Project>-<Topic>-Handoff-<YYYY-MM-DD>-v<N>.md`, incrementing N from the previous handoff.

Required sections:

- **Session:** this session's label and, at a hand-over, the successor's label ("<Name> session 1.1 → 1.2").
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

## Where to save

1. Attached Project: `project_write` under `claude/`. A new version is a new file; don't overwrite the prior version.
2. No Project: working directory (and, at a hand-over, the worktree branch), then send it to the user as a file.
3. Tell the user the doc name in one line and remind them to upload it to their project files if they keep their own copy.

## Successor (fresh session)

A fresh session resumes by:

1. noting its label from the bootstrap prompt (`<Name> session 1.2`) and telling the user it is continuing the named predecessor's work;
2. reading the latest handoff fully;
3. verifying project root, branch, HEAD, working tree, and live systems against it;
4. surfacing drift;
5. reporting readiness before modifying anything.

When it later hands over, the next session is `<Name> session 1.3`, and so on.

Authority order: current source + Git state > fresh live-system evidence > durable memory > handoff doc > summaries.

**Fresh source beats old narrative. Evidence beats continuity theater.**
