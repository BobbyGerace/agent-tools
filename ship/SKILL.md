---
name: ship
description: Explicit invocation only. Use only when the user names `$ship`; never activate it by inferring intent from a request to commit, push, open a PR, prepare work for review, or address reviewer findings. Commits finished work, writes review and verification material, and opens a draft PR.
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
git remote get-url origin                                    # which host: Gitea or GitHub
git rev-parse --abbrev-ref --symbolic-full-name @{u}         # the tracking branch
```

**Host.** Pick the CLI from the origin URL, never by habit: `tea` for a Gitea remote, `gh` for
GitHub. A repo that migrated hosts often leaves an archived copy behind, so the wrong CLI either
fails or finds the stale copy. Then check for an existing PR:

```bash
# Gitea — 404 means no PR yet. Fields: number, state, draft, html_url, body, base.ref
tea api repos/<owner>/<repo>/pulls/<base>/<branch>
# GitHub
gh pr view --json number,state,isDraft,url,body,baseRefName
```

**Base branch.** New PRs branch off the repo's default branch — read it, don't assume
(Gitea: `tea api repos/<owner>/<repo> | jq -r .default_branch`; GitHub:
`gh repo view --json defaultBranchRef -q .defaultBranchRef.name`). Don't stack on an unmerged branch — if there's a real code dependency,
ask first. A base named in the invocation is that answer; use it, including in the `--base` below.
If the base is ambiguous, **stop and ask**.

**On `main`?** Create a branch with a short kebab-case name derived from the change, and move the
work over. Choose the name yourself; it has no consequence worth a question.

**Verify the feature, not merely the build.** Reuse credible implementation evidence when it
exists. Otherwise perform the cheapest direct exercise appropriate to the change: run the command,
exercise the affected flow, inspect resulting state, or visually inspect the UI. Do not require a
production deployment to prove work that can only run after merge; describe that limitation and
make it part of Monitoring & Verification instead.

### Pre-push checks

Optimize this gate for **time-to-merge**, not local reproduction of CI. Catch cheap, likely, and
deterministic failures before publishing, then start authoritative CI promptly. The gate normally
consists of the repository's formatter/linter, a scoped checked build or typecheck, affected tests,
required generation or contract checks, and direct feature verification. It does not automatically
include every repository test or the complete CI matrix.

Before an expensive command, establish its prerequisites, make orchestration fail fast with a
trustworthy exit status, and estimate its cost. If an applicable environment skill provides a
cheaper valid build loop, load and follow it. Prefer the narrowest check that can disprove the
change; reserve broad or aggregate commands for cases where repository guidance requires them or
the change's blast radius genuinely makes narrower selection unsafe.

#### Reuse verification evidence

Verification evidence is portable across agents, sessions, and handoffs. Trust evidence when it
identifies the repository and tree, records the exact commands and results, and is credible enough
to audit. `implement` records a working-tree fingerprint for this purpose. Compare it when present:

```bash
{ git rev-parse HEAD; git status --porcelain; git diff HEAD; } | shasum -a 1 | cut -c1-12
```

- **Matching fingerprint and green evidence** → do not re-run it. Name the checks and their source:
  `checked build + lint + affected tests already green on <fingerprint> — not re-run`.
- **No usable evidence** → run the local gate above. Absence of same-session history is not a
  reason to recreate the full CI matrix.
- **Fingerprint changed after verification** → inspect the intervening diff and invalidate only
  evidence whose inputs or behavior could have changed. Re-run the formatter after formatting;
  re-run the affected test target after a test-fixture correction; do not repeat unrelated frontend,
  backend, or repository-wide checks merely because the global fingerprint changed. If impact
  cannot be bounded confidently, broaden the relevant check rather than every check.

Do not claim that an identical tree can never produce a different result: infrastructure-backed
and flaky tests exist. Reuse prior evidence because repeating it is usually low-value, while CI is
the authoritative exhaustive run—not because execution is mathematically deterministic.

When you do run checks, check for a concurrent build first and cap your own parallelism, exactly as
`implement` describes. Use commands **discovered from this repo**, not remembered from another one.
CI and repository aggregate commands reveal what must be covered, but they are not automatically the
right local command: select scoped repository-supported targets when they establish the same claim
more cheaply.

**Don't assume a git hook ran checks for you.** Hooks are frequently disabled and a skipped hook is
silent. Conversely, do not manually recreate a whole hook or CI workflow merely because it will be
skipped. Follow explicit repository or environment guidance about `--no-verify`, and deliberately
run only the useful affected checks the hook would otherwise provide.

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

Include relevant, reviewer-accessible source links in **Additional Context**. Look for the ticket
when there is one, plus any Notion spec, Figma design, public document, discussion, or other
stable URL that materially explains the change. Prefer links already present in user-provided
context, the branch or commit history, an existing PR body, or committed repository material;
do not guess URLs. Use descriptive link text and omit links that the PR's reviewers cannot open.

Do **not** search personal uncommitted planning or design files for links, summarize those files
into the PR, or link to them. Untracked files and planning/design changes outside the committed
PR diff are private working material unless the user explicitly provides a public URL from them.

**Short wins.** Anything derivable from the diff stays out: class names, call sites, config
keys, file-by-file mechanics, test commands. A good hand-written PR is about half the length
of the exhaustive first draft. Aim for something skimmed in under a minute.

- **Problem** — the user-facing or system problem being solved. The _why_, not the what.
- **Implementation** — the shape of the approach at altitude: the key pieces and how they fit.
  The reviewer gets mechanics from the diff; give them the map.
- **Additional Context** — relevant source links, then what the diff can't show: gotchas,
  surprises, deliberate trade-offs, the risky parts, decisions that look wrong but aren't. If a
  sentence doesn't earn its place in one of these four sections, it belongs in a code comment
  instead.
- **Monitoring & Verification** — below. Required.

## Step 4: Monitoring & Verification

No PR is complete without it, and it must be **fully self-contained** — every query written
out inline, in the PR body. Never point at `verify-spec`, `.scratch/`, or any local tooling.

**Start from the design.** Its `## Production verification` section should already name the signal
that proves question 1, and any instrumentation needed for it should be in the diff. If the design
named a signal and it isn't there, that's a gap worth raising before opening the PR. If the handoff
has no production-verification section, work it out here — but expect to find that the needed log
line doesn't exist, which is the reason the question belongs upstream.

