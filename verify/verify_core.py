"""verify_core — shared spec loading, credentials, connectors, and scheduling.

Imported by two front ends that must agree on every one of these:

  * `verify-spec` (~/.local/bin) — the original single-spec CLI. Scans the
    current worktree's `.scratch/verify/` by default, unchanged.
  * `verify-board` (~/.local/bin) — the aggregate TUI. Watches every spec in
    `$VERIFY_HOME/active/` on a per-spec backoff ladder.

The spec shape is owned by this module: `SCHEMA_TEXT` is what `verify-spec
schema` prints, so an author regenerating their knowledge from the tool can
never drift from what the runner accepts.

Nothing here writes to a terminal. Rendering belongs to the front ends.
"""

from __future__ import annotations

import datetime as dt
import getpass
import json
import os
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field

USER = os.environ.get("USER") or getpass.getuser()

# Where the aggregate board keeps its specs. Overridable so a test run can
# point somewhere disposable instead of the live store.
VERIFY_HOME = os.path.expanduser(os.environ.get("VERIFY_HOME", "~/verify"))
ACTIVE_DIR = os.path.join(VERIFY_HOME, "active")
ARCHIVE_DIR = os.path.join(VERIFY_HOME, "archive")
STATE_PATH = os.path.join(VERIFY_HOME, "state.json")

# `verify-spec`'s original default: the current worktree, not the shared store.
WORKTREE_VERIFY_DIR = os.path.join(".scratch", "verify")

# Keychain service names (login keychain, account = $USER).
KC_PG_DSN = "verify-spec-pg-dsn"

# The telemetry command: whatever on PATH honors the contract in README.md
# ("The telemetry command"). It owns its backend's auth and dialect, so nothing
# here knows which observability store sits behind it. Overridable so a test —
# or a second backend — can substitute its own.
TELEMETRY_CMD = os.environ.get("VERIFY_TELEMETRY_CMD", "telemetry-query")

# Sources this runner once had. A spec still naming one is told where its check
# went, rather than getting a bare "unknown source" and a guess.
RETIRED_SOURCES = {
    "datadog": "logs are now SQL against the telemetry store",
    "spans": "spans are now SQL against the telemetry store",
    "rum": "there is no browser source; a frontend-only change has no automatable check",
}

OPS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    "le": lambda a, b: a <= b,
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "ge": lambda a, b: a >= b,
}

PASS, FAIL, ERROR = "PASS", "FAIL", "ERR "

# A failed check is not always proof. An absolute invariant ("zero orphaned rows")
# failing means something is broken; a volume heuristic ("the poll is still
# serving") failing at 3am on a Sunday means nothing. `level` on the check says
# which, and a failed `warn` check evaluates to WARN rather than FAIL so the
# state alone decides the colour — nothing downstream has to recombine the two.
WARN = "WARN"
LEVELS = ("alert", "warn")

# A spec whose PR hasn't merged yet is not failing — there's simply nothing
# deployed to check. Held specs don't run at all, so their queries never produce
# a red that only means "not shipped".
HOLD = "HOLD"

# Specs may name their repo bare (`api-service`) when every repo lives under one
# GitHub owner. Set VERIFY_GH_OWNER to that owner to enable the shorthand; with it
# unset, a bare name can't be resolved and the spec's PR gate fails open (see
# `merge_state`). Writing `owner/name` in the spec always works.
DEFAULT_GH_OWNER = os.environ.get("VERIFY_GH_OWNER", "")


# --------------------------------------------------------------------------- #
# Spec loading + validation                                                   #
# --------------------------------------------------------------------------- #


class SpecError(Exception):
    """A spec file is malformed. Raised before any network access."""


def _require(check: dict, key: str, where: str):
    if key not in check or check[key] in (None, ""):
        raise SpecError(f"{where}: missing required field '{key}'")
    return check[key]


