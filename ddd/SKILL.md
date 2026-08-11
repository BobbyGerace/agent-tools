---
name: ddd
description: A domain-modeling standard — make impossible states impossible, functional core with I/O at the edges, opaque values at the boundaries, and the six test layers. Loaded by design, implement, and ship rather than invoked directly; use it when writing or reviewing domain logic, state machines, result types, identifiers, provider adapters, or anything with money, time, or a multi-field status.
---

# Domain Modeling Standard

Twelve rules: ten about the shape of the domain, two about what crosses into it.
Each is phrased so it can be answered yes or no against a diff.

Most examples are C#, and the rules are sharpest on a typed OO language with records and
pattern matching. The reasoning carries to anything with a type system — rules 1 and 9 in particular
apply unchanged to a TypeScript frontend, where a discriminated union is a tagged union and an
opaque type is a branded one.

## Scope: code you write, not code you touch

- **Greenfield** — all twelve apply.
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

A state space also hides in a **single nullable field**, and the fix is the same union. When
one `null` stands for "not started", "failed", "not loaded", and "no choice made", the legal
next action differs in each case and the code has to guess. The worst variant is a default that
looks chosen — a form initialized to a plausible value, so what the user never picked is
indistinguishable from what they did. Model it `Unselected | Selected(value)`.

The tell that a boolean is hiding variants: its documentation contains **"means", "except",
"only while", or "treated as."**

**2. No result type that can express its own contradiction.**
`WarningDispatchResult(Succeeded: true, ShouldRequeue: true, FailureReason: "...")` compiles
today. Replace with `Delivered / RetryableFailure / PermanentFailure`.

The same discipline applies _between_ outcomes, not only inside one. "The customer opted out",
"the database timed out", and "the notification didn't send after the order saved" are three
different kinds of answer — a decision the caller must handle, a transient failure worth
retrying, and a partial success whose failed half still needs reconciling. Collapse them into
one generic failure branch and every caller re-derives which is which, differently.
`detectors.md` #1 lists the eight categories worth keeping apart.

**3. One representation per concept.** `null` and `""` must not both mean "no relation".
Normalize at the mapper boundary or wrap it. _Automated reviewers often catch this one — so
don't spend design effort here, but don't rely on it either (see `ship`)._

**4. Units live in the type or the name.** Money is `MoneyCents` or at minimum
`*AmountCents` — never a bare `int` called `Quantity`. The failure shape is a whole-dollar
cast that silently discards the remainder on every record it touches. An instant that gets
rendered to a human carries its zone: store UTC and return only UTC, and a 10am appointment
in one timezone displays as 1pm to a viewer in another. The fix is a companion
`*TimeZoneId`, not a comment.

## Functional core, I/O at the edges

**5. Decision functions take data and return data.** `Decide(state, facts, now) -> Decision`,
with everything the decision needs present in the parameters. The test is not _where the
function lives_ — a `private static` helper in the same class is fine, and often better. The
test is whether the function can **reach** I/O: it must not take a `DbContext`, a message
bus, or a `CancellationToken` and go looking for facts mid-decision. If it needs a fact, the
caller loads it first.

**6. Effects are data.** The core returns command records; the shell executes them. Disabling
one effect must not remove another — two independent decisions hung off one boolean means
turning off the first silently disables the second.

Name the pieces so a reader recognizes the pattern on sight, and follow whatever the codebase
already uses. A convention that works:

| Piece               | Name                                 |
| ------------------- | ------------------------------------ |
| the pure core       | `<Thing>Planner` or `<Thing>Policy`  |
| its decision output | `<Thing>Plan`                        |
| the facts it takes  | `<Thing>Input` or `<Thing>Facts`     |
| the effect records  | `<Thing>Effects` or `<Thing>Command` |

**7. One rule, one place.** No reimplementing a policy in a second endpoint or an aggregate
projection. The shape to look for: the same adjective — "actionable", "eligible", "billable",
"standing" — computed in more than one file. Once two definitions exist they diverge, and the
second one is usually the wrong one. _Automated review partially covers this too._

**8. Load facts → decide → one commit → effects after commit.** No read-modify-save
interleaved with dispatch. The failure is a handler that reads a row moments before its
marker is committed, concludes the marker is absent, and silently never fires the downstream
event.

## Boundaries

Rules 1–8 are about the shape of the domain. These two are about what is allowed to cross
into it, and they fail the same way: something from outside — a wire string, a table row, a
provider status, a projection built for a screen — gets used as though it were a domain value,
so the code reasons over whatever shape was easiest to store or receive.

**9. Identifiers and domain values are opaque types, parsed once at the edge.** Not
`string tenantId, string orderId, string customerId, string userId` in one signature, where
every argument is assignable to every parameter and a transposition compiles. Private
constructor, static `Parse` returning a result — and **a function promising a validated type
never returns null or defers the check to `ToString()`**, because a wrapper that always
constructs has moved the check without making it. In TypeScript this is a branded type; the
rule is identical. `detectors.md` #13 has both forms.

**Strings at the edge, types in the application and domain layers.** Wire models and ORM,
JSON, and protobuf converters still serialize strings — that is what an edge is for. Don't add
a public constructor taking unchecked values to save mapping code. And don't call one
identifier by another's name for convenience; two concepts get two types and two names.

Identity is also **fixed at a moment**, not just typed: an irreversible command carries its
target and its idempotency key from when the decision was made, rather than reading them from
ambient state at send or retry time. (`detectors.md` #20)

**10. Shapes from outside are mapped, not adopted.** A row, a DTO, or a provider payload may
need mutable setters and serialization-friendly fields. None of that makes it the aggregate.
Map to an immutable domain value, decide over that, and apply an explicit plan through a
repository that owns concurrency and persistence mapping. Mapping needs an escape hatch:
**preserve a provider value you don't recognize** as its own case rather than letting it fall
through to a business failure nobody decided on.

## Testing

**11. Six layers in four groups, and the truth table lives in layer 1.** Pure transition and
property tests; then boundary fidelity — persistence mapping and provider contract; then replay
and interleaving; then a thin end-to-end set. **The transition table is the budget, not the
state × event cross product**, and there is no standing layer of mock-sequencing tests:
"does it call the reader?" cannot fail for a reason a user would notice, and "does it dispatch
after the commit?" is better asked as behavior under an adverse ordering. Full contents, and
what to delete, in `references/test-layers.md`.

**12. Branch coverage, not line coverage — to aim, not to fill.** High line coverage beside low
branch coverage means the failure modes are untested: the retryable-partial-success paths, the
permanent-failure paths, the already-handled-idempotent paths. Measure both on the code you
touched. A wide gap says the missing tests are failure edges; it does not say write one per
branch.

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

## Reviewing without reading every line

Nearly every shape in this document is visible in a **type declaration** — a record, a
constructor, a method signature — without opening a single method body. Nullable field soup,
a discriminator beside a polymorphic payload, a parameter list of bare strings, an enum result
mixing denial with infrastructure failure, a `bool` returned from a classifier: all of them are
legible from the declaration alone.

So the first pass over an unfamiliar diff is the set of types it adds or changes, and the
question at each one is **what illegal combination does this still permit?** That is a
tractable review even on a large change, and it finds a different class of defect than reading
the logic does.

## References

- `references/detectors.md` — the anti-shape catalog: what it looks like in code, how it
  fails, what to write instead. Read it when reviewing a design or a diff; if none of those
  shapes are present, the design probably satisfies rules 1–10.
- `references/test-layers.md` — the six layers, what belongs in each, what not to write, and
  what to delete.
