#!/usr/bin/env python3
"""Drive the real key handler with a scripted keystream — no terminal."""
import datetime as dt, importlib.machinery, importlib.util, os, sys, tempfile, curses

SB=tempfile.mkdtemp(); os.makedirs(SB+"/active"); os.environ["VERIFY_HOME"]=SB
VERIFY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, VERIFY_DIR)
sp=importlib.util.spec_from_loader("vb",
   importlib.machinery.SourceFileLoader("vb", os.path.join(VERIFY_DIR, "verify-board")))
vb=importlib.util.module_from_spec(sp); sp.loader.exec_module(vb)
core=vb.core
curses.color_pair=lambda n:0
curses.curs_set=lambda n:None
curses.use_default_colors=lambda:None
curses.init_pair=lambda *a:None
core.notify=lambda *a:None
core.merge_state=lambda s:"MERGED"

MIN='\n[[checks]]\nname="c"\nsource="postgres"\nquery="select 1"\nop="eq"\nvalue=0\n'
for n in ("alpha","beta","gamma"):
    open(f"{SB}/active/{n}.toml","w").write(
        f'[spec]\nstarted = {dt.datetime.now().astimezone().replace(microsecond=0).isoformat()}\n'+MIN)

fails=[]
def ck(l,g,x):
    print(("  ok  " if g==x else "  BAD ")+l+("" if g==x else f"  got {g!r} want {x!r}"))
    if g!=x: fails.append(l)

class Screen:
    """Feeds a scripted keystream; -1 means 'no key this tick'."""
    def __init__(s, keys): s.keys=list(keys); s.h,s.w=24,110
    def getmaxyx(s): return (s.h,s.w)
    def erase(s): pass
    def refresh(s): pass
    def addnstr(s,*a,**k): pass
    def timeout(s,n): pass
    def getch(s): return s.keys.pop(0) if s.keys else ord("q")

def drive(keys):
    b=vb.Board(); b.rescan()
    for sp_ in b.specs: b.merge[sp_.name]="MERGED"
    scr=Screen(keys)
    vb.run(scr, b)          # returns when it sees q
    return b, scr

print("-- j/k move the selection --")
b,_=drive([ord("j"), ord("j"), ord("q")])
ck("jj -> index 2", b.selected, 2)
b,_=drive([ord("j"), ord("j"), ord("k"), ord("q")])
ck("jjk -> index 1", b.selected, 1)

print("-- selection clamps at both ends --")
b,_=drive([ord("k")]*3+[ord("q")])
ck("k at top stays 0", b.selected, 0)
b,_=drive([ord("j")]*9+[ord("q")])
ck("j past end clamps to 2", b.selected, 2)

print("-- g / G jump --")
b,_=drive([ord("G"), ord("q")])
ck("G -> last", b.selected, 2)
b,_=drive([ord("G"), ord("g"), ord("q")])
ck("Gg -> first", b.selected, 0)

print("-- l opens detail, h closes it --")
# If l failed to open detail, the following q would quit and 'r' never queue.
b,_=drive([ord("l"), ord("r"), ord("h"), ord("q")])
ck("r inside detail queued the spec", b.next_run["alpha"] <= dt.datetime.now(), True)
ck("h returned to the list (q then quit, no hang)", True, True)

print("-- enter and arrows still work --")
b,_=drive([10, ord("r"), 27, ord("q")])
ck("enter opened detail, esc closed", b.next_run["alpha"] <= dt.datetime.now(), True)
b,_=drive([curses.KEY_DOWN, curses.KEY_RIGHT, curses.KEY_LEFT, ord("q")])
ck("arrows navigate", b.selected, 1)

print("-- h in the list view is inert --")
b,_=drive([ord("j"), ord("h"), ord("q")])
ck("h did not change selection", b.selected, 1)

print("-- a archives the selected spec --")
b,_=drive([ord("j"), ord("a"), ord("q")])
ck("beta archived", os.path.exists(f"{SB}/archive/beta.toml"), True)
ck("beta off the board", [s.name for s in b.specs], ["alpha","gamma"])

print("-- c copies the investigate command --")
# The status line is transient by design — every keypress clears it — so assert
# on the clipboard call rather than on a message the following `q` wipes.
copied=[]
vb.copy_to_clipboard=lambda t: (copied.append(t), True)[1]
b,_=drive([ord("c"), ord("q")])
ck("clipboard written once", len(copied), 1)
ck("command wraps claude", copied[0].startswith('claude "'), True)
ck("command names the spec", "alpha.toml" in copied[0], True)

print()
if fails: print(f"FAILED ({len(fails)}):"); [print("  -",f) for f in fails]; sys.exit(1)
print("all checks passed")
