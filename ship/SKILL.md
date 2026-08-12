---
name: ship
description: Commit the work, write the PR description, author the prod verification spec, and open a draft PR. Use when the user says to ship it, push it, open a PR, or that the implementation is ready for review. Also covers responding to an automated reviewer's findings.
---

# Ship

Turn finished, verified work into a draft PR with a description a stranger can review and
verification checks that will actually run.

Announce at start: "I'm using ship to open the PR."

Load `ddd` for the pre-push self-check.

## Step 1: Pre-flight

Run these together:

```bash
git branch --show-current                                    # never ship from main
git status --porcelain                                       # what's about to be committed
gh pr view --json number,state,isDraft,url,body,baseRefName  # does a PR already exist
git rev-parse --abbrev-ref --symbolic-full-name @{u}         # the tracking branch
```

**Base branch.** New PRs branch off the repo's default branch — read it, don't assume
(`gh repo view --json defaultBranchRef -q .defaultBranchRef.name`). Don't stack on an unmerged branch — if there's a real code dependency,
ask first. If the base is ambiguous, **stop and ask**.

**On `main`?** Ask for a branch name, create it, move the work over.

**Verify the feature works before shipping.** Not the build — the feature. Run the endpoint,
execute the command, query the state. If it can't be verified, stop and ask how.

### Pre-push checks

The required checks from `implement` — it compiles, format and lint are clean, the tests pass —
must all have passed on **exactly the tree being pushed**.

**Don't re-run them if they already passed on this tree.** `implement` usually runs in the same
session and prints a fingerprint with its green result. Compare:

```bash
{ git rev-parse HEAD; git status --porcelain; git diff HEAD; } | shasum -a 1 | cut -c1-12
```

- **Matches a green run from this session** → skip them and say so, naming what was run:
  `build + lint + tests already green on <fingerprint> from implement — not re-run`. The tree is the only input; an
  identical tree cannot produce a different result, and re-running a full test suite to learn
  something you already know is a minute of nothing.
- **Anything else** → run them. That includes a different fingerprint, no fingerprint recorded, a
  fresh session, a green run you only inferred rather than saw, and any file you changed after
  it — **including your own formatter run**. When unsure, run it: the cost of a
  redundant run is a minute, and the cost of a skipped one is a red CI on a published PR.

When you do run them, check for a concurrent build first and cap your own parallelism, exactly as
`implement` describes — the collision risk is the same whichever skill triggers the build.
Use the commands **discovered from this repo**, not remembered from another one. `.github/workflows/*.yml` is the authority; a repo-defined aggregate script (`check`, `ci`,
a `Makefile` target) beats a hand-assembled list because it can't drift from CI.

**Don't assume a git hook ran these for you.** Hooks are frequently disabled outright
(`HUSKY=0` and friends), and a skipped hook is silent. None of these checks are optional.

**Only run the formatter the repo actually uses.** Don't reach for `prettier` because it's
installed. Running the wrong formatter reformats files against the repo's own convention and
buries the real change in noise. The discovery step above already finds the right one.

Two failure modes worth knowing, because they produce a local green and a red CI:

- **A bare compile can skip the analyzers CI enforces**, so style and unused-import violations
  surface only in the pipeline. Find the flag or target the workflow uses. When the analyzers are
  doc-comment rules, note that a reference inside a summary does not satisfy a missing-parameter
  rule — those want their own tags.
- **Generated artifacts may need regenerating** when contracts, DTOs, messages, or entities
  change. That failure appears as an unexpected diff in CI rather than a build error.

### DDD self-check

Before pushing, read the diff against `ddd/references/detectors.md`. Cheaper to fix a
contradictory result type here than to argue about it in review.

**Start with the types, not the logic** — `ddd`'s *Reviewing without reading every line*.

Do **not** treat a clean automated domain review as evidence the rules were followed — see Step 6.

## Step 2: Commit

Conventional format, no trailing period:

```
feat(crm): Add overage true-up planner
fix(messaging): Stop double-sending meeting reminders
chore(website-builder): Remove dead publish path
```

Scope vocabulary is per-repo. Read what this one actually uses rather than reaching for
another repo's list:

```bash
git log --oneline -40 --format='%s' | grep -oE '^[a-z]+\(([^)]+)\)' | sort | uniq -c | sort -rn
```

Pick the existing scope matching the changed paths; invent one only when nothing fits.

