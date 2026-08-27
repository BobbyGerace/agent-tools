---
name: implement-v2
description: Explicit invocation only. Use only when the user names `$implement-v2`. Builds a settled design-v2 patch brief or specification by establishing needed domain shapes, developing behavior test-first with cost-aware execution cadence, and verifying once at the end.
---

# Implement v2

Build a settled `design-v2` patch brief or specification without a separate planning or design pass.
Establish any needed domain vocabulary first, then develop behavior test-first. Leave the finished
work uncommitted for review; `ship` owns commits and publication.

Announce at start: "I'm using implement-v2 to build <subject> from the settled handoff."

Load `ddd` before writing code and use its test-layer reference to interpret the specification's test
table.

## Preconditions

Accept either a specification path or the settled patch brief in the current conversation. A patch
brief is intentionally same-context; if neither it nor a specification is available, stop rather
than reconstructing one from a vague request.

For a specification, read the whole file, retrieve every required `## Context` artifact, and map each
`B` behavior to its `T` tests and execution slice. For a patch, treat the brief as one slice and map
its adjustment to the named tests and verification. The handoff is authoritative, but verify current
symbols, callers, and repository conventions before editing because the code may have moved.

Do not ask the user to approve the specification or print a new test budget. The grill already made
those decisions. Stop only when implementation would require a missing or contradictory product,
domain, persistence, contract, or architectural choice; report the exact gap instead of silently
designing around it.

## Workspace

Detect the branch and repository root. Work in the current checkout only when it is already a
worktree on a non-default branch. From the main checkout on the default branch, create the worktree
with `gtr`, never `git worktree`, and continue there. Preserve unrelated changes and never work
directly on the default branch.

Discover build, format, lint, code-generation, and test commands from CI, repository instructions,
and manifests. Discover the narrowest supported test filters and how infrastructure-backed tests are
started. Do not assume commands from another repository.

Before changing a signature, find all callers, including positional calls and direct construction in
test projects. Change declarations and affected callers together.

## Execution slices

Implement the specification's one or two slices in order, or a patch brief as one slice. Announce a
compact summary when a slice begins and ends, but do not ask for sign-off between them. Do not commit
between slices.

### 1. Establish domain shapes

When the handoff calls for new domain vocabulary, write only the structural shapes the tests and
implementation need:

- opaque identifiers, values with units, unions, and result/failure cases;
- decision inputs and outputs, effect records, and stable public interfaces;
- persistence declarations required for boundary tests.

For a patch that changes no domain shape, skip this phase. Otherwise enforce construction-time
invariants that belong to the type and compile or typecheck the narrowest relevant target. “Types
first” is not permission to implement behavior: method bodies remain absent, stubbed, or minimal
until a failing behavioral test requires them.

### 2. Develop behavior test-first

Test-first governs evidence order, not process-startup count. Use the specification's `Cost` column
when present; for a patch brief, classify each named test from whether it needs a database, server,
provider, browser, or similarly expensive fixture.

For **fast tests** that execute in seconds without infrastructure:

```text
write one meaningful failing test
→ run the narrowest target and observe the expected red
→ implement the behavior
→ rerun green
→ refactor under green
```

For **infrastructure-backed tests**, batch the cases for one coherent seam:

```text
write the repository/endpoint/migration/provider batch
→ start or reuse its infrastructure once
→ run the narrowest supported target once and observe the batch red
→ implement the complete seam
→ rerun that target until green
```

Do not start a database, server, browser, or provider fixture once per assertion. Do not run the full
integration suite between behaviors or slices. If the repository cannot select a narrow target,
batch more aggressively rather than repeatedly paying for the whole suite.

A red observation must be real, not inferred. It is sufficient for the batch failures collectively
to demonstrate the missing seam; every assertion need not fail independently. A new behavioral test
that passes immediately is a finding: determine whether behavior already exists, the seam is wrong,
or the assertion is weak before proceeding.

Tests assert outputs, observable state, and boundary fidelity rather than mock call sequences. Mock
external boundaries, not the unit's own collaborators. Prefer one faithful database round trip,
captured provider payload, or replay test over several cheap tests that cannot detect the production
failure.

### 3. Wire boundaries after the core

Load facts, call the pure decision, commit state once, then execute effects after commit, following
the settled transaction and recovery model. Map rows, wire models, and provider payloads at the edge;
do not admit their representations into the domain for convenience.

Develop persistence mapping, serialization, migrations, adapters, and endpoint wiring at their
specified test seams using the cost-aware cadence above. Run code generation when the repository
requires it.

## Verification

After the final slice, perform one broad verification phase. Run the repository-defined equivalents
of:

1. build or typecheck;
2. format and lint;
3. affected test suites, including the infrastructure-backed batches;
4. required code generation and a clean generated diff;
5. actual execution, state inspection, or visual inspection appropriate to the feature.

Build success alone is not verification. Where the specification names a production signal, confirm
that the implementation emits or preserves it. If a required real boundary cannot be reached, ask
the user for the smallest external verification rather than claiming a source-derived fixture proves
it.

Fix ordinary local failures autonomously and rerun the narrowest affected check before repeating the
broad phase. Stop only for a changed design decision, missing authority/access, destructive or
out-of-scope work, inseparable pre-existing damage, or repeated approaches that yield no credible
next step.

For commands likely to exceed five minutes, follow the repository's detached tmux convention and
poll without blocking the conversation for more than a minute. Before starting resource-heavy
builds, check for competing builds and ask whether to wait when the machine is already saturated.
Use repository-supported parallelism controls; never terminate shared build servers or other
sessions' processes.

Record the final commands, results, and a working-tree fingerprint:

```bash
{ git rev-parse HEAD; git status --porcelain; git diff HEAD; } | shasum -a 1 | cut -c1-12
```

Summarize completed behavior by `B` IDs, tests by `T` IDs, deviations from the specification, and
anything requiring human or production verification. Leave all changes uncommitted.
