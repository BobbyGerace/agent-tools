---
name: review
description: Explicit invocation only. Use only when the user names `$review`; never activate it by inferring intent from a request to inspect or assess code. Independently reviews finished implementation work in one fresh background agent and returns only verified findings.
---

# Review

Review finished implementation work without carrying the implementer's assumptions into the
review. The current agent only launches and receives the review; one fresh background agent owns
the investigation and verdict.

Announce at start: "I'm using review to send the finished change to a fresh, independent reviewer."

## Isolation boundary

Spawn exactly one background reviewer with a new context that inherits no conversation turns. In a
runtime with an explicit history-fork option, select no history (`fork_turns="none"` in Codex).
Do not review the change in the current agent, and do not ask the reviewer to spawn more agents.

Give the reviewer only objective inputs:

- the repository and worktree path;
- the review scope: uncommitted work, a commit, or a base comparison;
- the path to the authoritative design or specification when one exists;
- the literal settled patch brief when that is the authoritative handoff;
- any scope or emphasis the user supplied with `$review`.

Do not summarize the implementation, explain why choices were made, suggest likely problem areas,
or pass along the implementer's reasoning. Commit messages and PR descriptions are orientation, not
evidence. The reviewer must establish the change and its intent from the handoff, diff, repository
instructions, code, and tests.

If the runtime cannot provide a genuinely separate background context, stop and say so rather than
performing an in-context review. If no review scope can be determined without a material choice,
ask the user for that scope before spawning the reviewer.

## Reviewer task

Instruct the reviewer to:

1. Read the applicable repository instructions and the complete authoritative handoff, when one
   exists.
2. Read the entire intended diff, including relevant untracked files, before selecting findings.
   Preserve unrelated user changes and report when the intended scope cannot be separated from
   them.
3. Load `ddd` and apply its review guidance when the change contains domain logic, state, time,
   money, identifiers, persistence, provider boundaries, or multi-field status. Start with changed
   types, contracts, and state shapes before tracing implementation logic.
4. Inspect enough surrounding code, callers, tests, and boundary contracts to evaluate behavior;
   changed lines alone are not sufficient evidence.
5. Look primarily for defects introduced by the change: incorrect behavior, violated handoff or
   repository contracts, illegal states, security or authorization failures, data loss, races,
   broken compatibility, and missing tests where the absent test leaves changed behavior
   unproved. Do not report formatting, taste, speculative generalization, or pre-existing defects.
6. Verify every candidate against primary evidence. Run focused tests or static checks when they
   materially prove or disprove a candidate, but do not edit source files, commit, push, publish,
   or contact external systems. A proposed fix is not evidence that a finding is real.
7. Return a concise final report only; omit the exploration transcript and rejected candidates.

## Report contract

Order findings by severity. For every finding include:

- severity and a short title;
- a precise file and line;
- the concrete failure or violated contract;
- the evidence that establishes it;
- the conditions under which it occurs.

Include a proposed direction only when it helps define the required behavior, and distinguish it
from the finding itself. Do not inflate confidence or severity to fill the report.

If there are no findings, say so explicitly and name only material residual risks or verification
gaps. A clean review means no defect was found in the examined scope; it is not proof of absence.

End with exactly one verdict:

```text
Review clean. Continue with `$ship`.
```

or

```text
Review found issues. Address the findings, then run `$review` again.
```

## Hand-back

Wait for the background reviewer to finish. Return its report to the user without independently
re-reviewing, weakening, embellishing, or converting findings into edits. The original
implementation session can act on the report without copying it between sessions.

Every later `$review` invocation starts another new reviewer with no inherited turns, including
reviews performed after fixes.
