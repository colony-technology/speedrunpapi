"""Driver: for each batch of 8 prompts, the plain run, the traced run, the checks, the planted faults; trace deleted after.

    PY run.py --exact DIR --cache CACHE --batches 0 1 ... [--faults N] [--out results.jsonl]
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
ap.add_argument("--exact", type=Path, required=True)
ap.add_argument("--cache", type=Path, required=True)
ap.add_argument("--batches", type=int, nargs="+", required=True)
ap.add_argument("--faults", type=int, default=0, help="planted faults per batch")
ap.add_argument("--out", type=Path, default=HERE / "results.jsonl")
ap.add_argument("--skip-plain", action="store_true")
a = ap.parse_args()
env = dict(os.environ, EXACT_LLM_CACHE=str(a.cache))
py = sys.executable


def run(args):
    t0 = time.perf_counter()
    r = subprocess.run([py, "-I"] + [str(x) for x in args], capture_output=True, text=True, env=env)
    line = [l for l in r.stdout.splitlines() if l.startswith("{")]
    res = json.loads(line[-1]) if line else {"error": r.stderr[-800:]}
    res["wall_s"] = round(time.perf_counter() - t0, 2)
    res["exit"] = r.returncode
    return res


for b in a.batches:
    tdir = HERE / ("trace_b%d" % b)
    rec = {"batch": b}
    if not a.skip_plain:
        rec["plain"] = run([HERE / "trace.py", "--exact", a.exact, "--batch-index", b, "--plain"])
    rec["trace"] = run([HERE / "trace.py", "--exact", a.exact, "--batch-index", b, "--out", tdir])
    base = [HERE / "check.py", "--exact", a.exact, "--cache", a.cache, "--wdir", HERE / "w", "--trace", tdir]
    rec["check_freivalds"] = run(base + ["--logits", "freivalds"])
    rec["check_direct"] = run(base + ["--logits", "direct"])
    if a.faults:
        rec["faults"] = run(base + ["--logits", "freivalds", "--faults", a.faults, "--seed", 1000 + b])
    with open(a.out, "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(json.dumps({k: (v if not isinstance(v, dict) else {kk: v.get(kk) for kk in ("verdict", "wall_s", "check_s", "prep_s", "trace_bytes", "caught", "faults", "exit", "error")})
                      for k, v in rec.items()}), flush=True)
    shutil.rmtree(tdir)
