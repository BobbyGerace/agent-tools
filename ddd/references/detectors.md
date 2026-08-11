# Anti-Shape Catalog

Each entry: what it looks like in code, how it fails, what to write instead, and — where the
shape is easy to miss — how to spot it.

Use this when reviewing a design or a diff. If none of these shapes are present, the design
probably satisfies rules 1–10; that's the fastest way to check. Almost every entry is visible
in a type declaration — see `ddd`'s *Reviewing without reading every line*.

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

**The categories worth keeping apart**, because each has a different caller obligation:

| Category | Example |
| --- | --- |
| invalid request | malformed time, unknown enum, missing required selection |
| business denial | not enrolled, address missing, ineligible assignee |
| conflict | claim race, version conflict, stale expected state |
| no change | duplicate command, stale event, already in the requested state |
| retryable infrastructure | database, transient provider, message bus |
| permanent integration | invalid auth, unsupported capability, corrupt payload |
| accepted / deferred | the source exists but the projection is still processing |
| partial success | core outcome committed, best-effort effect failed |

The last one is the one usually missing, and it is the one that needs the most from the type:
the failed effect has to stay **identifiable and reconcilable**, not merely reported.

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

## 13. A parameter list of interchangeable strings

```csharp
Task<ErrorOr<Success>> CancelShipmentAsync(
    string tenantId,
    string shipmentId,
    string? carrierBookingId = null
);
```

Every argument is assignable to every parameter, so a transposition compiles and ships. It
fails quietly: the call succeeds against the wrong scope, or an equality check compares two
values that are both "valid" strings and simply aren't the same kind of thing. The version that
actually bites is two textual forms of the *same* id — a prefixed and an unprefixed user id,
both plausible, exact string equality standing in for canonical identity — where a fraction of
records silently lose attribution and nothing errors.

**Instead** — opaque types with private constructors and a `Parse` that returns a result:

```csharp
public sealed record ShipmentId
{
    public string Value { get; }
    private ShipmentId(string value) => Value = value;

    public static ErrorOr<ShipmentId> Parse(string value) => /* canonical form */;
}
```

Strings stay at the edge — wire models, ORM converters, protobuf mappers. Types start one
layer in. Don't add a public constructor taking unchecked values to save mapping code; that
reopens the hole.

**How to spot it:** two or more `string` parameters in one signature whose names end in `Id`,
`Uid`, `Key`, or `Ref`. Also a wrapper type whose factory always succeeds — `From(...)` that
returns an object and a `ToString()` that can return null is a validation that never happened.

---

## 14. A discriminator beside a polymorphic payload

```csharp
public required DocumentType Type { get; set; }
public required IDocumentMetadata Metadata { get; set; }
```

`Type = Invoice` with `ContractMetadata` attached is representable, so every consumer validates
the pair at runtime — usually via an `IsValid(DocumentType)` method on the metadata, which is
the type system asking to be used and being declined.

**Instead** — one value that carries both, and derive the persisted discriminator from it:

```csharp
public abstract record DocumentBody
{
    private DocumentBody() { }

    public sealed record Invoice(InvoiceMetadata Metadata) : DocumentBody;
    public sealed record Contract(ContractMetadata Metadata) : DocumentBody;
}

public static ErrorOr<DocumentBody> ToDomain(DocumentRow row) => (row.Type, row.Metadata) switch
{
    (DocumentType.Invoice, InvoiceMetadata m)   => new DocumentBody.Invoice(m),
    (DocumentType.Contract, ContractMetadata m) => new DocumentBody.Contract(m),
    _ => Error.Unexpected(code: "Document.InconsistentBody"),
};
```

Legacy corruption stays detectable; new invalid combinations stop being a service's problem.

**How to spot it:** an enum property and an interface-typed or `object` property on the same
entity, especially with a validation method taking the enum as its argument.

---

## 15. One `null` standing for several states

```csharp
public string? RecordingPath { get; set; }
```

