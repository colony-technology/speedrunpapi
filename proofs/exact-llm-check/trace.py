"""The prover's side: runs the exact model (exact_llm.py, unchanged, imported) on one batch of the 64 prompts and
records, for every forward call, the exact integer sum of every product before its rounding shift.

    EXACT_LLM_CACHE=... python3 trace.py --exact DIR/proofs/exact-llm --batch-index I --out TRACE_DIR [--plain]

Per forward call c, TRACE_DIR/call_c.npz holds int64 arrays, keys "L{i}.{q,k,v,s,ctx,o,gate,up,down}" and "logits":
  q k v o gate up down : clamp(x) @ W, [rows, out]           (down: the sum of its six chunks, as the model sums them)
  s                    : clamp(q) @ clamp(k)^T, [B, 3, 3, L, T]
  ctx                  : p @ clamp(v), [B, 3, 3, L, 64]
  logits               : clamp(h) @ E^T, [rows, 49152]
TRACE_DIR/claim.json: the batch's prompts' index range and the claimed continuations.
--plain runs the same batch with the unmodified Exact class and records nothing (the run's own time).
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--exact", type=Path, required=True)
ap.add_argument("--batch-index", type=int, required=True)
ap.add_argument("--out", type=Path)
ap.add_argument("--plain", action="store_true")
ap.add_argument("--perturb-weight", help="NAME:IN:OUT, add one unit to that integer weight (planted-model control)")
ap.add_argument("--resid", action="store_true", help="also record the residual entering each layer (L{i}.r0) and the final one")
a = ap.parse_args()
sys.path.insert(0, str(a.exact.resolve()))
import exact_llm as X                                                        # noqa: E402


class Tracing(X.Exact):
    resid = False

    def __init__(self, *k, **kw):
        super().__init__(*k, **kw)
        self.rec = {}
        self.layer = 0
        self.kind = None

    def clamp(self, x, site, layer=None):
        y = super().clamp(x, site, layer)
        if self.resid and site == "residual":                              # first residual clamp of layer i: its input
            key = "final" if layer == X.LAYERS else "L%d.r0" % layer
            self.rec.setdefault(key, y)
        return y

    def linear(self, x, name, site):
        xc = self.clamp(x, site).astype(np.float64)
        w = self.matrix(name)
        n = X.SPLIT.get(site, w.shape[0])
        y = sum((xc[:, s:s + n] @ w[s:s + n]).astype(np.int64) for s in range(0, w.shape[0], n))
        key = name.split(".")[-2]                                            # q_proj ... down_proj
        self.rec["L%d.%s" % (int(name.split(".")[2]), key[:-5] if key.endswith("_proj") else key)] = y
        return X.rshift_round(y, X.WB)

    def attention(self, q, k, v, kvalid):
        B, _, L, _ = q.shape
        qc = self.clamp(q, "q").astype(np.float64).reshape(B, X.KV, X.HEADS // X.KV, L, X.HEAD)
        kc = self.clamp(k, "k").astype(np.float64)[:, :, None]
        vc = self.clamp(v, "v").astype(np.float64)[:, :, None]
        s = (qc @ kc.swapaxes(-1, -2)).astype(np.int64)
        key = kvalid[:, None, None]
        m = np.where(key, s, -(1 << 62)).max(-1, keepdims=True)
        t = np.maximum(m - s, 0) >> (X.A + 3)
        e = np.where(key, self.exp(t), 0)
        p = X.fdiv(e << X.A, e.sum(-1, keepdims=True))
        ctx = (p.astype(np.float64) @ vc).astype(np.int64)
        self.rec["L%d.s" % self.layer] = s
        self.rec["L%d.ctx" % self.layer] = ctx
        self.layer += 1
        return X.rshift_round(ctx, X.A).reshape(B, X.HEADS, L, X.HEAD)

    def logits(self, h):
        hc = self.clamp(h, "logits input").astype(np.float64)
        out = np.empty((h.shape[0], X.VOCAB), dtype=np.int32)
        sums = np.empty((h.shape[0], X.VOCAB), dtype=np.int64)
        for s in range(0, X.VOCAB, 8192):
            e = np.asarray(self.E[s:s + 8192], dtype=np.float64)
            y = (hc @ e.T).astype(np.int64)
            sums[:, s:s + 8192] = y
            blk = X.rshift_round(y, X.WB)
            assert np.abs(blk).max() < (1 << 31)
            out[:, s:s + 8192] = blk
        self.rec["logits"] = sums
        return out

    def forward(self, ids, pos, cache, kvalid):
        self.rec, self.layer = {}, 0
        out = super().forward(ids, pos, cache, kvalid)
        np.savez(self.dir / ("call_%d.npz" % self.ncall), **self.rec)
        self.bytes += sum(v.nbytes for v in self.rec.values())
        self.ncall += 1
        return out


texts = X.prompts()[a.batch_index * 8:(a.batch_index + 1) * 8]
W = None
if a.perturb_weight:
    name, i, j = a.perturb_weight.split(":")
    W = dict(X.int_weights())
    w = np.array(W[name])
    w[int(i), int(j)] += 1
    W[name] = w
if a.plain:
    model = X.Exact(W)
    t0 = time.perf_counter()
    cont = X.run_prompts(model, X.tokenizer(), texts, 8)
    print(json.dumps({"batch": a.batch_index, "run_s": time.perf_counter() - t0, "continuations": cont}))
    raise SystemExit(0)
a.out.mkdir(parents=True, exist_ok=True)
model = Tracing(W)
model.dir, model.ncall, model.bytes, model.resid = a.out, 0, 0, a.resid
t0 = time.perf_counter()
cont = X.run_prompts(model, X.tokenizer(), texts, 8)
dt = time.perf_counter() - t0
json.dump({"batch": a.batch_index, "prompts": [a.batch_index * 8, a.batch_index * 8 + len(texts)], "continuations": cont,
           "calls": model.ncall, "trace_bytes": model.bytes, "trace_run_s": dt, "clamped": model.clamped},
          open(a.out / "claim.json", "w"))
print(json.dumps({"batch": a.batch_index, "calls": model.ncall, "trace_bytes": model.bytes, "trace_run_s": round(dt, 2)}))
