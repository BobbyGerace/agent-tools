#!/usr/bin/env python3
"""Chunk 2 verification: the board's state machine and rendering, no prod."""

import datetime as dt
import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import time

SANDBOX = tempfile.mkdtemp(prefix="verify-board-test-")
os.makedirs(os.path.join(SANDBOX, "active"))
os.environ["VERIFY_HOME"] = SANDBOX
VERIFY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, VERIFY_DIR)

spec_ = importlib.util.spec_from_loader(
    "verify_board",
    importlib.machinery.SourceFileLoader(
        "verify_board", os.path.join(VERIFY_DIR, "verify-board")),
)
vb = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(vb)
core = vb.core

fails = []
notifications = []


def check(label, got, want):
    if got != want:
        fails.append(f"{label}: got {got!r}, want {want!r}")
    else:
        print(f"  ok  {label}")


def truthy(label, got):
    check(label, bool(got), True)


# --- stub everything that leaves the process --------------------------------- #

VERDICTS = {}          # spec name -> list of states to hand back


def fake_evaluate_spec(spec):
    states = VERDICTS.get(spec.name, [core.PASS] * len(spec.checks))
    return {
        c["label"]: {"state": states[i], "detail": f"stub {states[i].strip()}",
                     "raw": "row1\nrow2", "query": "select 1"}
        for i, c in enumerate(spec.checks)
    }


core.evaluate_spec = fake_evaluate_spec
core.notify = lambda title, msg: notifications.append((title, msg))
vb.copy_to_clipboard = lambda text: True

MINIMAL = """
[[checks]]
name   = "check one"
source = "postgres"
query  = "select 1"
op     = "eq"
value  = 0
healthy = "zero is good"

[[checks]]
name   = "check two"
source = "datadog"
query  = "service:x"
op     = "gt"
value  = 0
healthy = "some events means it is alive"
"""


def write_spec(name, started=None, pr=None, repo="api-service"):
    header = ["[spec]", f'title   = "{name.replace("-", " ").capitalize()}"']
    if started:
        header.append(f"started = {started.isoformat(timespec='seconds')}")
    if pr:
        header.append(f"pr      = {pr}")
    header.append(f'repo    = "{repo}"')
    path = os.path.join(SANDBOX, "active", f"{name}.toml")
    with open(path, "w") as fh:
        fh.write("\n".join(header) + "\n" + MINIMAL)
    return path


now = dt.datetime.now()

print("\n-- rescan picks up files --")
write_spec("alpha", started=now - dt.timedelta(minutes=10), pr=100)
write_spec("beta", started=now - dt.timedelta(days=5), pr=200, repo="ops-tool")
board = vb.Board()
board.rescan()
check("found both", sorted(s.name for s in board.specs), ["alpha", "beta"])

print("\n-- new specs are due immediately --")
truthy("something is due", board.due() is not None)

print("\n-- checker evaluates and schedules by the ladder --")
VERDICTS["alpha"] = [core.PASS, core.PASS]
VERDICTS["beta"] = [core.PASS, core.FAIL]
worker = __import__("threading").Thread(target=vb.checker, args=(board,), daemon=True)
worker.start()
deadline = time.time() + 5
while time.time() < deadline and len(board.results) < 2:
    time.sleep(0.05)
board.stop.set()
worker.join(timeout=2)

check("both evaluated", sorted(board.results), ["alpha", "beta"])
check("alpha all passing", core.summarize(board.results["alpha"]), (2, 2))
check("beta one failing", core.summarize(board.results["beta"]), (1, 2))
check("alpha verdict", vb.spec_verdict(board.results["alpha"]), core.PASS)
check("beta verdict", vb.spec_verdict(board.results["beta"]), core.FAIL)

gap_alpha = (board.next_run["alpha"] - board.last_run["alpha"]).total_seconds()
gap_beta = (board.next_run["beta"] - board.last_run["beta"]).total_seconds()
check("fresh spec on 20m", round(gap_alpha), 20 * 60)
check("5-day-old spec on 24h", round(gap_beta), 24 * 60 * 60)

print("\n-- failures notify, clean starts stay quiet --")
titles = [t for t, _ in notifications]
truthy("beta notified", any("Beta" in t for t in titles))
check("alpha silent (clean first tick)", any("Alpha" in t for t in titles), False)

