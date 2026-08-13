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
import urllib.error
import urllib.request
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
KC_DD_API_KEY = "verify-spec-dd-api-key"
KC_DD_APP_KEY = "verify-spec-dd-app-key"
KC_DD_SITE = "verify-spec-dd-site"
DEFAULT_DD_SITE = "datadoghq.com"

# Facets that exist on APM spans and not on log or RUM events. This is Datadog's
# data model, not anyone's configuration: a log query using one of these matches
# nothing and counts zero — which reads as "the feature never ran" on a `gt` check
# and, worse, as a clean pass on an `lt` error gate. Caught at validate time
# because there is no way to tell the two apart from the result: both are the
# integer 0.
#
# There is no APM connector here (see CONNECTORS below), so a span-addressed check
# has to be rewritten against logs/SQL — or you add a connector and prove it.
#
# The span *tag* half of the mistake stays unlintable — `@my.span.tag:true` is
# indistinguishable from a log attribute. The span-name selector is the tell, and
# in practice it always travels with the tag.
APM_ONLY_FACETS = (
    "resource_name:",
    "operation_name:",
    "span_name:",
    "span_type:",
    "span.kind:",
)


def apm_facets_in(query: str) -> list[str]:
    """APM-only facets present in a query. Substring match on `facet:` is enough —
    these names have no log-side homonym, so there is nothing to disambiguate."""
    lowered = query.lower()
    return [f for f in APM_ONLY_FACETS if f in lowered]

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
    if source == "spans":
        raise SpecError(
            f"{where} ({name}): there is no APM connector. One was tried against "
            "/api/v2/spans/analytics/aggregate and removed on 2026-08-06 because it "
            "could not be made to return a trustworthy count — see CONNECTORS in "
            "verify_core.py. Rewrite the check against logs (\"datadog\") or SQL "
            '("postgres"), or say in the PR that this change has no automatable '
            "check. If APM aggregates do work against your account, add a connector "
            "and prove one query end to end through this code path first."
        )
    if source not in CONNECTORS:
        raise SpecError(
            f"{where} ({name}): source must be one of {sorted(CONNECTORS)}"
        )
    _require(check, "query", where)
    if source in ("datadog", "rum"):
        apm = apm_facets_in(check["query"])
        if apm:
            raise SpecError(
                f"{where} ({name}): query uses the APM-only facet "
                f"{', '.join(apm)} but source '{source}' queries the "
                f"{'Logs' if source == 'datadog' else 'RUM'} API. Span names do "
                "not exist on log or RUM events, so this counts zero forever — "
                "red on a 'gt' check, and a false green on an 'lt' one. There is "
                "no APM source to switch to. Find a log line or a SQL predicate "
                "instead, or state in the PR that the change is not verifiable "
                "this way."
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
        "window": check.get("window", "1h"),
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

# How often to re-ask about a PR that hasn't merged. A `gh pr view` is ~0.5s, so
# this is cheap; the interval exists to keep a 20-spec board from making 20 API
# calls every UI tick.
MERGE_RECHECK_SECONDS = 5 * 60


def merge_state(spec: Spec) -> str | None:
    """`MERGED` / `OPEN` / `CLOSED`, or None when it can't be determined.

    None means "no idea", and callers must treat that as runnable. Failing open
    is deliberate: an expired `gh` token or a missing `pr` field should not
    silently disable verification for every spec on the board.
    """
    if spec.pr is None or spec.gh_repo is None:
        return None
    proc = subprocess.run(
        ["gh", "pr", "view", str(spec.pr), "--repo", spec.gh_repo,
         "--json", "state", "-q", ".state"],
        capture_output=True,
        text=True,
        timeout=30,
    )
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


def _datadog_post(path: str, payload: dict, what: str) -> dict:
    """POST to a Datadog aggregate API and return the parsed body.

    Credentials, site resolution and error shaping live here so the three
    aggregate connectors can differ in payload and response shape — which they
    do — without each re-deriving the 403-scope hint.
    """
    api_key = require_cred(KC_DD_API_KEY, "Datadog API key")
    app_key = require_cred(KC_DD_APP_KEY, "Datadog application key")
    site = keychain_get(KC_DD_SITE) or DEFAULT_DD_SITE
    req = urllib.request.Request(
        f"https://api.{site}{path}",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "DD-API-KEY": api_key,
            "DD-APPLICATION-KEY": app_key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        hint = ""
        if exc.code == 403:
            hint = (f" — the application key may lack {what} read scope; "
                    "check its scopes in Datadog")
        raise RuntimeError(f"Datadog HTTP {exc.code}: {detail}{hint}")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Datadog request failed: {exc.reason}")


def _datadog_aggregate(check: dict, path: str, what: str) -> tuple[float, str]:
    """Count events matching a query over a window, via a Datadog aggregate API.

    Logs and RUM expose byte-identical contracts — `{compute:[{aggregation,type}],
    filter:{query,from,to}}` in, `data.buckets[].computes` out — so they share
    this. Verified against RUMQueryFilter/RUMCompute in Datadog's own API client:
    `from`/`to` are strings accepting relative values like `now-1h`, and `count`
    is a valid aggregation.

    (APM spans did not share this contract; that connector was removed — see
    CONNECTORS below.)
    """
    body = _datadog_post(
        path,
        {
            "compute": [{"aggregation": "count", "type": "total"}],
            "filter": {
                "query": check["query"],
                "from": f"now-{check['window']}",
                "to": "now",
            },
        },
        what,
    )
    buckets = body.get("data", {}).get("buckets", [])
    if not buckets:
        return 0.0, f"count=0 (no matching {what} buckets in window)"
    computes = buckets[0].get("computes", {})
    if not computes:
        return 0.0, "count=0"
    count = float(next(iter(computes.values())))
    return count, f"count={num(count)} over {check['window']}"


def run_datadog(check: dict) -> tuple[float, str]:
    """Count Datadog log events matching the query over the window."""
    return _datadog_aggregate(check, "/api/v2/logs/analytics/aggregate", "log")


def run_rum(check: dict) -> tuple[float, str]:
    """Count Datadog RUM events — browser errors, views, actions.

    CAVEAT worth knowing before trusting a zero: a RUM setup can ingest
    everything (`sessionSampleRate: 100`, no Limits) and still have *retention
    filters* decide what stays queryable. A check that returns zero may mean "no
    such error" or "not retained". Prove the query can be non-zero before relying
    on it as a regression gate.
    """
    return _datadog_aggregate(check, "/api/v2/rum/analytics/aggregate", "RUM")


# REMOVED 2026-08-06: `source = "spans"`, which hit
# /api/v2/spans/analytics/aggregate. It never returned a number worth acting on:
# seven checks written, three FAIL, four never run, and its only greens were `lt`
# gates counting zero on a query that matched nothing — including against addresses
# confirmed correct in the Trace Explorer.
#
# Whether that generalizes is unknown; the likely cause was APM retention filters
# keeping almost nothing in the indexed store the aggregate API reads, and that was
# never pinned down. Two things about the failure DO generalize, and they are the
# reason this is a comment rather than a fixed connector:
#
#   * A span visible in a trace explorer is not necessarily a countable one. The UI
#     and the aggregate API can read different stores.
#   * Query tooling can search a different store than your runner does. Datadog's
#     MCP tools search with historicalData=true and returned confident non-zero
#     counts for spans this runner could not see; two repairs of the same spec were
#     "controlled" against those numbers and both shipped broken. Measure a control
#     through the same path the runner uses, or you have not measured it.
#
# If you want APM: prove one query end to end through THIS code path, then add the
# connector. Do not reintroduce it on the strength of a count from a UI or an MCP
# tool.

CONNECTORS = {
    "postgres": run_postgres,
    "datadog": run_datadog,
    "rum": run_rum,
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
title   = "Onsite brief timeline sources"
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
name    = "no orphaned dial actions"   # required, short label
source  = "postgres"                   # required: postgres | datadog | rum
query   = '''                          # required
  select count(*) from call_actions where owner_id is null
'''
metric  = "value"   # "value" = first scalar cell (postgres) / event count
                    # (datadog); "rows" = number of returned rows (postgres)
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
name    = "no call_failed spike"
source  = "datadog"                    # backend logs
query   = "env:prod service:api-service-bg @evt.name:call_failed"
window  = "30m"     # datadog/rum only; relative window, default "1h"
metric  = "value"   # event count
op      = "lt"
value   = 5
healthy = "fewer than 5 failures in 30m"

[[checks]]
name    = "no new browser errors"
source  = "rum"                        # frontend, Datadog RUM
query   = "@type:error service:webapp env:production"
window  = "2h"
metric  = "value"
op      = "lt"
value   = 5
healthy = "browser error rate is at its usual floor"

Datadog notes — two usable stores, and picking the wrong one fails silently:
  * `source = "datadog"` is the **Logs** API; `source = "rum"` is browser RUM.
    They do not share a query language, and a query aimed at the wrong one
    counts zero rather than erroring.
  * **There is no APM connector.** One existed until 2026-08-06 and was removed
    because it could not be made to return a trustworthy count — including
    against addresses confirmed correct in the Trace Explorer. `validate`
    rejects `source = "spans"`, and rejects an APM facet (`resource_name:`,
    `operation_name:`, …) under `"datadog"`/`"rum"` — that second rule is about
    Datadog's data model, not anyone's config: span facets do not exist on log
    or RUM events, so such a query counts zero forever.
  * So if a change's only evidence is a span name or a span tag, it is **not
    verifiable by this tool as shipped.** Find a log line or a SQL predicate, or
    say plainly in the PR that this change has no automatable check — do not
    ship one that cannot fail. (If APM aggregates work against your account,
    add a connector; see the note above CONNECTORS.) A span *tag* stays
    unlintable (`@my.span.tag:true` looks exactly like a log attribute), so
    that one is on the author.
  * Always scope by `env:` (`env:prod` or `env:production` depending on the
    emitter). Without it a check silently counts dev and staging traffic.
  * **Prove an error gate can go non-zero before trusting its green.** Any
    `lt`/`lte` check observing 0 passes identically whether the system is
    healthy or the query is simply wrong — a typo'd message string, a renamed
    `@SourceContext`, a wrong service. Run the positive form of the query (drop
    the `status:error`, widen the window, or point at a period you know had
    failures) and confirm it returns something.

RUM notes, for a browser frontend:
  * Scope by `service:<your-rum-service>` and `env:` — check what values your own
    RUM init actually sends; environment naming is per-setup.
  * `@type:error` is a JS error; `@type:view` a page view; `@type:action` a
    tracked user action. Scope every check by service AND env — RUM has no
    equivalent of a log index to keep environments apart.
  * RUM events carry `version:<commit sha>` when the init sets it, so a check can
    be scoped to the exact deploy containing the change: `version:a1b2c3d`.
  * If a separate error tracker (Sentry or similar) also receives frontend errors,
    remember this tool queries only RUM; when RUM shows nothing and you expected
    something, check there before concluding the frontend is clean.
  * At 100% sampling with no Limits, *retention filters* still decide what stays
    queryable. A zero can mean "no errors" or "not retained" — prove a query can
    return non-zero before trusting a zero as a gate.

Check interval, per spec, from `started`: under 6h old -> every 20 minutes;
under 3 days -> hourly; after that -> daily.

Postgres creds come from the Keychain DSN; Datadog from the Keychain API/app
keys (set once via `verify-spec setup`). The author never needs the creds.
"""
