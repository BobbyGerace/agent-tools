#!/usr/bin/env python3
"""RUM connector: request shape, response parsing, error handling. No network."""
import io, json, os, sys, tempfile, urllib.error
SB=tempfile.mkdtemp(); os.makedirs(SB+"/active"); os.environ["VERIFY_HOME"]=SB
VERIFY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, VERIFY_DIR)
import verify_core as core

fails=[]
def ck(l,g,x=True):
    print(("  ok  " if g==x else "  BAD ")+l+("" if g==x else f"   got {g!r} want {x!r}"))
    if g!=x: fails.append(l)

# stub creds so nothing touches the Keychain
core._cred_cache.update({core.KC_DD_API_KEY:"api", core.KC_DD_APP_KEY:"app", core.KC_DD_SITE:"datadoghq.com"})

captured={}
class Resp:
    def __init__(s,body): s.body=json.dumps(body).encode()
    def read(s): return s.body
    def __enter__(s): return s
    def __exit__(s,*a): return False

def fake_urlopen(body):
    def f(req, timeout=None):
        captured["url"]=req.full_url
        captured["method"]=req.method
        captured["headers"]=dict(req.headers)
        captured["payload"]=json.loads(req.data)
        return Resp(body)
    return f

import urllib.request
CHK={"query":"@type:error service:webapp env:production","window":"2h","metric":"value"}

print("\n-- rum hits the RUM endpoint with the verified body shape --")
urllib.request.urlopen=fake_urlopen({"data":{"buckets":[{"computes":{"c0":7}}]}})
val,raw=core.run_rum(dict(CHK))
ck("path is the rum aggregate endpoint", captured["url"], "https://api.datadoghq.com/api/v2/rum/analytics/aggregate")
ck("POST", captured["method"], "POST")
ck("compute is count/total", captured["payload"]["compute"], [{"aggregation":"count","type":"total"}])
ck("filter carries the query", captured["payload"]["filter"]["query"], CHK["query"])
ck("from is relative", captured["payload"]["filter"]["from"], "now-2h")
ck("to is now", captured["payload"]["filter"]["to"], "now")
ck("api key header", captured["headers"].get("Dd-api-key"), "api")
ck("app key header", captured["headers"].get("Dd-application-key"), "app")
ck("count parsed", val, 7.0)
ck("raw mentions the window", "over 2h" in raw)

print("\n-- logs still hit the LOGS endpoint (no regression) --")
urllib.request.urlopen=fake_urlopen({"data":{"buckets":[{"computes":{"c0":3}}]}})
v,_=core.run_datadog({"query":"service:x","window":"30m","metric":"value"})
ck("logs path unchanged", captured["url"], "https://api.datadoghq.com/api/v2/logs/analytics/aggregate")
ck("logs count parsed", v, 3.0)

print("\n-- empty results --")
urllib.request.urlopen=fake_urlopen({"data":{"buckets":[]}})
v,raw=core.run_rum(dict(CHK)); ck("no buckets -> 0", v, 0.0); ck("raw says RUM", "RUM" in raw)
urllib.request.urlopen=fake_urlopen({"data":{"buckets":[{"computes":{}}]}})
v,_=core.run_rum(dict(CHK)); ck("empty computes -> 0", v, 0.0)

print("\n-- 403 explains the likely cause --")
def raise403(req, timeout=None):
    raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, io.BytesIO(b'{"errors":["Forbidden"]}'))
urllib.request.urlopen=raise403
try:
    core.run_rum(dict(CHK)); ck("raised", False)
except RuntimeError as e:
    ck("mentions 403", "403" in str(e))
    ck("names the scope problem", "read scope" in str(e))
    ck("says RUM specifically", "RUM" in str(e))

print("\n-- a 403 on logs mentions log scope, not RUM --")
try:
    core.run_datadog({"query":"x","window":"1h","metric":"value"}); ck("raised", False)
except RuntimeError as e:
    ck("log scope hint", "log read scope" in str(e))

print("\n-- evaluate() integrates rum like any other source --")
urllib.request.urlopen=fake_urlopen({"data":{"buckets":[{"computes":{"c0":2}}]}})
r=core.evaluate({"source":"rum","query":CHK["query"],"window":"2h","metric":"value",
                 "op":"lt","value":5.0,"healthy":"","label":"x:y"})
ck("passes when under threshold", r["state"], core.PASS)
r=core.evaluate({"source":"rum","query":CHK["query"],"window":"2h","metric":"value",
                 "op":"lt","value":1.0,"healthy":"","label":"x:y"})
ck("fails when over", r["state"], core.FAIL)

print("\n-- spec validation --")
ck("rum is a known source", "rum" in core.CONNECTORS)
p=os.path.join(SB,"active","r.toml")
open(p,"w").write('[[checks]]\nname="e"\nsource="rum"\nquery="@type:error"\nop="lt"\nvalue=5\n')
ck("loads", len(core.load_spec(p).checks), 1)
open(p,"w").write('[[checks]]\nname="e"\nsource="webrum"\nquery="x"\nop="lt"\nvalue=5\n')
try: core.load_spec(p); ck("rejects typo", False)
except core.SpecError as e: ck("rejects a near-miss source", "rum" in str(e))

print()
if fails: print(f"FAILED ({len(fails)}):"); [print("  -",f) for f in fails]; sys.exit(1)
print("all checks passed")