def validate_check(check: dict, where: str) -> dict:
    """Validate one check and return it normalized. No network."""
    name = _require(check, "name", where)
    source = _require(check, "source", where)
    if source in RETIRED_SOURCES:
        raise SpecError(
            f"{where} ({name}): source '{source}' was removed — "
            f"{RETIRED_SOURCES[source]}. Write the check as source = \"telemetry\" "
            f"with a SQL count; `{TELEMETRY_CMD} --help` lists the tables."
        )
    if source not in CONNECTORS:
        raise SpecError(
            f"{where} ({name}): source must be one of {sorted(CONNECTORS)}"
        )
    _require(check, "query", where)
    if "window" in check:
        # A window outside the statement would read as the check's scope while
        # the SQL's own time bound decides what is actually counted.
        raise SpecError(
            f"{where} ({name}): 'window' is not a field — put the time bound in "
            "the query itself, where it also keeps the statement fast"
        )
    op = _require(check, "op", where)
    if op not in OPS:
        raise SpecError(f"{where} ({name}): op '{op}' not one of {sorted(OPS)}")
    if "value" not in check:
        raise SpecError(f"{where} ({name}): missing required field 'value'")
    if not isinstance(check["value"], (int, float)):
        raise SpecError(f"{where} ({name}): 'value' must be a number")
    metric = check.get("metric", "value")
    if metric not in ("value", "rows"):
        raise SpecError(f"{where} ({name}): metric must be 'value' or 'rows'")
    level = check.get("level", "alert")
    if level not in LEVELS:
        raise SpecError(f"{where} ({name}): level must be one of {list(LEVELS)}")
    return {
        "name": name,
        "source": source,
        "query": check["query"],
        "metric": metric,
        "op": op,
        "value": float(check["value"]),
        "healthy": check.get("healthy", ""),
        "level": level,
    }


def load_spec_file(path: str) -> list[dict]:
    """Parse and validate a single spec file into a list of checks.

    The historical entry point: returns only checks, ignoring any `[spec]`
    header. `verify-spec` still uses this, so its behavior is unchanged for
    every spec written before the header existed.
    """
    return load_spec(path).checks


def _read_toml(path: str) -> dict:
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        raise SpecError(f"spec not found: {path}")
    except tomllib.TOMLDecodeError as exc:
        raise SpecError(f"{path}: invalid TOML — {exc}")


@dataclass
class Spec:
    """One spec file: its `[spec]` metadata plus its validated checks."""

    path: str
    name: str                      # file stem; the board's stable identity
    title: str
    started: dt.datetime           # full timestamp — the ladder is in hours
    pr: int | None
    repo: str
    checks: list[dict] = field(default_factory=list)
    mtime: float = 0.0             # so an edit can force a re-check

    @property
    def age(self) -> dt.timedelta:
        """Never negative.

        A future-dated `started` is a real thing that happens: a naive timestamp
        written as UTC by an author in a UTC-negative zone reads as the future
        here. Clamping keeps the ladder and the day counter sane instead of
        showing `d-1` and treating the spec as not-yet-begun.
        """
        return max(_now_local() - self.started, dt.timedelta(0))

    @property
    def started_date(self) -> dt.date:
        """For display; the board shows whole days, not timestamps."""
        return self.started.date()

    @property
    def gh_repo(self) -> str | None:
        """`owner/name` for `gh --repo`, or None when it can't be determined.

        Accepts either form in the header: `someorg/thing` is passed through, and
        a bare `api-service` picks up `VERIFY_GH_OWNER`. None when the spec names
        no repo, or names a bare one with no owner configured — callers treat that
        as "unknown", which fails open rather than holding the spec forever.
        """
        if not self.repo:
            return None
        if "/" in self.repo:
            return self.repo
        return f"{DEFAULT_GH_OWNER}/{self.repo}" if DEFAULT_GH_OWNER else None


def load_spec(path: str) -> Spec:
    """Parse a spec file into metadata plus checks. No network."""
    data = _read_toml(path)
    raw_checks = data.get("checks")
    if not raw_checks:
        raise SpecError(f"{path}: no [[checks]] defined")

    stem = os.path.splitext(os.path.basename(path))[0]
    checks = []
    for i, check in enumerate(raw_checks):
        normalized = validate_check(check, where=f"{path} [[checks]] #{i + 1}")
        # Namespace the display name by file so a merged board stays readable.
        normalized["label"] = f"{stem}:{normalized['name']}"
        checks.append(normalized)

    meta = data.get("spec") or {}
    return Spec(
        path=path,
        name=stem,
        title=str(meta.get("title") or stem),
        started=_coerce_started(meta.get("started"), path),
        pr=_coerce_pr(meta.get("pr"), path),
        repo=str(meta.get("repo") or ""),
        checks=checks,
        mtime=os.path.getmtime(path),
    )


