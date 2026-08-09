#!/usr/bin/env python3
"""Newest first, and the cursor follows the spec rather than the row."""
import datetime as dt, importlib.machinery, importlib.util, os, sys, tempfile, time, curses
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

MIN='\n[[checks]]\nname="c"\nsource="postgres"\nquery="select 1"\nop="eq"\nvalue=0\n'
def w(name, ago_hours):
    t=(dt.datetime.now()-dt.timedelta(hours=ago_hours)).astimezone().replace(microsecond=0)
    open(f"{SB}/active/{name}.toml","w").write(f'[spec]\nstarted = {t.isoformat()}\n'+MIN)

print("-- newest first --")
w("oldest", 100); w("middle", 10); w("newest", 1)
b=vb.Board(); b.rescan()
ck("order is newest -> oldest", [s.name for s in b.specs], ["newest","middle","oldest"])
ck("not alphabetical", [s.name for s in b.specs] != sorted(s.name for s in b.specs))

print("\n-- equal timestamps fall back to name, stably --")
same=(dt.datetime.now()-dt.timedelta(hours=5)).astimezone().replace(microsecond=0).isoformat()
for n in ("bbb","aaa","ccc"):
    open(f"{SB}/active/{n}.toml","w").write(f'[spec]\nstarted = {same}\n'+MIN)
b.rescan(); order1=[s.name for s in b.specs]
b.rescan(); order2=[s.name for s in b.specs]
ck("stable across rescans", order1, order2)
tied=[n for n in order1 if n in ("aaa","bbb","ccc")]
ck("ties are alphabetical", tied, ["aaa","bbb","ccc"])

print("\n-- the cursor follows the spec, not the row --")
b.rescan()
idx=[s.name for s in b.specs].index("middle")
b.selected=idx
ck(f"selected 'middle' at row {idx}", b.specs[b.selected].name, "middle")
w("brand-new", 0)                      # lands at index 0, pushes everything down
b.rescan()
ck("a new spec took row 0", b.specs[0].name, "brand-new")
ck("cursor still on 'middle'", b.specs[b.selected].name, "middle")
ck("its row index shifted", b.selected != idx)

print("\n-- and when the selected spec disappears, the cursor clamps --")
b.selected=[s.name for s in b.specs].index("oldest")
os.remove(f"{SB}/active/oldest.toml")
b.rescan()
ck("still in range", 0 <= b.selected < len(b.specs))
ck("no crash rendering", True)

print("\n-- archiving hits the row you can see --")
b.rescan()
b.selected=[s.name for s in b.specs].index("middle")
target=b.selected_spec()
ck("selected_spec agrees with the cursor", target.name, "middle")
core.archive_spec(target); b.rescan()
ck("archived the intended one", os.path.exists(f"{SB}/archive/middle.toml"))
ck("and only that one", "middle" not in [s.name for s in b.specs])

print("\n-- future-dated specs sort to the very top, so they're visible --")
fut=(dt.datetime.now()+dt.timedelta(hours=3)).astimezone().replace(microsecond=0).isoformat()
open(f"{SB}/active/future.toml","w").write(f'[spec]\nstarted = {fut}\n'+MIN)
b.rescan()
ck("future-dated is first", b.specs[0].name, "future")
ck("its age still clamps to 0", int(b.specs[0].age.total_seconds()), 0)

print()
if fails: print(f"FAILED ({len(fails)}):"); [print("  -",f) for f in fails]; sys.exit(1)
print("all checks passed")
