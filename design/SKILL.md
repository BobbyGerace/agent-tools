---
name: design
description: Explicit invocation only. Use only when the user names `$design`; never activate it by inferring intent from a request to design, spec, plan, build, or think through a change. Collaboratively develops a design doc through annotated rounds, then appends an implementation task list.
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

Round 1 is committed before the first handoff because the whole skeleton needs a full read. After
that, each round begins with a checkpoint commit and ends with an uncommitted working-tree diff.
The checkpoint records the document exactly as the user left it, including their annotations;
the dirty revision is the next proposal.

```bash
git -C ~/designs add <topic>.md
git -C ~/designs commit -m "docs(<topic>): checkpoint round N annotations" -- <topic>.md
```

**Name your own file in both commands — never `add -A`, `add .`, or a bare `commit`.**
This repo is shared, and other sessions have their own designs open in it at the same time.
Staging broadly sweeps someone else's half-written doc into your checkpoint, where they find it
committed under your message and your topic. The `-- <topic>.md` on `commit` is the guard that
actually holds: it limits the commit to that path even when another file is already staged.

The user reads the whole document from top to bottom. Ordinary changed-line indicators in any
Git-aware editor show where the round changed the baseline and where to slow down. The working
tree stays dirty so that requires no editor-specific base override. If they want a command-line
fallback, give them `git -C ~/designs diff --word-diff -- <topic>.md`; it is navigation help, not
the deliverable.

## The loop

1. **Research, then write a skeleton.** Headings filled only where research makes the answer
   unambiguous; everything else an explicit `**Q<n>:**` block with the options, a
   recommendation, and why the recommendation follows. Commit it as
   `docs(<topic>): round 1 skeleton`.
2. **The user annotates** with lines starting `@:` (leading whitespace is fine — their formatter
   indents them). Grep for them with `^\s*@:`.
3. **Checkpoint exactly what they reviewed**, including their annotations, using the scoped add
   and commit above. This becomes the baseline for the next dirty revision.
4. **Fold each annotation in**, per the archive rules below.
5. **Format and hand over the dirty document.** Run `prettier --write <topic>.md` when `prettier`
   is on the PATH — it realigns the tables so
   a sub-rowed noun list stays readable. It can't churn the doc: prettier's default
   `proseWrap: preserve` leaves your prose line breaks alone, and running it over an existing
   design doc should leave unrelated prose alone. Skip it silently if prettier isn't installed.
   Print a `Material changes this round` list, then ask the user to reread the whole document;
   changed-line indicators are attention guidance, not a substitute for that read.
6. **Repeat** until no `Q` blocks are open.
7. **Append a `## Tasks` section** — concrete, ordered, each one a chunk. This is the handoff
   to the downstream `$implement` workflow, and it lets that workflow start from a clean context.
   Leave this final proposal dirty for review too. After the user approves it, commit it as
   `docs(<topic>): finalize design` before handing it to `$implement`.

### Material changes

A later answer can expose work that was not in the question it answered. Do not silently settle
that consequence. Add a new `Q` block when a round introduces or reverses any of these without the
user already approving it:

- durable storage or a migration,
- an endpoint, message, or breaking contract change,
- an external effect,
- a rollout phase or compatibility mechanism,
- a materially different consistency, retry, or ownership model.

At handoff, list every newly introduced item from those categories under `Material changes this
round`; write `None` when there are none. Name the mechanism, not only its purpose: “add a durable
dispatch table and migration,” not “make retries safe.” This callout directs review; it does not
replace the full-document read or the specification in `## Domain`.

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

**Prune as you fold.** `## Resolved` is the only place history belongs; everything above it is the
spec someone builds from. So each round leaves the body reading as though the design had been
right the first time — a claim a later round disproved is **deleted, not struck through**, a
paragraph that only made sense against a superseded mechanism goes with it, and a number that
turned out to measure the wrong thing is removed rather than annotated. This applies to your own
findings, not just to their annotations: most of what goes stale is research from an earlier round
that a later one overtook. Nothing is lost by deleting it, because the thread that produced it is
preserved below — and the working-tree diff is where they watch it go.

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
  nothing else in it. Its working-tree diff will be honestly unreadable, and everyone knows why.

**Pruning is not restructuring.** What this rule forbids is _moving_ text. Deleting a claim a
later round disproved is the most legible diff there is, and it is required — see _Prune as you
fold_.

No `~vN` markers on touched headings. They churn every round, and the editor gutter already shows
what changed.

## Starting over: a v2

