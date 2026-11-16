"""One command: the checker's verdicts on one batch of 8 prompts, honest and planted.

    python reproduce.py [--batch 0]

Needs ../exact-llm with its cache filled (`python exact_llm.py check` there, or EXACT_LLM_CACHE set as for it).
Steps, each a separate process:
  1. the prover (trace.py) runs the batch and writes its trace;
  2. check.py, logits by Freivalds, with 125 random planted faults and one at every (kind, layer): accept, all caught;
  3. check.py, logits computed directly: accept;
  4. three wrong claimed tokens: each rejected;
  5. spot.py: every unit of the committed trace checked alone (0 fail), then one commit-and-open run at k = 16, 64, 256;
  6. two provers with one weight changed by one unit: the same 384 tokens as the honest run, each rejected;
     for the first, the number of units that fail (spot.py map).
Prints only what does not depend on the machine or the random draws; times and full records go to reproduce.jsonl.
Exit 0 if every line is as expected.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--batch", type=int, default=0)
ap.add_argument("--exact", type=Path, default=HERE.parent / "exact-llm")
a = ap.parse_args()
cache = Path(os.environ.get("EXACT_LLM_CACHE", a.exact / ".cache"))
env = dict(os.environ, EXACT_LLM_CACHE=str(cache))
py = sys.executable
log = open(HERE / "reproduce.jsonl", "w")
ok = True


def run(args):
    t0 = time.perf_counter()
    r = subprocess.run([py, "-I"] + [str(x) for x in args], capture_output=True, text=True, env=env)
    line = [l for l in r.stdout.splitlines() if l.startswith("{")]
    res = json.loads(line[-1]) if line else {"error": r.stderr[-1500:]}
    res["wall_s"], res["exit"] = round(time.perf_counter() - t0, 2), r.returncode
    log.write(json.dumps({"args": [str(x) for x in args[1:]], "result": res}) + "\n")
    log.flush()
    return res


def say(text, good):
    global ok
    ok &= bool(good)
    print(("ok    " if good else "FAIL  ") + text, flush=True)


common = ["--exact", a.exact, "--cache", cache, "--wdir", HERE / "w"]
honest = HERE / ("trace_honest_b%d" % a.batch)
tr = run([HERE / "trace.py", "--exact", a.exact, "--batch-index", a.batch, "--out", honest, "--resid"])
claim = json.load(open(honest / "claim.json"))
tokens = sum(len(c) for c in claim["continuations"])
say("prover: batch %d, %d forward calls, %d claimed tokens" % (a.batch, tr.get("calls", -1), tokens), tr.get("exit") == 0)

ck = run([HERE / "check.py"] + common + ["--trace", honest, "--logits", "freivalds", "--faults", 125, "--grid", "--seed", 3000])
say("check, Freivalds logits: %s; %d of %d planted faults caught, %d of 271 (kind, layer) places"
    % (ck.get("verdict"), ck.get("caught", -1), ck.get("faults", -1), ck.get("pairs_caught", -1)),
    ck.get("verdict") == "accept" and ck.get("caught") == ck.get("faults") and ck.get("pairs_caught") == 271)
cd = run([HERE / "check.py"] + common + ["--trace", honest, "--logits", "direct"])
say("check, direct logits: %s" % cd.get("verdict"), cd.get("verdict") == "accept")

for spec in ("0:0:199", "3:10:199", "7:47:505"):
    b, t, v = (int(z) for z in spec.split(":"))
    if claim["continuations"][b][t] == v:
        v = (v + 1) % 49152
        spec = "%d:%d:%d" % (b, t, v)
    c = run([HERE / "check.py"] + common + ["--trace", honest, "--claim-token", spec])
    say("wrong claimed token (row %d, token %d := %d): %s" % (b, t, v, c.get("verdict")), str(c.get("verdict", "")).startswith("reject"))

m = run([HERE / "spot.py", "map"] + common + ["--trace", honest])
say("commitment: %d leaves, %d units; units failing on the honest trace: %d" % (m.get("leaves", -1), m.get("units", -1), m.get("failing_units", -1)),
    m.get("failing_units") == 0)
s = run([HERE / "spot.py", "spot"] + common + ["--trace", honest, "--reps", 1])
for r in s.get("runs", []):
    say("commit and open, k = %d: %d failing, %d bad paths" % (r["k"], r["failing"], r["bad_paths"]), r["failing"] == 0 and r["bad_paths"] == 0)
shutil.rmtree(honest)

for q, spec in enumerate(("model.layers.3.mlp.up_proj.weight:100:200", "model.layers.20.self_attn.v_proj.weight:5:100")):
    pdir = HERE / ("trace_perturb_b%d" % a.batch)
    run([HERE / "trace.py", "--exact", a.exact, "--batch-index", a.batch, "--out", pdir, "--resid", "--perturb-weight", spec])
    pc = json.load(open(pdir / "claim.json"))
    same = sum(x == y for c1, c2 in zip(pc["continuations"], claim["continuations"]) for x, y in zip(c1, c2))
    c = run([HERE / "check.py"] + common + ["--trace", pdir])
    say("prover with %s + 1: %d of %d tokens as honest; %s" % (spec, same, tokens, c.get("verdict")), str(c.get("verdict", "")).startswith("reject"))
    if q == 0:
        m = run([HERE / "spot.py", "map"] + common + ["--trace", pdir])
        say("  units failing: %d, all in layer %s" % (m.get("failing_units", -1), m.get("failing_layers")), m.get("failing_units", 0) > 0)
    shutil.rmtree(pdir)

print("ALL AS EXPECTED" if ok else "NOT AS EXPECTED")
raise SystemExit(0 if ok else 1)
