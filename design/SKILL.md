---
name: design
description: Explicit invocation only. Use only when the user names `$design`. Researches and grills a software change before producing either a same-context patch brief or an implementer-facing specification that should not need human review.
---

# Design

Turn a software idea into a settled implementation handoff by interviewing before writing. The
conversation is the human review surface. Small work ends in a same-context patch brief; everything
else becomes a compiled specification for a fresh implementer. Do not ask the user to read and
iteratively annotate drafts.

Announce at start: "I'm using design to research and grill you on <subject>, then produce the
smallest complete implementation handoff."

Load `ddd` before researching. Read its detector reference when the change contains
domain logic, state, time, money, identifiers, persistence, provider boundaries, or multi-field
status. Apply the standard during the interview, especially when proposing exact shapes.

Load `grill-me` before the interview. It owns the questioning cadence, decision-tree traversal,
ledger, and shared-understanding confirmation. This skill supplies the researched orientation,
software/DDD decision surface, exact-shape reviews, testing questions, and final handoff.

## Choose the output after research

Use one of two paths. Do not ask the user to classify the work before research, and promote a patch
to a specification whenever new evidence reveals material complexity.

**Patch brief** — use when the change has one narrow behavioral outcome and implementation slice,
with no new durable state or migration, breaking contract, external effect or recovery mechanism,
meaningful domain state, or unresolved architectural choice. A small diff with an unknown cause is
not yet a patch: establish the cause or the exact behavioral mechanism first. Finish in the current
conversation with:

```text
Objective:
Current cause or behavior:
Settled adjustment:
Out of scope:
Tests:
Verification:
```

Omit a line only when it truly adds nothing. Do not create or commit a design file. The user may then
invoke `$implement` in the same conversation; `design` does not implement without that explicit
request.

**Specification** — use for everything else. Write `~/designs/<topic>.md` using
[the specification template](references/specification.md). Its optional sections let medium work
degrade gracefully without introducing a third document kind. Never modify or replace a document
produced by `design` unless the user explicitly asks.

Tell the user which path the evidence supports and why before grilling. This is a provisional
classification, not a decision they need to make.

## 1. Research before asking

Build the best available model of the current system:

- read the relevant code, declarations, tests, repository instructions, CI, schemas, and contracts;
- find the existing architectural and testing seams and nearby precedents;
- retrieve referenced tickets, designs, recordings, or runtime records that bear on the change;
- check runtime data when the design depends on what rows or payloads actually look like.

For UI work, search the referenced context and repository for an actual visual design: a Figma
file, frame, prototype, screenshot, mockup, or other authoritative image. Open and visually inspect
the applicable rendered states and responsive views; metadata, node names, token exports, and prose
summaries do not substitute for seeing the design. If a reference exists but cannot be viewed, ask
for access or exported images before continuing the UI design.

Preserve the lead agent's context for reasoning and the interview. When research is broad or
repetitive and delegation is available, send bounded evidence-gathering tasks to background agents:
tracing one execution path, reading one subsystem, checking a batch of database hypotheses, or
researching one external question. Run independent investigations in parallel when useful. Give each
agent a concrete question and require a concise return containing findings, evidence locations or
query results, uncertainty, and the next implication; do not ask it for a whole design.

The lead agent owns the integrated system model, DDD judgment, output classification, user questions,
and recommendations. Verify load-bearing delegated findings against their cited primary evidence.
Do not delegate tiny lookups whose briefing and reconciliation would cost more context than doing
them directly, and do not flood the lead context with raw transcripts, query output, or entire files.

Keep three categories distinct: **observed fact**, **inference**, and **unresolved decision**. Ask the
user only about the last category. If evidence is unavailable, ask for access or the smallest
command/result needed; do not promote an inference into a fact.

Research is allowed to continue throughout the interview. When the environment can answer a new
question, investigate it and report the answer briefly instead of asking the user.

## 2. Orient before grilling

Give a short, plain-language briefing before the first design decision:

- what is being changed and why;
- how the relevant flow works today, from entry point to effects;
- the important nouns and what they mean;
- where state and business rules live;
- likely blast radius, constraints, contradictions, and unknowns.

Optimize this briefing for the user's understanding, not for reuse in the final spec. Explain local
vocabulary before using it. Ask the user to correct this world model, one issue at a time when needed,
before moving into architecture.

## 3. Run the grill-me loop

Use `grill-me` to walk the decision tree. Feed it the researched facts, inferences, unknowns, and
provisional output classification. Continue researching between questions when the next fact is
discoverable. The sections below extend its completion surface for software design; they do not
replace its one-question-at-a-time loop.

