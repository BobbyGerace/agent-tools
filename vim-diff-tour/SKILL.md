---
name: vim-diff-tour
description: Turn a diff, PR, branch, or commit range into a guided Neovim quickfix "tour" — a short, deliberately ordered list of only the highest-leverage changes, written as a JSON file the user loads with setqflist(). Use this whenever the user wants to review, understand, walk through, or be walked through a set of code changes in Vim or Neovim, or asks for a quickfix list / qflist / jump list built from a diff, PR, or commit range. Also use it when they ask "what should I actually look at in this diff" and they're a Vim user. Do NOT use it to produce an exhaustive change log — the whole point is aggressive selection.
---

# Vim Diff Tour

Build a **tour**: a small, ordered set of quickfix entries that walk a reader through a diff in the order that makes it comprehensible, pointing only at the parts that carry real meaning.

A tour is not a summary of the diff and not a list of its changes. It is a reading order. Assume the reader will hit `:cnext` repeatedly and read the surrounding code at each stop. Your job is to choose the stops and sequence them so that each one is understandable by the time they arrive at it.

## Workflow

1. **Read the whole diff first.** `git diff <range>`, `gh pr diff`, or whatever the user pointed at. Don't start selecting until you've seen all of it — selection depends on knowing what the change is *for*.
2. **Say what the change does, in one sentence, to yourself.** Then pick the stops a reader needs in order to reconstruct that sentence themselves. If an entry doesn't contribute to that, it isn't a stop.
3. **Order the stops** (see *Telling the story*).
4. **Write the JSON** to a topic-scoped path (see *Naming the file*).
5. **Verify it** with `scripts/check_tour.py`. Anchors that don't resolve turn the tour into a pile of `E486` errors, so don't skip this.
6. **Deliver it** (see *Loading the tour*).

## Naming the file

Use `/tmp/diff-tour-<slug>.json`, where `<slug>` is a short kebab-case name for *this* change — the branch name, the PR number, or two or three words from the one-sentence summary you wrote in step 2. `/tmp/diff-tour-token-refresh.json`, `/tmp/diff-tour-pr-<number>.json`.

A fixed filename silently clobbers the tour from whatever else the user is reading in another session — and the failure is invisible, because a stale-but-valid tour loads without complaint. The slug is what keeps two concurrent reviews apart, so it has to name the change, not the tool: `diff-tour-tour.json` or `diff-tour-review.json` collide as reliably as no slug at all.

Overwriting your *own* earlier tour of the same change is fine and expected. `/tmp` is the right home — these are disposable.

If the user gave a path, use theirs verbatim and don't add a slug.

## What earns a stop

Prioritize changes where the *consequences* are larger than the diff, or where the intent isn't legible from the code alone:

- **Shape of the data** — schema and migrations, data models, serialization and wire formats, anything persisted.
- **Public surface** — endpoints and route handlers, exported APIs, CLI flags, config keys, env vars, feature flags. Anything a caller outside the diff can observe.
- **Load-bearing logic** — concurrency, locking, transactions, retries, ordering guarantees, cache invalidation, state machines, invariants. The parts where being subtly wrong is quiet rather than loud.
- **Security and authz boundaries** — anything touching who is allowed to do what.
- **Changed failure modes** — errors newly swallowed, surfaced, retried, or reclassified.
- **Changed defaults** — a constant or config value whose new value changes runtime behavior. These are one-line diffs with enormous blast radius, and they're easy to miss precisely because they look trivial.
- **Deletions** — behavior removed is invisible in a diff viewer's happy path and often the most interesting thing in the change.

## What does not earn a stop

- Formatting, import shuffling, lint fixes, pure renames.
- Lockfiles, generated code, vendored dependencies, snapshots, fixtures.
- Mechanical call-site updates that merely follow a signature change. Collapse them: point at the signature once and say how many sites followed. Only break one out if its semantics actually shifted.
- Test churn — with one exception: a test that documents a new invariant or pins down the tricky case is worth a stop, because it tells the reader what the author was worried about.
- Comments and docs, unless they encode a contract.

**One idea, one stop.** If eight hunks express a single idea, point at the most representative one and describe the idea. A reader who understands it will recognize the other seven on sight.

**Aim for 5–9 stops.** Three is fine for a small change. Past twelve you've stopped curating, and the tour loses the property that makes it useful — that finishing it is obviously achievable. If a diff genuinely contains more than twelve load-bearing changes, say so in the title and tour the most important twelve rather than silently expanding.

## Telling the story

Order by **dependency of comprehension**: each stop should be understandable given the stops before it. Never order by filename, and never by the order hunks happen to appear in the diff.

The default arc, which fits most changes:

1. **Premise** — the change everything else follows from. Usually the data shape, a new type, a config switch, or a new dependency. What the reader has to hold in their head for the rest to parse.
2. **Mechanism** — the core logic that implements the premise. The trickiest, most load-bearing hunks go here.
3. **Surface** — how the change becomes visible from outside: endpoints, exported functions, flags, output formats.
4. **Consequences** — migrations, backfills, call sites whose behavior actually changed, removed code paths.
5. **Landmines** — anything risky, subtle, inconsistent, or unfinished that deserves a fresh look at the end, once the reader has full context.

