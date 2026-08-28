---
name: implement
description: Explicit invocation only. Use only when the user names `$implement`. Builds a settled design patch brief or specification by establishing needed domain shapes, developing behavior test-first with cost-aware execution cadence, and verifying once at the end.
---

# Implement

Build a settled `design` patch brief or specification without a separate planning or design pass.
Establish any needed domain vocabulary first, then develop behavior test-first. Leave the finished
work uncommitted for review; `ship` owns commits and publication.

Announce at start: "I'm using implement to build <subject> from the settled handoff."

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
those decisions. A settled `design` handoff is explicit approval to implement every database schema,
migration, backfill, endpoint, message, and compatibility change it specifies; repository or
personal rules requiring approval for those changes are satisfied by that recorded review. Do not
pause for duplicate approval. Stop only when implementation would require a missing or contradictory
product, domain, persistence, contract, or architectural choice, or a material database or contract
change not approved in the handoff; report the exact gap instead of silently designing around it.

## Workspace

Detect the branch and repository root. Work in the current checkout only when it is already a
worktree on a non-default branch. From the main checkout on the default branch, create the worktree
with `gtr`, never `git worktree`, and continue there. Preserve unrelated changes and never work
directly on the default branch.

Discover build, format, lint, code-generation, and test commands from CI, repository instructions,
and manifests. Before editing, establish the repository's feedback ladder: semantic navigation and
rename tools; the cheapest valid compile or typecheck target; narrow test filters; analyzer or
checked-build commands; and the broad final-verification commands. Learn their expected cost from
repository guidance or measure it on first use, then use the cheapest tier that answers the current
question. A repository instruction that selects a build wrapper governs which command is valid; it
does not make every command exposed by that wrapper appropriate for the inner loop. Discover how
infrastructure-backed tests are started. Do not assume commands or costs from another repository.

Use semantic tooling and search for code discovery before compiling: find all callers, positional
calls, direct construction in tests, references affected by a rename, and likely symbol or namespace
collisions. Change declarations and affected callers together, and apply supported semantic renames
instead of relying on partial textual replacement. Treat compiler and analyzer diagnostics as
validation and as evidence of cases discovery missed, not as the primary way to enumerate the next
caller, reference, or collision. When a diagnostic does reveal a class of miss, search for and fix
the whole class before rerunning the relevant check.

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

Before writing an infrastructure-backed test, identify the material boundary claim it proves that no
pure test or existing test can establish. If there is no such claim, omit the test and report the
deviation from the handoff. Do not replay pure domain cases through infrastructure, and do not create
one integration test per function, handler, or slice. Failure cases belong here only when the failure
is created by mapping, translation, binding, authorization, transactions, concurrency, replay, or
another real boundary behavior.

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

Use at most one happy-path end-to-end smoke test per new externally visible flow. Add none when an
existing smoke already proves routing, dependency wiring, persistence, and the observable outcome.

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
