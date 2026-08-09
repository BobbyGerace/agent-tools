# The Four Test Layers

The point of the layering is that **the domain truth table belongs in layer 1**, where it
costs nothing to be exhaustive.

```
╭────────────────────────────────────────────────────────────────────╮
│ 1. Pure decision tests                                             │
│    No mocks. Every state × event × outcome combination.             │
├────────────────────────────────────────────────────────────────────┤
│ 2. Shell tests                                                     │
│    Mock reader/store/effect ports. Sequencing and wiring only.      │
├────────────────────────────────────────────────────────────────────┤
│ 3. Adapter integration tests                                       │
│    Real ORM. Mapping, JSON replacement, constraints, queries.       │
├────────────────────────────────────────────────────────────────────┤
│ 4. End-to-end consumer tests                                       │
│    A small number proving DI, messaging, retry, persistence.        │
╰────────────────────────────────────────────────────────────────────╯
```

## Layer 1 — pure decision tests

Records in, records out. No database, no mocks, no bus, no DI, no async.

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

**Retry and partial-failure edges are testable here too** — the cases that are effectively
impossible to reach through integration tests, and therefore the ones that ship broken:

```csharp
[Fact]
public void WarningDispatch_WhenChatSucceededButCustomerPublishFailed_CommitsAuditAndRetries()
{
    var outcome = new DispatchOutcome.RetryableFailure(
        Error.Failure("CustomerNotification.PublishFailed", "Pub/Sub unavailable."),
        new DispatchReceipt(MessageId: "1712345678.123456",
                            CustomerNotificationSentAt: null, WarningCopyNumber: null)
    );

    var completion = BreachWarningMachine.CompleteWarning(state, command, outcome);

    var retry = Assert.IsType<DispatchCompletion.CommitAndRetry>(completion);
    Assert.Equal("1712345678.123456", retry.NewState.Evidence.WarningMessageId);
}
```

**Write the truth table first, then one test per row.** For a state machine that's the
deliverable, not a nice-to-have:

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
│ chat accepted, bus failed    │ dispatch result          │ Commit + retry   │
│ permanent initial failure    │ dispatch result          │ Dismiss + ack    │
╰──────────────────────────────┴──────────────────────────┴──────────────────╯
```

## Layer 2 — shell tests

Mock the ports. Assert **sequencing and wiring, never business rules.** The shell's whole job
is small, so its test list is short and closed:

- Does it call the reader?
- Does it pass the correct records to the decision function?
- Does it persist the returned state?
- Does it execute returned effects *after* persistence?
- Does it return retry errors to the consumer correctly?
- Is an after-commit effect suppressed when persistence fails?

If a shell test asserts something about eligibility, cure windows, or amounts, that assertion
belongs in layer 1 and its presence here means the rule leaked back into the shell.

This is the same conclusion the validation guidance in `implement` reaches independently:
`test("calls repository.save once")` is low-value because it asserts on mock interactions
rather than behavior. The exception is exactly this layer, where the interaction *is* the
behavior under test.

## Layer 3 — adapter integration tests

Real ORM against a real database. Mapping, JSON column replacement semantics, constraints, and
whether the queries actually translate. This is where a predicate that can't be translated to
SQL gets caught.

**Generate seed IDs per test; never hard-code them.** Transaction rollback between tests does
not prevent two test classes running in parallel from contending on the same fixed IDs, and
that failure presents as an intermittent lock timeout rather than as a conflict.

## Layer 4 — end-to-end consumer tests

Deliberately few. Prove DI resolves, messaging round-trips, retry behaves, persistence
happens. Not a place to test rules.

## Why the split matters

A codebase with high line coverage and low branch coverage has a specific gap, and it is always
the same one: the retryable-partial-success paths, the permanent-failure paths, the
already-handled-idempotent paths. They're untested because reaching them through the
infrastructure stack is genuinely hard — which is an argument for layer 1, not an argument for
more integration tests. Measure both numbers on the code you touched; if they diverge, the
tests you're missing are failure edges.

When proposing tests, each one gets a one-line reason it's worth writing. Aim for the
behaviors that would otherwise reach production, not a test per function.
