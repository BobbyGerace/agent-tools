# The Test Layers

Six layers in four groups. The organizing question is **what each layer can fail for** — a
layer whose failures don't correspond to something a user would notice is not a layer, it's
overhead.

```
╭─ Pure ─────────────────────────────────────────────────────────────╮
│ 1. Transition tests      one per row of the table, not per cell    │
│ 2. Property/invariant    statements that hold across all inputs    │
├─ Boundary fidelity ────────────────────────────────────────────────┤
│ 3. Persistence mapping   real ORM, real rows, including legacy     │
│ 4. Provider contract     real payloads, real binding, real headers │
├─ Adversarial ordering ─────────────────────────────────────────────┤
│ 5. Replay and interleaving   duplicates, races, failure mid-flow   │
├─ Whole-system smoke ───────────────────────────────────────────────┤
│ 6. End-to-end            deliberately few; outcomes, not calls     │
╰────────────────────────────────────────────────────────────────────╯
```

The middle group exists because your code's idea of a shape and the outside world's idea of it
drift independently, and neither a pure test nor an end-to-end test notices.

**This is not a stack.** Layer 2 is as pure as layer 1; layer 4 is orthogonal to integration
depth entirely. Read it as a checklist of kinds, not a pyramid to fill from the bottom.

## Group 1 — Pure

No database, HTTP server, provider SDK, message bus, UI framework, or logger mocks. Records in,
records out.

### Layer 1 — transition tests

**Write the truth table first, then one test per row.** For a state machine the table is the
deliverable, not a nice-to-have — and it is also the *budget*. One test per row; the table has
a row where the outcome is interesting and no row where it isn't.

```
╭──────────────────────────────┬──────────────────────────┬──────────────────╮
│ Starting condition           │ Event / fact             │ Expected decision│
├──────────────────────────────┼──────────────────────────┼──────────────────┤
│ already warned               │ duplicate warning        │ NoOp             │
│ open + ineligible            │ warning due              │ Dismiss          │
│ open + call found            │ warning due              │ Resolve          │
│ open + before blocking       │ warning due              │ Dispatch warning │
│ open + after blocking        │ warning due              │ Mark evaluated   │
│ open + cure expired + no call│ cure wakeup              │ Dispatch breach  │
│ accepted downstream, bus fail│ dispatch result          │ Commit + retry   │
│ permanent initial failure    │ dispatch result          │ Dismiss + ack    │
╰──────────────────────────────┴──────────────────────────┴──────────────────╯
```

**Do not enumerate the state × event cross product.** A nine-state, eight-event machine has 72
cells and roughly a dozen rows worth testing. Enumerating the grid is wrong in both directions
at once: it generates cells nobody cares about, *and* it misses whole categories that are not
cells in the grid at all. Three of the eight kinds below have no coordinates on those axes.

The kinds of row that earn a test:

- a legal transition
- a **duplicate** event — same event applied twice
- a **stale** event — an event that was superseded before it arrived
- an event arriving **after a terminal state**
- a command issued **before the resource it acts on exists**
- an **unknown value** from outside — a status string, enum, or code you don't recognize
- **cancellation or supersession** mid-flow
- a **time boundary** — the instant a window opens or closes, and either side of it

The last three are the ones a cross product structurally cannot produce, and they are
disproportionately where the bugs are.

```csharp
[Fact]
public void WarningDue_WithQualifyingCall_ResolvesObligation()
{
    var callAttempt = new CallAttempt(
        "conversation-123",
        new DateTimeOffset(2026, 6, 10, 15, 0, 0, TimeSpan.Zero)
    );
    var state = BreachWarningStateMother.Open(warningMessageId: "1712345678.123456");
    var facts = new BreachWarningWakeupFacts(
        WakeupKind.WarningDue,
        WarningTiming.BusinessDays,
        new DateTimeOffset(2026, 6, 11, 15, 0, 0, TimeSpan.Zero),
        IsEligible: true,
        QualifyingCallAttempt: callAttempt
    );

    var result = BreachWarningMachine.Decide(state, facts);

    var commit = Assert.IsType<BreachWarningDecision.Commit>(result.Value);
    Assert.Equal(ObligationStatus.Resolved, commit.NewState.Status);
    Assert.Equal(callAttempt.StartedAt, commit.NewState.Evidence.RectifiedAt);
    var rectified = Assert.IsType<AfterCommitEffect.SendRectified>(Assert.Single(commit.Effects));
    Assert.Equal(callAttempt, rectified.CallAttempt);
}
```

