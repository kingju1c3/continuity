# Memory protocol

## What continuity means

The next session can reconstruct the user's active work from inspectable records:
what matters, what was decided, why, what was actually tested, what remains,
and where to begin. This is functional continuity. It does not establish continuity
of subjective experience, a persistent self, or an identity independent of the host.

Use three levels:

1. **Orientation:** a short checkpoint, unresolved conflicts, source freshness flags.
2. **Retrieval:** ranked previews and topic timelines, then full selected records.
3. **Evidence:** source files, measurements, current repository state, or authorized
   connected sources. The evidence can override an inaccurate summary.

## Record contract

Each record has an ID, exact scope, kind, stable topic key, title, body, epistemic
class, confidence, provenance, creation time, optional review date, and status.
A topic organizes a proposition or decision. Do not use one topic for an entire
unrelated notebook; multiple active records under a topic are flagged as possible
conflicts, including complementary records that need human interpretation.

Recommended kinds: observation, decision, preference, task, lesson, question,
session. A concise body can use:

- **What:** the result or decision.
- **Why:** evidence, tradeoffs, and alternatives considered.
- **Where:** file paths, issue identifiers, explicit source labels.
- **Learned:** reusable implication and the condition that would change it.

Class A means an empirical claim with a named source. The CLI requires provenance
but cannot prove the claim. A user statement supports “the user said X,” not
necessarily “X is true.” Class B is a deduction conditional on explicit premises.
Class C is a hypothesis, speculation, or unassessed imported assertion.
Confidence is low, medium, high, or unassessed; it is not a measured probability.

## Corrections and conflicts

1. Search the topic and inspect its timeline.
2. Identify whether records contradict, describe different contexts, or coexist.
3. Verify the current source and relevant user intent. Repetition is not independent
   corroboration. A newer timestamp is not by itself stronger evidence.
4. If correction is justified, save a new record with the same topic and
   `--supersedes <old-id>`. Keep the reason and source in the new body.
5. If the conflict is unresolved, preserve both, flag it, and continue work that
   does not depend on a fabricated resolution.

Supersession requires the same scope/topic and an active predecessor. A correction
creates a new ID and leaves history inspectable. Retirement is a reversible
workflow in the sense that information remains available for explicit resaving;
there is no undelete command. It is not secure erasure.

## Promotion and pruning

Turn short-lived observations into reusable lessons only after review. Do not
silently convert speculation into fact. Set a timezone-aware `review_after` when
an assertion depends on versions, schedules, or changing external facts. Date
fields from upstream imports remain in provenance; review them explicitly.

Avoid saving filler, greetings, repeated summaries, tokens, passwords, or raw
conversation dumps. Search before saving. Exact deduplication ignores the time a
source fingerprint was checked; changed content, evidence or confidence creates
a distinct candidate. Semantic deduplication is a reasoning step, not an engine
capability claimed by this release.

## Handoff quality

A good checkpoint names a concrete next action with enough context to execute it.
“Continue working” is inadequate. “Run the migration test against the sample SQLite
fixture; if it passes, update the schema-version note in docs/storage.md” is useful.
Record failed attempts and blockers so the next session need not repeat them.

`review_due` reports only whether the optional review deadline has passed. Source
freshness is independent: a missing or changed source needs attention even when
`review_due` is false.