It must answer **both** of these, always:

1. **Does the thing we built actually work?** Positive evidence the new behavior is happening
   in prod — new rows appearing, new log lines firing, the new code path being taken.
2. **Did we break the happy path?** The pre-existing core flow this change touches still
   completes at its normal volume. Checks that only watch the new machinery can all pass
   while the feature is 100% broken, so at least one check must catch the change silently
   suppressing or failing the main flow.

For backend changes that's usually a telemetry count over logs or spans and/or a database query
— the actual statement, plus what a healthy result looks like. Telemetry lives behind
`telemetry-query`; run `telemetry-query --help` for where the data is, its tables and columns,
and how to write a query that finishes, rather than guessing them from another system's schema.
Include the threshold that distinguishes working from broken. For a `> 0` check on new behavior,
say when it should first go non-zero: at deploy it reads zero with everything working, and on a
low-traffic feature it can stay zero for days.

**Bound every SQL query on a column that is actually indexed.** A check re-runs on the backoff
ladder for as long as the spec is open, so an unbounded query is a full table scan every tick and
will time out rather than return anything — and a check that times out is unverified, not
failing. Confirm the index exists rather than assuming it: the migrations and entity
configuration are in the repo, so this is checkable before you ship. The semantically obvious
column is often the unindexed one, and if you substitute an indexed column for it, make sure the
substitute can't exclude rows the original would have kept. Telemetry statements need the same
bound: `--help` names the time and sort-key columns every one must filter on.

**Say which store each query targets** — telemetry (logs and spans) or the database — because
the spec has to route it and they fail when swapped. Log evidence is a message string or the
logger's category (Serilog's `SourceContext`); span evidence is a span name, route, status, or
span attribute. `source` is the first element of a check's address — see below.

