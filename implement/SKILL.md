---
name: implement
description: Explicit invocation only. Use only when the user names `$implement`. Builds a settled design patch brief or specification by establishing needed domain shapes, implementing the behavior, and verifying once at the end.
---

# Implement

Build a settled `design` patch brief or specification without a separate planning or design pass.
Establish any needed domain vocabulary first, then implement the behavior. Leave the finished
work uncommitted for review; `ship` owns commits and publication.

Announce at start: "I'm using implement to build <subject> from the settled handoff."

Load `ddd` before writing code.

## Preconditions

Accept either a specification path or the settled patch brief in the current conversation. A patch
brief is intentionally same-context; if neither it nor a specification is available, stop rather
than reconstructing one from a vague request.

For a specification, read the whole file, retrieve every required `## Context` artifact, and map each
`B` behavior to its execution slice. For a patch, treat the brief as one slice. The handoff is authoritative, but verify current
symbols, callers, and repository conventions before editing because the code may have moved.

Required context is a precondition, not optional background. If any artifact, document, design,
recording, environment, or other source needed to implement the handoff cannot be retrieved or read,
stop before editing and ask the user for the smallest access or material that unblocks it. Do not
skip the source, replace it with an inference, or quietly implement the parts that remain.

For UI work, search the handoff, its context, and the repository for a Figma file, frame, prototype,
screenshot, mockup, or other authoritative image. If one exists, open and visually inspect it before
writing code. Reading a link, node name, metadata, generated description, design-token export, or
prose summary is not viewing the design. Inspect the rendered layout and the applicable states,
variants, and responsive views at a useful scale. If the reference cannot be viewed, stop and ask
for access or exported images.

When no visual reference exists, proceed only if the settled handoff records that the visual design
was discussed with the user and supplies the approved layout, hierarchy, styling direction, states,
and responsive behavior, or records explicit permission for the implementer to improvise specified
visual choices. Otherwise report that the handoff is incomplete and wait for the user to decide how
to resolve it. Do not conduct a design interview, invoke `$design`, infer a new design from the
existing implementation, or invent one from prose inside an `$implement` run.

Do not ask the user to approve the specification. The grill already made
those decisions. A settled `design` handoff is explicit approval to implement every database schema,
migration, backfill, endpoint, message, and compatibility change it specifies; repository or
personal rules requiring approval for those changes are satisfied by that recorded review. Do not
pause for duplicate approval. Stop only when implementation would require a missing or contradictory
product, domain, persistence, contract, or architectural choice, or a material database or contract
change not approved in the handoff; report the exact gap instead of silently designing around it.

## Workspace

Detect the branch and repository root. Work in the current checkout only when it is already a
worktree on a non-default branch. From the main checkout on the default branch, create the worktree
with `git gtr new <branch>`, never a standalone `gtr` command or `git worktree`, and continue there.
The tool is a Git subcommand installed as `git-gtr`, so every invocation begins `git gtr`. Preserve
unrelated changes and never work directly on the default branch.

Discover build, format, lint, code-generation, and test commands from CI, repository instructions,
and manifests. Before editing, establish the repository's feedback ladder: semantic navigation and
rename tools; the cheapest valid compile or typecheck target; narrow test filters; analyzer or
checked-build commands; and the broad final-verification commands. Learn their expected cost from
repository guidance or measure it on first use, then use the cheapest tier that answers the current
question. A repository instruction that selects a build wrapper governs which command is valid; it
does not make every command exposed by that wrapper appropriate for the inner loop. Do not assume
commands or costs from another repository.

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

When the handoff calls for new domain vocabulary, write only the structural shapes the
implementation needs:

- opaque identifiers, values with units, unions, and result/failure cases;
- decision inputs and outputs, effect records, and stable public interfaces;
- persistence declarations required by the design.

For a patch that changes no domain shape, skip this phase. Otherwise enforce construction-time
invariants that belong to the type and compile or typecheck the narrowest relevant target. “Types
first” is not permission to implement behavior: method bodies remain absent, stubbed, or minimal
until the behavior requires them.

### 2. Implement the behavior

Test domain decisions through the functional core’s public seam. Test an infrastructure boundary only for behavior that the pure tests cannot establish: mapping fidelity, real provider binding, persistence semantics, or adverse ordering. Do not repeat domain cases through infrastructure.

### 3. Wire boundaries after the core

Load facts, call the pure decision, commit state once, then execute effects after commit, following
the settled transaction and recovery model. Map rows, wire models, and provider payloads at the edge;
do not admit their representations into the domain for convenience.

Develop persistence mapping, serialization, migrations, adapters, and endpoint wiring at their
specified boundaries. Run code generation when the repository requires it.

## Verification

After the final slice, perform one broad verification phase. Run the repository-defined equivalents
of:

1. build or typecheck;
2. format and lint;
3. affected test suites;
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

Summarize completed behavior by `B` IDs, verification performed, deviations from the specification, and
anything requiring human or production verification. Leave all changes uncommitted.
