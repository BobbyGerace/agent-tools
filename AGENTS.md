# Working in this repo

**This is a public repository.** Anything committed here is world-readable, permanently, and
indexed. Treat every change as a publication.

## The rule

Nothing in this repo may be specific to a particular employer, codebase, client, or private
environment. And nothing may ever be sensitive.

That is stronger than "don't paste secrets." The test to apply to every line is:

> Would this still be true and useful for someone at a different company, on a different
> codebase?

If the answer is no, the line does not belong here — and **renaming the proper noun is not the
fix.** A claim that is only true in one codebase becomes a false or vacuous claim when you
genericize its subject, which is worse than the original because it reads as general advice.
Delete it, or rewrite it as the mechanism that does transfer.

Worked examples of the distinction, all of which have already come up here:

| Not portable | What was done |
| --- | --- |
| "Complexity correlates with defects in this codebase at r² ≈ 0.82" | Deleted the statistic; kept the argument that splitting a method relocates complexity rather than removing it |
| A table of three named repos and their build commands | Deleted; replaced with the four failure modes it existed to demonstrate |
| "This pattern already exists in six places — see these file paths" | Deleted the file; kept the naming convention |
| A lint hard-rejecting a query type because it failed against *one* observability account | Kept the guard, rewrote the message to say what generalizes and how to re-enable it |
| 32 real PR numbers cited as evidence | Deleted; the shapes they illustrated carry themselves |

## Never commit

- Credentials, tokens, API keys, DSNs, connection strings, `.env` contents — in any form,
  including "example" ones that happen to be real.
- Production queries. A SQL statement or observability query written against a real system
  leaks its schema, service names, and logging structure even when it returns nothing.
- Internal hostnames, service names, database or table names, log attribute names, span names.
- Internal repo names, project/namespace prefixes, ticket IDs, PR numbers, or file paths from a
  private codebase.
- Coworkers' names, internal document titles, wiki paths, or org-internal metrics (defect
  rates, coverage figures, headcount).
- Machine-specific facts presented as general ones — core counts, local paths, personal shell
  configuration.
- Vendor or tool names where the surrounding claim depends on that vendor's *configuration*
  rather than its documented behavior. Naming a tool as one option among others is fine.

Personal names are fine in a `LICENSE` or a commit author. They are not fine as instructions
("the user reviews the diff", not a name).

## Before every commit and every push

**Read the actual diff. Do not assume it is clean because you personally did not add anything
bad.** Agents working in other repositories reach into these skills to edit them, and their
context is full of exactly the material this file prohibits. A diff you did not author is the
likely source of a violation, not the unlikely one.

```bash
git diff                     # unstaged
git diff --cached            # staged
git diff origin/main..HEAD   # everything about to be pushed
```

Read them against the portability test above, line by line. That reading **is** the check. There
is no mechanical substitute, and it is worth being precise about why: whether a line is
company-specific is **semantic, not lexical**. Each of these is private, and no pattern-matcher
finds any of them, because none contains an identifier:

- "three divergent definitions of whether an update was actionable"
- "the 24-business-hour clock doesn't start until Monday 9am"
- "the daily 72-hour digest, 8 files"

So the questions to ask of each changed line are judgment questions:

1. Does it assert something only true in one codebase? A statistic, a coverage figure, a local
   convention, "this already exists in six places".
2. Does it describe a real system's behaviour — a rule, threshold, schedule, or schema — even
   without naming it?
3. Does it name a repo, service, table, namespace, ticket, PR, tool, or person?
4. Would a reader elsewhere be actively misled, or merely unable to use it?

Then run the secret scan, which covers the one category that *is* mechanizable:

```bash
./scripts/check-public.sh
```

It matches strings whose **form** identifies them: token formats, connection strings carrying
credentials, personal absolute paths, internal hostnames. It needs no knowledge of your employer
and produces no false positives on a clean tree, so a red run means something real.

- **A clean run is not a pass.** It means "no credential-shaped string" and nothing more.
- **When it flags something you did not write, stop and ask** rather than deciding for the
  person whose material it is.

It also greps an untracked `.check-public-private` when that file exists — names already removed
from this repo once. That is a **regression test, not a detector**: a denylist only knows what
someone thought to add, so it cannot catch the new internal name an agent from another repo
pastes in, which is the actual risk. The list stays untracked because publishing an employer's
internal names would leak precisely what this repo must not contain.

GitHub's own secret scanning and push protection run server-side on public repos, are better
maintained than this script, and block a push rather than trusting a local hook to have run.
Those are the backstop; the script is convenience.

### Hooks

`scripts/hooks/` holds a `pre-commit` (staged content) and a `pre-push` (the range being
published), both wrappers around the script above. Enable them once per checkout:

```bash
git config core.hooksPath scripts/hooks
```

If a hook blocks you, **read the finding rather than reaching for `--no-verify`.** Bypassing is
available and sometimes correct, but it is a judgment you are making on the record. When the
finding sits in a change you did not author, ask instead of bypassing on someone else's behalf.

Never assume the hooks ran. They are opt-in, git cannot activate them from a clone, and a fresh
checkout has them off — so the reading step above is not optional just because tooling exists.

## If something already leaked

A public repo's history is not private. Removing a line in a new commit does not unpublish it.
Say so plainly and immediately rather than quietly fixing it forward: the response has to be a
history rewrite and a credential rotation if a credential was involved, and that is the
repo owner's decision to make, not yours.

## Other conventions

- `verify/` carries the only executable code. Its tests are network-free and must stay that
  way — connectors and `gh` are stubbed. Run `./verify/tests/run-all.sh` after touching
  `verify_core.py`.
- Never hard-code a clone location. Tests derive the repo root from `__file__`; the CLIs derive
  it from `realpath(__file__)`. `$VERIFY_HOME` points only at data, never at code.
- The skills are prose that a model executes. Prefer stating the mechanism and the failure it
  prevents over stating a rule, since a rule with a reason survives paraphrase and a bare rule
  does not.
