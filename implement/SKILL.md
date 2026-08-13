---
name: implement
description: Execute a settled design — set up the worktree, work through the task list in chunks, verify once at the end, and leave everything uncommitted for review. Use when the user says to implement, build, or work through a design doc or a concrete task list. Replaces the old plan-then-work split; there is no separate planning pass.
---

# Implement

Take a settled design and build it. No separate planning pass — if the design doc's task list
is concrete, an agent with the file open produces the right edit without a transcribed edit
packet first.

Announce at start: "I'm using implement to build <subject>."

Load `ddd` before writing domain code — C# or TypeScript; rules 1, 9, and 10 apply to a
frontend unchanged.

## Input

```
implement ~/designs/<topic>.md
```

The design doc's `## Tasks` section is the task list, and the doc is the context — that's why
this can start in a fresh session with the full budget for the work.

**No design doc?** Then the one thing the old planning phase guaranteed is missing: blocking
questions asked before any code exists. So ask them first. Each question needs the decision,
the options, a recommendation, and why. Don't start writing until the answers that change the
shape of the work are in.

## Step 1: Where am I working

Detect, don't ask:

- **Already in a worktree on a non-default branch** → work here. This covers arriving via any
  personal setup script.
- **In the main checkout on the default branch** → create a worktree (`git worktree add`, or
  whatever wrapper this setup uses) and move into it.
- **Never work directly on the default branch.**

One `git branch --show-current` and `git rev-parse --show-toplevel` answers this. Don't open a
multiple-choice prompt about it.

## Step 2: The chunk loop

Each chunk is at most a few hundred lines.

```
write the chunk → next chunk → … → verify once, at the end
```

**Don't build or run the suite per chunk.** It is the single biggest waste in this loop: a
`dotnet build -p:EnforceCodeStyle=true` plus `dotnet test` per chunk multiplies the slowest part
of the work by the number of chunks. And it produces false failures — chunk 2 routinely adds the
caller for the signature chunk 1 introduced, so an intermediate state legitimately doesn't
compile.

What each chunk _does_ get: reread what you wrote, and if you added a focused test that runs in
seconds, run that one test. Nothing that touches the whole solution.

**No commits.** Leave everything uncommitted unless explicitly told otherwise — the user reviews
the whole change at the end, and intermediate commits make that final `git diff` harder to
read. `ship` does the committing.

**No sign-off between chunks.** Proceed automatically with a one-line summary:

```
Chunk 3 complete. Board now archives on `a`. Moving to chunk 4...
```

Have a rough chunk breakdown up front; adjusting it as you go is fine and expected.

**Print the test table with it.** Same three-column format the design doc uses — layer, case,
expected, one row per test, count on the last line — before any test is written. The user strikes
the rows they don't want; what survives is the budget. If the design already has the table, print
that one and note what you'd change rather than inventing a second. This is the whole
intervention: a test list is only a budget if someone can see the number and argue with it, and
after the tests exist nobody re-litigates them.

## Step 3: Before changing any signature

Find **all** callers — not just one level up. Integration test projects instantiate services
directly with `new ServiceName(...)`, per-project builds miss them, and it surfaces in CI
instead.

- A Roslyn-backed find-references tool for C# when the setup has one; `grep -rn "MethodName(" src/`
  otherwise.
- Check **positional argument** usage specifically. Adding a parameter in the middle compiles
  fine at some call sites and silently changes meaning at others.
- Fix affected callers in the same chunk, or place the new parameter so nothing shifts.

## Step 4: Verify the work

Once the chunks are written, not between them. Validation is broader than tests — pick what
actually proves the feature works:

| Method               | Fits                                                       |
| -------------------- | ---------------------------------------------------------- |
| **Run it and check** | CLI tools, scripts, endpoints — execute it with real input |
| **Query the state**  | migrations, mutations, generated files                     |
| **Visual check**     | UI work                                                    |
| **Existing suite**   | refactors and bug fixes with coverage                      |
| **New tests**        | real business logic, edge cases, transformations           |

**Build success is not verification.** A compiling feature that was never executed is
unverified, and saying otherwise is the thing not to do. But the reverse is also true: running
the feature is not a substitute for the required checks below. Both, always — and both once.