Pruning keeps the body true. It cannot fix a doc whose _shape_ is wrong, and after several
changes of direction that is what you have: sections ordered by the sequence the questions
arrived in rather than what a reader needs, a subsection per round, back-references to threads,
and vocabulary chosen under a mechanism that has since been replaced. **A frame survives pruning**,
because every sentence inside it is accurate. That is how a clause that reads as housekeeping
under the old model ships as an instruction under the new one — which it has.

A v2 is a clean slate — not a revision of the old doc, a new one written from what is known now,
in the shape of a round 1.

- **A new file**, `~/designs/<topic>-v2.md`. The old doc is left exactly as it is: it is the
  record of how the design got here and worth keeping. Put one line at the top of it pointing at
  the v2, so nobody builds from the wrong file.
- **The decisions carry over; the deliberation does not.** Every settled fact is stated plainly
  as a fact — no strikethroughs, no "corrected in round 5", no quoted thread that produced it.
  `## Resolved` starts empty, because everything it would hold is in v1.
- **Write it from the premises that turned out to be true.** The whole point is that round 1 gets
  written a second time with the right assumptions, so the doc no longer argues its way toward
  them.
- **Fewer open questions than a real round 1**, often none. A v2 is not deliberately incomplete
  the way a first draft is.
- **A round 1's length.** If the rewrite lands anywhere near the length of the doc it replaces,
  it was copied rather than rewritten.

When a design needs this is a judgment, and it stays one — many rounds, direction changed more
than once, too much the reader has to hold in their head to keep from tripping over something
that used to be true. **The user calls for it; you don't need to offer it.**

## The template

Seven top-level headings. The DDD material is collapsed into one.

```markdown
# <Feature> Design

## Problem

## Approach

## Domain

## Test plan

### Pre-merge tests

### Production verification

## Tasks

## Open questions

## Resolved
```

### Approach

The shape of the change in two or three paragraphs: which existing mechanism it extends or
replaces, what moves, what stays. It exists so `## Domain` has an antecedent — a reader who meets
the noun list first has no way to tell why a type is marked touched, because nothing has yet
proposed doing anything to it.

It holds the reasoning the whole design rests on, stated once, so the `Q` blocks below don't each
restate it. It resolves nothing: every fork it names has a live `Q`.

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
| `StaleLeadDigestWorkflow` | an obsolete scheduled workflow                    | **delete**      |
```

Use the layer headings that fit what you found — typically **persisted state**, **functional
core**, **imperative shell**, **contracts**, and frontend when it's involved. Note the project
or directory next to the heading so the reader knows where to look.

Rules, because this section fails in predictable ways:

- **One line per noun. No exceptions.** This table is an index, not a spec — its job is to let
  you see what's in play and what the blast radius is, in one pass. The moment a cell holds a
  field list or two sentences, markdown pads every other cell to match and the table stops being
  readable at all.
- **No lists in cells.** If a noun's fields, columns, or enum members matter, they belong in
  `### Persistence changes` (for tables), `### API contract changes` (for endpoints and messages),
  or `### Proposed types` (for internal types) — not here. Here it gets a phrase: “the follow-up
  row; the only durable cadence state”.
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
- **Name the nouns that don't have types yet.** Identifiers and quantities that cross a boundary
  should use domain-specific types rather than bare `string` or `int` values. Give each one a row,
  and say which are becoming opaque types and which stay primitive because they never leave the
  edge.

Then any of these as `###` subsections, only when the change actually calls for them:

```markdown
### Persistence changes # new/changed DB tables — see below

### API contract changes # new/changed endpoints and messages — see below

### State space # states today; illegal combinations currently expressible

### Proposed types # unions and value objects, with units

### Decisions as data # the Decide/Plan signature and its cases

### Effects # the command records the core returns

### Rule ownership # each rule: where it lives now → where it lives after

### Invariants # what must always be true, and what enforces it
```

**`### State space` carries the transition table** when the change is a state machine. Document
the states and legal transitions. Also specify four concerns that transition diagrams often omit:
the event identity that provides idempotency; duplicate, stale, and out-of-order events; terminal
versus resumable states; and concurrency behavior.

**Mark the rows that become individual transition tests with a `Test?` column containing `yes` or
`no`.** The table has two jobs — it documents the machine's legal transitions and sets the
transition-test budget — and they do not necessarily have the same row set. A transition worth
naming is not automatically worth asserting. The test plan cites the number of `yes` rows, so the
reader can change the test count without deleting useful state-machine documentation.

Rules that keep the optionality honest:

- **A subsection appears when it has content, and is omitted otherwise** — never included
  with "unchanged" written under it. An empty heading is worse than no heading: it's a line
  you have to read to learn nothing.
- **State in one line at the end of `## Domain` which you skipped and why.** That makes
  skipping a visible decision they can push back on rather than a silent omission.