One commit for the whole change unless it genuinely splits into independently reviewable
pieces. The user reviews the final diff, so a clean single commit beats a chain of chunk commits.

## Step 3: The PR description

Four `##` headings, in this order, exactly these names. They're the standard ones — no cute
variants.

```markdown
## Problem

## Implementation

## Additional Context

## Monitoring & Verification
```

Write for **a reviewer with none of your context and no access to your tooling.** Every
section must stand on its own from the diff plus the PR text. Never reference a local path, a
scratch file, or a tool the reviewer doesn't have — a pointer they can't follow is worse than
nothing.

**Short wins.** Anything derivable from the diff stays out: class names, call sites, config
keys, file-by-file mechanics, test commands. A good hand-written PR is about half the length
of the exhaustive first draft. Aim for something skimmed in under a minute.

- **Problem** — the user-facing or system problem being solved. The _why_, not the what.
- **Implementation** — the shape of the approach at altitude: the key pieces and how they fit.
  The reviewer gets mechanics from the diff; give them the map.
- **Additional Context** — what the diff can't show: gotchas, surprises, deliberate
  trade-offs, the risky parts, decisions that look wrong but aren't. If a sentence doesn't
  earn its place in one of these four sections, it belongs in a code comment instead.
- **Monitoring & Verification** — below. Required.

## Step 4: Monitoring & Verification

No PR is complete without it, and it must be **fully self-contained** — every query written
out inline, in the PR body. Never point at `verify-spec`, `.scratch/`, or any local tooling.

**Start from the design.** Its `## Test plan` should already name the signal that proves question
1, and any instrumentation needed for it should be in the diff. If the design named a signal and
it isn't there, that's a gap worth raising before opening the PR. If there was no design doc, work
it out here — but expect to find that the needed log line doesn't exist, which is the reason the
question belongs upstream.

It must answer **both** of these, always:

1. **Does the thing we built actually work?** Positive evidence the new behavior is happening
   in prod — new rows appearing, new log lines firing, the new code path being taken.
2. **Did we break the happy path?** The pre-existing core flow this change touches still
   completes at its normal volume. Checks that only watch the new machinery can all pass
   while the feature is 100% broken, so at least one check must catch the change silently
   suppressing or failing the main flow.

For backend changes that's usually a Datadog logs query (the actual query string, plus what a
healthy result looks like) and/or SQL (the actual statement and the expected row shape).
Include the threshold that distinguishes working from broken.

**Bound every SQL query on a column that is actually indexed.** A check re-runs on the backoff
ladder for as long as the spec is open, so an unbounded query is a full table scan every tick and
will time out rather than return anything — and a check that times out is unverified, not
failing. Confirm the index exists rather than assuming it: the migrations and entity
configuration are in the repo, so this is checkable before you ship. The semantically obvious
column is often the unindexed one, and if you substitute an indexed column for it, make sure the
substitute can't exclude rows the original would have kept.

**Say which store each query targets** — logs, browser RUM, or SQL — because the spec has to
route it and they fail silently when swapped. Log evidence is a message string or
`@SourceContext`. `source` is the first element of a check's address — see below. **APM spans are
not one of the options**; if the only evidence is a span name or an `Activity.SetTag` tag, the
change is not verifiable here (details under the spec file, below).

**An instrumented service is not necessarily a queryable one.** Code that starts a span or writes
a log proves the signal is *emitted*, never that it reaches the store you are about to query — a
service can carry a correct-looking name in its own source and export nowhere you can see. So the
service and store are part of the address, not something the diff can establish. Control them
(below) rather than reading them off the code.

**Request liveness and request errors may not live in the same store.** An app can log errors with
request scope while emitting no per-request event at all, in which case a path or route facet with
no other predicate matches only incidental logs that happen to fire during a request — a `> 0`
check on it stays empty and can go green off an unrelated startup line, while the same facet with
`status:error` is perfectly sound. Control each direction separately; see rule 1.

**For frontend changes, use RUM** — `source = "rum"` in the spec, or an inline RUM query in the
PR body. A backend log query proves nothing about a browser bug. Read the app's RUM init for the
service name and env values rather than guessing them, then:

- `@type:error service:<app> env:<prod-env>` is the error channel.
- If the init sets a release, RUM events carry `version:<commit sha>`, so question 1 can be
  scoped to the exact deploy: `@type:error service:<app> env:<prod-env> version:<sha>`. That is
  much stronger evidence than a global error count, which drifts for unrelated reasons.