Deviate when the change has its own natural narrative — a bug fix usually reads best as *the broken assumption → the fix → the guard that keeps it fixed*. The arc is a default, not a template to force a diff into.

When two stops are independent, put the one with the larger blast radius first.

When a diff contains several unrelated changes, tour them one theme at a time. Don't interleave — a reader can hold one thread at a time.

### Chapter headers

For tours of six or more stops, add header entries to make the arc visible. An entry with **no** `filename` renders as an unnavigable line in the quickfix window and is skipped by `:cnext`, so headers cost the reader nothing:

```json
{"text": "── Premise: sessions now carry an expiry ──"}
```

Name the chapter after what the reader is about to learn, not after the arc stage. "Premise" and "Mechanism" are scaffolding for you; the reader wants "What the new token shape is" and "How refresh decides to fire".

## Writing the `text`

This is the part that makes or breaks the tour. Each `text` shares one screen line with a filename and line number, so it must fit without wrapping.

- **Target 55 characters, hard ceiling 70.**
- Say **what changed and why it matters**, not what the code is. "Refresh now fires before the expiry check" beats "updated Refresh method".
- Don't repeat the filename or function name — the reader can see the file and is about to see the code.
- Fragments, not sentences. No trailing period. Lead with the verb or the noun that carries the information.
- Flag risk explicitly and briefly when it exists: `— off-by-one risk`, `— no timeout`, `— silently drops errors`.
- Never write filler like "important change" or "review carefully". Every stop is important; that's why it's a stop.

**Examples:**

| Weak | Strong |
| --- | --- |
| Updated the session refresh logic | Refresh moved before expiry check — off-by-one risk |
| Changed MaxConns | MaxConns 10→50, no matching timeout bump |
| Error handling change | Shutdown() error now swallowed |
| Added a new field to the User struct | New `deleted_at`; every query needs the filter |

For long paths that eat the line budget, set `module` — the quickfix window displays it instead of the filename:

```json
{"filename": "internal/services/auth/session/manager.go", "module": "session/manager.go", ...}
```

## The JSON format

Write an object with `title` and `items`. This maps directly onto `setqflist()`'s options dict, so it loads in one call.

```json
{
  "title": "Session expiry tour (main..feat/token-refresh)",
  "items": [
    {"text": "── How tokens are shaped now ──"},
    {
      "filename": "internal/auth/token.go",
      "pattern": "\\Vtype Token struct",
      "text": "Token gains ExpiresAt; zero value now means expired"
    },
    {
      "filename": "internal/auth/session.go",
      "pattern": "\\Vfunc (s *Session) Refresh",
      "text": "Refresh moved before expiry check — off-by-one risk"
    },
    {
      "filename": "internal/db/pool.go",
      "lnum": 47,
      "text": "MaxConns 10→50, no matching timeout bump"
    }
  ]
}
```

Include only `filename`, `pattern` or `lnum`, `text`, and optionally `module`. **Omit `type`, `nr`, and `col`** — `type` renders an extra `error`/`warning` column that steals characters from the text and implies a severity you don't mean, and `col` adds a number the reader doesn't need.

### Anchoring: prefer `pattern` over `lnum`

Line numbers drift the moment the user rebases, stashes, or edits a file mid-tour, and computing them from `@@` hunk headers is error-prone. A `pattern` finds the line wherever it moved to.

- Use `\V` (very-nomagic) so the rest of the anchor is treated literally: `"\\Vfunc (s *Session) Refresh"` — note the doubled backslash for JSON.
- Anchor on a line from the **added** side of the diff that is unique within its file. A function signature or type declaration is usually ideal.
- Avoid anchors containing backslashes; `\` stays special even under `\V`, and the double-escaping through JSON gets ugly fast.
- If the interesting line is a **deletion**, anchor on the nearest surviving line and make the `text` carry the point: `Retry loop removed here — failures now propagate`.
- Fall back to `lnum` only when nothing distinctive is nearby. Count against the **post-image** (the `+++` side).

## Verifying

```bash
python3 scripts/check_tour.py /tmp/diff-tour-token-refresh.json --root .
```

It checks that every file exists, every pattern matches exactly once, every `lnum` is in range, and every `text` is within budget. Fix what it reports and re-run before handing the tour over. A pattern that matches twice is worth fixing even though Vim will accept it — it means the anchor isn't as distinctive as you thought, and it'll break as soon as the file grows.

## Loading the tour

If `$NVIM` is set, you're running inside the user's Neovim and can load it directly:

```bash
TOUR=/tmp/diff-tour-token-refresh.json
nvim --server "$NVIM" --remote-expr \
  "setqflist([], 'r', json_decode(join(readfile('$TOUR'))))" >/dev/null
nvim --server "$NVIM" --remote-send '<C-\><C-N>:copen<CR>'
```

Otherwise print the line for the user to paste, and nothing else — no wrapper script, no instructions on how to use quickfix:

```vim
:call setqflist([], 'r', json_decode(join(readfile('/tmp/diff-tour-token-refresh.json')))) | copen | cfirst
```

Substitute the real path in both cases. A paste line still carrying a placeholder fails with `E484` in the user's editor, where fixing it is their problem rather than yours.

Then, in chat, give a **two-or-three-sentence** orientation: what the change does and what the arc of the tour is. Do not restate the stops — they're in the list, and repeating them defeats the point of building it.