def _coerce_started(value, path: str) -> dt.datetime:
    """Resolve `[spec].started` to a timestamp, falling back to the file's mtime.

    The ladder's first tier is six hours, so this has to carry a time of day. A
    bare `2026-08-03` is accepted and read as midnight, which means a spec
    hand-dated today may land straight in the hourly tier — `ship` writes a full
    timestamp for exactly that reason.

    The mtime fallback is what lets an unmigrated worktree spec work if one gets
    copied into `active/`: there's always a real timestamp, so a months-old spec
    is scheduled by when it was last touched instead of looking brand new and
    being polled every 20 minutes forever.
    """
    if isinstance(value, dt.datetime):
        # tomllib hands back an aware datetime for offset timestamps; the rest
        # of the module works in local naive time, so normalize.
        return value.astimezone().replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, dt.date):
        return dt.datetime.combine(value, dt.time.min)
    if isinstance(value, str) and value.strip():
        try:
            return _coerce_started(dt.datetime.fromisoformat(value.strip()), path)
        except ValueError:
            raise SpecError(
                f"{path}: [spec].started '{value}' is not an ISO date or timestamp"
            )
    if value is not None:
        raise SpecError(
            f"{path}: [spec].started must be a date or timestamp, "
            f"got {type(value).__name__}"
        )
    return dt.datetime.fromtimestamp(os.path.getmtime(path))