**An instrumented service is not necessarily a queryable one.** Code that starts a span or writes
a log proves the signal is *emitted*, never that it reaches the store you are about to query — a
service can carry a correct-looking name in its own source and export nowhere you can see. So the
service and store are part of the address, not something the diff can establish. Control them
(below) rather than reading them off the code.

**"There is no signal" is an address claim too**, and it holds only after trying a path other than
the one that failed. Declaring one dead on a single attempt stops the measuring — the same outcome
as having no signal, reached without the evidence.

**Request liveness and request errors may not live in the same store.** An app can log errors with
request scope while emitting no per-request event at all, in which case a path or route facet with
no other predicate matches only incidental logs that happen to fire during a request — a `> 0`
check on it stays empty and can go green off an unrelated startup line, while the same facet with
an error predicate is perfectly sound. Control each direction separately; see rule 1.

**Frontend changes have no browser source.** A backend query proves nothing about a browser bug,
and the telemetry store holds no browser events. So a frontend-only change gets no automatable
check: say so in Monitoring & Verification, and say what a person should look at after deploy
instead — including a separate error tracker, if one collects frontend errors. When the change
also alters what the frontend asks of the backend — a new API call, a changed request — that half
is checkable as spans on the backend route, and so is question 2: the route's request volume
holding at its normal level shows the page still calls it.

If a change genuinely can't be verified this way, say so explicitly and explain why. Don't
omit the section.

### Every check needs a control

A check is an **address** plus a **predicate**. The address says where to look: `source`
(telemetry / postgres), the environment, service, table, columns, attribute keys _and their
value patterns_, enum literals. The predicate is the part this PR changes — the new message
string, the new column's value, an error-severity filter.

Only the predicate is unprovable before deploy. The address is provable now, and an unproven
address is the most expensive defect in this workflow: a misaddressed query returns 0, which
reads as "the feature hasn't fired yet" on a `> 0` check and as "healthy" on an error gate.
The cost is never the red — it's the green that isn't evidence.

For every check, before it ships:

1. **Reuse an address that already works — but only in the direction it was proven.** grep
   `$VERIFY_HOME/active/*.toml` and `archive/` for a check with the same `source` hitting the
   same service — failing that, a prior PR's Monitoring & Verification — and copy its address
   verbatim. A passing sibling is stronger evidence than anything you can reason out. Two limits
   on what a sibling can lend you, both of which have shipped false greens:
   - **An address proven for an error gate (`eq 0`) is NOT proven for `> 0`.** A sibling error
     gate reading zero tells you the query parses; it does not tell you the address can ever
     return data. If the sibling's op differs from yours, you have inherited nothing.
   - **A sibling's PASS only counts if that sibling's address was itself proven.** "Same shape ran
     clean through PR #X" launders a false baseline forward when #X's green was also an empty
     query. Follow the citation to a measured non-zero, or re-measure.
2. **Run the control, through the runner's path — not a side channel.** The same query with
   the predicate removed and _nothing else changed_ — same env, same service, same attributes,
   same table. It must return non-zero. Widening the time bound is allowed; a window is not an
   address. Dropping or loosening scope is not, because then you've proven an address you
   aren't shipping. For a telemetry check that path is `telemetry-query query`, the command the
   runner itself calls — not a UI, an MCP tool, or another client that happens to reach the
   same data.

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
4. **Record which.** One line in the check's `healthy` and beside the check in the PR body:
   `control: <query> = <n> over <window>`, or `address: <element> is new here, matches
   <file>:<line>`. Every check gets one or the other.
5. **Fail closed.** If an element is unproven in both directions, say so in the check and in
   the PR body. Don't ship it looking live.

### The spec file

Separately from the PR body — this is your own tooling and stays out of the description
entirely — write the same checks as a spec:

```bash
verify-spec schema                                    # get the current shape; don't trust memory
telemetry-query --help                                # the telemetry store: tables, bounds, limits
# write $VERIFY_HOME/active/<descriptor>.toml
verify-spec validate $VERIFY_HOME/active/<descriptor>.toml
```