- For question 2, count views or a tracked action rather than errors —
  `@type:view service:<app> env:<prod-env>` at its normal volume proves the app still loads,
  which an error count alone does not.
- **A RUM zero is weaker than a logs zero.** Retention filters decide what stays queryable, so
  "no matching events" can also mean "not retained". The control below still has to run in the
  env you are shipping: if the query only returns non-zero under a dev env, you have proven its
  shape and _not_ its prod address. Record that rather than shipping it as a gate.
- If a separate error tracker also collects frontend errors, remember this tooling queries only
  RUM. When RUM is silent where you expected signal, check there before concluding the frontend
  is clean.

If a change genuinely can't be verified this way, say so explicitly and explain why. Don't
omit the section.

### Every check needs a control

A check is an **address** plus a **predicate**. The address says where to look: `source`
(logs / RUM / postgres), the env tag, service, facet names _and their value patterns_,
table, columns, enum literals. The predicate is the part this PR changes — the new message
string, the new column's value, `status:error`.

Only the predicate is unprovable before deploy. The address is provable now, and an unproven
address is the most expensive defect in this workflow: a misaddressed query returns 0, which
reads as "the feature hasn't fired yet" on a `> 0` check and as "healthy" on an error gate.
The cost is never the red — it's the green that isn't evidence.

For every check, before it ships:

1. **Reuse an address that already works — but only in the direction it was proven.** grep
   `$VERIFY_HOME/active/*.toml` and `archive/` for a check hitting the same store and
   service, and copy its address verbatim. A passing sibling is stronger evidence than anything
   you can reason out. Two limits on what a sibling can lend you, both of which have shipped
   false greens:
   - **An address proven for `status:error`/`eq 0` is NOT proven for `> 0`.** A sibling error gate
     reading zero tells you the query parses; it does not tell you the address can ever return
     data. If the sibling's op differs from yours, you have inherited nothing.
   - **A sibling's PASS only counts if that sibling's address was itself proven.** "Same shape ran
     clean through PR #X" launders a false baseline forward when #X's green was also an empty
     query. Follow the citation to a measured non-zero, or re-measure.
2. **Run the control, through the runner — not a side channel.** The same query with the
   predicate removed and _nothing else changed_ — same env, same service, same facets, same
   table. It must return non-zero. Widening the window is allowed; a window is not an address.
   Dropping or loosening scope is not, because then you've proven an address you aren't
   shipping.

   **The tool you measure with is part of the control.** A query tool can search a different
   store than the runner does — a different index, a historical/archive tier, a different
   default scope — and hand back a confident non-zero count for data the runner cannot see.
   Then the check ships with a recorded control and still reads zero forever. If you cannot
   measure through the same path the runner uses, say the address is unproven and mark the
   check `level = "warn"`; do not launder an out-of-band number into a `control:` line. The
   strongest control is an existing check the runner has itself scored PASS — prefer reusing
   one of those addresses over any measurement you take yourself.
3. **Prove new elements against the diff instead.** A message string, column, or route that
   this PR creates can't be controlled against prod. Match it to the artifact that will create
   it — the `Log.Here()` literal, the migration, the route attribute — copied character for
   character, never retyped from memory.
4. **Record which.** One line in `healthy`: `control: <query> = <n> over <window>`, or
   `address: <element> is new here, matches <file>:<line>`. Every check gets one or the other.
5. **Fail closed.** If an element is unproven in both directions, say so in the check and in
   the PR body. Don't ship it looking live.

### The spec file

Separately from the PR body — this is your own tooling and stays out of the description
entirely — write the same checks as a spec:

```bash
verify-spec schema                                    # get the current shape; don't trust memory
# write $VERIFY_HOME/active/<descriptor>.toml
verify-spec validate $VERIFY_HOME/active/<descriptor>.toml
```

Pick each check's `source` from where its evidence actually lives: `postgres` for SQL,
`datadog` for logs, `rum` for browser events. Same query string either way — only the `source`
differs, and getting it wrong is the failure this lint exists to catch.

**There is no APM source.** `spans` existed until 2026-08-06 and was removed for never returning
a usable count, including against addresses confirmed correct in the Trace Explorer. So if a
change's only evidence is a span name (`resource_name:`) or an `Activity.SetTag` tag, it is **not
verifiable by this tooling** — find a log line or a SQL predicate, or say plainly in the PR that
the change has no automatable check. Don't invent one that cannot fail.

