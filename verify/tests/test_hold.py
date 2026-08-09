#!/usr/bin/env python3
"""Unmerged specs must not run, must render dim, and must fail open on unknown."""
import datetime as dt, importlib.machinery, importlib.util, os, sys, tempfile, threading, time, curses

SANDBOX = tempfile.mkdtemp(prefix="verify-hold-")
os.makedirs(os.path.join(SANDBOX, "active"))
os.environ["VERIFY_HOME"] = SANDBOX
VERIFY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, VERIFY_DIR)
sp = importlib.util.spec_from_loader("vb",
     importlib.machinery.SourceFileLoader("vb", os.path.join(VERIFY_DIR, "verify-board")))
vb = importlib.util.module_from_spec(sp); sp.loader.exec_module(vb)
core = vb.core
curses.color_pair = lambda n: 0

fails=[]
def check(l,g,w):
    if g!=w: fails.append(f"{l}: got {g!r} want {w!r}")
    else: print(f"  ok  {l}")

MIN = """
[[checks]]
name = "c1"
source = "postgres"
query = "select 1"
op = "eq"
value = 0
"""
def spec(name, pr=None, repo="api-service"):
    h=["[spec]", f'started = {(dt.datetime.now()-dt.timedelta(minutes=5)).isoformat(timespec="seconds")}']
    if pr: h.append(f"pr = {pr}")
    if repo: h.append(f'repo = "{repo}"')
    p=os.path.join(SANDBOX,"active",f"{name}.toml")
    open(p,"w").write("\n".join(h)+"\n"+MIN); return p

print("\n-- gh_repo resolution --")
spec("bare", pr=1); spec("qualified", pr=2, repo="someorg/thing"); spec("norepo", pr=3, repo=None)
byname={s.name:s for s in core.discover_active().specs}
check("owner/name passes through", byname["qualified"].gh_repo, "someorg/thing")
check("no repo -> None", byname["norepo"].gh_repo, None)
# A bare name needs VERIFY_GH_OWNER. Unset, it must resolve to None rather than to
# a half-built "/api-service" — None fails open (see merge_state), a broken slug
# would send `gh` looking for a repo that cannot exist.
check("bare name, no owner configured -> None", byname["bare"].gh_repo, None)
_saved = core.DEFAULT_GH_OWNER
core.DEFAULT_GH_OWNER = "someorg"
check("bare name + VERIFY_GH_OWNER -> owner/name", byname["bare"].gh_repo, "someorg/api-service")
check("owner/name still wins over the default", byname["qualified"].gh_repo, "someorg/thing")
core.DEFAULT_GH_OWNER = _saved

print("\n-- should_run --")
for state, want in [("MERGED",True),("OPEN",False),("CLOSED",False),(None,True)]:
    check(f"{state!r} -> run={want}", core.should_run(state), want)

print("\n-- hold_reason --")
check("OPEN", core.hold_reason("OPEN"), "PR not merged")
check("CLOSED reason mentions archive", "archive" in core.hold_reason("CLOSED"), True)
check("MERGED has no reason", core.hold_reason("MERGED"), "")

print("\n-- merge_state needs a pr and a repo --")
check("no pr -> None", core.merge_state(byname["bare"]._replace() if hasattr(byname["bare"],"_replace") else core.Spec(
    path="x",name="x",title="x",started=dt.datetime.now(),pr=None,repo="api-service",checks=[])), None)
check("no repo -> None", core.merge_state(core.Spec(
    path="x",name="x",title="x",started=dt.datetime.now(),pr=5,repo="",checks=[])), None)

print("\n-- held specs are never due, and never evaluated --")
evaluated=[]
def fake(s):
    evaluated.append(s.name)
    return {c["label"]: {"state": core.PASS, "detail":"ok","raw":"","query":"q"} for c in s.checks}
core.evaluate_spec = fake
core.notify = lambda *a: None
core.merge_state = lambda s: {"bare":"OPEN","qualified":"MERGED","norepo":None}.get(s.name)

b = vb.Board(); b.rescan()
w = threading.Thread(target=vb.checker, args=(b,), daemon=True); w.start()
deadline=time.time()+6
while time.time()<deadline and len(evaluated)<2: time.sleep(0.05)
b.stop.set(); w.join(timeout=2)

