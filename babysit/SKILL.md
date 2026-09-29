---
name: babysit
description: Explicit invocation only. Use only when the user names `$babysit`; never activate it by inferring intent from a request to monitor, watch, wait, poll, or keep checking. Monitors a long-running operation at a requested cadence until it succeeds, fails, or becomes genuinely blocked.
---

# Babysit

Monitor to a terminal outcome with a deterministic cadence. A persistent goal or automatic continuation is not a clock: never use turn completion to implement a polling interval.

## Establish the contract

Extract these from the request and current state:

- The exact target and authoritative status source.
- Success, failure, and hard-blocked terminal conditions.
- The requested interval; use five minutes when the user says “every five minutes.”
- Actions already authorized when a failure appears, such as inspecting logs, editing, testing, pushing, or rerunning.

Resolve identifiers before waiting. For CI, record the repository, pull request, workflow run, and relevant job IDs. Re-resolve them after a push or rerun because new runs receive new IDs.

## Choose the waiting mechanism

Prefer, in order:

1. A native blocking watcher with an explicit interval and terminal exit status.
2. One long-lived command or tool session polled at the requested interval.
3. A single open agent turn with bounded wait calls whose total equals the interval.

For a GitHub Actions run, prefer:

```bash
gh run watch <run-id> --repo <owner/repo> --interval <seconds> --exit-status
```

Do not use `gh pr checks --watch` when success depends on optional or aggregate jobs that are not required checks; watch the authoritative workflow run instead.

Gitea has no blocking watcher, so poll at the requested cadence (option 2 or 3). A PR's runs report `head_branch: null`, so resolve them by commit, not branch:

```bash
tea api "repos/<owner>/<repo>/actions/runs?head_sha=<sha>"   # every run for the PR head: id, path, status, conclusion
tea api repos/<owner>/<repo>/actions/runs/<run-id>           # one run: status, conclusion, html_url
tea api repos/<owner>/<repo>/commits/<sha>/status            # combined check state, one status per job
tea actions runs logs <run-id> --repo <owner>/<repo>         # logs once something fails
```

A run is terminal when `status` is `completed`; `conclusion` then says how. Required checks posted by an external service rather than a workflow appear only in the combined commit status, not as runs.

If the environment limits individual blocking waits, divide the interval into permitted chunks while keeping the same turn open. For example, implement five minutes as five 60-second waits, then perform exactly one status query. Do not end a turn between chunks when ending it causes immediate automatic continuation.

Use an operating-system cron only when the user explicitly wants a durable schedule and accepts persistent machine configuration. Prefer an in-session watcher for a one-off operation because it terminates with the target.

## Monitor without noise

- Query no faster than the requested cadence. Record the monotonic time of each authoritative query when the watcher does not enforce cadence itself.
- Report state changes, discovered failures, remediation, and terminal outcomes.
- Avoid sending chat updates for early scheduler wakes or unchanged state unless the environment requires a heartbeat. If it does, keep the turn alive and send the minimum permitted heartbeat without issuing another status query.
- Never claim that a recurring goal is a cron job or that a cadence is configured unless a clock-based mechanism actually enforces it.

## Handle outcomes

On success, perform one fresh authoritative check covering the full requested success condition, stop the watcher, and report completion.

On failure:

1. Capture the failing job, step, logs, and commit or deployment revision.
2. Decide whether the failure is related, flaky, infrastructure-only, or a real defect.
3. Apply only authorized, in-scope remediation.
4. Verify proportionately, push or rerun when authorized, resolve the new run ID, and resume watching.

Do not rerun blindly when logs expose an actionable defect. Do not modify product code merely to hide an unrelated infrastructure failure.

On a possible blocker, exhaust safe read-only diagnostics and in-scope alternatives first. Ask the user only when progress requires new authority, unavailable credentials, an external decision, or an external-state change with no useful work remaining. State the exact blocker and the smallest decision needed.

## Finish cleanly

Terminate background watchers or sessions when the target reaches a terminal state or the user cancels. Report the final status, any remediation performed, and the authoritative run or job link when available.