Absent because it was never requested, absent because it hasn't finished uploading, absent
because it failed permanently, absent because nobody loaded it — all one value. The legal next
action differs in every case, so the code guesses, and the guess is usually "permanently gone",
which turns normal latency into a false alarm and a real loss into silence.

The same shape appears as a *default that looks chosen*: a form initialized to the next
half-hour, so a time the user never picked is indistinguishable from a deliberate one.

**Instead** — name the states whose next actions differ:

```csharp
public abstract record ArtifactAvailability
{
    private ArtifactAvailability() { }

    public sealed record NotRequested : ArtifactAvailability;
    public sealed record Pending(Instant SinceAt) : ArtifactAvailability;
    public sealed record Ready(ArtifactPath Path) : ArtifactAvailability;
    public sealed record Failed(FailureReason Reason) : ArtifactAvailability;
}
```

and, for user intent, `Unselected | Selected(value)` — never a plausible value doubling as the
sentinel.

**How to spot it:** a nullable field whose null is explained differently in two places, a
`?? "default"` beside a `is null` branch that means something else, or a comment starting "if
this is null it usually means". Also: a UI state initialized to a computed real value rather
than to nothing.

---

## 16. A classifier that returns `bool`

```csharp
public static bool ShouldAlert(DeliveryFailure failure) => /* two exclusion sets */;
```

The function knows three things — this is an expected recipient outcome, this is a known defect
tracked elsewhere, this is genuinely actionable — and returns one bit. Every caller that needs
the distinction rebuilds it, and the telemetry can't tell a healthy suppression from a broken
pipeline.

**Instead** — return the classification and let the boolean be derived:

```csharp
public abstract record FailureDisposition
{
    private FailureDisposition() { }

    public sealed record ExpectedOutcome(ErrorCode Code) : FailureDisposition;
    public sealed record KnownDefect(ErrorCode Code, RemediationRef Remediation) : FailureDisposition;
    public sealed record Actionable(ErrorCode? Code) : FailureDisposition;

    public bool ShouldPage => this is Actionable;
}
```

**How to spot it:** a `bool`-returning method whose body has three or more branches, or whose
name starts `Should`/`Is` and whose implementation consults more than one set.

---

## 17. A provider's vocabulary loose in the domain

```csharp
if (payload.Status == "completed" || payload.Status == "no-answer")
```

Raw external strings compared throughout services and controllers. Two failures: a value you
don't recognize falls through to whatever the last `else` does — usually "failed", which is a
business conclusion nobody decided — and the provider's meaning of a word gets confused with
yours. "Completed" for the transport is not "completed" for the business, and an upload can
still be in flight after the thing that produced it finished.

**Instead** — parse once at the adapter, and keep unknowns:

```csharp
public abstract record ProviderStatus
{
    private ProviderStatus() { }

    public sealed record Completed : ProviderStatus;
    public sealed record NoAnswer : ProviderStatus;
    public sealed record Unknown(string Raw) : ProviderStatus;   // preserved, not collapsed

    public static ProviderStatus Parse(string raw) => raw.Trim().ToLowerInvariant() switch
    {
        "completed" => new Completed(),
        "no-answer" => new NoAnswer(),
        _           => new Unknown(raw),
    };
}
```

Then keep three vocabularies apart: what the provider says, what the evidence indicates, and
what it means to the business. A provider error code becomes a typed result (`NotStartedYet`),
and the domain decides what that means given its current state.

**How to spot it:** a string literal from an external system compared anywhere outside an
adapter; a `switch` on a provider status with a `default` that returns a business outcome; an
error-code integer or string compared below the adapter boundary.

---

## 18. The latest row treated as the state

```csharp
var latest = await LoadLatestFollowUpAsync(recordId);
if (latest?.CompletedAt is not null) return null;      // terminal
return latest is null ? Attempt.Zero : latest.Attempt + 1;
```

The most recent persistence row stands in for the aggregate. Any row that happens to be last —
a cancellation, a superseded attempt — becomes terminal, and everything the history knew
(how many attempts have run, whether a human took ownership, whether it was paused or truly
exhausted) is unreachable. The entity is never wrong; the *conclusion drawn from it* is.