**Neither is a test whose fixtures you wrote by reading source.** A provider's code gives you its
shape, never that your request works or that real rows look like your fixture. So where the design
says to call the thing — a live request, a captured payload, a query against real data — call it.
If you can't reach it, **stop and ask them to run it**; shipping the inference instead needs their
sign-off out loud, not a line in the deviation list. And if the change renders something, look at
it rendered.

### Required checks — once, after the last chunk

When the work is done, these must pass:

1. **It compiles** — build or typecheck, whichever the language has.
2. **Format and lint are clean.**
3. **The tests pass** — the existing suite for what you touched, plus anything you wrote.

**Once, not per chunk.** The cost of the alternative is the whole point: these are the slowest
commands in the loop, and running them N times to learn the same thing N times is where an
implementation session quietly loses its afternoon.

What that trades away is attribution — a failure at the end doesn't say which chunk caused it.
That's recoverable and cheap: the chunk summaries say what each one touched, and everything is
still uncommitted, so `git diff` plus the summaries narrows it in one pass. Fail-fast per chunk
would only be worth its cost if the checks were fast; on a large solution they are not.

### Don't start a build while another one is running

If you run agents building in the background while you test, two builds colliding is the normal
failure, not a rare one. Two uncapped .NET builds each grab roughly one MSBuild node per core,
so they oversubscribe the box by 2× and can push it into swap. Check first:

```bash
cores=$(sysctl -n hw.ncpu)
active=$(ps -Ao ppid=,command= | awk '$1 != 1 && /MSBuild\.dll/' | wc -l | tr -d ' ')
load=$(sysctl -n vm.loadavg | awk '{print $2}')
echo "active MSBuild nodes: $active   load1: $load / $cores cores"
```

- **`active` > 0** → another build is live. Say which and **ask** whether to wait or proceed.
- **`load1` > cores** → the box is saturated by something. Same treatment.
- Otherwise → go.

**Ask; don't loop waiting.** A poll that blocks until the box is quiet wedges the session when
it never gets quiet. Report and let the user decide.

Two traps that make the naive versions of this check useless:

- **`ppid != 1` is load-bearing.** Finished builds leave MSBuild nodes idling ~15 minutes,
  reparented to PID 1. A plain `pgrep -f MSBuild.dll` counts those too, and the idle leftovers
  routinely outnumber the live ones several times over — so the naive count is wrong roughly
  all the time.
- **`pgrep -f` matches your own wrapper.** The agent's own shell command line contains whatever
  pattern you searched for, so `pgrep -f 'dotnet build|vitest'` reliably finds itself. Use
  `ps` + `awk` on a pattern that can't appear in your own invocation, or the load average.

### Cap your own build's parallelism

Pass `-m:N` on `dotnet build` and `dotnet test`, with N around 40% of the box's cores — chosen
so two concurrent builds fit inside the core count instead of oversubscribing to double it.
Individual builds get somewhat slower; concurrent builds get dramatically less awful, which is
the right trade when something is usually building in another session.

Two things this does **not** cover, so don't claim it does:

- **A repo's own build wrapper may ignore it.** A Cake/Make/script target that constructs its
  own MSBuild invocation without setting `MaxCpuCount` runs uncapped no matter what you passed.
  Check whether the aggregate target honours `-m` before claiming the cap applied; changing it
  means changing the repo, which is a team conversation rather than something to slip into a
  personal skill.
- **`MSBUILDNODECOUNT` is not a thing.** `MSBuildNodeCount` is a reserved MSBuild _property_
  reflecting `-maxcpucount`; there is no environment variable of that name that sets
  parallelism. Exporting it looks like a fix and isn't. `-m:N` is the form that works.
  (`MSBUILDDISABLENODEREUSE=1` _is_ real, and belongs in a shell profile, not here.)

**Never run `dotnet build-server shutdown` or reap MSBuild nodes from this skill.** VBCSCompiler
is shared across sessions — shutting it down mid-build breaks another session's build. Fine to
run by hand on an idle box; wrong as an automatic step.

### Discovering the commands

**Discover them; never assume.** These repos disagree with each other, and guessing produces a
green light that means nothing. In descending order of authority:

1. **CI workflows** — `.github/workflows/*.yml`. This is the definition of correct: whatever
   the `pr-*` jobs run is what has to pass, stated by the repo itself.
2. **The repo's `AGENTS.md` / `CLAUDE.md`**, which sometimes names the commands directly.
3. **Manifest scripts** — `package.json` scripts called `check`, `lint`, `typecheck`, `test`,
   `format`; a `Makefile`/`justfile` target; a `scripts/` directory of `check-*` files.
