---
name: design
description: Collaboratively design a feature or change by iterating on a design doc — you write a skeleton with open questions, the user annotates it, you fold the annotations in, repeat until settled, then append a task list for implementation. Use before building anything non-trivial, when a change needs domain modeling thought, or when the user asks to design, spec, or think through an approach. Not for planning mechanical edits to an already-settled design.
---

# Design

A design doc built in rounds, not in one shot. The point is that the user absorbs a design by
arguing with it, so the first draft is deliberately incomplete: scaffolding plus honest
questions, never a finished proposal to rubber-stamp.

Announce at start: "I'm using design to work through <subject>."

Load `ddd` before writing anything. Five of the doc's sections exist to force domain-modeling
decisions, and this skill is where that standard actually gets applied — by review time the
types are already written.

## Where docs live

`~/designs/`, one git repo, one file per design:
`~/designs/<topic>.md`. Not in the project repo — these are almost never checked in,
and they need to outlive the worktree they were written in.

Each round is a commit. That's how a round gets read:

```bash
git -C ~/designs add <topic>.md
git -C ~/designs commit -m "docs(<topic>): Round N — <what changed>" -- <topic>.md
git -C ~/designs diff HEAD~1 -- <topic>.md
```

**Name your own file in all four commands — never `add -A`, `add .`, or a bare `commit`.**
This repo is shared, and other sessions have their own designs open in it at the same time.
Staging broadly sweeps someone else's half-written doc into your round, where they find it
committed under your message and your topic. The `-- <topic>.md` on `commit` is the guard that
actually holds: it limits the commit to that path even when another file is already staged.

Same rule for reading. A round's diff is only legible if it's scoped — an unscoped `HEAD~1`
mixes another topic's edits into the thing the user is being asked to review.

`--word-diff` is the one that matters. A plain line diff marks every reflowed line as changed
and is useless on prose.

## The loop

1. **Research, then write a skeleton.** Headings filled only where research makes the answer
   unambiguous; everything else an explicit `**Q<n>:**` block with the options, a
   recommendation, and why the recommendation follows. Commit as round 1.
2. **The user annotates** with lines starting `@:` (leading whitespace is fine — their formatter
   indents them). Grep for them with `^\s*@:`.
3. **Fold each annotation in**, per the archive rules below.
4. **Format, then commit the round and print both diff commands.** Run
   `prettier --write <topic>.md` first when `prettier` is on the PATH — it realigns the tables so
   a sub-rowed noun list stays readable. It can't churn the doc: prettier's default
   `proseWrap: preserve` leaves your prose line breaks alone, and running it over an existing
   design doc produced a zero-line diff. Skip it silently if prettier isn't installed. The diff
   is the deliverable; they read that, not the doc.
5. **Repeat** until no `Q` blocks are open.
6. **Append a `## Tasks` section** — concrete, ordered, each one a chunk. This is the handoff
   to `implement`, and it's what lets that skill start from a clean context.

### Handling annotations

- **Open thread** → answer inline with `**A:**` directly under their annotation, and leave both
  in place. Nothing with an open question gets swept.
- **Settled** → move it to `## Resolved` as `R<round>.<n>`, with **their words quoted verbatim**
  (use markdown `>` blockquote syntax)
  plus what came of them. Update the body to state the decision.
- **Body content that exists only because they asked** carries a back-reference: `(→ R3.1)`.

That last rule is not optional bookkeeping. Deleting a question orphans its answer — a
paragraph appears mid-section with nothing explaining why it's there, and the doc reads like
a series of non-sequiturs. If a paragraph would confuse someone who never saw the question,
it needs the pointer.

`Resolved` is append-only and lives at the bottom, so it never shows up in a round's diff
except as new lines at the end. IDs never renumber. By round 6 it will be the longest section
in the doc; that's fine, it's the part worth having in three months.

## Edit in place; never restructure

**Hard rule, and it's what makes the diff readable.** A moved paragraph and a
delete-plus-add produce the same diff, so one reorganization destroys the round's diff no
matter how good the tooling is. After round 1:

- Section headings and their order are frozen.
- New material goes in a new subsection at the end of its parent, not woven into existing
  prose.
- Renaming a concept is an explicit find-and-replace, not licence to rewrite the section.
- If the doc genuinely needs reorganizing, **ask first**, and do it as its own round with
  nothing else in it — one commit whose diff is honestly unreadable, and everyone knows which.

No `~vN` markers on touched headings. They churn every round and `--stat` already answers it.

## The template

Six top-level headings. The DDD material is collapsed into one.

```markdown
# <Feature> Design

## Problem

## Domain

## Test plan # pre-merge: which of the six layers apply

                 # post-deploy: what signal proves it worked, and does it exist yet?

## Tasks

## Open questions

## Resolved
```

`## Domain` always carries **the noun list**. That part is cheap and always pays — but only if
it's written as a reference table, not a run-on of backticked names.

### The noun list

Group by **layer**, and give every noun a table row with three things: the real type name, one
line on what it is or decides, and whether this change touches it.

The format, with a made-up example — use your repo's real layers, paths, and type names:

```markdown
**Persisted state** — `Data/Model/Scheduler/`

| Type                      | What it is                                        | Touched?        |
| ------------------------- | ------------------------------------------------- | --------------- |
| `SchedulerSnooze`         | the follow-up row; the only durable cadence state | **new columns** |
| `SchedulerFollowUpSource` | `Auto` = a cadence retry, `Human` = a promise     | read            |
| `StaleLeadDigestWorkflow` | the daily 72-hour digest, 8 files                 | **delete**      |
```

Use the layer headings that fit what you found — typically **persisted state**, **functional
core**, **imperative shell**, **contracts**, and frontend when it's involved. Note the project
or directory next to the heading so the reader knows where to look.

Rules, because this section fails in predictable ways:

- **One line per noun. No exceptions.** This table is an index, not a spec — its job is to let
  you see what's in play and what the blast radius is, in one pass. The moment a cell holds a
  field list or two sentences, markdown pads every other cell to match and the table stops being
  readable at all. A real design doc reached **351 characters** on a line this way.
- **No lists in cells.** If a noun's fields, columns, or enum members matter, they belong in
  `### Contract changes` (for tables and endpoints) or `### Proposed types` (for internal types) —
  not here. Here it gets a phrase: "the follow-up row; the only durable cadence state".
- **No prose in cells either.** One clause, lowercase, no trailing period. If you need a
  sentence, the noun needs its own subsection. If you need two, you're writing the wrong section.
- **Never a prose run of names separated by `·` or commas.** A reader can't scan it, can't tell
  a static policy class from an EF entity, and learns nothing they couldn't get from grep. If
  the list is one paragraph, it is wrong.
- **The "Touched?" column is the point.** `read` vs `extend` vs **`fix`** vs **`new`** tells the
  reader the blast radius before they read another word. Bold the ones being changed, and keep
  the value to one or two words — explanation goes in the row's own subsection, not this cell.
- **Group by layer, because the grouping is a finding.** Noticing that four of the types are
  already `static` and I/O-free tells you this is an edit inside an existing functional core
  rather than an extraction — which changes the whole shape of the work. Say that conclusion
  out loud in a sentence under the tables.
- **Verify the kind before you write it.** Whether something is a `static class`, a
  `sealed record`, an `abstract record` (a union), or a DI-injected service is exactly the
  information the table exists to carry, and it's the thing most easily got wrong from memory.
  `grep` the declaration.
- **Name the nouns that don't have types yet.** Identifiers and quantities this change passes
  around as bare `string` or `int` are nouns whose row is missing (`ddd` rule 9). Say which are
  becoming opaque types and which stay primitive because they never leave the edge.

Then any of these as `###` subsections, only when the change actually calls for them:

```markdown
### Contract changes # new/changed DB tables and endpoints — see below

### State space # states today; illegal combinations currently expressible

### Proposed types # unions and value objects, with units

### Decisions as data # the Decide/Plan signature and its cases

### Effects # the command records the core returns

### Rule ownership # each rule: where it lives now → where it lives after

### Invariants # what must always be true, and what enforces it
```

**`### State space` carries the transition table** when the change is a state machine. The
variants and the legal transitions you would write anyway; four more get skipped and are the
ones worth forcing: **the identity that makes each event idempotent**, behavior for
**duplicate, stale, and out-of-order** arrival, which states are **terminal versus resumable**,
and the **concurrency rule**. Those double as the layer-1 test rows.

**Mark the rows that get a test with a `T` column.** The table has two jobs — it documents the
machine's legal transitions *and* it is the layer-1 test budget — and they don't have the same
row set. A transition worth naming isn't automatically a transition worth asserting, so without
the column the reader can't cut a test without deleting documentation, and every transition
added to the spec silently buys a test. The marked count is what `## Test plan` cites, and the
marks are where the argument about the count happens.

Rules that keep the optionality honest:

- **A subsection appears when it has content, and is omitted otherwise** — never included
  with "unchanged" written under it. An empty heading is worse than no heading: it's a line
  you have to read to learn nothing.
- **State in one line at the end of `## Domain` which you skipped and why.** That makes
  skipping a visible decision they can push back on rather than a silent omission.

Depth scales with how much is being written from scratch. Greenfield fills most of the
subsections. A small modification to existing code may have nothing but the noun list and a
test plan — see `ddd`'s scope rule.

### Contract changes

The noun list is an index; this is the spec. It covers **new or changed database tables and API
surface only** — endpoints, gRPC routes, pubsub messages. Internal types don't belong here; they
get their one-line row in the noun list and, if they need shape, `### Proposed types`.

Only what moves. An unchanged table gets its one-liner upstairs and nothing more, and a table
you're altering shows the columns you're adding or changing — not its existing 30. No DDL:
`implement` writes the migration.

**Governing rule: per-column facts go in the table, anything spanning columns goes below it.**
A compound index, a composite primary key, a multi-column unique, a partial unique with a
`where` clause — none of those fit in a cell and all of them are the interesting part.

