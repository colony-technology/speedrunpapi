"""Negative controls on one batch, each a run of the unchanged checker that must reject:
  1. wrong claimed token (--claim-token), several places;
  2. faulty trace files on disk: one integer of one hint changed by one, the rest hard-linked to the honest trace;
  3. a prover with one weight changed by one unit (trace.py --perturb-weight), checked against the pinned weights.
Also the honest trace's bytes by kind of product.

    PY controls.py --exact DIR --cache CACHE --batch 0 [--out controls.jsonl]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--exact", type=Path, required=True)
ap.add_argument("--cache", type=Path, required=True)
ap.add_argument("--batch", type=int, default=0)
ap.add_argument("--out", type=Path, default=HERE / "controls.jsonl")
a = ap.parse_args()
env = dict(os.environ, EXACT_LLM_CACHE=str(a.cache))
py = sys.executable
rng = np.random.default_rng(77)


def run(args):
    t0 = time.perf_counter()
    r = subprocess.run([py, "-I"] + [str(x) for x in args], capture_output=True, text=True, env=env)
    line = [l for l in r.stdout.splitlines() if l.startswith("{")]
    res = json.loads(line[-1]) if line else {"error": r.stderr[-800:]}
    res["wall_s"] = round(time.perf_counter() - t0, 2)
    res["exit"] = r.returncode
    return res


def check(tdir, extra=()):
    return run([HERE / "check.py", "--exact", a.exact, "--cache", a.cache, "--wdir", HERE / "w", "--trace", tdir,
                "--logits", "freivalds"] + list(extra))


def emit(rec):
    with open(a.out, "a") as f:
        f.write(json.dumps(rec) + "\n")
    keep = ("verdict", "exit", "wall_s", "error")
    print(json.dumps({k: (v if not isinstance(v, dict) else {kk: v.get(kk) for kk in keep}) for k, v in rec.items()}), flush=True)


honest = HERE / ("ctl_honest_b%d" % a.batch)
emit({"control": "trace", "trace": run([HERE / "trace.py", "--exact", a.exact, "--batch-index", a.batch, "--out", honest])})
claim = json.load(open(honest / "claim.json"))
calls = claim["calls"]

# bytes by kind
by = {}
for c in range(calls):
    z = np.load(honest / ("call_%d.npz" % c))
    for k in z.files:
        kind = k.split(".")[-1]
        by[kind] = by.get(kind, 0) + z[k].nbytes
emit({"control": "bytes_by_kind", "bytes": by, "total": sum(by.values()), "calls": calls})

# 0. the honest trace accepted (same files the faulty copies link to)
emit({"control": "honest", "check": check(honest)})

# 1. wrong claimed tokens
for b, t in ((0, 0), (3, 10), (7, calls - 1)):
    v = (claim["continuations"][b][t] + 1) % 49152
    emit({"control": "claim_token", "row": b, "token": t, "id": v, "check": check(honest, ["--claim-token", "%d:%d:%d" % (b, t, v)])})

# 2. faulty trace files
sites = [(0, "L0.q"), (0, "L12.s"), (int(rng.integers(1, calls)), "L5.ctx"), (int(rng.integers(1, calls)), "L29.down"),
         (calls - 1, "logits"), (int(rng.integers(1, calls)), "L17.gate")]
for c, key in sites:
    fdir = HERE / ("ctl_fault_b%d" % a.batch)
    fdir.mkdir()
    for f in honest.iterdir():
        os.link(f, fdir / f.name)
    z = np.load(honest / ("call_%d.npz" % c))
    arrs = {k: z[k] for k in z.files}
    S = arrs[key].copy()
    idx = tuple(int(rng.integers(0, d)) for d in S.shape)
    d = 1 if rng.integers(0, 2) else -1
    S[idx] += d
    arrs[key] = S
    (fdir / ("call_%d.npz" % c)).unlink()
    np.savez(fdir / ("call_%d.npz" % c), **arrs)
    emit({"control": "fault_file", "call": c, "key": key, "index": list(idx), "delta": d, "check": check(fdir)})
    shutil.rmtree(fdir)

# 3. perturbed weight in the prover
for spec in ("model.layers.3.mlp.up_proj.weight:100:200", "model.layers.20.self_attn.v_proj.weight:5:100"):
    pdir = HERE / ("ctl_perturb_b%d" % a.batch)
    tr = run([HERE / "trace.py", "--exact", a.exact, "--batch-index", a.batch, "--out", pdir, "--perturb-weight", spec])
    pc = json.load(open(pdir / "claim.json"))
    same = sum(int(x == y) for r1, r2 in zip(pc["continuations"], claim["continuations"]) for x, y in zip(r1, r2))
    emit({"control": "perturb_weight", "weight": spec, "trace": tr, "tokens_same_as_honest": same,
          "tokens": sum(len(r) for r in claim["continuations"]), "check": check(pdir)})
    shutil.rmtree(pdir)

shutil.rmtree(honest)