**Instead** — reconstruct from the facts that determine legal transitions:

```csharp
public abstract record CadenceState
{
    public sealed record NeverRun : CadenceState;
    public sealed record Running(int Attempt, Instant StartedAt, Instant EligibleAt) : CadenceState;
    public sealed record HumanOwned(Instant EligibleAt, Instant PromisedAt) : CadenceState;
    public sealed record Paused(Instant PausedAt, PauseReason Reason) : CadenceState;
    public sealed record Exhausted(Instant ExhaustedAt, int AttemptsMade) : CadenceState;
}
```

built from the latest row *plus* the retry high-water mark *plus* any terminal stamp. This is
not an argument for event sourcing; it's an argument against mistaking persistence order for
domain meaning.

**How to spot it:** `OrderByDescending(...).FirstOrDefault()` whose result is then treated as
current state, or any `latest?.SomeTimestamp is not null` used as a terminal check.

---

## 19. A partial projection feeding a whole-aggregate write

A read model built for a detail screen omits a collection it didn't need. A replace-all update
consumes that same model, reads the omission as an empty collection, and deletes rows the user
never touched — while adding one.

The related shape: a projection that buckets a multi-day interval by its start day serves both
rendering *and* a booking-safety decision, so later days look free.

**Instead** — a replace command consumes a complete, versioned document, and `Empty` is a value
the domain can distinguish from "not loaded":

```csharp
public sealed record ReplaceContactDetails(
    TenantId TenantId,
    ContactDetailsDocument Desired,      // complete by construction
    DocumentVersion? ExpectedVersion
);
```

A projection optimized for one consumer is not business truth for a write or a safety check.
Give read models explicit completeness and provenance, and derive presentation buckets from
the domain interval rather than storing the bucket as the fact.

**How to spot it:** a DTO used as both a query response and a command body; a `Patch` type full
of nullables where null means three things ("unchanged", "clear", "my client version doesn't
know this field") — two independently deployed callers will erase each other's data; a
day/bucket-shaped table that something other than the UI reads.

---

## 20. Identity read from the world at execution time

```ts
async function send() {
  const body = composer.text // component state
  const to = selectedLead.phone // a store that may have moved
  await api.send(to, body)
}
```

Two values read at two different times. Draft a message to one record, navigate to another —
a cached composer keeps the first one's text — and hit send: the first body goes to the second
number. Neither read was wrong; they just weren't simultaneous. The same shape on retry lets
an attempt adopt a sender, assignee, or timestamp that wasn't current when it was first made,
so retrying converges on nothing.

**Instead** — the command is a value built at the moment of the decision, and the send function
takes only that:

```ts
type PreparedMessage = {
  to: E164PhoneNumber
  body: string
  conversationId: ConversationId
  key: IdempotencyKey // which attempt this is, decided with the content
}
```

The key belongs in the same record for the same reason: the action is irreversible, so you
have to know whether it already happened, and a key derived at execution time varies per
attempt and never dedupes. Scheduled work is this with a longer gap — a wakeup carries enough
snapshot identity to prove the thing it was scheduled for still exists, or the timer fires
against whatever replaced it.

**How to spot it:** a send/execute/dispatch function that takes few or no parameters and reads
its subject from a store, context, hook, or ambient request scope. Also a retry path that
rebuilds its payload instead of replaying the original.

---

## Not everything is a modeling problem

The same meeting arriving through two synced calendars produces duplicate reminders because
concurrent handlers each cancel and reschedule. A pure core would not have fixed it; that
needed a deterministic cross-calendar key, schedule-level throttling, and delivery-time dedup.

What the pattern *does* buy is an obvious place for the invariant to live —
`ScheduleNotifications(MeetingKey, ReminderAt, FollowUpAt)` — with the durable adapter
providing the concurrency guarantee. Architecture makes the invariant visible and testable; it
doesn't enforce it. Don't oversell it.
