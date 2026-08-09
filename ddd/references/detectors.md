# Anti-Shape Catalog

Each entry: what it looks like in code, how it fails, what to write instead, and — where the
shape is easy to miss — how to spot it.

Use this when reviewing a design or a diff. If none of these shapes are present, the design
probably satisfies rules 1–8; that's the fastest way to check.

---

## 1. Success and failure in the same record

```csharp
WarningDispatchResult(
    bool Succeeded,
    bool ShouldRequeue,
    string? MessageId,
    string? FailureReason
)
```

Permits `Succeeded && ShouldRequeue`, failure with no reason, and success *with* a failure
reason. Every caller has to know which combinations are real, and no two callers agree.

**Instead** — name the outcomes, and let the payload differ per outcome:

```csharp
public abstract record DispatchOutcome
{
    public sealed record Delivered(DispatchReceipt Receipt) : DispatchOutcome;
    public sealed record RetryableFailure(Error Error, DispatchReceipt? Partial) : DispatchOutcome;
    public sealed record PermanentFailure(string Reason, DispatchReceipt? Partial) : DispatchOutcome;
}
```

**How to spot it:** a record with a `bool Succeeded` (or `IsError`, `Ok`) *next to* nullable
payload fields. Also `(Value, Errors)` and `(Value?, Commands, Errors)` pairs — those are
`Found / NotFound / Failure` wearing a trench coat.

---

## 2. Two booleans encoding four states

```csharp
public bool IsOptional { get; set; }
public bool? SelectedByRecipient { get; set; }
```

Encodes `Required / OptionalUndecided / OptionalSelected / OptionalDeclined`, so every
consumer reconstructs the semantics from two fields. They drift one at a time: a schedule
that ignores declined items, an update path that silently drops `IsOptional`, a PDF and an
email that disagree about what's included, a total that taxes the wrong subset. Each is a
separate fix to the same missing type.

**Instead** — four cases, and the compiler stops the fifth from existing.

**How to spot it:** a `bool` and a `bool?` on the same type whose names are about the same
subject, or any comment of the form "if X is true and Y is null, that means…".

---

## 3. Two fields for one quantity

```csharp
public int Quantity { get; set; }
public decimal? DecimalQuantity { get; set; }

[NotMapped]
public decimal EffectiveQuantity => DecimalQuantity ?? Quantity;
```

Now every consumer must know that decimal wins when present, that the int is a rounded
compatibility value, what the precision limits are, and what to do with contradictory pairs.
The abstraction solves none of it and hands the whole problem to the caller.

**Instead** — one field, one type, the precision you actually need. If a migration forces a
transition period, make the old field private and expose only the resolved value.

---

## 4. Money without units

```csharp
var dollars = (long)Math.Floor(source.TotalCents * percent / 10000m);
```

A whole-dollar quantity computed from cents, discarding up to $0.99 on every record it
touches. It reconciles to the penny in testing with round numbers and drifts in production.

**Instead** — `MoneyCents` as a value object, or at minimum `*AmountCents` in every name so
the unit is visible at each call site: `OverageAmountCents`, `TargetCents`, `BilledCents`.
Consistent naming is enough; the value object is better.

**How to spot it:** a bare `int`/`long`/`decimal` named `Quantity`, `Amount`, `Total`, or
`Price`, and any `/ 100`, `/ 10000`, `Math.Floor`, or cast in an arithmetic chain.

---

## 5. An instant with no zone

```csharp
public sealed record AppointmentDto(string Id, DateTimeOffset StartsAt);   // UTC only
```

The stored instant is correct and the API is correct, and the feature is still wrong: the
client has nothing to localize *to*, so it uses the viewer's zone. A 10am appointment in one
timezone renders as 1pm to a coordinator in another, and both of them think the other is
confused.

**Instead** — if a timestamp will be shown to a human, it travels with the zone it means
something in:

```csharp
public sealed record AppointmentDto(string Id, DateTimeOffset StartsAt, string TimeZoneId);
```

**How to spot it:** a `DateTimeOffset` crossing an API boundary toward a UI, with no
neighbouring zone field. Related shapes worth the same look: local times persisted without
conversion, and timezone resolution reimplemented per call site instead of once.

---

## 6. A state machine made of nullable evidence fields

An entity carrying `Status`, `LastEvaluatedAt`, `LastNotifiedAt`, `WarningSentAt`,
`CustomerNotifiedAt`, `FollowUpNotifiedAt`, `InterventionNeededAt`, `BreachNotifiedAt`, plus
dispatcher booleans. The states `warningDue / warningSent / customerWarned / followUpSent /
cureExpired / resolvedByCall / dismissed` are real but never named — each one is inferred,
everywhere, slightly differently.

The cost isn't elegance, it's that business-rule testing has to travel through the entire
infrastructure stack. To test "a qualifying call resolves the obligation" you need a
DbContext, a seeded tenant/record/owner graph, a persisted row, a fake bus, a mocked alerter,
a feature-flag implementation, a fake clock, consumer construction, a reload, and assertions
against persisted JSON.

**Instead** — an explicit state record with named transition methods, projected over the
existing table. No migration required to start:

```csharp
public sealed record BreachWarningState(
    string ObligationId,
    ObligationStatus Status,
    DateTimeOffset BlockingAt,
    DateTimeOffset? LastEvaluatedAt,
    DateTimeOffset? LastNotifiedAt,
    BreachWarningEvidence Evidence
)
{
    public BreachWarningState Dismiss(DateTimeOffset now) => this with { ... };
    public BreachWarningState Resolve(CallAttempt call) => this with { ... };
}
```

