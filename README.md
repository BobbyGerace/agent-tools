# agent-tools

A set of Claude Code skills for a design → implement → ship loop, plus the prod-verification
tooling that loop depends on.

Everything is symlinked into place rather than copied, so the working copy is the repo and there
is nothing to sync.

## Skills

Symlink each one into `~/.claude/skills/`:

```bash
REPO=$(pwd)                       # wherever you cloned this
for s in explain-context design implement ship ddd vim-diff-tour; do
  ln -s "$REPO/$s" ~/.claude/skills/"$s"
done
```

| Skill             | Does                                                            | Invoked              |
| ----------------- | --------------------------------------------------------------- | -------------------- |
| `explain-context` | Explains a domain from the ground up so you can work in it      | by you               |
| `design`          | Iterates a design doc in annotated rounds until it's settled    | by you               |
| `implement`       | Builds a settled design in chunks, verified once at the end     | by you               |
| `ship`            | Commits, writes the PR, authors the verify spec, opens a draft  | by you               |
| `ddd`             | The domain-modeling standard and code shape rules               | loaded by the others |
| `vim-diff-tour`   | Turns a diff or PR into an ordered Neovim quickfix reading tour | by you               |

The loop: `explain-context` (if the domain is unfamiliar) → `design` → `implement` → `ship`.
`ddd` is a reference bundle the other three load; there's no reason to invoke it directly.
`vim-diff-tour` sits outside the loop — it's for reading someone else's change, not making one.

`design` keeps its docs in `~/designs/` as a git repo, one file per design, one commit per
round. Create it before first use:

```bash
git init ~/designs
```

## `verify/` — prod verification tooling

Two front ends over one shared module:

|                  |                                                                  |
| ---------------- | ---------------------------------------------------------------- |
| `verify-spec`    | single-spec CLI: `run`, `watch`, `validate`, `schema`, `setup`   |
| `verify-board`   | one curses window watching every active spec on a backoff ladder |
| `verify_core.py` | spec loading, credentials, connectors, evaluation, scheduling    |

```bash
ln -s "$REPO/verify/verify-spec"  ~/.local/bin/verify-spec
ln -s "$REPO/verify/verify-board" ~/.local/bin/verify-board
```

**Code and data are deliberately separate.** The source lives here and is source-controlled.
The specs live in `$VERIFY_HOME` (default `~/verify/`) — `active/`, `archive/`, `state.json` —
which is **not a git repo and must not become one**, because `active/*.toml` carries live
production SQL and observability queries. The front ends find the module via
`realpath(__file__)`, so the symlink above is what connects the two; `VERIFY_HOME` only ever
points at the data.

```bash
mkdir -p ~/verify/active ~/verify/archive
```

### Configuration

| Variable           | Default        | What it does                                            |
| ------------------ | -------------- | ------------------------------------------------------- |
| `VERIFY_HOME`      | `~/verify`     | Where specs and board state live                        |
| `VERIFY_GH_OWNER`  | unset          | GitHub owner for specs that name their repo bare        |

`VERIFY_GH_OWNER` is worth setting. A spec's `pr` field is what holds it off the board until the
PR merges, and resolving that needs `owner/name`. With the variable unset, a spec written as
`repo = "api-service"` cannot be resolved, so it **fails open and runs its checks immediately** —
which produces reds that only mean "not deployed yet". Either export the owner or write
`repo = "owner/api-service"` in the spec.

Credentials are readonly and live in the macOS Keychain (`verify-spec setup`); nothing here
stores a secret. That makes the credential path macOS-only — on another platform, replace
`keychain_get`/`keychain_set` in `verify_core.py`. Everything else is portable.

There is **no APM connector**. One existed and was removed because it could not be made to
return a trustworthy count; see the note above `CONNECTORS` in `verify_core.py` for what
generalizes from that and what to prove before adding one back.

### Tests

```bash
./verify/tests/run-all.sh
```

279 assertions, no network — connectors and `gh` are stubbed throughout, so the suites never
touch prod. Worth running after any change to `verify_core.py`, which two sessions have edited
concurrently before now.

## Scope

The skills assume a git repo, `gh`, and a CI config they can read; `implement` and `ship`
discover build/lint/test commands from the repo rather than hard-coding them. `ddd` is written
around C# records and pattern matching — the twelve rules carry to any typed language, the
examples don't. Nothing here is tied to a particular employer, codebase, or internal tool; where a
practice depends on local setup, it says so instead of assuming.

## Contributing

**This repo is public, and these skills get edited by agents running in other repositories** —
whose context is full of private material. [`AGENTS.md`](AGENTS.md) is the standard: what may
not be committed, and why renaming a proper noun is not a substitute for deleting a claim that
only holds in one codebase.

Before any commit, read the diff against that standard, then run:

```bash
./scripts/check-public.sh
```

The script catches only strings whose *form* gives them away — token shapes, connection strings
with credentials, personal absolute paths. Whether a line is company-specific is semantic, and no
regex decides it, so a clean run is not a pass. Reading the diff is the check.

### Setup

```bash
make setup
```

Activates the hooks and verifies the denylist exists. Both halves are needed and **neither
travels with a clone**, so this is once per checkout:

| Piece | In git? | Arrives with a clone? |
| --- | --- | --- |
| `scripts/hooks/*` | Yes | Yes — the files are there |
| `core.hooksPath` activation | No, it's `.git/config` | **No** |
| `.check-public-private` | No, gitignored | **No** |

Git cannot activate hooks from a clone — if it could, cloning any repo would be arbitrary code
execution. `make doctor` reports what's configured and what isn't.

`pre-commit` scans staged content; `pre-push` scans the range being published and is the one that
matters, since a bad commit can be amended but a pushed one can't be unpublished. Both are
bypassable with `--no-verify`, which is a decision to own rather than a formality.

### The local denylist

`.check-public-private` lists names that must never reappear here, one regex per line:

```
my-employer
internal-service-name
Namespace\.[A-Z][A-Za-z]*
TICKETPREFIX-[0-9]+
```

`make denylist` scaffolds it. It's gitignored and must stay that way: a list of an employer's
internal names is exactly the material this repo must not publish.

**The hooks fail when it's missing rather than passing quietly** — a green run with this category
silently switched off is worse than a red one, and it's invisible exactly when it matters, on a
fresh clone nobody has set up. `make check` (without `--require-denylist`) still runs for
exploring.

Be clear on what it is: a **regression test**, catching names already removed once. It cannot
catch a new internal name, because a denylist only knows what someone thought to add. That gap is
what reading the diff is for.

