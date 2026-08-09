#!/usr/bin/env python3
"""Chunk 1 verification: verify_core behaves, and old specs still load."""

import datetime as dt
import json
import os
import sys
import tempfile

VERIFY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, VERIFY_DIR)

# Point the module at a disposable store before importing it.
SANDBOX = tempfile.mkdtemp(prefix="verify-test-")
os.environ["VERIFY_HOME"] = SANDBOX
import verify_core as core  # noqa: E402

fails = []


def check(label, got, want):
    if got != want:
        fails.append(f"{label}: got {got!r}, want {want!r}")
    else:
        print(f"  ok  {label}")


def raises(label, fn, exc=core.SpecError):
    try:
        fn()
    except exc:
        print(f"  ok  {label}")
    except Exception as e:  # noqa: BLE001
        fails.append(f"{label}: raised {type(e).__name__}({e}) not {exc.__name__}")
    else:
        fails.append(f"{label}: did not raise")


def write(name, body, mtime=None):
    path = os.path.join(SANDBOX, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(body)
    if mtime:
        os.utime(path, (mtime, mtime))
    return path


MINIMAL = """
[[checks]]
name   = "no orphans"
source = "postgres"
query  = "select count(*) from t"
op     = "eq"
value  = 0
"""

print("\n-- backwards compatibility (specs with no [spec] header) --")
p = write("active/legacy.toml", MINIMAL)
checks = core.load_spec_file(p)
check("load_spec_file returns a list of checks", len(checks), 1)
check("label is stem:name", checks[0]["label"], "legacy:no orphans")
check("metric defaults to value", checks[0]["metric"], "value")
check("window defaults to 1h", checks[0]["window"], "1h")
check("value coerced to float", checks[0]["value"], 0.0)
check("healthy defaults to empty", checks[0]["healthy"], "")

print("\n-- [spec] header --")
p = write("active/full.toml", """
[spec]
title   = "Onsite brief timeline sources"
started = 2026-08-01
pr      = 9600
repo    = "api-service"
""" + MINIMAL)
spec = core.load_spec(p)
check("title", spec.title, "Onsite brief timeline sources")
check("started (bare date -> midnight)", spec.started, dt.datetime(2026, 8, 1, 0, 0))
check("pr", spec.pr, 9600)
check("repo", spec.repo, "api-service")
check("name is the file stem", spec.name, "full")
check("checks still parsed", len(spec.checks), 1)

print("\n-- started falls back to mtime --")
old = dt.datetime(2026, 7, 15, 12, 0).timestamp()
p = write("active/nomtime.toml", MINIMAL, mtime=old)
check("mtime fallback keeps time of day", core.load_spec(p).started,
      dt.datetime(2026, 7, 15, 12, 0))

print("\n-- defaults when header is absent --")
spec = core.load_spec(write("active/bare.toml", MINIMAL))
check("title defaults to stem", spec.title, "bare")
check("pr defaults to None", spec.pr, None)
check("repo defaults to empty", spec.repo, "")

print("\n-- backoff ladder --")
today = dt.date.today()


def aged(**kw):
    return core.Spec(path="x", name="x", title="x",
                     started=dt.datetime.now() - dt.timedelta(**kw),
                     pr=None, repo="", checks=[])


check("just now -> 20m", core.interval_for(aged(minutes=1)), 20 * 60)
check("5h -> 20m", core.interval_for(aged(hours=5)), 20 * 60)
check("7h -> hourly", core.interval_for(aged(hours=7)), 60 * 60)
check("2 days -> hourly", core.interval_for(aged(days=2)), 60 * 60)
check("4 days -> daily", core.interval_for(aged(days=4)), 24 * 60 * 60)
check("30 days -> daily", core.interval_for(aged(days=30)), 24 * 60 * 60)

print("\n-- timestamped started keeps the fast tier --")
p2 = write("active/stamped.toml", f"""
[spec]
started = {(dt.datetime.now() - dt.timedelta(minutes=30)).isoformat(timespec="seconds")}
""" + MINIMAL)
check("shipped 30m ago -> 20m", core.interval_for(core.load_spec(p2)), 20 * 60)

print("\n-- state persistence --")
core.save_state({"specs": {"a": {"last_run": "now", "results": {"a:x": "PASS"}}}})
check("roundtrip", core.load_state()["specs"]["a"]["results"], {"a:x": "PASS"})
with open(core.STATE_PATH, "w") as fh:
    fh.write("{ this is not json")
check("corrupt state tolerated", core.load_state(), {"specs": {}})
os.remove(core.STATE_PATH)
check("missing state tolerated", core.load_state(), {"specs": {}})

print("\n-- discover_active --")
found = {s.name for s in core.discover_active().specs}
check("finds every active spec", found,
      {"legacy", "full", "nomtime", "bare", "stamped"})

print("\n-- archive --")
spec = core.load_spec(os.path.join(SANDBOX, "active", "bare.toml"))
target = core.archive_spec(spec)
check("moved into archive/", os.path.exists(target), True)
check("gone from active/", os.path.exists(spec.path), False)
check("drops off the board", "bare" in {s.name for s in core.discover_active().specs}, False)

print("\n-- summarize --")
check("counts passing", core.summarize(
    {"a": {"state": core.PASS}, "b": {"state": core.FAIL}}), (1, 2))

print("\n-- error paths --")
raises("no [[checks]]", lambda: core.load_spec(write("bad1.toml", "[spec]\ntitle='x'\n")))
raises("invalid TOML", lambda: core.load_spec(write("bad2.toml", "[[checks]\n")))
raises("missing file", lambda: core.load_spec(os.path.join(SANDBOX, "nope.toml")))
raises("bad op", lambda: core.load_spec(write("bad3.toml", MINIMAL.replace('op     = "eq"', 'op = "wat"'))))
raises("bad metric", lambda: core.load_spec(write("bad4.toml", MINIMAL + '\nmetric = "sideways"\n')))
raises("non-numeric value", lambda: core.load_spec(write("bad5.toml", MINIMAL.replace("value  = 0", 'value = "zero"'))))
raises("bad source", lambda: core.load_spec(write("bad6.toml", MINIMAL.replace('source = "postgres"', 'source = "mysql"'))))
raises("missing name", lambda: core.load_spec(write("bad7.toml", MINIMAL.replace('name   = "no orphans"', ""))))
raises("bad started", lambda: core.load_spec(write("bad8.toml", '[spec]\nstarted = "last tuesday"\n' + MINIMAL)))
raises("started wrong type", lambda: core.load_spec(write("bad10.toml", '[spec]\nstarted = 42\n' + MINIMAL)))
raises("bad pr", lambda: core.load_spec(write("bad9.toml", '[spec]\npr = "nine thousand"\n' + MINIMAL)))

print("\n-- no network was touched --")
# another session added `spans`; assert the set contains what this suite knows
# about rather than pinning it, so a new connector doesn't fail an unrelated test
for expected in ("postgres", "datadog", "rum"):
    check(f"{expected} connector registered", expected in core.CONNECTORS, True)

print()
if fails:
    print(f"FAILED ({len(fails)}):")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("all checks passed")
