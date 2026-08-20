---
name: investigate
description: Investigate bugs, incidents, surprising behavior, and factual questions about a running system using runtime data as well as code. Use when the user asks to investigate, diagnose, find out what happened, explain why a particular case behaved differently, or validate a causal hypothesis. Requires evidence from logs, traces, databases, API responses, recordings, screenshots, reproduction, or equivalent observations; code alone can describe possibilities but cannot establish what occurred.
---

# Investigate

Determine what happened, why, and how certain that conclusion is. Do not change the system unless
the user separately asks for a fix.

Announce at start: "I'm using investigate to trace <subject> from runtime evidence."

## Evidence standard

Treat sources according to what they can establish:

- Runtime data establishes what happened in the observed case: logs, traces, database rows, API
  responses, recordings, screenshots, metrics, queue state, and a faithful reproduction.
- Code establishes what could happen and connects observations into a causal mechanism.
- Tests and documentation establish intended or previously asserted behavior, not production fact.
- User-provided facts are premises. Preserve them unless evidence contradicts them; call out any
  contradiction instead of silently replacing them.

Never present a code-only explanation as the cause of a real event. If runtime evidence is
unavailable, report a hypothesis and the exact evidence needed to confirm or reject it.

## Workflow

### 1. Frame the question

Write down, briefly and for yourself:

- the behavior to explain;
- the known facts, identifiers, and time range;
- the expected behavior;
- the leading hypotheses, including the user's;
- what observation would distinguish them.

Resolve times to one timezone before comparing them. Do not discard awkward facts to make a
hypothesis fit.

### 2. Find the evidence surfaces

Read repository instructions and locate the relevant runtime sources before settling on a cause.
Inspect enough code to learn the identifiers, events, storage, and boundaries worth querying.
Then obtain the most discriminating runtime evidence available; do not mechanically query every
system.

Start narrow with the supplied case, then widen only when comparison is useful. Prefer correlated
events and exact records over broad searches or aggregate dashboards. Use read-only access. Avoid
exposing secrets or unnecessary personal data in notes and output.

If an important source is inaccessible, exhaust available connectors and local artifacts. Then
ask the user for the smallest concrete result needed: provide a read-only query or precise lookup,
say which fields matter, and explain which hypotheses the result separates. Continue with other
evidence while waiting when possible.

### 3. Reconstruct the case

Build a chronological path across boundaries. For each important step, retain:

- observation and source;
- identifier and timestamp when applicable;
- what the observation proves;
- what it does not prove.

Trace both successful and missing steps. Absence is evidence only after confirming the source
should contain the event, the query covers the right scope and retention window, and ingestion or
sampling cannot explain the gap.

### 4. Test hypotheses

For each viable hypothesis, derive a prediction and look for it. Also seek the strongest available
counterexample or alternative explanation. Compare a nearby normal case when that separates
case-specific data from general behavior.

A root-cause claim needs an evidenced causal chain from trigger through the relevant decisions and
effects to the observed outcome. A suspicious branch, null, race, or configuration value is not a
root cause merely because it could produce the symptom.

### 5. Fact-check before reporting

Run a deliberate consistency pass:

1. List every material claim in the proposed explanation.
2. Attach evidence to each claim, or label it inference or hypothesis.
3. Check the timeline, identifiers, counts, state transitions, and terminology against one another.
4. Check every known fact from step 1; explain any that the conclusion does not account for.
5. Try to falsify the conclusion with the strongest competing hypothesis.
6. Lower confidence or keep investigating when a causal link is unsupported.

Do not use confidence language to paper over a contradiction.

## Report

Lead with the outcome and confidence. Keep the report compact, but include:

- **Conclusion:** what happened and why, or the leading hypothesis if not proven.
- **Evidence:** the small set of runtime observations that establishes the conclusion, with code
  references only where they explain the mechanism.
- **Consistency check:** how the conclusion accounts for the original facts and what competing
  explanation was rejected. State unresolved contradictions plainly.
- **Unknowns:** missing evidence and the exact next check, if any.

Use precise labels: **observed**, **inferred**, and **hypothesized**. Include queries or raw excerpts
only when they help the user verify the reasoning; redact sensitive values and avoid dumping data.

## Stop conditions

Stop with a confirmed conclusion only when runtime evidence supports the causal chain and the
consistency pass finds no unexplained material fact. Otherwise stop with an explicitly provisional
result when the remaining evidence is unavailable, destructive to obtain, outside the authorized
scope, or unlikely to change the decision.
