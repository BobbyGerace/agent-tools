# Implementation specification

The interview is the human review surface. This document preserves the resulting behavior, exact
shapes, decisions, and evidence for a fresh implementation session. Write for precise execution,
not progressive teaching. Omit inapplicable subsections rather than writing “none” throughout.

Only `Objective` and `Behavioral contract` are always required. Include every
other section that carries an implementation-relevant fact or settled boundary, and omit it entirely
when it would be empty. Medium work should produce a shorter instance of this specification, not a
different document kind.

```markdown
# <Feature> Specification

## Objective

## Current-system facts <!-- optional -->

## Behavioral contract

## Domain model <!-- optional -->

## Persistence and external contracts <!-- optional -->

## Implementation decisions <!-- optional -->

## Tests <!-- optional -->

## Execution slices <!-- optional when one obvious slice covers the work -->

## Out of scope <!-- optional -->

## Production verification <!-- optional -->

## Context <!-- optional -->
```

## Objective

State the problem, why it matters, and the intended outcome. Describe the solution only at the level
needed to establish its boundary.

## Current-system facts

Include only implementation-relevant facts: current control flow, ownership, precedents, limitations,
and observed runtime properties. Label source-only conclusions as inferences. Use real symbols and
paths when they help a fresh implementer retrieve the code; this is a near-term local handoff, not a
timeless product requirements document.

## Behavioral contract

Write an extensive numbered list of independently checkable behavior, including failures, repeat
operations, compatibility, permissions, and externally observable effects:

```text
B1. When <precondition/event>, the system <observable behavior>.
B2. If <failure>, the system <observable recovery or result>.
B3. Repeating <event> with the same identity does not <duplicate effect>.
```

Use actor-style user stories only when they communicate a behavior more precisely. Execution slices
cite the behavior IDs they cover.

## Domain model

Include exact declarations, tables, or concise pseudocode when shape carries meaning. Use applicable
subsections:

- **Types** — unions, opaque identifiers, quantities with units, inputs, results, and failures.
- **State and transitions** — legal transitions plus duplicate, stale, terminal, cancellation, and
  out-of-order behavior.
- **Decisions and effects** — the pure decision signatures and data returned for execution.
- **Invariants** — what must always be true and what construction or boundary enforces it.
- **Rule ownership** — each material rule and its single owner after the change.

State whether the work is greenfield or a modification that follows established local conventions.

## Persistence and external contracts

Specify changed boundaries exactly. For persistence, give database types, nullability, keys,
constraints, indexes, migration/backfill behavior, and concurrency semantics. For endpoints and
messages, give fields, errors, authorization, serialization, and whether the change is additive or
breaking. Include transaction ownership, partial-success recovery, retries, and idempotency identity
where applicable. Do not reproduce unchanged schemas.

## Implementation decisions

Record settled decisions compactly with stable IDs and their specific reasons:

```text
D1. <decision>
    Reason: <why this choice follows>.
```

Name a rejected alternative only when an implementer might reasonably reintroduce it. This is a
decision ledger, not an interview transcript.

## Tests

Test domain decisions through the functional core’s public seam. Test an infrastructure boundary only for behavior that the pure tests cannot establish: mapping fidelity, real provider binding, persistence semantics, or adverse ordering. Do not repeat domain cases through infrastructure.

Name particular tests only when their seam or boundary claim is material to implementing the design.

## Execution slices

Use one or two coherent vertical slices, not a kanban board or microtask list. For each slice name:

- behaviors it completes;
- domain and boundary output it produces;
- dependencies on the other slice;
- the observable condition that makes it complete.

## Out of scope

Name adjacent behavior and cleanup deliberately excluded. Be concrete enough to prevent an
implementer from helpfully expanding the change.

## Production verification

Name the signal proving the new behavior works, the signal protecting the existing happy path, and
any instrumentation that must be added. Specify evidence, not transient query text or thresholds.

## Context

Provide a retrieval index of required external artifacts: stable links or exact identifiers plus one
clause saying what each contributes. Fold every fact needed for implementation into the body; context
links are supporting evidence, not missing chapters. Omit this section when there is nothing external.