def _coerce_pr(value, path: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise SpecError(f"{path}: [spec].pr '{value}' is not a number")


def discover_specs(arg: str | None) -> list[dict]:
    """Resolve a file arg, or scan the current worktree's `.scratch/verify/`.

    `verify-spec`'s discovery, unchanged — the worktree default is deliberate,
    since most existing specs still live beside the branch that created them.
    """
    if arg:
        return load_spec_file(arg)
    if not os.path.isdir(WORKTREE_VERIFY_DIR):
        raise SpecError(
            f"no spec given and {WORKTREE_VERIFY_DIR}/ not found "
            "(run from the worktree root, or pass a spec path)"
        )
    files = _toml_files(WORKTREE_VERIFY_DIR)
    if not files:
        raise SpecError(f"{WORKTREE_VERIFY_DIR}/ has no .toml specs")
    checks = []
    for path in files:
        checks.extend(load_spec_file(path))
    return checks


@dataclass
class ActiveScan:
    """One pass over `active/`: what loaded, and what didn't.

    Separated because a single unparseable file must not stop the other specs
    from updating — a half-saved TOML would otherwise freeze every edit on the
    board until it was fixed.
    """

    specs: list[Spec] = field(default_factory=list)
    broken: dict[str, str] = field(default_factory=dict)   # spec name -> error


def discover_active() -> ActiveScan:
    """Load every spec in the shared `active/` store, sorted by name.

    Re-read on every board cycle rather than cached, so dropping a file in is
    the whole add path — nothing to restart. Files that fail to parse are
    reported rather than raised, so one bad file costs only itself.
    """
    scan = ActiveScan()
    if not os.path.isdir(ACTIVE_DIR):
        return scan
    for path in _toml_files(ACTIVE_DIR):
        stem = os.path.splitext(os.path.basename(path))[0]
        try:
            scan.specs.append(load_spec(path))
        except SpecError as exc:
            scan.broken[stem] = str(exc)
    return scan


def _toml_files(directory: str) -> list[str]:
    return sorted(
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if f.endswith(".toml")
    )


def archive_spec(spec: Spec) -> str:
    """Move a spec out of `active/`. Returns the new path."""
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    target = os.path.join(ARCHIVE_DIR, os.path.basename(spec.path))
    os.replace(spec.path, target)
    return target


# --------------------------------------------------------------------------- #
# Scheduling                                                                   #
# --------------------------------------------------------------------------- #

# A spec matters most on the day it ships and less every day after, so the
# check interval widens with its age instead of burning prod queries forever.
BACKOFF_LADDER = (
    (dt.timedelta(hours=6), 20 * 60),      # first 6h: every 20 minutes
    (dt.timedelta(hours=72), 60 * 60),     # to 3 days: hourly
)
BACKOFF_FLOOR = 24 * 60 * 60               # after that: daily


def interval_for(spec: Spec) -> int:
    """Seconds between checks for this spec, from its age."""
    age = spec.age
    for threshold, seconds in BACKOFF_LADDER:
        if age < threshold:
            return seconds
    return BACKOFF_FLOOR


def _now_local() -> dt.datetime:
    return dt.datetime.now()


# --------------------------------------------------------------------------- #
# Merge state                                                                  #
# --------------------------------------------------------------------------- #

# How often to re-ask about a PR that hasn't merged. A PR lookup is ~0.5s, so
# this is cheap; the interval exists to keep a 20-spec board from making 20 API
# calls every UI tick.
MERGE_RECHECK_SECONDS = 5 * 60


def merge_state(spec: Spec) -> str | None:
    """`MERGED` / `OPEN` / `CLOSED`, or None when it can't be determined.

    Asks Gitea first, then GitHub: a repo migrated to Gitea keeps its PR numbers
    and may leave an archived GitHub copy, so the Gitea answer wins. A repo
    only on GitHub gets a 404 from Gitea and falls through.

    None means "no idea", and callers must treat that as runnable. Failing open
    is deliberate: an expired token or a missing `pr` field should not
    silently disable verification for every spec on the board.
    """
    if spec.pr is None or spec.gh_repo is None:
        return None
    return (_gitea_merge_state(spec.gh_repo, spec.pr)
            or _github_merge_state(spec.gh_repo, spec.pr))


def _gitea_merge_state(repo: str, pr: int) -> str | None:
    try:
        proc = subprocess.run(
            ["tea", "api", f"repos/{repo}/pulls/{pr}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        return None
    if proc.returncode != 0:
        return None
    try:
        return gitea_pr_state(json.loads(proc.stdout))
    except ValueError:
        return None


def gitea_pr_state(payload: object) -> str | None:
    """Map a Gitea pull-request payload onto the GitHub state names.

    `tea api` exits 0 on a 404 and returns `{"message": "not found"}`, so a
    payload without `state` is "unknown", not an error.
    """
    if not isinstance(payload, dict) or "state" not in payload:
        return None
    if payload.get("merged"):
        return "MERGED"
    return {"open": "OPEN", "closed": "CLOSED"}.get(payload["state"])


def _github_merge_state(repo: str, pr: int) -> str | None:
    try:
        proc = subprocess.run(
            ["gh", "pr", "view", str(pr), "--repo", repo,
             "--json", "state", "-q", ".state"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        return None
    if proc.returncode != 0:
        return None
    state = proc.stdout.strip().upper()
    return state if state in ("MERGED", "OPEN", "CLOSED") else None


def should_run(state: str | None) -> bool:
    """Whether a spec with this merge state is worth checking.

    Only a definitively unmerged PR blocks. `MERGED` runs, and so does None —
    see `merge_state` on failing open.
    """
    return state not in ("OPEN", "CLOSED")


def hold_reason(state: str | None) -> str:
    """Why a held spec is held, for the board's line."""
    if state == "OPEN":
        return "PR not merged"
    if state == "CLOSED":
        return "PR closed unmerged — archive?"
    return ""


# --------------------------------------------------------------------------- #
# Board state (survives a restart)                                             #
# --------------------------------------------------------------------------- #


def load_state() -> dict:
    """Read `state.json`, tolerating absence or corruption.

    A damaged state file must not stop the board from starting; the worst case
    is that every spec looks due and gets checked once on the next cycle.
    """
    try:
        with open(STATE_PATH, "rb") as fh:
            state = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"specs": {}}
    if not isinstance(state, dict) or not isinstance(state.get("specs"), dict):
        return {"specs": {}}
    return state


def save_state(state: dict) -> None:
    """Write `state.json` atomically, so a kill mid-write can't corrupt it."""
    os.makedirs(VERIFY_HOME, exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
    os.replace(tmp, STATE_PATH)


# --------------------------------------------------------------------------- #
# Credentials (Keychain)                                                       #
# --------------------------------------------------------------------------- #


class CredError(Exception):
    """A required credential is missing from the Keychain."""


_cred_cache: dict[str, str | None] = {}


def keychain_get(service: str) -> str | None:
    """Read a Keychain secret, memoized for the process so a multi-check run
    (or a long watch) triggers at most one Keychain prompt per item, not one
    per check."""
    if service in _cred_cache:
        return _cred_cache[service]
    proc = subprocess.run(
        ["security", "find-generic-password", "-s", service, "-a", USER, "-w"],
        capture_output=True,
        text=True,
    )
    value = proc.stdout.strip() if proc.returncode == 0 else None
    _cred_cache[service] = value
    return value


def keychain_set(service: str, secret: str, binary: str | None = None):
    """Store a secret, granting `binary` (the calling front end) access.

    The caller passes its own path: `-T` authorizes one executable, and this
    module is imported by two of them, so `__file__` here would authorize
    neither.
    """
    authorized = os.path.realpath(binary or sys.argv[0])
    subprocess.run(
        ["security", "add-generic-password", "-U", "-a", USER, "-s", service,
         "-w", secret, "-T", authorized],
        check=True,
    )
    _cred_cache.pop(service, None)


def require_cred(service: str, human: str) -> str:
    secret = keychain_get(service)
    if not secret:
        raise CredError(
            f"missing credential '{service}' ({human}). Run `verify-spec setup`."
        )
    return secret


# --------------------------------------------------------------------------- #
# Connectors                                                                   #
# --------------------------------------------------------------------------- #


def run_postgres(check: dict) -> tuple[float, str]:
    """Run a readonly SQL query; return (metric, raw output for display)."""
    dsn = require_cred(KC_PG_DSN, "prod readonly Postgres DSN")
    proc = subprocess.run(
        ["psql", dsn, "-tAc", check["query"]],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "psql failed")
    rows = [line for line in proc.stdout.splitlines() if line.strip() != ""]
    raw = proc.stdout.strip()
    if check["metric"] == "rows":
        return float(len(rows)), raw
    if not rows:
        raise RuntimeError("query returned no rows but metric is 'value'")
    first_cell = rows[0].split("|")[0].strip()
    try:
        return float(first_cell), raw
    except ValueError:
        raise RuntimeError(f"first cell '{first_cell}' is not numeric")


def run_telemetry(check: dict) -> tuple[float, str]:
    """Run one SQL statement through the telemetry command; return (metric, raw).

    The command is the one an author runs a control through, so a check and its
    control read one store by construction. That is why this shells out rather
    than calling a backend itself. An earlier trace connector never returned a
    count worth acting on, and two lessons from it generalize past the vendor it
    ran against:

      * A span visible in a trace UI is not necessarily a countable one. The UI
        and a query API can read different stores.
      * Query tooling can search a different store than the runner does and
        hand back confident non-zero counts for data the runner cannot see.
        Controls measured that way ship checks that read zero forever.

    The statement goes in on stdin, so no quoting has to survive a shell.
    """
    try:
        proc = subprocess.run(
            [TELEMETRY_CMD, "query", "--json", "--limit", "500"],
            input=check["query"],
            capture_output=True,
            text=True,
            timeout=90,
        )
    except FileNotFoundError:
        raise RuntimeError(
            f"`{TELEMETRY_CMD}` is not on PATH — see README.md, 'The telemetry command'"
        )
    if proc.returncode != 0:
        lines = proc.stderr.strip().splitlines()
        raise RuntimeError(lines[-1] if lines else f"{TELEMETRY_CMD} exited {proc.returncode}")
    try:
        result = json.loads(proc.stdout)
        columns, rows = result["columns"], result["rows"]
    except (ValueError, KeyError, TypeError):
        raise RuntimeError(f"{TELEMETRY_CMD} printed something other than its JSON result")
    raw = "\n".join(
        " ".join(f"{c}={v}" for c, v in zip(columns, row)) for row in rows[:8]
    ) or "(no rows)"
    if check["metric"] == "rows":
        if result.get("truncated"):
            raise RuntimeError(
                "more rows matched than the command returns, so the count would be "
                "a floor — count them in the query and use metric = \"value\""
            )
        return float(len(rows)), raw
    if not rows or not rows[0]:
        raise RuntimeError("query returned no rows but metric is 'value'")
    first_cell = rows[0][0]
    try:
        return float(first_cell), raw
    except (TypeError, ValueError):
        raise RuntimeError(f"first cell '{first_cell}' is not numeric")


CONNECTORS = {
    "postgres": run_postgres,
    "telemetry": run_telemetry,
}


# --------------------------------------------------------------------------- #
# Evaluation                                                                   #
# --------------------------------------------------------------------------- #


def evaluate(check: dict) -> dict:
    """Run one check and return {state, observed, detail, raw, query}."""
    try:
        observed, raw = CONNECTORS[check["source"]](check)
    except (RuntimeError, CredError, subprocess.TimeoutExpired) as exc:
        return {"state": ERROR, "observed": None, "detail": str(exc),
                "raw": "", "query": check["query"]}
    passed = OPS[check["op"]](observed, check["value"])
    fmt = f"{check['metric']}={num(observed)} {check['op']} {num(check['value'])}"
    if passed:
        state = PASS
    else:
        state = WARN if check.get("level", "alert") == "warn" else FAIL
    return {"state": state, "observed": observed,
            "detail": fmt, "raw": raw, "query": check["query"]}


def evaluate_spec(spec: Spec) -> dict[str, dict]:
    """Run every check in a spec. Returns results keyed by check label."""
    return {check["label"]: evaluate(check) for check in spec.checks}


def summarize(results: dict[str, dict]) -> tuple[int, int]:
    """(passing, total) — the board's headline number for one spec.

    A WARN is not a pass. The count says how many checks are clean; the spec's
    colour says how alarmed to be about the rest.
    """
    return sum(1 for r in results.values() if r["state"] == PASS), len(results)


def worst(states) -> str:
    """The most alarming state present. ERROR > FAIL > WARN > PASS."""
    for candidate in (ERROR, FAIL, WARN):
        if candidate in states:
            return candidate
    return PASS


def num(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:g}"


# --------------------------------------------------------------------------- #
# Notifications                                                                #
# --------------------------------------------------------------------------- #


def notify(title: str, message: str):
    """macOS banner + terminal bell. Best-effort; never raises."""
    sys.stderr.write("\a")
    sys.stderr.flush()
    safe = message.replace('"', "'")
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{safe}" with title "{title}"'],
            capture_output=True,
            timeout=10,
        )
    except Exception:
        pass


def state_changes(prev: dict[str, str], results: dict) -> list[str]:
    """Human messages for checks whose state changed.

    First tick (empty prev): announce anything already broken, stay quiet on
    healthy checks so a clean start is silent.
    """
    messages = []
    for label, res in results.items():
        was = prev.get(label)
        now = res["state"]
        if was is None:
            if now != PASS:
                messages.append(f"{label}: {now.strip()}")
        elif now != was:
            messages.append(f"{label}: {was.strip()} -> {now.strip()}")
    return messages


# --------------------------------------------------------------------------- #
# Schema (the tool owns the spec shape)                                        #
# --------------------------------------------------------------------------- #

SCHEMA_TEXT = """
verify-spec TOML schema
=======================
A spec is a TOML file with one or more [[checks]]. Each check runs a prod query
and asserts a numeric threshold.

Write new specs to $VERIFY_HOME/active/<name>.toml (default ~/verify/active) —
`verify-board` polls that directory, so dropping the file in is the whole add
path. (`verify-spec` itself still defaults to the current worktree's
.scratch/verify/ for older specs that live beside their branch.)

[spec]                                 # optional header, used by the board
title   = "Invoice reminder backfill"
started = 2026-08-03T14:30:00-04:00   # drives the backoff; defaults to file mtime
pr      = 9600                        # optional; unmerged PR = spec is held
repo    = "owner/api-service"          # optional; owner/name, or a bare name
                                       # when VERIFY_GH_OWNER is set

# `started`: write an offset-aware timestamp (the -04:00 above). A bare date
# reads as midnight, so a spec dated today can skip the 20-minute tier; a naive
# timestamp is read as LOCAL time, so writing one in UTC dates the spec into the
# future. `date -Iseconds` produces the right thing.
#
# A spec whose `pr` hasn't merged is held: the board shows it dimmed and runs no
# checks, because nothing is deployed yet and a red would only mean "not shipped".

[[checks]]
name    = "no orphaned reminders"      # required, short label
source  = "postgres"                   # required: postgres | telemetry
query   = '''                          # required
  select count(*) from reminders
  where invoice_id is null and created_at > now() - interval '2 days'
'''
metric  = "value"   # "value" = the first row's first cell;
                    # "rows" = the number of rows returned
op      = "eq"      # eq | ne | lt | lte | gt | gte
value   = 0         # required numeric threshold: assert  metric <op> value
level   = "alert"   # "alert" (default) = something bad was OBSERVED -> red
                    # "warn" = nothing was observed, which may mean nothing -> yellow
healthy = "zero orphaned rows means the backfill ran"   # optional note

Choosing `level` — one absolute rule: **red is only for a positive failure.
Absence of evidence is always `warn`.** The test that settles it: ask what the
check does the instant the PR deploys, before anything has had a chance to happen.
If it fails then, it is `warn`.

The op usually decides it outright. `eq 0` / `lt <n>` on an error or orphan count
is `alert` — failing means the query FOUND something, which is proof, and zero
passes so it cannot fire early. `gt 0` / `gte <volume>` is `warn` — failing means
it found NOTHING, which at deploy time is expected, and on a low-traffic feature
stays true for days with everything working. "A row that should exist and doesn't"
is absence of evidence too, not an invariant.

So a new feature's "did it fire" check is `warn` even though it is the one you
care most about. A red on this board must mean "stop and look", never "it hasn't
fired yet" — that is what keeps the board worth reading. Promote a `gt 0` check to
`alert` only after you have watched it read non-zero.

The code default is still `alert` for back-compatibility with specs written before
this rule, so set `level` explicitly on every check rather than relying on it.

[[checks]]
name    = "no reminder send failures"
source  = "telemetry"                  # logs and spans, as SQL
query   = '''
  SELECT count() AS n FROM otel_logs
  WHERE Timestamp >= now() - INTERVAL 30 MINUTE
    AND ServiceName = 'reminder-worker'
    AND ResourceAttributes['deployment.environment.name'] = 'production'
    AND SeverityText = 'ERROR'
    AND Body ILIKE '%reminder send failed%'
'''
metric  = "value"
op      = "lt"
value   = 5
level   = "alert"
healthy = "fewer than 5 send failures in 30m"

That example is written against the OpenTelemetry ClickHouse exporter's default
schema. Your store's tables, columns and dialect come from `telemetry-query
--help` — never from this example or from another system's schema.

Telemetry notes:
  * `source = "telemetry"` runs the query through the telemetry command
    (`telemetry-query`, or whatever VERIFY_TELEMETRY_CMD names). Run the
    check's control through that same command, so the check and its control
    read one store. A count from a UI or another query tool is not a control:
    it can come from a store the command never reads.
  * The query is one statement whose first cell is the metric. Alias it
    (`count() AS n`).
  * Bound every statement on the store's time column and on whatever leads
    its sort key, usually the service; `--help` says which. An unbounded count
    scans all of retention and times out, and a timeout is ERR: unverified,
    never a pass.
  * The time bound lives in the statement. There is no `window` field.
  * Always scope by environment. Without it a check silently counts dev and
    staging traffic.
  * Logs and spans are both queryable, so a span name or span attribute is as
    good an address as a log line, under the same control.
  * `metric = "rows"` counts returned rows, and the command returns a bounded
    number of them. When more matched, the check errors rather than report a
    floor; count in the query instead.
  * **Prove an error gate can go non-zero before trusting its green.** Any
    `lt`/`lte` check observing 0 passes identically whether the system is
    healthy or the query is simply wrong — a typo'd message string, a renamed
    logger category, a wrong service. Run the positive form of the query (drop
    the error predicate, widen the time bound, or point at a period you know
    had failures) and confirm it returns something.
  * There is no browser source. A frontend-only change has no automatable
    check here; say so in the PR. The backend half of a frontend change — the
    API call it makes — is checkable as spans.

Check interval, per spec, from `started`: under 6h old -> every 20 minutes;
under 3 days -> hourly; after that -> daily.

Postgres creds come from the Keychain DSN (set once via `verify-spec setup`).
The telemetry command handles its own login. The author never needs the creds.
"""