4. **Toolchain default**, only when the first three say nothing: `dotnet build` + `dotnet test`,
   `tsc --noEmit`, and so on.

Prefer a single repo-defined aggregate when one exists — a `check` script that chains
format + lint + typecheck + test is the repo telling you exactly what it wants, and it can't
drift from CI the way a hand-assembled list can.

Assume nothing carries over between repos, including two repos in the same language and the
same org. The specific traps that make guessing expensive:

- **A bare compile can skip the analyzers CI runs.** Style and unused-import rules are often
  gated behind a flag or a separate target, so the build passes locally and fails CI on
  something the local invocation never checked. Find the flag in the workflow.
- **The formatter is per-repo and not inferable from the language.** Reaching for the one that
  happens to be installed reformats files against the repo's own convention and buries the real
  change in noise.
- **Codegen may be a required step.** Some repos need a schema/contract regeneration target run
  whenever DTOs, messages, or entities change; skipping it fails CI with a diff, not a
  compile error.
- **A solution plus a frontend needs both halves run.** A green `dotnet test` says nothing about
  the `www/` bundle beside it.

**Record what you discovered** in the first chunk's summary, so later chunks reuse it instead
of re-deriving it, and so a wrong guess is visible rather than silent.

**Record the tree they passed on.** These checks are a function of the working tree, so a green
result is only a fact about one exact state of it. Print a fingerprint alongside the result:

```bash
{ git rev-parse HEAD; git status --porcelain; git diff HEAD; } | shasum -a 1 | cut -c1-12
```

`ship` compares against this to avoid re-running everything a minute later on an identical
tree. Verified behaviour: it changes when a tracked file is edited or an untracked file appears,
returns to its previous value on revert, and **deliberately ignores gitignored files** — those
aren't pushed and CI never sees them, so they can't invalidate a result. It does not capture the
_contents_ of untracked files, only their paths.

**If the design named a signal for prod verification, make sure it actually lands.** The design's
`## Test plan` may say a log event or metric must exist so `ship` can verify the change in prod.
If it turns out that signal can't be emitted where the design assumed — wrong layer, no access to
the field, the event fires on a path that doesn't run — **say so now, in the chunk summary.**
Discovering it at `ship` means shipping without verification or going back to instrument.

**A failing test is a stop, not a note.** Report it with the output and wait — do not proceed
to the next chunk, and do not describe the work as done. If a test was already failing on the
base commit, say so explicitly and carry on; a pre-existing failure is context, not permission.

If discovery genuinely turns up nothing runnable, **ask** rather than inventing a command.

### What makes a test worth writing

Each proposed test gets a one-line reason — the `Expected` clause of its row in the table, not a
second paragraph beside it. That requirement exists to force articulating value instead of writing
tests reflexively. If the reason is hard to write, that is the finding.

**Which layers a change touches is a claim about its risk**, so the count is a finding as much as
a plan: an ordinary change is one to three tests across one or two layers, and the budget belongs
at the boundary rather than in a third pure case. See `ddd`'s *Eligibility, not obligation*.

- **High value** — guards an edge case that silently returns null and crashes downstream;
  tests a business rule with several conditions; covers a failure or retry edge that
  integration tests can't reach; states an invariant that must hold across all inputs.
- **Low value** — `constructor sets properties` (the type system has it),
  `calls repository.save once` (asserts on a mock, breaks on any refactor),
  `maps field A to field B`, `returns correct type`, and **a hand-built DTO asserted field by
  field** — that tests your own constructor, and proves nothing about model binding or the
  payload the sender actually transmits.
- **Mock external boundaries** (HTTP, DB, filesystem, third parties), not the unit's own
  collaborators. If `OrderService` calls `PriceCalculator`, test them together.

**Assert on output or observable state, not on interactions.** The narrow exception is a
sequencing guarantee with no observable proxy — and before reaching for it, check whether a
replay/interleaving test (`ddd` layer 5) asks the same question better, as behavior under an
adverse ordering rather than as a mock call sequence.

**For a state machine, the transition table is the test budget** — one test per row that
matters, not one per cell of the state × event grid. See `ddd`'s rule 11.

Prefer 1–3 high-value tests over a test per function. **And a test you can't attach a
user-visible failure to leaves with your change** when you're already in that file — not a
mandate to sweep the suite, just the ones in reach.

## Step 5: When something's wrong

