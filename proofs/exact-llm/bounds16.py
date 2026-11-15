"""The certificate for exact-16 (exact_llm.Exact16): every product exact on each of its three routes, and no int64
overflow in the work around the products. Writes bounds-16.json.

Every product operand is an integer with |a| <= 2^15 - 1 (asserted by block16 at run time; weights by
int16_weights; p held at 2^15 - 1). A product over n inputs then has |partial sums| <= n (2^15 - 1)^2 on the f64
route; on the f32 route each byte product term is at most 128 x 128 = 2^14 and a chunk holds 1,024 inputs; on the
i8 route each term is a product of two unsigned bytes, at most 255 x 255, and the accumulator is int32. The int64
rows use the clamps of Exact (the same sites) and the 16-bit weights with their row scales.

The bound that matters is what a kernel may hold inside, not only its output: "kernel_intermediate" states, per
route, the largest value any partial sum can take in any order and grouping, and the narrowest type that holds it.

usage: python bounds16.py
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import exact_llm as X  # noqa: E402

W16 = X.int16_weights()
W = X.int_weights()
C = {k: v << X.A for k, v in X.CLAMP.items()}
L53, L31, L24, L63 = 1 << 53, 1 << 31, 1 << 24, 1 << 63
M = X.LIM16
SITE = {"q_proj": "attention input", "k_proj": "attention input", "v_proj": "attention input", "o_proj": "o input",
        "gate_proj": "mlp input", "up_proj": "mlp input", "down_proj": "down input",
        "embed_tokens": "logits input"}


def shmax(c):
    """Largest block shift for inputs within [-c, c]: bitlen(c) - 15, plus one for the rounding."""
    return max(0, c.bit_length() - (X.B16 - 1)) + 1


T_MAX = X.ROPE_POS                                       # keys per query: at most the 512 rotary positions
products = {}
for kind, site in SITE.items():
    names = [n for n in W16 if n.endswith(kind + ".weight")]
    n_in = W16[names[0]].shape[0]
    products[kind] = {"site": site, "inputs": n_in, "matrices": len(names)}
products["scores q.k"] = {"site": "q, k", "inputs": X.HEAD, "matrices": 0}
products["context p.vh, p.vl"] = {"site": "p; v = 2^15 vh + vl", "inputs": T_MAX, "matrices": 0}

routes = []
for kind, p in products.items():
    n = p["inputs"]
    f64 = n * M * M
    f32 = min(n, X.CHUNK32) * 128 * 128
    i8 = n * 255 * 255
    assert f64 < L53 and f32 <= L24 and i8 < L31, kind
    routes.append({"product": kind, "inputs": n, "f64_bound": f64, "f64_log2": round(math.log2(f64), 3),
                   "f32_chunk": min(n, X.CHUNK32), "f32_bound": f32, "f32_log2": round(math.log2(f32), 3),
                   "i8_bound": i8, "i8_log2": round(math.log2(i8), 3)})

# int64 around the products, per matrix kind: T = 2^sh S + peeled terms, and the rounded output y
rows, lin_out, gs = [], 0, {}
for kind, site in SITE.items():
    c = C[site]
    sh = shmax(c)
    big_T, big_y = 0, 0
    for name in [n for n in W16 if n.endswith(kind + ".weight")]:
        w, g = W16[name], np.asarray(W16[name + ".g"])
        for s in range(0, w.shape[1], 8192):
            a = np.abs(np.asarray(w[:, s:s + 8192], dtype=np.int64))
            col = a.sum(axis=0)                                   # sum of |w16| over one output's inputs
            # |2^sh x16| <= c + 2^(sh-1) for every input; the peeled inputs (|x| <= c) are within the same bound
            t = col * (c + (1 << (sh - 1)))
            big_T = max(big_T, int(t.max()))
            gg = g[s:s + 8192]
            big_y = max(big_y, int(((t + (1 << (gg - 1).clip(0))) >> gg).max()) + 1)
        lo, hi = gs.get(kind, (99, -99))
        gs[kind] = (min(lo, int(g.min())), max(hi, int(g.max())))
    rows.append(("%s: 2^sh x16 . w16 plus the peeled terms (sh <= %d), plus rounding constant" % (kind, sh),
                 big_T + (1 << (gs[kind][1] - 1))))
    if kind != "embed_tokens":
        lin_out = max(lin_out, big_y)
    else:                                                 # int32 storage: asserted on every call, as in Exact
        rows.append(("logits: |y| in int64 (stored as int32; |y| < 2^31 asserted on every call)", big_y))
N_MAX = max(p["inputs"] for p in products.values())
shq, shk = shmax(C["q"]), shmax(C["k"])
qk = X.HEAD * M * M
sp = ((1 << X.A) + T_MAX) // 2                       # sum of p at 2^-15 (rounded halves) over one row
vh = (C["v"] >> (X.B16 - 1)) + 1                     # |v >> 15| within the clamp
assert vh <= M, "vh fits 16 bits"
pv = sp * (vh << (X.B16 - 1)) + sp * M                # 2^15 p.vh + p.vl, at 2^-31
normw = max(int(np.abs(np.asarray(W[n])).max()) for n in W if W[n].ndim == 1)
res = C["residual"]
rows += [
    ("residual: clamp plus one linear output", res + lin_out),
    ("rope: q or k (a linear output) times cos, two terms", 2 * lin_out * (1 << X.ROPE)),
    ("scores: q16 . k16 shifted by sh_q + sh_k (<= %d + %d), at 2^-32" % (shq, shk), qk << (shq + shk)),
    ("scores: max minus score", 2 * (qk << (shq + shk))),
    ("context: 2^15 p16 . vh + p16 . vl (|vh| <= %d, vl < 2^15), at 2^-31" % vh, pv),
    ("peel key: |x| 2^11 + index, |x| within the largest clamp", (max(C[s] for s in SITE.values()) << 11) + 2047),
    ("i8 route: sum of u_a u_b, u = a + 2^15 <= 2^16 - 1, over the widest product (n = %d)" % N_MAX,
     N_MAX * ((1 << 16) - 1) ** 2),
    ("i8 route: 2^15 (row sum of a + column sum of b) + n 2^30", (2 * N_MAX * M << 15) + (N_MAX << 30)),
    ("rms: y * norm weight (as Exact)", (25 << X.A) * normw),
    ("exp interpolation, softmax, silu, gate times up: as Exact (bounds.json)", C["gate"] * C["up"]),
]
for what, v in rows:
    assert v < L63, what
out = {"operands": "every product operand an integer with |a| <= 2^15 - 1 = %d" % M,
       "routes": {"f64": "one float64 product; exact while n (2^15 - 1)^2 < 2^53, n below 2^23",
                  "f32": "a = 256 a1 + a0, a0 in [-128, 127], a1 in [-128, 128]; four float32 products in chunks of "
                         "1,024 inputs; |partial sums| <= 1024 x 2^14 = 2^24. The digits need 8 significant bits, so "
                         "they are exact as TF32 (11) and bfloat16 (8) inputs too, with float32 accumulation",
                  "i8": "u = a + 2^15 in [1, 2^16 - 1], u = 256 u1 + u0, u1 and u0 in [0, 255] (uint8), the same for "
                        "b; four int32 MatMulInteger products of uint8 by uint8; partial sums <= n 255^2 < 2^31, "
                        "n <= 33,025; then a b = u_a u_b - 2^15 (row sums of a + column sums of b) - n 2^30 in int64"},
       "kernel_intermediate": [
           {"route": "f64", "largest partial sum, any order or grouping, with or without fused multiply-add":
            "n (2^15 - 1)^2 < 2^53 (n = %d: 2^%.3f)" % (N_MAX, math.log2(N_MAX * M * M)),
            "why exact": "every product and every partial sum is an integer below 2^53, and every integer below 2^53 "
                         "is a float64; a sum or a fused a b + c whose exact value is a float64 is returned exactly"},
           {"route": "f32", "largest partial sum, any order or grouping, with or without fused multiply-add":
            "1,024 x 128 x 128 = 2^24 within a chunk; the chunks are added in int64",
            "why exact": "every digit product is an integer of magnitude at most 2^14 and every partial sum of a "
                         "chunk, in any order, is an integer of magnitude at most 2^24; every integer of magnitude "
                         "at most 2^24 is a float32, so no addition or fused multiply-add rounds. The digits have at "
                         "most 8 significant bits (|d| <= 128), so they are also exact as TF32 or bfloat16 inputs"},
           {"route": "i8", "kernel intermediate, int16 pair sum": "2 x 255 x 255 = 130,050",
            "why exact": "one uint8 by uint8 product (up to 65,025) does not fit a signed 16-bit lane, so a uint8 by "
                         "uint8 kernel has to widen before it adds: a pair needs 18 bits, any sum of k products is at "
                         "most k 255^2 < 2^31 for k <= 33,025. routes_test.py's 'all +max' puts every pair at "
                         "130,050 and fails on a kernel that keeps less. uint8 by uint8 is the MatMulInteger type "
                         "pair every onnxruntime version implements",
            "the digits it replaces": "a1 = a >> 8 (int8), a0 = a & 255 (uint8): a uint8 by int8 kernel without "
                                      "VNNI adds adjacent pairs in int16 with saturation, and 2 x 255 x 128 = 65,280 "
                                      "> 32,767; a 7-bit unsigned digit (2 x 127 x 128 = 32,512) would hold, at six "
                                      "products instead of four. onnxruntime 1.23.2 (macOS x86-64) could not build a "
                                      "MatMulInteger session for one of the pairs with an int8 operand "
                                      "(NOT_IMPLEMENTED)"}],
       "products": routes,
       "weight_row_scales_g": {k: list(v) for k, v in gs.items()},
       "block_shift_max": {s: shmax(C[s]) for s in sorted(set(SITE.values()) | {"q", "k"})},
       "int64": [{"operation": w, "largest_magnitude": v, "log2": round(math.log2(v), 3)} for w, v in rows]}
json.dump(out, open(os.path.join(HERE, "bounds-16.json"), "w"), indent=1)
print("bounds-16: %d product kinds on 3 routes" % len(routes))
for r in routes:
    print("  %-14s n %5d  f64 2^%.3f  f32 2^%.3f (chunk %d)  i8 2^%.3f" % (
        r["product"], r["inputs"], r["f64_log2"], r["f32_log2"], r["f32_chunk"], r["i8_log2"]))
print("  weight row scales g:", ", ".join("%s %d..%d" % (k, *v) for k, v in gs.items()))
print("  kernel intermediate: f64 partial sums < 2^53; f32 partial sums <= 2^24 per chunk; i8 uint8 x uint8, a pair "
      "2 x 255^2 = 130,050 (no int16 lane holds one product), any k products < 2^31 for k <= 33,025")
print("  int64: %d operations below 2^63, largest 2^%.3f; wrote bounds-16.json" % (
    len(rows), max(math.log2(v) for _, v in rows)))