`validate` is a lint on the _queries_, not just the TOML shape: `source = "spans"` and any APM
facet under `datadog`/`rum` are both rejected outright, because they could never return data. A
span *tag* is still unlintable — `@my.span.tag:true` looks exactly like a log attribute — so that
one is on you. `validate` runs no network, so it is always safe to run.

`verify-board` polls `active/`, so dropping the file in is the entire add path — nothing to
restart. Include the `[spec]` header:

```toml
[spec]
title   = "Overage true-up planner"
started = 2026-08-04T14:30:00-04:00   # from `date -Iseconds` — see below
pr      = 9812
repo    = "owner/api-service"
```

Get `started` from `date -Iseconds` rather than composing it. Two ways to get it wrong: a
bare date reads as midnight and skips the 20-minute tier that matters right after a deploy,
and a _naive_ timestamp is read as local time — so writing one in UTC dates the spec into the
future and the board shows a negative age.

`pr` is not decoration: the board holds a spec whose PR hasn't merged, showing it dimmed and
running no checks, because nothing is deployed yet and a red would only mean "not shipped".
Always include it, and `repo` too whenever the spec store covers more than one repo.

One `[[checks]]` entry per M&V check. It mirrors the inline queries; it never replaces them.

**Set `level` on every check.** It decides whether a failure shows red or yellow on the board, and
getting it wrong is what makes a board stop being trusted:

- `level = "alert"` (the default) — **failing is proof.** Absolute invariants: a non-zero orphan
  count, a digest that didn't build, an enum that won't resolve, a row that should exist and
  doesn't.
- `level = "warn"` — **failing might be nothing.** Volume and rate heuristics: "the poll is still
  serving", "contacts are still being captured", "no error spike". These fail on a quiet Sunday
  with nothing broken.

The M&V split maps onto this almost exactly. Question 1 — _does the new thing work_ — is usually
`alert`, because you're asserting a specific new behavior happened. Question 2 — _did we break the
happy path_ — is usually `warn`, because it's a volume comparison against normal traffic and
normal traffic varies. Say which you chose when the answer isn't obvious.

**Never run `verify-spec run` or `verify-spec watch`, or `verify-board`.** Those hit prod and
are the user's to run.

## Step 5: Open the PR

```bash
gh pr create --draft --base main --title "<type>(<scope>): <Sentence>" --body "<body>"
```

**Always `--draft`.** Never `gh pr ready`, never `gh pr merge`, never mark ready for review —
the user publishes when they are ready.

If a PR already exists: update the body with `gh pr edit <n> --body`, and fix the base with
`--base` if it drifted.

If the push fails on a pre-existing hook or CI-style check, read the error, fix it, retry.
After the **same error twice**, stop and report what was tried.

Title gets the PR number appended once it exists:
`feat(crm): Add overage true-up planner (#9812)`.

### Report

```
## PR open
**#<number>** — <title>
**URL:** <bare https:// URL on its own line — terminal, so no markdown links>
**Status:** Draft
**Spec:** $VERIFY_HOME/active/<descriptor>.toml (<n> checks) — on the board within 10s
```

## Step 6: Responding to an automated reviewer

Whatever bot reviews PRs here, treat it as useful and **not reliable in either direction**. The
two failure modes to expect, both observed in practice:

- **A confident false positive.** A CRITICAL finding asserting a documented behavior backwards —
  e.g. that a SQL function returns NULL when any argument is NULL, when the documentation says
  NULL arguments are ignored and existing production code depends on that. Severity is not
  evidence.
- **A real finding with a harmful fix.** It correctly spots a miscount, then proposes a patch
  that clamps the value to an unrelated display limit and destroys the real number.

It also misses things, including the worst defect in a run, so silence is not coverage.

So when the user asks "are those findings real and worth fixing?" they want **a per-finding
verdict with evidence, not implementation**:

- **Judge the finding and the proposed patch separately.** A real finding can come with a
  harmful fix.
- **Prove factual claims.** Fetch the documentation, or point at production code that depends on
  the behavior. Never reason from the review text.
- **When rejecting one, leave a code comment citing the evidence** so the next review doesn't
  re-raise it: `// NOTE: <reason>, per <evidence>`.
- Get confirmation before changing code in response.

Do **not** treat a clean automated domain review as evidence the `ddd` rules were followed.

## Never

- Push or open a PR without being asked.
- Omit `--draft`, or publish, or merge.
- Reference local tooling or paths in the PR body.
- Ship without the Monitoring & Verification section.
- Run anything that queries prod.