**How to spot it:** three or more nullable `DateTimeOffset?` fields on one entity whose names
describe things that happened. That's a state machine.

---

## 7. The same rule decided twice

Two surfaces that must agree, each computing the answer its own way: a per-item path that
correctly understands completed payments, and an aggregate projection that reimplements the
rule and counts unsent drafts in the total. Or three definitions of whether a record is
"actionable" — one trusting a persisted snapshot, one evaluating live signals and 404ing, one
in a queue nobody checked.

The tell that this is systemic rather than a one-off: a previous fix already tried to
consolidate it and missed cases.

**Instead** — one pure function every surface calls:

```csharp
StaleRecordAvailability EvaluateAvailability(
    PersistedObligation obligation,
    LiveEvaluation live,
    DateTimeOffset now
);
```

returning `Actionable / Snoozed / WaitingForEvidence / Drifted / Terminal`.

**How to spot it:** the same adjective ("actionable", "eligible", "billable", "standing")
computed in more than one file. Grep the adjective, not the type.

---

## 8. Effects coupled to each other

Two independent decisions — should the record move to the next stage, and should the system
start automated outreach — tied to one flag. Disable outreach automation and a legitimate
booking silently stops advancing the stage, because both hung off the same boolean.

**Instead** — separate effect records, so removing one leaves the other:

```csharp
public abstract record CalendarTriggerEffect
{
    public sealed record MoveStage(string TargetStageId) : CalendarTriggerEffect;
    public sealed record StartOutreach(string AutomationId) : CalendarTriggerEffect;
}
```

**How to spot it:** one feature flag or one `if` guarding two effects that a reader would
describe with the word "and".

---

## 9. Persisting despite a failed result

```csharp
.ThenAsync(async updatedContact =>
{
    await database.SaveChangesAsync(cancellationToken);
    await transaction.CommitAsync(cancellationToken);
    return updatedContact;
})
```

A nested fallible result is ignored and the save runs anyway — the textbook
Railway-Oriented-Programming failure, the exact thing ROP exists to prevent. An invalid phone
number, or removing the only contact method, persists the preceding mutations.

**Instead** — a core that returns a validated plan, and a shell that saves only successful
plans. If you're writing the ladder by hand, check the error state *before* the commit, not
after.

**How to spot it:** a `SaveChanges`/`Commit` inside a `Then`/`Map`/`Select` continuation, or a
result-typed value assigned and never inspected.

---

## 10. Decision and persistence in one flow

Recording an outcome and moving the record's stage happen in the same method, so selecting
"quote sent" or "quote signed" can move the stage before the required quote operation has
run. Each new case adds another guard condition to the same flow, and the guards are what
regress.

**Instead** — decide, then execute:

```csharp
public sealed record OutcomePlan(
    Outcome OutcomeToRecord,
    IReadOnlyList<OutcomeEffect> Effects
);
```

and the test becomes an assertion about the plan, with no database:

```csharp
var plan = DecideOutcome(currentRecord, selectedOption, submittedValues);
Assert.Empty(plan.Effects.OfType<OutcomeEffect.MoveStage>());
Assert.Contains(plan.Effects, e => e is OutcomeEffect.RequireQuoteSend);
```

**How to spot it:** a method whose name contains "and", or one that both writes and dispatches
before returning.

---

## 11. Reacting to state instead of to a transition

```csharp
if (invoice.Payments.Any(p => p.Status == PaymentStatus.Completed))
    await SendReceiptAsync(invoice);
```

The handler fires on *the existence of a completed payment* rather than on the event of one
becoming completed, so it re-fires on every subsequent write to the invoice. The entity state
stays correct the whole time — only the side effect is wrong, which is why it survives review
and shows up as duplicate customer email.

**Instead** — model the transition and dispatch on it:

```csharp
public abstract record PaymentTransition
{
    public sealed record PendingToCompleted(string PaymentId) : PaymentTransition;
    public sealed record CompletedToRefunded(string PaymentId) : PaymentTransition;
}
```

**How to spot it:** a side effect guarded by `.Any(...)`, `!= null`, or a status equality check
rather than by something that names a change. Also the near-miss version: moving a heavy side
effect off the hot path is right, but if the effect has no single consumption layer the move
itself introduces the bug.

---

## 12. Loading only the rows you expect

```csharp
var row = await db.Obligations
    .Where(o => o.Id == id && o.Status == ObligationStatus.Pending)
    .SingleOrDefaultAsync(ct);
if (row is null) return NotFound();
```

Retrying a request that already succeeded looks identical to a request for something that
never existed, so the endpoint is non-idempotent by construction. Clients retry on timeout;
this turns a successful-but-slow call into a 404.

**Instead** — load the owned state first, then distinguish:

```csharp
var row = await db.Obligations.SingleOrDefaultAsync(o => o.Id == id, ct);
return row switch
{
    null                                => NotFound(),
    { Status: Pending }                 => Process(row),
    { Status: Resolved }                => AlreadyHandled(row),   // successful no-op
    _                                   => Conflict(row.Status),
};
```

This falls out for free once transitions are typed.

**How to spot it:** a status predicate in the same `Where` as the identity predicate.

---

## Not everything is a modeling problem

The same meeting arriving through two synced calendars produces duplicate reminders because
concurrent handlers each cancel and reschedule. A pure core would not have fixed it; that
needed a deterministic cross-calendar key, schedule-level throttling, and delivery-time dedup.

What the pattern *does* buy is an obvious place for the invariant to live —
`ScheduleNotifications(MeetingKey, ReminderAt, FollowUpAt)` — with the durable adapter
providing the concurrency guarantee. Architecture makes the invariant visible and testable; it
doesn't enforce it. Don't oversell it.