check("open PR never evaluated", "bare" in evaluated, False)
check("merged PR evaluated", "qualified" in evaluated, True)
check("unknown state fails open and runs", "norepo" in evaluated, True)
check("held spec has no results", b.results.get("bare"), None)
check("merge state cached", b.merge["bare"], "OPEN")

print("\n-- merged is cached forever, unmerged is re-polled --")
b.merge["qualified"]="MERGED"; b.merge_checked["qualified"]=dt.datetime.now()-dt.timedelta(hours=99)
b.merge["bare"]="OPEN";        b.merge_checked["bare"]=dt.datetime.now()-dt.timedelta(hours=99)
stale=b.merge_stale()
check("merged not re-polled", stale.name != "qualified", True)
check("unmerged re-polled", stale.name, "bare")
b.merge_checked["bare"]=dt.datetime.now()
check("recently checked not re-polled", b.merge_stale() is None or b.merge_stale().name!="bare", True)

print("\n-- state survives restart --")
b._persist()
r = vb.Board()
check("merge state restored", r.merge.get("bare"), "OPEN")
check("merge_checked restored", "bare" in r.merge_checked, True)

print("\n-- rendering --")
class W:
    def __init__(s,h=24,w=120): s.h,s.w,s.rows=h,w,{}
    def getmaxyx(s): return (s.h,s.w)
    def erase(s): s.rows={}
    def refresh(s): pass
    def addnstr(s,y,x,t,n,a=0): s.rows[y]=(t[:n],a)
    def text(s): return "\n".join(v[0] for _,v in sorted(s.rows.items()))
    def attr_for(s,frag):
        return next((a for _,(t,a) in s.rows.items() if frag in t), None)

win=W(); vb.draw_list(win,b); out=win.text()
check("headline counts held", "(1 held)" in out, True)
check("held line shows reason", "PR not merged" in out, True)
check("held line shows pause mark", "⏸" in out, True)
check("held line hides counts", "0/1  bare" in out, False)
check("held line is dim", win.attr_for("bare") & curses.A_DIM > 0, True)
check("running line not dim", (win.attr_for("qualified") or 0) & curses.A_DIM, 0)

win2=W(h=30); vb.draw_detail(win2,b,byname["bare"],0); d=win2.text()
check("detail explains the hold", "Held: PR not merged" in d, True)
check("detail explains why no red", "not shipped" in d, True)


print("\n-- editing a spec re-polls merge state immediately (the 5-minute bug) --")
polls=[]
def counting_merge(s):
    polls.append(s.name)
    return "OPEN" if s.name=="late" else "MERGED"
core.merge_state=counting_merge

import time as _t
w2 = write_spec if False else None
p_late=os.path.join(SANDBOX,"active","late.toml")
open(p_late,"w").write(f'[spec]\nstarted = {dt.datetime.now().astimezone().replace(microsecond=0).isoformat()}\nrepo = "api-service"\n'+MIN)
b2=vb.Board(); b2.rescan()
late=next(s for s in b2.specs if s.name=="late")
check("no pr yet -> merge unknown", core.merge_state(late), "OPEN")
b2.record_merge(late, None)                      # simulate: polled before pr existed
b2.merge_checked["late"]=dt.datetime.now()       # freshly checked, so normally not stale
check("not stale right after a poll", b2.merge_stale() is None or b2.merge_stale().name!="late", True)
_t.sleep(0.01)
open(p_late,"w").write(f'[spec]\nstarted = {dt.datetime.now().astimezone().replace(microsecond=0).isoformat()}\npr = 3307\nrepo = "api-service"\n'+MIN)
os.utime(p_late,(_t.time()+1,_t.time()+1))
b2.rescan()
check("edit dropped the merge_checked stamp", "late" not in b2.merge_checked, True)
stale=b2.merge_stale()
check("so it is immediately re-polled", stale is not None and stale.name=="late", True)

print("\n-- spec_ref is uniform across repos --")
mk=lambda repo,pr: core.Spec(path="x",name="x",title="t",started=dt.datetime.now(),pr=pr,repo=repo,checks=[])
check("api-service carries its name too", vb.spec_ref(mk("api-service",4210)), "api-service#4210")
check("second repo, same shape", vb.spec_ref(mk("ops-tool",3307)), "ops-tool#3307")
check("no repo -> bare pr", vb.spec_ref(mk("",4210)), "#4210")
check("no pr is stated, not blank", vb.spec_ref(mk("api-service",None)), "api-service (no pr)")
check("neither", vb.spec_ref(mk("",None)), "(no pr)")