**Stop on failure.** Don't attempt fixes past the second try on the same error — report:

```
## Chunk N failed: <name>
Error: <message>
Files modified before failure: <list>
Options: 1) fix and retry  2) roll back  3) change the approach
```

If the design turns out to be wrong rather than the code, say so and stop. Grinding on a bad
design is worse than losing ten minutes.

**It is always fine to say a task is too hard.** Bad work is worse than no work.

## Step 6: Self-review before reporting done

Two passes, in this order. The order matters — there's no point critiquing the quality of the
wrong feature.

### Pass 1: did I build what was asked?

Read the actual code against the task list, not against memory of what was written. **Don't
trust the summary in your own head** — finishing quickly is a signal to check harder, not a
sign of success.

- **Missing:** anything in the task list not actually implemented? Anything claimed but
  stubbed?
- **Extra:** anything built that wasn't requested? Any speculative abstraction, any
  "while I was in there"?
- **Misread:** did any task get solved in a way the design didn't intend?

Over- and under-building is the most common failure. Check both directions explicitly.

### Pass 2: is it good?

- Names say what things do, not how they work.
- `ddd`'s **Code shape** section — single responsibility, method length as a smell, named
  helpers over inline blocks, and where to stop.
- `ddd`'s twelve rules, for anything with a state space, a result type, money, or time.
- `ddd`'s **Boundaries** rules (9–10) for anything crossing an edge: bare-string identifiers, a
  row or provider payload used directly as the domain model.
- **Read the types you changed as a set** — `ddd`'s *Reviewing without reading every line*.
- No unused usings (CI treats IDE0005 as an error).
- Tests assert behavior, not mock interactions — and any test you can't attach a user-visible
  failure to shouldn't be in the diff.

## Step 7: Report

```
## Implementation complete

**Design:** ~/designs/<topic>.md
**Checks:** <the commands run, and where they came from> → PASS, tree `<fingerprint>`
**Verification:** <command> → PASS/FAIL, with the actual output
**Files created:** <list with purpose>
**Files modified:** <list with what changed>

**Deviations from the design:**

- <task or decision it diverges from> — <what was done instead, and why>
- …

or `None — built as designed.`

**Left undone:** <anything skipped, and why — or None>
**Manual checks:** <what only a human can confirm, or None>

Uncommitted, ready for review. `ship` when you want the PR.
```

**"Manual checks" is for what only a human can confirm** — a judgment call, a production
permission, an aesthetic. It is not a parking spot for verification you could have done yourself.

### Deviations

The design doc is the reference, so anything the implementation does differently is a thing
the user needs to review it as a _decision_, not discover later as a surprise in the diff. It counts
as a deviation if you'd have to explain it to someone reading the design alongside the code:

- a different approach to a task than the one the design named
- a type, method, column, or endpoint named differently than the design specified
- a signature that changed shape, or a parameter the design didn't anticipate
- an extra file, class, or dependency the design didn't call for
- a task done in a different place than the design put it
- a design decision that turned out to be wrong, unbuildable, or already done

**Cite what it diverges from.** "Used `IReadOnlyList` instead of the design's `List`" is
reviewable; "made some type changes" is not. Point at the task or decision by name.

**`None — built as designed.` is a real answer and often the right one.** Don't manufacture
deviations to fill the section — an invented list is worse than an empty one, because it trains
the reader to skim past the real ones.

**Deviations and "Left undone" are different.** Deviated = built, differently. Undone = not
built. Something can't be both; pick the one that's true.

**Prefer raising a deviation when it happens.** If a chunk forces a real departure from the
design — not a naming nit, an actual change of approach — say so in that chunk's one-line
summary as well. The report is the backstop, not the first notice; a design that was wrong is
usually worth knowing before three more chunks are built on it.

Report faithfully throughout. If a test fails, say so and show the output. If a chunk was
skipped, say which and why. Don't hedge on things that are actually done and verified.

## Subagents

Default to single-agent sequential work — chunks usually build on each other, and the
coordination overhead isn't free.

Reach for a subagent per chunk only for **wide mechanical fan-out**: the same transformation
across many independent files, where one agent would accumulate all of it in context for no
benefit. Never run two implementation subagents in parallel on overlapping files.

## Never

- Work on `main` without explicit consent.
- Commit, push, or open a PR from this skill.
- Change a signature without finding every caller first.
- Report "done" on something that only compiles.
