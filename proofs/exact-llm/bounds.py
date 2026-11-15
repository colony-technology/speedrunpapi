"""The certificate that every product in exact_llm.py is exact and that no int64 overflows. Writes bounds.json.

Matrix products run in float64 on integer-valued arrays. float64 holds every integer up to 2^53 exactly, so a dot
product is exact in any summation order, with or without fused multiply-add, if the sum of the magnitudes of its
terms is at most 2^53. For y = x W with x clamped to [-C, C] (integer units), that sum is at most C times the
largest sum of |W| over one output's inputs. This script computes that row sum for every weight matrix from the
integer weights the model uses, with the clamp of its input site, and asserts the product is below 2^53. The
products of activations are bounded the same way: scores q.k (64 terms, each at most C_q C_k) and the context p.v
(the probabilities of a row are floors of numbers that sum to 2^16, so the sum is at most 2^16 C_v).

It lists every element-wise int64 operation with its largest possible magnitude, each below 2^63 (the isqrt inputs
below 2^62). Every isqrt and every floor division asserts its bracket at run time (exact_llm.isqrt, exact_llm.fdiv).

usage: python bounds.py
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import exact_llm as X  # noqa: E402

W = X.int_weights()
C = {k: v << X.A for k, v in X.CLAMP.items()}
LIM, L63, L62 = 1 << 53, 1 << 63, 1 << 62
out = {"scales": {"activation_fraction_bits": X.A, "weight_fraction_bits": X.WB, "rope_fraction_bits": X.ROPE,
                  "clamps_real": X.CLAMP, "norm_bits": X.NORM_BITS},
       "limit": "2^53 = %d" % LIM, "weight_products": [], "activation_products": [], "int64": []}
SITE = {"q_proj": "attention input", "k_proj": "attention input", "v_proj": "attention input", "o_proj": "o input",
        "gate_proj": "mlp input", "up_proj": "mlp input", "down_proj": "down input"}
worst, kinds, ymax, summed = 0, {}, 0, 0
for name in sorted(W):
    a = W[name]
    if a.ndim != 2 or name == "model.embed_tokens.weight":
        continue
    kind = name.split(".")[-2]
    n = X.SPLIT.get(SITE[kind], a.shape[0])                                  # inputs per product (chunk)
    aa = np.abs(np.asarray(a, dtype=np.int64))                                # [in, out]: one output sums over in
    row = max(int(aa[s:s + n].sum(axis=0).max()) for s in range(0, a.shape[0], n))
    bound = C[SITE[kind]] * row
    assert bound < LIM, name
    worst = max(worst, bound)
    full = C[SITE[kind]] * int(aa.sum(axis=0).max())                         # the chunks added in int64
    summed = max(summed, full)
    ymax = max(ymax, full >> X.WB)
    k = kinds.setdefault(kind, {"site": SITE[kind], "clamp_int": C[SITE[kind]], "inputs_per_product": n,
                                "max_row_sum_abs_int": 0})
    k["max_row_sum_abs_int"] = max(k["max_row_sum_abs_int"], row)
E = W["model.embed_tokens.weight"]
erow = max(int(np.abs(np.asarray(E[s:s + 8192], dtype=np.int64)).sum(axis=1).max()) for s in range(0, X.VOCAB, 8192))
kinds["lm_head (tied embedding)"] = {"site": "logits input", "clamp_int": C["logits input"], "max_row_sum_abs_int": erow}
assert C["logits input"] * erow < LIM
for kind, k in kinds.items():
    b = k["clamp_int"] * k["max_row_sum_abs_int"]
    out["weight_products"].append(dict(k, matrix=kind, bound=b, log2=round(math.log2(b), 3)))
qk = X.HEAD * C["q"] * C["k"]
pv = (1 << X.A) * C["v"]
assert qk < LIM and pv < LIM
out["activation_products"] = [
    {"product": "scores q.k", "bound": "64 C_q C_k", "value": qk, "log2": round(math.log2(qk), 3)},
    {"product": "context p.v", "bound": "2^16 C_v", "value": pv, "log2": round(math.log2(pv), 3)}]

normw = max(int(np.abs(np.asarray(W[n])).max()) for n in W if W[n].ndim == 1)
res = C["residual"]
lin_out = ymax                                  # largest linear output, integer units at 2^-16
rows = [
    ("linear: product (below 2^53) plus rounding constant", worst + (1 << (X.WB - 1))),
    ("linear, chunked: the chunks added in int64, plus rounding constant", summed + (1 << (X.WB - 1))),
    ("residual: clamp plus one linear output", res + lin_out),
    ("rms: sum of (x >> s)^2 over 576, s chosen so max |x >> s| < 2^26 (isqrt input, below 2^62)", 576 * (1 << 52)),
    ("rms: x * 2^16 (s = 0, x within the residual clamp)", res << X.A),
    ("rms: y * norm weight (|y| <= 25 * 2^16, asserted at run time: no coordinate exceeds sqrt(576) times the "
     "root mean square)", (25 << X.A) * normw),
    ("rms: max |x| below 2^42, so the shift is at most 16 (asserted at run time)", res),
    ("rope: q or k (a linear output) times cos, two terms", 2 * lin_out * (1 << X.ROPE)),
    ("scores: max minus score", 2 * qk),
    ("exp interpolation: E * 256", (1 << 24) << 8),
    ("softmax: e * 2^16", (1 << 24) << X.A),
    ("silu interpolation: S * 256", (16 << X.A) << 8),
    ("gate times up: silu(g) u, both clamped", C["gate"] * C["up"]),
    ("logits: product (below 2^53) plus rounding constant", C["logits input"] * erow + (1 << (X.WB - 1))),
]
for what, v in rows:
    limit = L62 if "isqrt" in what else L63
    assert v < limit, what
    out["int64"].append({"operation": what, "largest_magnitude": v, "log2": round(math.log2(v), 3)})
out["largest_weight_product_bound_log2"] = round(math.log2(worst), 3)
out["brackets"] = {"isqrt": "s^2 <= n < (s + 1)^2 asserted on every call (RMS norm)",
                   "floor division": "q d <= n < (q + 1) d asserted on every call (RMS mean, normalised value, "
                                     "softmax probabilities)"}
json.dump(out, open(os.path.join(HERE, "bounds.json"), "w"), indent=1)
print("bounds: %d weight matrices over 7 kinds and the tied head; largest C x row sum = 2^%.3f; scores 2^%.3f; "
      "context 2^%.3f; all below 2^53" % (sum(1 for n in W if W[n].ndim == 2) - 1, math.log2(worst),
                                          math.log2(qk), math.log2(pv)))
for kind, k in kinds.items():
    print("  %-26s clamp 2^%d x row sum %d = 2^%.3f" % (kind, int(math.log2(k["clamp_int"])), k["max_row_sum_abs_int"],
                                                     math.log2(k["clamp_int"] * k["max_row_sum_abs_int"])))
print("  int64: %d operations below their limits; wrote bounds.json" % len(rows))
