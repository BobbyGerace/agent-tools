#!/usr/bin/env python3
"""level=warn: a failed heuristic is yellow with '?', not red."""
import datetime as dt, importlib.machinery, importlib.util, io, json, os, sys, tempfile, curses, urllib.request
SB=tempfile.mkdtemp(); os.makedirs(SB+"/active"); os.environ["VERIFY_HOME"]=SB
VERIFY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, VERIFY_DIR)
sp=importlib.util.spec_from_loader("vb", importlib.machinery.SourceFileLoader("vb", os.path.join(VERIFY_DIR, "verify-board")))
vb=importlib.util.module_from_spec(sp); sp.loader.exec_module(vb)
core=vb.core; curses.color_pair=lambda n:0; core.notify=lambda *a:None; core.save_state=lambda s:None
core.merge_state=lambda s:"MERGED"

fails=[]
def ck(l,g,x=True):
    print(("  ok  " if g==x else "  BAD ")+l+("" if g==x else f"   got {g!r} want {x!r}"))
    if g!=x: fails.append(l)

def chk(level=None, op="eq", value=0):
    c={"name":"c","source":"postgres","query":"select 1","op":op,"value":value}
    if level: c["level"]=level
    return core.validate_check(c, "t")

print("-- default is alert --")
ck("level defaults to alert", chk()["level"], "alert")
ck("explicit warn kept", chk("warn")["level"], "warn")

print("\n-- evaluate maps level to state --")
core._cred_cache[core.KC_PG_DSN]="dsn"
import subprocess
def fake_psql(observed):
    def run(cmd, **kw):
        class P: returncode=0; stdout=f"{observed}\n"; stderr=""
        return P()
    return run
orig=subprocess.run

subprocess.run=fake_psql(0)
ck("alert passing -> PASS", core.evaluate(chk())["state"], core.PASS)
ck("warn passing -> PASS", core.evaluate(chk("warn"))["state"], core.PASS)
subprocess.run=fake_psql(7)
ck("alert failing -> FAIL", core.evaluate(chk())["state"], core.FAIL)
ck("warn failing -> WARN", core.evaluate(chk("warn"))["state"], core.WARN)
subprocess.run=orig

print("\n-- worst() precedence --")
for states, want in [({core.PASS}, core.PASS), ({core.PASS,core.WARN}, core.WARN),
                     ({core.WARN,core.FAIL}, core.FAIL), ({core.FAIL,core.ERROR}, core.ERROR),
                     ({core.PASS,core.WARN,core.FAIL,core.ERROR}, core.ERROR)]:
    ck(f"{sorted(s.strip() for s in states)} -> {want.strip()}", core.worst(states), want)

print("\n-- a warn is not counted as a pass --")
res={"a":{"state":core.PASS},"b":{"state":core.WARN},"c":{"state":core.FAIL}}
ck("summarize counts only PASS", core.summarize(res), (1,3))
ck("spec verdict is the worst", vb.spec_verdict(res), core.FAIL)
ck("warn-only spec is WARN", vb.spec_verdict({"a":{"state":core.WARN}}), core.WARN)

print("\n-- colours and glyphs --")
ck("WARN shares yellow with ERROR", vb._pair(core.WARN), vb._pair(core.ERROR))
ck("WARN is not red", vb._pair(core.WARN) != vb._pair(core.FAIL))
ck("glyph for warn is ?", vb.MARKS[core.WARN], "?")
ck("glyph for error is !", vb.MARKS[core.ERROR], "!")
ck("glyph for fail is ✗", vb.MARKS[core.FAIL], "✗")

print("\n-- the board row --")
MIN='\n[[checks]]\nname="poll still serving"\nsource="postgres"\nquery="select 1"\nop="gt"\nvalue=50\nlevel="warn"\n'
open(f"{SB}/active/s.toml","w").write(
  f'[spec]\nstarted = {dt.datetime.now().astimezone().replace(microsecond=0).isoformat()}\npr=1\nrepo="api-service"\n'+MIN)
b=vb.Board(); b.rescan(); s0=b.specs[0]
ck("level survives load", s0.checks[0]["level"], "warn")
b.merge["s"]="MERGED"
b.results["s"]={s0.checks[0]["label"]:{"state":core.WARN,"detail":"value=3 gt 50","raw":"3","query":"select 1"}}
b.last_run["s"]=dt.datetime.now()
class W:
    def __init__(s,h=14,w=118): s.h,s.w,s.rows=h,w,{}
    def getmaxyx(s): return (s.h,s.w)
    def erase(s): s.rows={}
    def refresh(s): pass
    def addnstr(s,y,x,t,n,a=0): s.rows[y]=(" "*x+t[:n], a)
    def text(s): return "\n".join(v[0] for _,v in sorted(s.rows.items()))
w=W(); vb.draw_list(w,b)
ck("row shows the ? glyph", "?" in w.text())
ck("row does not show ✗", "✗" not in w.text())
w2=W(h=24); vb.draw_detail(w2,b,s0,0)
ck("detail shows evidence for a warn", "select 1" in w2.text())

print("\n-- verify-spec exit code: warn does not fail the run --")
src=open(os.path.join(VERIFY_DIR, "verify-spec")).read()
ck("exit gate excludes WARN", "in (FAIL, ERROR)" in src)
ck("evidence printed for WARN", "(FAIL, WARN, ERROR)" in src)

print("\n-- validation rejects a bad level --")
try:
    chk("urgent"); ck("rejected", False)
except core.SpecError as e: ck("names the allowed values", "alert" in str(e) and "warn" in str(e))

print()
if fails: print(f"FAILED ({len(fails)}):"); [print("  -",f) for f in fails]; sys.exit(1)
print("all checks passed")
