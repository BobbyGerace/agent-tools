---
name: explain-context
description: Explain an unfamiliar part of the system from the ground up — entities, contracts, state, and where the business rules live — so the reader can reason about it before designing or changing anything. Use when the user asks what something is, how an area works, to be brought up to speed, to get their bearings, or names a subsystem/ticket/file they don't yet understand. Not for explaining a diff or a PR.
---

# Explain Context

## The goal, and how this skill fails

The reader needs to **understand a domain before working in it**. This is a teaching
artifact, not an inventory. It succeeds when they finish feeling oriented — able to
predict roughly where a change would go and what would break — and it fails when it is
technically complete but leaves them no wiser.

Three specific failures, all of which produce a document that looks right:

- **Jargon before introduction.** Using a type name like `DealObligation`, or a piece of
  in-house vocabulary like "hot lead" or "cure window", before saying what it is. Every term
  gets defined the first time it appears.
- **Entity dump first.** Opening with field lists is the most common shape and the least
  useful. Field lists mean nothing until the reader knows what the thing is *for*.
- **Explaining the change instead of the system.** This skill explains what exists. If
  there's a diff involved, the reader wants the ground it sits on, not a walkthrough.

Announce at start: "I'm using explain-context to get you oriented on <subject>."

## Output

Markdown, straight to the terminal. **No file, no artifact.** This is often run outside
any work loop — idle curiosity, or to answer a coworker — so it leaves nothing behind.

Aim for something read in 5–10 minutes. Long is allowed where the domain earns it; padding
is not. The deep-background section must be genuinely skippable, so a reader who already
knows the area can jump to §2 without losing the thread.

## Step 1: Resolve the subject

The argument may be a topic ("hot leads"), an area (a directory or project), a single file, a
type name, or a ticket ID. Before researching, know which.

- **Ticket** → read it first; it names the entities and usually the confusion worth
  resolving.
- **Topic or vague area** → find the code that owns it before explaining anything. Do not
  explain a domain you have not opened.
- **Ambiguous between two subsystems** → ask, in one line. Explaining the wrong one wastes
  the whole document.

## Step 2: Research

Prefer retrieval over recall. Anything asserted here gets read first — a plausible-sounding
explanation of code you didn't open is the main way this skill produces confident nonsense.

Order that tends to work:

1. **The entities.** Find the EF entity / record / proto message at the center. Read the
   whole type, not the summary. Note every nullable field — those carry the state (§Step 3.5).
2. **The contracts.** Which gRPC routes, endpoints, or pubsub messages read and mutate it.
   Find the repo's primary API surface rather than assuming — its `AGENTS.md` / `CLAUDE.md`
   often says, and a proto/schema directory or a controllers tree shows it. Repos disagree
   about this, so look rather than pattern-match from another one.
3. **The writers.** Every place that mutates the entity. A Roslyn-backed find-references tool
   beats grep for C#; use one when the setup has it.
4. **The rules.** Where eligibility, validation, and transitions are decided — and whether
   any rule is decided in more than one place.
5. **The written record**, if there is one — a knowledge base, an ADR directory, design docs.
   It often names the intended design where the code only implies it. Skip this step rather
   than inventing a source when the project has none.

When something looks wrong rather than merely unfamiliar, note it for §7 and keep going.
Diagnosing is a different job.

## Step 3: Write it

Seven sections, in this order. The order is the pedagogy — §4 before §3 is the failure mode
named above.

### 1. Deep background *(mark skippable)*

The surrounding system for someone who doesn't know it. Start from the business reality —
what a contractor or coordinator is actually doing when this code runs — and only then the
software. Head it with a note that a reader who knows the area can skip to §2.

### 2. Narrow background

The part that bears directly on the subject asked about. Two or three paragraphs. This is
where the reader learns which of the many things in §1 they actually need to hold.

### 3. Intuition

The essence, not the details, using **concrete toy data**. Walk one realistic case end to
end with made-up but plausible values — a named contractor, a specific timestamp, a real
dollar amount. This is the section the reader remembers; if only one section is good, make
it this one.

Toy data beats abstraction here. "A lead comes in at 4:55pm Friday and the 24-business-hour
clock doesn't start until Monday 9am" teaches more than any description of the clock.

### 4. Domain objects

*Now* the shapes. For each entity: what it represents in one line, then the real field list
with types. Call out explicitly:

- **Nullable fields**, and what `null` means for each — absence, "not yet", or "not
  applicable" are three different things and are frequently conflated.
- **Fields that only make sense together**, and which combinations are legal.
- **How the entities relate**, with the real FK/navigation names.

### 5. State

The state machine — whether or not one is written down. Expect it to be **implicit** more
often than not: reconstructed at read time from a cluster of nullable timestamp and boolean
"evidence" fields rather than held in a status column.

If it is implicit, say so plainly and list the exact fields it's inferred from. This is the
single most useful thing this skill produces, because it is what nobody can see from
reading any one file, and it is what makes a change dangerous.

Draw the states and transitions as ASCII (see below).

### 6. Where the rules live

Each business rule → the class and method that owns it. Then the question that matters:
**is any rule decided in more than one place?** A rule implemented in both an endpoint and
an aggregate projection is a latent divergence, and finding it here is cheap.

### 7. Seams

Where a change would naturally go, and what it would ripple into. Two or three sentences
per plausible direction. Also the place to note anything that looked wrong during research
— flagged, not diagnosed.

## Diagrams

ASCII only. No mermaid — it doesn't render in a terminal, which is the whole reason this
skill outputs text.

Use them where a shape genuinely beats a sentence: state machines, data flow across
services, which component owns what. Carry **real type and field names** inside the boxes,
not placeholders. Pick one or two diagram families and reuse them across sections rather
than inventing a new visual idiom per point.

```
  Open ──warningDue──▶ WarningSent ──cureExpired──▶ Breached
   │                        │
   │                        └──qualifyingCall──▶ Resolved
   └──ineligible──▶ Dismissed

  inferred from: Status, WarningSentAt, CustomerNotifiedAt,
                 BreachNotifiedAt, RectifiedAt
```

Three or four such figures is plenty. A dozen is worse than none.

## Rules

- **Define every term on first use.** No exceptions, including terms that feel obvious.
- **Real names throughout.** `OrderOutcomeService.CreateAsync`, the literal column name, the
  actual endpoint path. Never invent a nickname for something that has a name in the code.
- **Say when you're inferring.** If a claim comes from a filename or a naming convention
  rather than from code you read, mark it. Confident wrong explanations are the expensive
  failure here.
- **No diff walkthrough, no history, no how-we-got-here** unless asked. The reader wants
  the system as it is today.
- **No hedging filler.** "It's worth noting that", "essentially", "at a high level" — cut.

## Not this skill

- Explaining a code change, branch, or PR → that's `explain-diff-html`.
- Root-causing a bug → investigate it instead; this skill describes, it doesn't diagnose.
- Designing a change → that's `design`, which assumes the reader is already oriented and
  usually wants this skill run first.
