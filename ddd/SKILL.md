---
name: ddd
description: A domain-modeling standard — make impossible states impossible, functional core with I/O at the edges, and the four test layers. Loaded by design, implement, and ship rather than invoked directly; use it when writing or reviewing C# domain logic, state machines, result types, or anything with money, time, or a multi-field status.
---

# Domain Modeling Standard

Ten rules. Each is phrased so it can be answered yes or no against a diff.

The examples are C#, and the rules are sharpest on a typed OO language with records and
pattern matching. The reasoning carries to anything with a type system.

## Scope: code you write, not code you touch

- **Greenfield** — all ten apply.
- **Adding to or modifying existing code** — follow them where they fit. Don't rewrite the
  surroundings. Sometimes matching the local convention beats being locally correct and
  globally surprising.
- Say which it is out loud rather than pretending there's a mechanical rule. It's a
  judgment call and it should read like one.

A gRPC mapper, a dashboard script, or a one-line config change does not grow a functional
core. State machines, result types, money, time, and eligibility rules do.

**Check the local convention before citing any of this as "how we do it here."** If a
codebase already has a name for the functional-core pattern, use its name and its
precedents; asserting an idiom from somewhere else is exactly the
locally-correct-globally-surprising failure the scope rule warns about.

## Make impossible states impossible

**1. No multi-field encodings of a state space.** If N fields jointly encode M states and M
is smaller than the field cross-product, it's a closed union — an `abstract record` with
`sealed record` cases, or `OneOf`. The canonical violation:

```csharp
public bool IsOptional { get; set; }
public bool? SelectedByRecipient { get; set; }
```

Two fields, four real states (`Required / OptionalUndecided / OptionalSelected /
OptionalDeclined`), and a fifth combination the compiler still permits. Every consumer
reconstructs the semantics, and they drift.

**2. No result type that can express its own contradiction.**
`WarningDispatchResult(Succeeded: true, ShouldRequeue: true, FailureReason: "...")` compiles
today. Replace with `Delivered / RetryableFailure / PermanentFailure`.

**3. One representation per concept.** `null` and `""` must not both mean "no relation".
Normalize at the mapper boundary or wrap it. *Automated reviewers often catch this one — so
don't spend design effort here, but don't rely on it either (see `ship`).*

**4. Units live in the type or the name.** Money is `MoneyCents` or at minimum
`*AmountCents` — never a bare `int` called `Quantity`. The failure shape is a whole-dollar
cast that silently discards the remainder on every record it touches. An instant that gets
rendered to a human carries its zone: store UTC and return only UTC, and a 10am appointment
in one timezone displays as 1pm to a viewer in another. The fix is a companion
`*TimeZoneId`, not a comment.

## Functional core, I/O at the edges

**5. Decision functions take data and return data.** `Decide(state, facts, now) -> Decision`,
with everything the decision needs present in the parameters. The test is not *where the
function lives* — a `private static` helper in the same class is fine, and often better. The
test is whether the function can **reach** I/O: it must not take a `DbContext`, a message
bus, or a `CancellationToken` and go looking for facts mid-decision. If it needs a fact, the
caller loads it first.

**6. Effects are data.** The core returns command records; the shell executes them.
Disabling one effect must not remove another — two independent decisions hung off one
boolean means turning off the first silently disables the second.

Name the pieces so a reader recognizes the pattern on sight, and follow whatever the codebase
already uses. A convention that works:

| Piece | Name |
| --- | --- |
| the pure core | `<Thing>Planner` or `<Thing>Policy` |
| its decision output | `<Thing>Plan` |
| the facts it takes | `<Thing>Input` or `<Thing>Facts` |
| the effect records | `<Thing>Effects` or `<Thing>Command` |

**7. One rule, one place.** No reimplementing a policy in a second endpoint or an aggregate
projection. The shape to look for: the same adjective — "actionable", "eligible", "billable",
"standing" — computed in more than one file. Once two definitions exist they diverge, and the
second one is usually the wrong one. *Automated review partially covers this too.*

**8. Load facts → decide → one commit → effects after commit.** No read-modify-save
interleaved with dispatch. The failure is a handler that reads a row moments before its
marker is committed, concludes the marker is absent, and silently never fires the downstream
event.

## Testing

**9. Four layers, and the truth table lives in layer 1.** Pure decision tests with no mocks,
exhaustive over state × event; then shell wiring tests with mocked ports asserting sequencing
only and *zero* business rules; then adapter integration with a real ORM; then a thin
end-to-end set. Details and worked examples in `references/test-layers.md`.

**10. Branch coverage, not line coverage.** High line coverage next to low branch coverage is
the tell that failure modes are untested — the retryable-partial-success paths, the
permanent-failure paths, the already-handled-idempotent paths. Measure both on the code you
touched; if the gap is wide, the missing tests are failure edges, not more happy paths. Every
failure and retry edge in a union gets a layer-1 test.

## Code shape

Not domain modeling, but it's applied at the same moments and belongs in one place rather than
copied into every skill.

- **Single responsibility.** A method does one thing at one level of abstraction. When one
  mixes orchestration with fiddly details — header construction, parsing, object building,
  telemetry bookkeeping — pull the details into named private helpers so the top-level method
  reads like a summary of the steps.
- **Method length is a smell, not a rule.** Around 100 lines, get suspicious and look for the
  seams. Long before that: if a block has its own comment header, or could be named, it
  probably wants to be a helper.
- **Prefer small well-named helpers over inline blocks**, even at one call site — a good name
  is documentation. Collapse duplicated "do X then record Y" pairs into one helper so the
  halves can't drift.
- **Don't go full Uncle Bob.** No one-line methods for their own sake, no speculative
  abstraction, no indirection that makes the reader chase definitions. The goal is a method
  readable top to bottom without scrolling. Cohesion beats hitting a number.

## On cyclomatic complexity

Treat it as **a smell detector, never a target.** Splitting a complexity-30 method into three
10s lowers the measured number without removing any complexity from the system, and done
blindly it produces the worse problem where one rule now lives in five places.

A high number is a prompt to go looking for a state-space problem. What actually shrinks
total complexity is rule 1 — replacing a two-boolean-plus-nullable cross product with a
four-case union genuinely reduces the possibility space rather than relocating it. There is
no threshold and no gate. "No long methods" is a fine cheap proxy.

## References

- `references/detectors.md` — the anti-shape catalog: what it looks like in code, how it
  fails, what to write instead. Read it when reviewing a design or a diff; if none of those
  shapes are present, the design probably satisfies rules 1–8.
- `references/test-layers.md` — the four layers, what belongs in each, and where mocks help.