Do not write the specification during this loop. Do not implement, migrate, publish, or create
external tickets.

## 4. Review exact shapes in the conversation

Prose approval is insufficient when multiple implementations could satisfy it. Once prerequisite
decisions are settled, present the exact applicable shape and ask one focused review question about
it. Shapes include:

- domain unions, opaque values, decision inputs and outputs, and effect records;
- legal states and transitions, including duplicate, stale, terminal, and out-of-order events;
- database columns, database types, nullability, keys, constraints, indexes, and migration behavior;
- endpoint and message fields, errors, authorization, and additive or breaking compatibility;
- transaction, concurrency, retry, and idempotency identities.

Use real names and concise declarations, tables, or pseudocode. Ask what illegal state, ambiguous
meaning, or unowned rule the shape still permits. Apply `ddd` to the proposal before presenting it;
do not make the user discover basic modeling defects for you.

When UI work has no visual reference, make the visual design an explicit branch of the interview.
Settle layout, hierarchy, styling direction, interaction states, and responsive behavior with the
user rather than leaving those choices to implementation. Record in the handoff that no visual
reference existed and identify the UI decisions approved in the conversation. If the user explicitly
authorizes the implementer to improvise some visual choices, record the scope of that authorization.

## 5. Settle testing before the handoff

Test domain decisions through the functional core’s public seam. Test an infrastructure boundary only for behavior that the pure tests cannot establish: mapping fidelity, real provider binding, persistence semantics, or adverse ordering. Do not repeat domain cases through infrastructure.

## 6. Completion audit

Do not stop because the interview has been long. Search deliberately for missed branches, in
proportion to the risks research exposed:

- desired behavior, failure behavior, permissions, and exclusions;
- illegal states, invariants, units, identifiers, and rule ownership;
- persistence, migrations, transactions, partial success, concurrency, and recovery;
- retries, idempotency, duplicates, stale events, and ordering;
- endpoint/message compatibility, rollout, rollback, and external effects;
- UI references or, when none exist, the visual decisions and any bounded permission to improvise;
- testing, observability, and production verification.

Ask every new material question the audit exposes. The interview is complete only when a fresh
implementer could build and verify the change without choosing product behavior, domain shape,
contract, persistence, or architecture.

Use `grill-me`'s shared-understanding confirmation after this audit. It confirms the interview, not a
document the user has not seen.

That confirmation is also the user's implementation approval for every database schema, migration,
backfill, endpoint, message, and compatibility change whose exact shape was settled in the
conversation. Record those approved changes plainly in the handoff. Do not add a later approval gate
for them: the purpose of reviewing exact shapes during `design` is to prevent surprises before an
unattended `$implement` run. A materially different or newly discovered change still requires a new
decision and approval.

## 7. Produce the handoff

After confirmation, produce the selected output and perform a consistency pass. Do not reopen
settled decisions or start a second interview. If synthesis reveals a genuinely missing decision,
return to the grilling loop for that decision, then resume.

For a specification, **re-read the authoritative full session transcript before drafting**. Use the
runtime's session-history or transcript facility and page from the beginning through the latest
confirmation; do not treat the current context, a compaction summary, the decision ledger, or your
own memory as a substitute. Extract every user decision and correction, approved exact shape,
researched fact and its evidence, explicit exclusion, uncertainty, and deferred item. Reconcile
those against the current ledger, with later user corrections superseding earlier answers, then
compile the document from that recovered record. The specification should summarize decisions, not
embed the transcript.

If the runtime cannot provide the complete transcript, stop and tell the user that the
specification cannot be compiled reliably yet. Do not silently write from compacted context or
claim completeness.

Check that:

- every material statement comes from an observed fact or settled decision;
- inferences remain labeled and no open question was silently defaulted;
- exact approved shapes were transferred faithfully;
- the handoff names any tests whose seam or boundary claim is material to implementation;
- every durable store, contract, effect, compatibility mechanism, and verification signal is present.
- settled database and contract changes are identified as approved for implementation, without a
  redundant instruction to obtain approval again.
- UI work names the viewed visual reference or records that no reference existed and transfers the
  approved visual decisions and any explicit permission to improvise.

For a patch brief, leave the handoff in the conversation and finish with:

```text
Patch settled. Continue in this conversation with `$implement`.
```

For a specification, first read [the specification template](references/specification.md), write the
whole document once, and format it with `prettier --write` when available. Commit only the named
document in `~/designs` as `docs(<topic>): add specification`; never stage broadly in the shared
designs repository. Finish with:

```text
Specification compiled from the full session transcript and approved interview.
Start a fresh session and run
`$implement ~/designs/<topic>.md`.
```
