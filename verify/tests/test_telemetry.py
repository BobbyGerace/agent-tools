#!/usr/bin/env python3
"""Telemetry connector: the command contract, parsing, failure states. No network —
the telemetry command is a stub script that replays a canned reply."""
import json, os, stat, sys, tempfile
SB=tempfile.mkdtemp(); os.makedirs(SB+"/active"); os.environ["VERIFY_HOME"]=SB
VERIFY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, VERIFY_DIR)
import verify_core as core

fails=[]
def ck(l,g,x=True):
    print(("  ok  " if g==x else "  BAD ")+l+("" if g==x else f"   got {g!r} want {x!r}"))
    if g!=x: fails.append(l)

# The stub records what it was handed and answers from reply.json, so each case
# below is one reply plus the assertions on what the connector made of it.
STUB_DIR=tempfile.mkdtemp()
STUB=os.path.join(STUB_DIR,"telemetry-stub")
open(STUB,"w").write(f"""#!{sys.executable}
import json, os, sys
d = os.path.dirname(os.path.abspath(__file__))
json.dump(sys.argv[1:], open(os.path.join(d, "argv.json"), "w"))
open(os.path.join(d, "stdin.sql"), "w").write(sys.stdin.read())
r = json.load(open(os.path.join(d, "reply.json")))
sys.stdout.write(r.get("stdout", "")); sys.stderr.write(r.get("stderr", ""))
sys.exit(r.get("code", 0))
""")
os.chmod(STUB, os.stat(STUB).st_mode|stat.S_IXUSR)
core.TELEMETRY_CMD=STUB

def reply(stdout="", stderr="", code=0, result=None):
    if result is not None: stdout=json.dumps(result)
    json.dump({"stdout":stdout,"stderr":stderr,"code":code}, open(os.path.join(STUB_DIR,"reply.json"),"w"))

def result(columns, rows, truncated=False): return {"columns":columns,"rows":rows,"truncated":truncated}

def raises(l, fn, needle):
    try: fn()
    except RuntimeError as e: ck(l, True if needle in str(e) else str(e)); return
    ck(l, "did not raise")

SQL="SELECT count() AS n FROM logs\nWHERE svc = 'it''s' AND body ILIKE '%a \"quoted\" thing%'"
CHK={"source":"telemetry","query":SQL,"metric":"value"}

print("\n-- the command contract: `query --json --limit 500`, SQL on stdin --")
reply(result=result(["n"],[[7]]))
v,raw=core.run_telemetry(dict(CHK))
ck("argv", json.load(open(os.path.join(STUB_DIR,"argv.json"))), ["query","--json","--limit","500"])
ck("SQL arrives verbatim on stdin", open(os.path.join(STUB_DIR,"stdin.sql")).read(), SQL)
ck("value is the first cell", v, 7.0)
ck("raw names the column", raw, "n=7")

print("\n-- parsing --")
reply(result=result(["n"],[["12"]]))
ck("a numeric string still counts", core.run_telemetry(dict(CHK))[0], 12.0)
reply(result=result(["route","n"],[["a",1],["b",2],["c",3]]))
v,raw=core.run_telemetry(dict(CHK, metric="rows"))
ck("rows metric counts rows", v, 3.0)
ck("raw shows each row", raw.splitlines(), ["route=a n=1","route=b n=2","route=c n=3"])
reply(result=result(["n"],[]))
v,raw=core.run_telemetry(dict(CHK, metric="rows"))
ck("zero rows is a real zero for rows", v, 0.0); ck("raw says so", raw, "(no rows)")

print("\n-- answers that are not a number fail loudly, never as zero --")
reply(result=result(["route"],[[f"r{i}"] for i in range(500)], truncated=True))
raises("truncated rows are a floor, not a count", lambda: core.run_telemetry(dict(CHK, metric="rows")), "floor")
reply(result=result(["n"],[]))
raises("value with no rows", lambda: core.run_telemetry(dict(CHK)), "no rows")
reply(result=result(["route"],[["checkout"]]))
raises("non-numeric first cell", lambda: core.run_telemetry(dict(CHK)), "not numeric")
reply(stdout="Traceback (most recent call last):")
raises("output that is not the JSON result", lambda: core.run_telemetry(dict(CHK)), "JSON result")
reply(stdout=json.dumps({"rows":[[1]]}))
raises("JSON missing columns", lambda: core.run_telemetry(dict(CHK)), "JSON result")

print("\n-- the command's own failure is the message --")
reply(stderr="warming up\ntelemetry-query: login expired; log in again\n", code=1)
raises("last stderr line surfaces", lambda: core.run_telemetry(dict(CHK)), "login expired; log in again")
reply(code=3)
raises("silent failure names the exit code", lambda: core.run_telemetry(dict(CHK)), "exited 3")
core.TELEMETRY_CMD=os.path.join(STUB_DIR,"no-such-command")
raises("a missing command points at the contract", lambda: core.run_telemetry(dict(CHK)), "README.md")
core.TELEMETRY_CMD=STUB

print("\n-- evaluate(): a failed query is ERR (unverified), never a red --")
base={"source":"telemetry","query":SQL,"metric":"value","op":"lt","value":5.0,"healthy":"","label":"x:y"}
reply(result=result(["n"],[[2]]))
ck("passes under threshold", core.evaluate(dict(base))["state"], core.PASS)
reply(result=result(["n"],[[9]]))
ck("fails over threshold", core.evaluate(dict(base))["state"], core.FAIL)
ck("warn level softens it", core.evaluate(dict(base, level="warn"))["state"], core.WARN)
reply(stderr="telemetry-query: login expired\n", code=1)
r=core.evaluate(dict(base))
ck("auth failure is ERR", r["state"], core.ERROR); ck("and says why", r["detail"], "telemetry-query: login expired")

print("\n-- spec validation --")
ck("telemetry is a known source", "telemetry" in core.CONNECTORS)
p=os.path.join(SB,"active","t.toml")
def spec(body): open(p,"w").write(body); return core.load_spec(p)
OK='[[checks]]\nname="e"\nsource="telemetry"\nquery="SELECT 1"\nop="lt"\nvalue=5\n'
ck("loads", len(spec(OK).checks), 1)
for old in ("datadog","rum","spans"):
    try: spec(OK.replace('"telemetry"', f'"{old}"')); ck(f"{old} rejected", False)
    except core.SpecError as e:
        ck(f"{old} rejected, pointing at telemetry", 'source = "telemetry"' in str(e))
try: spec(OK.replace('"telemetry"','"rum"')); ck("rum rejected", False)
except core.SpecError as e: ck("rum says there is no browser source", "no browser source" in str(e))
try: spec(OK+'window="1h"\n'); ck("window rejected", False)
except core.SpecError as e: ck("window points into the query", "time bound in the query" in str(e))
try: spec(OK.replace('"telemetry"','"telemetri"')); ck("typo rejected", False)
except core.SpecError as e: ck("a near-miss source lists the real ones", "telemetry" in str(e))

print()
if fails: print(f"FAILED ({len(fails)}):"); [print("  -",f) for f in fails]; sys.exit(1)
print("all checks passed")
