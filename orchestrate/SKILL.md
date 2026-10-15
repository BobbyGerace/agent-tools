---
name: orchestrate
description: Explicit invocation only. Use only when the user names `$orchestrate`. Drives a multi-slice `design` specification through implementation, review, shipping, and CI to a green PR ready for the user to merge, one slice after another, while the orchestrator owns the bookkeeping and is the user's single point of contact.
---

# Orchestrate

Take a settled specification and carry each slice through `implement`, `review`, `ship`, and CI
to a PR the user can merge. The point is to lift the context switching off the user: which
environment each slice runs in, which checkout it uses, what it branches from, and the slow grind
of getting each PR to green. You own that bookkeeping; slice sessions own the code.

This file describes intent, not procedure. When a situation isn't covered, or following a line
here literally would produce something silly, do what the user would obviously want and tell them
what you did.

## Before the first slice

Read the specification and its slice list: dependencies, deploy order, which slices are settled and
which are open. An open slice needs a `$design` interview with the user before it can be built;
raise it when you reach it rather than guessing at its deferred decisions.

Settle up front anything every slice would otherwise stop to ask about — above all, where the work
runs, following whatever instructions the user already has for choosing an environment. Pass those
answers to every session explicitly. A slice session that has to ask the user something you could
have told it is wasted time.

## Slice sessions

Run each slice in its own top-level agent session, not a subagent. Subagents get a reduced system
prompt, may not load the user's memory or instructions, and end when you do; a top-level session
behaves exactly as it would if the user had started it. Prefer one that runs in the background and
that the user can attach to — for example `claude --bg`, or `claude -p` / `codex exec` resumed by
session ID. Check the CLI's `--help` for current flags rather than trusting this file.

Give each session what it needs to run unattended: the specification path and slice ID, the
environment, the checkout, the base branch, and your own session name so it can reach you. Have it
run `implement`, then `review`, then `ship`, and report back concisely. When it genuinely needs a
user decision, it should send you the smallest decision needed and end its turn rather than guess.

Route questions through you, not through an interactive prompt in the slice session. A question
asked in a background session blocks it until someone attaches, and a message does not answer it.
A message sent to a session that has ended its turn does resume it.

Start sessions in the same permission mode as yours; some harnesses hold messages between sessions
in different modes until a human approves them. A background session may refuse to start in a
directory the harness has not been told to trust, and a new worktree can be one. Ask the user to
trust it rather than working around the check.

Keep each session alive after its PR opens. It has the context to fix its own CI failures, and the
user can attach to it later to work on that slice directly.

## Checkouts and branches

Only one session works in a checkout at a time. Slices usually run in series, but the previous slice
still needs its checkout for CI fixes while the next one starts. So give each slice its own
worktree, or its own disposable environment, in which case that environment's main checkout is fine.

A fresh environment per slice is cleaner, but anything set up beyond its template — test data,
accounts, configuration — has to be recreated each time. Ask the implementer to leave that setup as
a replayable script, so the choice stays cheap either way.

Base each slice on the previous slice's branch while that branch is unmerged, and on the default
branch once it merges. When an earlier slice changes, restack the later ones between steps of work,
not while their session is mid-change.

## CI

After `ship`, the slice's session watches its PR to green (`babysit`). CI rounds are slow and often
fail for reasons unrelated to the change, so the cost to minimize is rounds, not fixes:

- Before each push, rebase onto the current base and run the full local checks. Merge conflicts,
  a migration that is no longer ordered last, and lint failures are predictable; catch them before
  CI does.
- On a red run, read every failing job before changing anything, then act by cause: a defect in the
  change gets fixed; a flaky test gets its failed jobs rerun (a flake that keeps recurring may be
  real); an infrastructure outage gets a wait and a rerun with no code change; a broken pipeline
  gets reported; a moved base gets a rebase.

Several PRs can sit in CI at once while later slices build. That overlap is where the time goes.

## Merging

Once a PR is green, mark it ready for review yourself: `ship` leaves every PR as a draft, and
invoking this skill is the user's standing permission to publish the PRs it produces. Never merge.
The user keeps that button. Tell them which PRs are ready, and when one merges, move the next
slice's base to the default branch and restack what sits above it.

## Smoke tests and the user's check

The implementer exercises the real code paths itself — through whatever the system offers, such as
impersonation, a database shell, or API calls — and records what it ran and what it saw. Aim for
slices that change nothing visible until the slice that turns the feature on, and check both states
where that applies.

Hands-on checks the user wants to do themselves, especially UI, can then wait until the end. When
that point comes, prepare everything they need — environment, URL, identity to use, data, steps, and
what they should see — and give them the session to attach to if they want to iterate with the
agent that built it.

## State and the user

Keep a ledger in one plain file beside the specification, uncommitted: for each slice its status,
checkout, branch, PR, CI state, session ID, and open questions. Update it as things change. It is
what survives your own context being compacted, and it is where the user looks instead of asking.

Batch questions for the user rather than relaying each session's as it arrives. Report when a slice
lands, when something needs them, and when the whole specification is done — not every status change.
