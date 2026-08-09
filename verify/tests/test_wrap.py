#!/usr/bin/env python3
"""Nothing in the detail view may be clipped."""
import datetime as dt, importlib.machinery, importlib.util, os, sys, tempfile, curses
SB=tempfile.mkdtemp(); os.makedirs(SB+"/active"); os.environ["VERIFY_HOME"]=SB
VERIFY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, VERIFY_DIR)
sp=importlib.util.spec_from_loader("vb", importlib.machinery.SourceFileLoader("vb", os.path.join(VERIFY_DIR, "verify-board")))
vb=importlib.util.module_from_spec(sp); sp.loader.exec_module(vb)
core=vb.core; curses.color_pair=lambda n:0; core.notify=lambda *a:None; core.save_state=lambda s:None

fails=[]
def ck(l,g,x=True):
    print(("  ok  " if g==x else "  BAD ")+l+("" if g==x else f"   got {g!r}"))
    if g!=x: fails.append(l)

# A realistically long, awkward check: a parenthesised OR of two globbed attribute
# values plus a negation. Long enough to need wrapping at every pane width tested,
# with tokens that must not be silently dropped mid-glob.
QUERY = ("env:prod source:api-service status:error (@SourceContext:*BillingPreferences* "
         "OR @SourceContext:*BillingPreferenceReader*) -@evt.name:email_opt_out")
HEALTHY = ("THE key check. Prod holds ~101 billing_preferences rows with type "
           "'account_needs_review' that must stay readable after the enum member is deleted.")
RAW = "count=3 over 24h"

open(f"{SB}/active/probe.toml","w").write(
 f'[spec]\ntitle = "account_needs_review code removal"\n'
 f'started = {dt.datetime.now().astimezone().replace(microsecond=0).isoformat()}\n'
 f'pr = 4210\nrepo = "api-service"\n'
 f'\n[[checks]]\nname = "billing-preference readers not erroring"\nsource = "datadog"\n'
 f'query = """{QUERY}"""\nop = "eq"\nvalue = 0\nhealthy = """{HEALTHY}"""\n')

b=vb.Board(); b.rescan()
spec=b.specs[0]
b.results["probe"]={spec.checks[0]["label"]: {"state":core.FAIL,"detail":"value=3 eq 0",
                                             "raw":RAW,"query":QUERY}}
b.last_run["probe"]=dt.datetime.now(); b.merge["probe"]="MERGED"

class W:
    """Strict: raises if anything is handed to addnstr wider than the pane.

    Used for draw_detail, where clipping loses information. draw_list is checked
    with L below instead: a spec row is deliberately one line and clipping it is
    the correct trade — wrapping rows would destroy the at-a-glance scan the
    board exists for.
    """
    def __init__(s,h=40,w=100): s.h,s.w,s.rows=h,w,{}
    def getmaxyx(s): return (s.h,s.w)
    def erase(s): s.rows={}
    def refresh(s): pass
    def addnstr(s,y,x,t,n,a=0):
        assert len(t)<=n, f"CLIPPED at row {y}: {len(t)} chars into {n}"
        s.rows[y]=" "*x+t
    def text(s): return "\n".join(s.rows.get(i,"") for i in range(max(s.rows)+1)) if s.rows else ""


class L(W):
    """Lenient: records the clip instead of raising."""
    def __init__(s,h=40,w=100):
        super().__init__(h,w); s.clipped=[]
    def addnstr(s,y,x,t,n,a=0):
        if len(t)>n: s.clipped.append((y,len(t),n))
        s.rows[y]=" "*x+t[:n]

for width in (70, 100, 140):
    w=W(h=40,w=width)
    ms=vb.draw_detail(w,b,spec,0)
    out=w.text()
    longest=max((len(l) for l in out.splitlines()), default=0)
    ck(f"w={width}: no row exceeds the pane", longest <= width-1)
    # every word of the query must survive somewhere in the output
    missing=[tok for tok in QUERY.split() if tok not in out]
    ck(f"w={width}: whole query present ({len(QUERY.split())} tokens)", missing, [])
    missing_h=[tok for tok in HEALTHY.split() if tok not in out]
    ck(f"w={width}: whole expect note present", missing_h, [])
    ck(f"w={width}: raw result present", RAW in out or "count=3" in out)

print("\n-- scroll indicator appears only when content overflows --")
w=W(h=8,w=80); vb.draw_detail(w,b,spec,0)
ck("shows position when scrollable", "/" in w.text().splitlines()[-1])
w=W(h=60,w=120); vb.draw_detail(w,b,spec,0)
ck("no indicator when it all fits", "[" not in w.text().splitlines()[-1])

print("\n-- scrolling reaches the end --")
w=W(h=8,w=80); ms=vb.draw_detail(w,b,spec,0)
w2=W(h=8,w=80); vb.draw_detail(w2,b,spec,ms)
ck("last page differs from first", w.text()!=w2.text())
ck("scroll clamps past the end", vb.draw_detail(W(h=8,w=80),b,spec,9999), ms)

print("\n-- wrap() itself --")
ck("short line untouched", vb.wrap("hi", 0, 40), [("hi",0)])
ck("indent preserved on continuations",
   all(l.startswith("        ") for l,_ in vb.wrap("        "+"x "*60, 0, 40)))
ck("unbreakable token is split, not dropped",
   "".join(l.strip() for l,_ in vb.wrap("A"*200, 0, 40)), "A"*200)
ck("zero width yields nothing", vb.wrap("x", 0, 0), [])

print("\n-- narrow panes: content wraps, footer shortens --")
for width in (24, 40, 55):
    w=W(h=20,w=width); vb.draw_detail(w,b,spec,0)
    ck(f"w={width}: nothing clipped", True)
w=W(h=20,w=24); vb.draw_detail(w,b,spec,0)
ck("tiny pane footer fits", len(w.text().splitlines()[-1].strip()) <= 21)
w=W(h=20,w=120); vb.draw_detail(w,b,spec,0)
ck("wide pane gets the full footer", "top/bottom" in w.text().splitlines()[-1])

print("\n-- list view: chrome fits, rows may clip by design --")
for width in (24, 50, 80, 120):
    l=L(h=12,w=width); vb.draw_list(l,b)
    rows=[y for y,_,_ in l.clipped]
    ck(f"list w={width}: headline never clipped", 0 not in rows)
    ck(f"list w={width}: footer never clipped", 11 not in rows)

print()
if fails: print(f"FAILED ({len(fails)}):"); [print("  -",f) for f in fails]; sys.exit(1)
print("all checks passed")