print("\n-- state survives a restart --")
restored = vb.Board()
check("verdicts restored", core.summarize(restored.results["beta"]), (1, 2))
truthy("schedule restored", "beta" in restored.next_run)
check("restored detail is labelled", restored.results["beta"]["beta:check one"]["detail"],
      "(from last session)")

print("\n-- run now makes a spec due --")
board.rescan()
alpha = next(s for s in board.specs if s.name == "alpha")
check("alpha not due yet", board.due() is None or board.due().name != "alpha", True)
board.run_now(alpha)
check("alpha now due", board.due().name, "alpha")

print("\n-- archive drops it off the board --")
beta = next(s for s in board.specs if s.name == "beta")
core.archive_spec(beta)
board.rescan()
check("gone from board", [s.name for s in board.specs], ["alpha"])
truthy("in archive/", os.path.exists(os.path.join(SANDBOX, "archive", "beta.toml")))
check("results pruned", "beta" in board.results, False)

print("\n-- selection stays in range after a spec disappears --")
board.selected = 5
board.rescan()
check("selection clamped", board.selected, 0)

print("\n-- investigate command --")
cmd = vb.investigate_command(alpha)
truthy("wraps in claude", cmd.startswith('claude "'))
truthy("names the spec path", alpha.path in cmd)

print("\n-- relative times --")
check("seconds", vb.relative(now - dt.timedelta(seconds=30), now), "30s")
check("minutes", vb.relative(now - dt.timedelta(minutes=14), now), "14m")
check("hours", vb.relative(now - dt.timedelta(hours=5), now), "5h")
check("days", vb.relative(now - dt.timedelta(days=3), now), "3d")
check("never", vb.relative(None, now), "—")

print("\n-- verdict precedence: error beats fail --")
check("error wins", vb.spec_verdict({
    "a": {"state": core.FAIL}, "b": {"state": core.ERROR}}), core.ERROR)
check("empty is blank", vb.spec_verdict({}), "")


# --- rendering into a fake window ------------------------------------------- #
#
# curses.color_pair() needs a live initscr(), which a headless test has no way
# to provide. Stubbing it exercises every layout and content decision; the only
# thing left unasserted is which colour each row gets, which is visible at a
# glance the first time the board runs.
import curses as _curses
_curses.color_pair = lambda n: 0


class FakeWin:
    def __init__(self, h=30, w=120):
        self.h, self.w, self.lines = h, w, []

    def getmaxyx(self):
        return (self.h, self.w)

    def erase(self):
        self.lines = []

    def refresh(self):
        pass

    def addnstr(self, y, x, text, n, attr=0):
        self.lines.append(text[:n])

    def text(self):
        return "\n".join(self.lines)


print("\n-- draw_list --")
win = FakeWin()
vb.draw_list(win, board)
out = win.text()
truthy("shows header count", "1 spec(s)" in out)
truthy("shows spec name", "alpha" in out)
truthy("shows pass count", "2/2" in out)
truthy("shows PR", "#100" in out)
truthy("shows keybindings", "archive" in out and "quit" in out)

print("\n-- draw_list with an empty board --")
empty = vb.Board()
empty.specs = []
win = FakeWin()
vb.draw_list(win, empty)
truthy("explains emptiness", "nothing in" in win.text())

print("\n-- draw_list survives a tiny terminal --")
win = FakeWin(h=3, w=20)
vb.draw_list(win, board)
print("  ok  no exception at 3x20")

print("\n-- draw_detail shows evidence only for failures --")
board.results["alpha"] = {
    "alpha:check one": {"state": core.PASS, "detail": "ok", "raw": "1", "query": "select 1"},
    "alpha:check two": {"state": core.FAIL, "detail": "bad", "raw": "9",
                        "query": "select failing_thing"},
}
win = FakeWin()
vb.draw_detail(win, board, alpha, 0)
out = win.text()
truthy("failing query shown", "select failing_thing" in out)
check("passing query hidden", "select 1" in out, False)
truthy("healthy note shown for the failing check",
       "expect: some events means it is alive" in out)
check("healthy note hidden for the passing check", "expect: zero is good" in out, False)
truthy("raw output shown", "got: 9" in out)

print("\n-- draw_detail scroll is clamped --")
max_scroll = vb.draw_detail(win, board, alpha, 9999)
truthy("max_scroll is finite", isinstance(max_scroll, int) and max_scroll >= 0)

print()
if fails:
    print(f"FAILED ({len(fails)}):")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("all checks passed")