Depth scales with how much is being written from scratch. Greenfield fills most of the
subsections. A small modification to existing code may have nothing but the noun list and a test
plan; include domain detail in proportion to the new state space and boundary risk.

### Persistence changes

The noun list is an index; this is the persistence spec. Every new or changed database table gets
this subsection even when persistence was discovered in a later round or exists only to support
an endpoint. A noun-list row is never enough to introduce durable state.

Only what moves. An unchanged table gets its one-liner upstairs and nothing more, and a table
you're altering shows the columns you're adding or changing — not its existing 30. No DDL: the
downstream `$implement` workflow writes the migration.

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

### API contract changes

Every new or changed endpoint, route, or message gets its request and response fields in a table.
Put the things that aren't per-field below it: the auth lane, status codes, and **whether the
change is additive or breaking**. Force that last one explicitly: wherever a repo has a
deprecation convention or a breaking-change gate on its schema diff, “is this additive?” is what
decides whether the work is one PR or two, and it is much cheaper to answer here than at review.

Internal types belong only in the noun list and, when their shape matters, `### Proposed types`.

**These sections usually answer `## Test plan`'s prod-verification question for free.** A new
column or endpoint is very often the exact signal that proves the feature worked. If you write one
here, say so there.

### Test plan

Under `### Pre-merge tests`, use **one table row per test, one line per row, and no explanatory
paragraphs**. A marked transition table may be one counted row because it already names the
individual cases. This section is approved by being skimmed — the user strikes the rows they do
not want — and prose hides the count, which is the thing worth arguing about.

```markdown
### Pre-merge tests

| Test kind         | Case                                    | Expected                         | Change           |
| ----------------- | --------------------------------------- | -------------------------------- | ---------------- |
| Transition        | transition table above, 5 rows marked   | outcomes shown in the table      | add 5            |
| Invariant         | blank key on either side                | never matches                    | add              |
| Provider contract | captured payload, contact with no email | href as the consumer receives it | rewrite existing |
| Provider contract | unauthorized response body              | unlinkable, distinct copy        | add              |

No persistence-mapping, replay/interleaving, or end-to-end tests: this change adds no
persistence, durable state, or ordering behavior. Total: 8 tests.
```

Under `### Production verification`, answer in a line or two **how this gets verified in
production after it deploys**. That question has a code consequence, and the downstream `$ship`
workflow is too late to discover it. If proving the feature works needs a log line, metric, or
column that does not exist yet, **that is a task**, and it goes in `## Tasks` like any other.
Otherwise `$ship` ends up writing a weak proxy check or going back to add instrumentation after
the fact.

Only the first of `$ship`'s two monitoring-and-verification questions usually needs anything:

- **"Does the new thing work?"** — new behavior, so often no signal exists yet. This is the one
  to think about here. Name the signal: the log event and its fields, the metric, the row that
  should appear.
- **"Did we break the happy path?"** — watches pre-existing behavior, so the signal almost always
  already exists at a known volume. Nothing to build; just note what it'll be.

Don't write the queries here. Thresholds and query strings are `$ship`'s job, and they would be
stale by the time it runs. This section decides **what must be observable**, not how it gets
asked.

## Length

**250 lines at the outside for a normal feature, and far less for a small modification.**

The template is not what makes a doc long; verbosity is, and it's the failure mode this
section exists to check. A one-union bug fix should produce a page, not a chapter. If a
section has nothing to say, it says nothing.

## Writing the questions

A `Q` block that just asks "what do you think?" wastes a round. Each one needs:

- the decision to be made,
- the options, concretely; when there is more than one, label them `A.`, `B.`, and so on so the
  user can answer with a letter,
- a recommendation that names the option's letter,
- why that recommendation follows — only the part specific to this fork, since the reasoning the
  design rests on is already in `## Approach`.

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
- **Read the code, then check the data.** Reading tells you what the code does. It does not tell
  you what the rows look like, whether a filter works, or what an endpoint returns — so anything
  the design leans on gets looked at: count what fraction of rows carry the field you plan to
  join on, call the endpoint once, read a real payload. A claim taken from source alone is
  inferred, and says so where it appears.
- **No access is a reason to ask, not to infer.** Hand over the query or the curl for them to
  run. A premise nobody could check stays an open question or carries their explicit sign-off —
  never a sentence that reads like a finding.

## Then what

When there are no open questions, do one more pass over the full document to check for
inconsistencies and fix what you find. Then write `## Tasks`, leave that final proposal dirty, and
ask the user for one last full-document review. Do not call the design settled yet.

After the user approves that revision, commit the named file as `docs(<topic>): finalize design`
and output:

```
Design settled. Start a new session (or /clear) and run
`$implement ~/designs/<topic>.md` — a fresh context gets the full budget
for the work, and the task list is the handoff.
```
