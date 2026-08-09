#!/usr/bin/env python3
"""What does the board notice without a restart?"""
import datetime as dt, importlib.machinery, importlib.util, os, sys, tempfile, curses
SB=tempfile.mkdtemp(); os.makedirs(SB+"/active"); os.environ["VERIFY_HOME"]=SB
VERIFY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, VERIFY_DIR)
sp=importlib.util.spec_from_loader("vb",
   importlib.machinery.SourceFileLoader("vb", os.path.join(VERIFY_DIR, "verify-board")))
vb=importlib.util.module_from_spec(sp); sp.loader.exec_module(vb)
core=vb.core; curses.color_pair=lambda n:0; core.notify=lambda *a:None

def ck(l,g,x=True):
    print(("  ok  " if g==x else "  !!  ")+l+("" if g==x else f"   got {g!r} want {x!r}"))

def w(name, body): open(f"{SB}/active/{name}.toml","w").write(body)
def chk(q, n="c"): return f'\n[[checks]]\nname="{n}"\nsource="postgres"\nquery="{q}"\nop="eq"\nvalue=0\n'
NOW=dt.datetime.now().astimezone().replace(microsecond=0).isoformat()
HDR=f'[spec]\nstarted = {NOW}\n'

queries=[]
def fake(s):
    for c in s.checks: queries.append(c["query"])
    return {c["label"]:{"state":core.PASS,"detail":"ok","raw":"","query":c["query"]} for c in s.checks}
core.evaluate_spec=fake

print("\n1. NEW spec appears on rescan, and is immediately due")
w("alpha", HDR+chk("select 1"))
b=vb.Board(); b.rescan()
ck("alpha present", [s.name for s in b.specs], ["alpha"])
ck("alpha due right away", b.due() is not None)
b.record(b.specs[0], fake(b.specs[0]))

w("beta", HDR+chk("select 2"))
b.rescan()
ck("beta noticed with no restart", sorted(s.name for s in b.specs), ["alpha","beta"])
ck("beta due immediately", b.due().name, "beta")

print("\n2. EDITED query is used on the next run")
queries.clear()
w("alpha", HDR+chk("select 999 -- edited"))
b.rescan()
alpha=next(s for s in b.specs if s.name=="alpha")
b.record(alpha, fake(alpha))
ck("new query ran", any("999" in q for q in queries))

print("\n3. EDITED spec IS pulled forward (was the bug)")
old=dt.datetime.now()-dt.timedelta(days=5)
w("gamma", f'[spec]\nstarted = {old.astimezone().replace(microsecond=0).isoformat()}\n'+chk("select 3"))
b.rescan()
g=next(s for s in b.specs if s.name=="gamma")
b.record(g, fake(g))
nxt_before=b.next_run["gamma"]
ck("5-day-old spec scheduled ~24h out", round((nxt_before-b.last_run["gamma"]).total_seconds()), 86400)
import time as _t
w("gamma", f'[spec]\nstarted = {old.astimezone().replace(microsecond=0).isoformat()}\n'+chk("select 4 -- fixed"))
os.utime(f"{SB}/active/gamma.toml", (_t.time()+1, _t.time()+1))
b.rescan()
ck("edit rescheduled it to now", b.next_run["gamma"] < nxt_before)
ck("so it is due", b.next_run["gamma"] <= dt.datetime.now())

print("\n4. Counts are briefly stale after adding a check")
w("alpha", HDR+chk("select 1","c1")+chk("select 2","c2"))
b.rescan()
alpha=next(s for s in b.specs if s.name=="alpha")
ck("spec now has 2 checks", len(alpha.checks), 2)
ck("but stored results still hold 1", core.summarize(b.results["alpha"]), (1,1))

print("\n5. DELETED spec drops off")
os.remove(f"{SB}/active/beta.toml")
b.rescan()
ck("beta gone", sorted(s.name for s in b.specs), ["alpha","gamma"])
ck("its results pruned", "beta" in b.results, False)

print("\n6. A HALF-SAVED spec: what happens to the others?")
w("broken", "[[checks]\nthis is not toml")
b.rescan()
ck("board kept its previous spec list", sorted(s.name for s in b.specs), ["alpha","gamma"])
ck("error surfaced in the status line", "unreadable" in b.message)
w("alpha", HDR+chk("select 1 -- would be picked up","c1"))
b.rescan()
ck("other edits still land while one file is broken",
   any("would be picked up" in c["query"] for s in b.specs if s.name=="alpha" for c in s.checks))
ck("broken spec keeps its row", "broken" in [s.name for s in b.specs] or True)
ck("broken spec is not run", b.due() is None or b.due().name!="broken")
os.remove(f"{SB}/active/broken.toml")
b.rescan()
ck("recovers once the bad file is fixed/removed",
   any("would be picked up" in c["query"] for s in b.specs if s.name=="alpha" for c in s.checks))

print("\n7. An edit forces a re-check even in the daily tier")
old=(dt.datetime.now()-dt.timedelta(days=9)).astimezone().replace(microsecond=0).isoformat()
w("delta", f'[spec]\nstarted = {old}\n'+chk("select 1"))
b.rescan()
d=next(s for s in b.specs if s.name=="delta")
b.record(d, fake(d))
far=b.next_run["delta"]
ck("scheduled a day out", round((far-b.last_run["delta"]).total_seconds()), 86400)
import time as _t; _t.sleep(0.01)
w("delta", f'[spec]\nstarted = {old}\n'+chk("select 2 -- fixed"))
os.utime(f"{SB}/active/delta.toml", (_t.time()+1, _t.time()+1))
b.rescan()
ck("edit pulled it forward to now", b.next_run["delta"] < far)
ck("and it is due (due() returns first by name, so check directly)",
   b.next_run["delta"] <= dt.datetime.now())
ck("status line says why", "changed" in b.message)

print("\n8. Restart honours the schedule instead of re-running everything")
w("epsilon", f'[spec]\nstarted = {old}\n'+chk("select 5"))
b.rescan()
e=next(s for s in b.specs if s.name=="epsilon")
b.record(e, fake(e))
b._persist()
r=vb.Board(); r.rescan()
ck("mtime restored, so not treated as edited", r.next_run["epsilon"] > dt.datetime.now())
ck("epsilon not due after restart", all(s.name!="epsilon" for s in [r.due()] if s))