**Retry and partial-failure edges belong here** — they are effectively unreachable through
integration tests, which is exactly why they ship broken:

```csharp
[Fact]
public void WarningDispatch_WhenAcceptedDownstreamButPublishFailed_CommitsAuditAndRetries()
{
    var outcome = new DispatchOutcome.RetryableFailure(
        Error.Failure("Notification.PublishFailed", "Bus unavailable."),
        new DispatchReceipt(MessageId: "1712345678.123456",
                            NotificationSentAt: null, WarningCopyNumber: null)
    );

    var completion = BreachWarningMachine.CompleteWarning(state, command, outcome);

    var retry = Assert.IsType<DispatchCompletion.CommitAndRetry>(completion);
    Assert.Equal("1712345678.123456", retry.NewState.Evidence.WarningMessageId);
}
```

### Layer 2 — property and invariant tests

A statement that must hold across **all** inputs, rather than one example of it. This is the
layer that reduces test count rather than raising it: one property subsumes every example you'd
otherwise write for it, and covers the cases you didn't think of.

Cheap to write, since these are as pure as layer 1. Few in number by construction.

The shapes that make good invariants:

- **Terminal states are terminal** — a completed state never returns to active, and a stale
  provider update never regresses a delivered status.
- **Intent survives until applied** — a recorded user decision isn't lost by an intervening
  transition that didn't act on it.
- **Bounds hold** — attempts never exceed the policy maximum, however you got there.
- **An exemption is never blocked by the thing it exempts.** The acknowledgement of an opt-out
  is not itself suppressed by that opt-out. This recurs wherever a rule has a carve-out, and the
  carve-out is typically implemented in one path and forgotten in the other.
- **Illegal values cannot be constructed or serialized**, and **a guarded value never reaches
  the far side of its guard** — the point of the guard is to hold at call sites nobody has
  written yet.
- **Reapplication is identity** — the same event applied twice produces the same state *and the
  same effect identities*, not merely a state that compares equal.

Property-based tooling is welcome but not required. What makes it a property test is that the
assertion is universally quantified.

## Group 2 — Boundary fidelity

Both layers here exist for the same reason: a shape you control and a shape you don't have
drifted, and no amount of pure testing can see it.

### Layer 3 — persistence mapping

Real ORM against a real database. Mapping, JSON/document column replacement semantics,
constraints, and whether the queries actually translate. This is where a predicate that can't
be turned into SQL gets caught.

- **Every domain variant round-trips.** With a union persisted over existing columns, this is
  the test that makes the whole compatibility-projection approach safe.
- **Legacy field combinations map deterministically.** Every combination of the old nullable
  flags produces exactly one variant, including the combinations that shouldn't exist. If one
  of them has no sensible mapping, assert that it is *detected*, not that it silently picks a
  default.
- **A discriminator/payload mismatch is detected** rather than passed through.
- **The concurrency token or claim permits exactly one winner** under a contended write.
- **Tenant predicates and unique keys match the production schema shape**, including partial
  and composite indexes. An index that exists in a test database and not in production is
  worse than no test.

**Generate seed IDs per test; never hard-code them.** Transaction rollback between tests does
not stop two test classes running in parallel from contending on the same fixed IDs, and that
failure presents as an intermittent lock timeout rather than as a conflict — so it gets
retried, ignored, and eventually muted.

### Layer 4 — provider and binding contract

Captured or sanitized real payloads, or a test account where practical.

**A hand-constructed DTO test does not prove model binding, and it does not prove the payload
shape the provider actually sends.** Newing up a request object in a test and asserting its
fields is a test of your own constructor. This is the single most common shape of test that
generates confidence and catches nothing.

What belongs here:

- **Actual field names and optionality** from a captured payload, bound through the real
  framework pipeline rather than assembled by hand.
- **Signature or token validation against the externally visible request representation** —
  the URL and body as the sender saw them, not as your framework reconstructed them.