```markdown
`scheduler_overdue_lead_alerts` — **new table**

| Column        | Type          | Null | Key | Meaning                      |
| ------------- | ------------- | ---- | --- | ---------------------------- |
| `id`          | `text`        | no   | PK  |                              |
| `team_id`     | `text`        | no   | FK  | → `teams`                    |
| `due_at`      | `timestamptz` | no   |     | when the obligation came due |
| `resolved_at` | `timestamptz` | yes  |     | null = still pending         |

- unique `(team_id, deal_id, obligation_kind, obligation_key)` where `resolved_at is null`
- index `(team_id, due_at)` — the scan's access path
```

- **`Type` is the database type, not the language one.** This is the schema contract, and left
  alone an agent writes `DateTimeOffset?` where what matters is `timestamptz null`. Where the ORM
  mapping is conventional (`snoozed_until` → `SnoozedUntil`) the property is derivable and needs
  no row; note it in `Meaning` only when the mapping _isn't_ the obvious one, because that is
  where bugs live.
- **`Key` is a flag, not a description** — `PK`, `FK`, or blank. A two-character vocabulary stays
  scannable. The FK target is short enough for `Meaning`; composite keys go below with everything
  else that spans columns, so nothing is stated twice.
- **Defaults go in `Meaning`**, not their own column — only a few columns have one, so a
  dedicated column would be mostly empty.

For an endpoint, route, or message: request and response fields in the table, and below it the
things that aren't per-field — the auth lane, the status codes, and **whether the change is
additive or breaking**. Force that last one explicitly: wherever a repo has a deprecation
convention or a breaking-change gate on its schema diff, "is this additive?" is what decides
whether the work is one PR or two, and it is much cheaper to answer here than at review.

**This section usually answers `## Test plan`'s prod-verification question for free.** A new
column or a new endpoint is very often the exact signal that proves the feature worked. If you
write one here, say so there.

### Test plan

**A table, one row per test, one line per row, and no prose.** This section is approved by being
skimmed — the user strikes the rows they don't want — and prose defeats that in a specific way: it
hides the count, which is the thing worth arguing about. Thirty lines of justified paragraphs make
nine proposed tests look like a description of care rather than a number someone should push back
on.

```markdown
| L   | Case                                    | Expected                         |
| --- | --------------------------------------- | -------------------------------- |
| 1   | transition table above, 5 of 9 marked   | —                                |
| 2   | blank key on either side                | never matches                    |
| 4   | captured payload, contact with no email | href as the consumer receives it |
| 4   | 401 body                                | unlinkable, distinct copy        |

3, 5, 6 — none: no persistence, no durable state, no ordering.
Rewrite: the existing owner-button test. 8 tests.
```

It also answers, in a line or two, **how this gets verified in prod after it deploys** — because
that question has a code consequence and `ship` is too late to discover it. If proving the
feature works needs a log line, a metric, or a column that doesn't exist yet, **that's a task**,
and it goes in `## Tasks` like any other. Otherwise `ship` ends up writing a weak proxy check or
going back to add instrumentation after the fact.

Only the first of `ship`'s two M&V questions usually needs anything:

- **"Does the new thing work?"** — new behavior, so often no signal exists yet. This is the one
  to think about here. Name the signal: the log event and its fields, the metric, the row that
  should appear.
- **"Did we break the happy path?"** — watches pre-existing behavior, so the signal almost always
  already exists at a known volume. Nothing to build; just note what it'll be.

Don't write the queries here. Thresholds and query strings are `ship`'s job, and they'd be stale
by the time it runs. This section decides **what must be observable**, not how it gets asked.

## Length

**80–150 lines for a normal feature. Over 250 needs a reason.**

The template is not what makes a doc long; verbosity is, and it's the failure mode this
section exists to check. A one-union bug fix should produce a page, not a chapter. If a
section has nothing to say, it says nothing.

## Writing the questions

A `Q` block that just asks "what do you think?" wastes a round. Each one needs:

- the decision to be made,
- the options, concretely,
- a recommendation,
- why that recommendation follows from the research.

Ask only what research can't answer and what materially changes the design. If two readings
of the request lead to the same work, pick one and note the assumption instead of asking.

Prefer surfacing a fork early over discovering it in round 4 — an architectural question
answered in round 1 is cheap, and the same question after two rounds of dependent prose is
a restructure.

## Rules

- **Real names throughout.** `OrderOutcomeService.CreateAsync`, the literal column, the actual
  endpoint. Never a nickname coined earlier in the doc.
- **Never delete their annotations** while a thread is open, and never paraphrase them when
  archiving — verbatim, so the record is their words and not your summary of them.
- **Don't build.** This skill produces a document. "Let's do X" inside a design round means
  the decision goes into the doc, not into the codebase.
- **Open the code before describing it.** Anything asserted about existing behavior gets read
  first; mark anything inferred.

## Then what

When there are no open questions, do one more pass over the full document
to check for inconsistencies and fix what you find. Then write `## Tasks` and output:

```
Design settled. Start a new session (or /clear) and run
`/implement ~/designs/<topic>.md` — a fresh context gets the full budget
for the work, and the task list is the handoff.
```