Pick each check's `source` from where its evidence actually lives: `postgres` for the application
database, `telemetry` for logs and spans. Both take SQL, but in different dialects against
different tables, so a statement under the wrong `source` usually errors on every tick instead of
counting anything.

A telemetry check is one statement whose first cell is the count — `SELECT count() AS n ...` in
the dialect `--help` describes. The time bound goes in the statement; there is no `window` field.
Spans are as queryable as logs, so a change whose only evidence is a span name, route, or span
attribute is verifiable here, under the same control as a log line. A span visible in a trace UI
does not prove it reaches the store the runner reads; the control through `telemetry-query` does.
There is no browser source — see the frontend paragraph above.

`validate` is a lint on the spec, not the queries: it runs no network, so it is always safe to
run, and it cannot tell you whether a statement parses or returns data. The control does that.

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
getting it wrong is what makes a board stop being trusted. There is one rule, and it is absolute:

> **Red is only ever for a positive failure — something bad was observed. Absence of evidence is
> always `warn`, never `alert`.**

The mechanical test, and it settles nearly every case: **ask what the check does the instant the
PR deploys, before anything has had a chance to happen.** If it fails then, it is `warn`. No
exceptions, including checks you are confident about.

The op usually tells you outright:

- `eq 0`, `lt <n>` on an error or orphan count → **`alert`**. Failing means the query *found*
  something: orphaned rows exist, the fault rate is above the ceiling, errors are spiking. That is
  proof, and it cannot fire before the feature runs — zero passes.
- `gt 0`, `gte <volume>` → **`warn`**. Failing means the query found *nothing*, which at deploy
  time is exactly what you expect and tells you nothing. Every `gt 0` check on new behavior is red
  the moment it ships, and on a low-traffic feature it can stay red for days with everything
  working perfectly.

So the M&V split maps onto this the opposite way round from how it reads: Question 1 — _does the
new thing work_ — is a `gt 0` check and therefore **`warn`**, even though it's the check you care
most about. Question 2 — _did we break the happy path_ — is a volume floor and therefore `warn`
too. Most specs are mostly yellow-capable, and that is correct: a red on this board should mean
"stop and look", not "the feature hasn't fired yet".

"A row that should exist and doesn't" is absence of evidence, not an invariant. It is `warn`.

Once you have watched a `gt 0` check read non-zero, promoting it to `alert` is fair — at that
point a return to zero is a real regression rather than a cold start. That is a follow-up edit
after an observation, not something to ship on day one.

**Never run `verify-spec run` or `verify-spec watch`, or `verify-board`.** Those hit prod on a
loop and are the user's to run. A control is one read-only statement through `telemetry-query`,
which rule 2 requires; that is the only prod query this skill runs.

## Step 5: Open the PR

```bash
# Gitea
tea pr create --draft --base main --title "<type>(<scope>): <Sentence>" --description-file <body.md>
# GitHub
gh pr create --draft --base main --title "<type>(<scope>): <Sentence>" --body "<body>"
```

**Always `--draft`.** Never mark ready for review (`tea pr edit --ready`, `gh pr ready`), never
merge (`tea pr merge`, `gh pr merge`) — the user publishes when they are ready. On Gitea a draft
is just a `WIP: ` title prefix, so any title edit must keep it: pass `--draft` alongside
`--title` (it is idempotent).

If a PR already exists: update the body (`tea pr edit <n> --description-file <body.md>` /
`gh pr edit <n> --body`), and fix the base if it drifted (Gitea:
`tea api -X PATCH repos/<owner>/<repo>/pulls/<n> -f base=<branch>`; GitHub: `--base`). In
`tea pr edit`, `-r` means `--add-reviewers`, not `--repo` — spell `--repo` out.

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
- Mine personal uncommitted planning or design files for PR content or links.
- Ship without the Monitoring & Verification section.
- Run anything that queries prod, beyond a read-only control through `telemetry-query`.