print("\n-- and it renders in the row for both repos --")
for repo,pr in (("api-service",4210),("ops-tool",3307)):
    bb=vb.Board(); bb.specs=[mk(repo,pr)]; bb.specs[0].__dict__["name"]=f"s-{repo}"
    bb.merge[f"s-{repo}"]="MERGED"
    w=type("W",(),{"h":16,"w":120,"rows":{},"getmaxyx":lambda s:(16,120),"erase":lambda s:None,
                   "refresh":lambda s:None,"addnstr":lambda s,y,x,t,n,a=0:s.rows.__setitem__(y,t[:n]),
                   "text":lambda s:"\n".join(s.rows.values())})()
    w.rows={}
    vb.draw_list(w,bb)
    check(f"{repo} row shows {repo}#{pr}", f"{repo}#{pr}" in w.text(), True)

print("\n-- editing a spec re-polls merge state immediately (the 5-minute bug) --")
polls=[]
def counting_merge(s):
    polls.append(s.name)
    return "OPEN" if s.name=="late" else "MERGED"
core.merge_state=counting_merge

import time as _t
w2 = write_spec if False else None
p_late=os.path.join(SANDBOX,"active","late.toml")
open(p_late,"w").write(f'[spec]\nstarted = {dt.datetime.now().astimezone().replace(microsecond=0).isoformat()}\nrepo = "api-service"\n'+MIN)
b2=vb.Board(); b2.rescan()
late=next(s for s in b2.specs if s.name=="late")
check("no pr yet -> merge unknown", core.merge_state(late), "OPEN")
b2.record_merge(late, None)                      # simulate: polled before pr existed
b2.merge_checked["late"]=dt.datetime.now()       # freshly checked, so normally not stale
check("not stale right after a poll", b2.merge_stale() is None or b2.merge_stale().name!="late", True)
_t.sleep(0.01)
open(p_late,"w").write(f'[spec]\nstarted = {dt.datetime.now().astimezone().replace(microsecond=0).isoformat()}\npr = 3307\nrepo = "api-service"\n'+MIN)
os.utime(p_late,(_t.time()+1,_t.time()+1))
b2.rescan()
check("edit dropped the merge_checked stamp", "late" not in b2.merge_checked, True)
stale=b2.merge_stale()
check("so it is immediately re-polled", stale is not None and stale.name=="late", True)

print("\n-- spec_ref is uniform across repos --")
mk=lambda repo,pr: core.Spec(path="x",name="x",title="t",started=dt.datetime.now(),pr=pr,repo=repo,checks=[])
check("api-service carries its name too", vb.spec_ref(mk("api-service",4210)), "api-service#4210")
check("second repo, same shape", vb.spec_ref(mk("ops-tool",3307)), "ops-tool#3307")
check("no repo -> bare pr", vb.spec_ref(mk("",4210)), "#4210")
check("no pr is stated, not blank", vb.spec_ref(mk("api-service",None)), "api-service (no pr)")
check("neither", vb.spec_ref(mk("",None)), "(no pr)")

print("\n-- and it renders in the row for both repos --")
for repo,pr in (("api-service",4210),("ops-tool",3307)):
    bb=vb.Board(); bb.specs=[mk(repo,pr)]; bb.specs[0].__dict__["name"]=f"s-{repo}"
    bb.merge[f"s-{repo}"]="MERGED"
    w=type("W",(),{"h":16,"w":120,"rows":{},"getmaxyx":lambda s:(16,120),"erase":lambda s:None,
                   "refresh":lambda s:None,"addnstr":lambda s,y,x,t,n,a=0:s.rows.__setitem__(y,t[:n]),
                   "text":lambda s:"\n".join(s.rows.values())})()
    w.rows={}
    vb.draw_list(w,bb)
    check(f"{repo} row shows {repo}#{pr}", f"{repo}#{pr}" in w.text(), True)

print()
if fails: print(f"FAILED ({len(fails)}):"); [print("  -",f) for f in fails]; sys.exit(1)
print("all checks passed")