- **Identifier semantics** where a provider has more than one kind and they relate: parent and
  child, root and leg, resource and sub-resource.
- **Status and enum parsing**, including a value you don't recognize.
- **Error code mapping**, especially the codes that mean "not yet" rather than "no".
- **Content type, size, and header handling** for anything uploaded or downloaded.

The capability half matters as much as the shape half: a provider adapter should make required
capabilities explicit and test the **deployed configuration**, not only response shapes. A
fallback path mocked as success passes forever while the real credential lacks permission for
that API.

## Group 3 — Adversarial ordering

### Layer 5 — replay and interleaving

Durable state under duplicates, races, and failure part-way through. The concerns usually
chased with mock call sequences belong here instead, asked as behavior.

The minimum set:

- the same callback or message **delivered twice concurrently**
- processing **cancelled after each durable step** — one test per step, walking the cut point
  forward
- a **later status arriving before an earlier one**
- a user action **racing with in-progress work** it would cancel
- **completion racing with upload**, or any pair where one lifecycle's end is mistaken for
  another's
- the record **persisted but the downstream publish failing**
- the **remote resource created but the local write failing** — the inverse, and the one
  usually forgotten
- the **request acknowledged while the worker restarts**

Assert on durable state and on effect identity, never on which collaborator was called.

**Why there is no mock-wiring layer.** "Does it execute effects after persistence?" asserted
against a mock's call order breaks when you rename a collaborator and stays green when the
effect genuinely fires before the commit. The same question asked here — "cancel between commit
and dispatch: is the effect suppressed, and is it recoverable?" — fails only when something is
actually wrong.

A small number of wiring tests is still fine where the sequencing is genuinely load-bearing and
has no observable proxy. That is a judgment per case, not a layer to populate by default, and
it is the *only* place where asserting on an interaction is the right call.

## Group 4 — Whole-system smoke

### Layer 6 — end-to-end

Real route registration, DI, database, and provider adapter substitutes. Deliberately few.

**Assert customer-visible outcomes and durable state — not only method calls.** An end-to-end
test that verifies a service was invoked is a shell-wiring test wearing an expensive costume.

Prove that DI resolves, messaging round-trips, retries behave, and persistence happens. Not a
place to test rules. For a flow that spans repositories, rerun on current main and verify the
final composition, since each half can be green against a stale counterpart.

## Naming

**Name the invariant and the timing.** The timing clause is what distinguishes an interleaving
test from the transition test it superficially resembles, and it is the part most often
dropped:

```
StopRequested_WhileAwaitingResourceStart_PersistsIntentAndAppliesItOnStart
CompletedCallback_WhenAlreadyFinalized_IsIdempotentAndDoesNotRepublish
UndeliveredStatus_AfterDelivered_IsRecordedAsStaleAndDoesNotRegress
CampaignUrl_FromGeneratedSite_AlwaysUsesTheApprovedHost
```

A name ending in the assertion tells a reader what broke without opening the file.

## Targeting: branch coverage, not line coverage

High line coverage next to low branch coverage has a specific gap, and it is always the same
one: the retryable-partial-success paths, the permanent-failure paths, the
already-handled-idempotent paths. They're untested because reaching them through the
infrastructure stack is genuinely hard — which is an argument for layers 1 and 5, not an
argument for more integration tests.

Measure both on the code you touched. **Use the gap to aim, not to fill.** A wide gap says
"your untested branches are failure edges"; it does not say "write a test for every branch."
The table in layer 1 is still the budget.

## What not to write, and what to delete

Each test gets a one-line reason it exists. If the reason is hard to write, that is the finding.

The low-value catalog lives in `implement` — `constructor sets properties`, `calls
repository.save once`, a hand-built DTO asserted field by field, mechanical mapping assertions,
`returns correct type`, and a test per function rather than per behavior.

**Delete the ones you touch.** When a diff brings you into a test file, a test you cannot
attach a user-visible failure to should leave with your change rather than be preserved out of
politeness. This is not licence to sweep an existing suite — the standing shell-test layer that
older code accumulated stays where it is. It means stop adding to it, and take the ones in
reach.

Prefer 1–3 high-value tests over a test per function. The aim is the behaviors that would
otherwise reach production.
