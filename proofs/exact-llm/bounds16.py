"""The certificate for exact-16 (exact_llm.Exact16): every product exact on each of its three routes, and no int64
overflow in the work around the products. Writes bounds-16.json (SmolLM2-135M) or bounds-16-<model>.json.

Every product operand is an integer with |a| <= 2^15 - 1 (asserted by block16 at run time; weights by
int16_weights; p held at 2^15 - 1). A product over n inputs then has |partial sums| <= n (2^15 - 1)^2 on the f64
route; on the f32 route each byte product term is at most 128 x 128 = 2^14 and a chunk holds 1,024 inputs; on the
i8 route each term is a product of two unsigned bytes, at most 255 x 255, and the accumulator is int32.

The clamps are by rule (exact_llm.clamps16): for each site the largest power of two at which every int64 row of
exact_llm.bounds16_rows stays below its limit, from the config and the 16-bit weights' column sums and row scales
(exact_llm.weight_stats16). This script lists those rows with the clamps, the clamp-free rows, and, when a run has
recorded them (record/peaks-16<model>.json, from `exact_llm.py hash --engine exact16-f64 --peaks FILE`), the
measured peak, the margin and the count of clamped values of every site.

The bound that matters is what a kernel may hold inside, not only its output: "kernel_intermediate" states, per
route, the largest value any partial sum can take in any order and grouping, and the narrowest type that holds it.

usage: python bounds16.py [--model M]
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import exact_llm as X  # noqa: E402

if "--model" in sys.argv:
    X.use_model(sys.argv[sys.argv.index("--model") + 1])
st = X.weight_stats16()
CL = X.clamps16(st)                                       # real units
C = {k: v << X.A for k, v in CL.items()}                  # integers at 2^-16
W = X.int_weights(small=True)
L53, L31, L24, L63 = 1 << 53, 1 << 31, 1 << 24, 1 << 63
M = X.LIM16

T_MAX = X.ROPE_POS                                       # keys per query: at most the 512 rotary positions
products = {k: {"site": v["site"], "inputs": v["inputs"], "matrices": v["matrices"]} for k, v in st.items()}
products["scores q.k"] = {"site": "q, k", "inputs": X.HEAD, "matrices": 0}
products["context p.vh, p.vl"] = {"site": "p; v = 2^15 vh + vl", "inputs": T_MAX, "matrices": 0}

routes = []
for kind, p in products.items():
    n = p["inputs"]
    f64 = n * M * M
    f32 = min(n, X.CHUNK32) * 128 * 128
    i8 = n * 255 * 255
    assert f64 < L53 and f32 <= L24 and i8 < L31 and n <= X.N_I8, kind
    routes.append({"product": kind, "inputs": n, "f64_bound": f64, "f64_log2": round(math.log2(f64), 3),
                   "f32_chunk": min(n, X.CHUNK32), "f32_bound": f32, "f32_log2": round(math.log2(f32), 3),
                   "i8_bound": i8, "i8_log2": round(math.log2(i8), 3)})

rows, lin_out = X.bounds16_rows(C, st)
N_MAX = max(p["inputs"] for p in products.values())
normw = max(int(np.abs(np.asarray(W[n])).max()) for n in W if W[n].ndim == 1)
rows += [
    ("logits: |y| in int64 (stored as int32; |y| < 2^31 asserted on every call)", lin_out["embed_tokens"], L63,
     "logits input"),
    ("i8 route: sum of u_a u_b, u = a + 2^15 <= 2^16 - 1, over the widest product (n = %d)" % N_MAX,
     N_MAX * ((1 << 16) - 1) ** 2, L63, "none"),
    ("i8 route: 2^15 (row sum of a + column sum of b) + n 2^30", (2 * N_MAX * M << 15) + (N_MAX << 30), L63, "none"),
    ("rms: sum of (x >> s)^2 over %d values, max |x >> s| < 2^%d (isqrt input)" % (X.HIDDEN, X.NORM_BITS),
     X.HIDDEN << (2 * X.NORM_BITS), 1 << 62, "none"),
    ("rms: y * norm weight, |y| <= %d * 2^16 (asserted at run time)" % X.RMS_Y, (X.RMS_Y << X.A) * normw, L63, "none"),
    ("exp interpolation: E * 256", (1 << 24) << 8, L63, "none"),
    ("softmax: e * 2^16", (1 << 24) << X.A, L63, "none"),
    ("silu interpolation: S * 256", (16 << X.A) << 8, L63, "none"),
]
for what, v, lim, _ in rows:
    assert v < lim, what

peaks_path = os.path.join(HERE, "record", "peaks-16%s.json" % X.SUFFIX)
peaks = json.load(open(peaks_path))["sites"] if os.path.exists(peaks_path) else {}
clamps = {}
for s in CL:
    e = {"clamp_real": CL[s], "clamp_log2": CL[s].bit_length() - 1}
    if s in peaks:
        e.update({"peak": peaks[s]["peak"], "margin_log2": peaks[s]["margin_log2"], "clamped": peaks[s]["clamped"]})
    clamps[s] = e

out = {"model": X.MODEL, "revision": X.PIN["revision"],
       "config": {"layers": X.LAYERS, "hidden": X.HIDDEN, "heads": X.HEADS, "kv_heads": X.KV, "head": X.HEAD,
                  "ff": X.FF, "vocab": X.VOCAB, "rope_theta": X.THETA, "norm_bits": X.NORM_BITS, "rms_y": X.RMS_Y},
       "operands": "every product operand an integer with |a| <= 2^15 - 1 = %d" % M,
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
       "clamp_rule": "each clamp the largest power of two (real units) at which every int64 row below stays under "
                     "its limit; q and k together, gate and up together; computed in exact_llm.clamps16",
       "clamps": clamps,
       "peaks_from": os.path.relpath(peaks_path, HERE) if peaks else None,
       "products": routes,
       "weight_stats": st,
       "block_shift_max": {s: X.shmax(C[s]) for s in sorted(C)},
       "int64": [{"operation": w, "largest_magnitude": v, "limit_log2": round(math.log2(lim)), "site": s,
                  "log2": round(math.log2(v), 3)} for w, v, lim, s in rows]}
path = os.path.join(HERE, "bounds-16%s.json" % X.SUFFIX)
json.dump(out, open(path, "w"), indent=1)
print("bounds-16 %s: %d product kinds on 3 routes" % (X.MODEL, len(routes)))
for r in routes:
    print("  %-18s n %5d  f64 2^%.3f  f32 2^%.3f (chunk %d)  i8 2^%.3f" % (
        r["product"], r["inputs"], r["f64_log2"], r["f32_log2"], r["f32_chunk"], r["i8_log2"]))
print("  weight row scales g:", ", ".join("%s %d..%d" % (k, v["g_min"], v["g_max"]) for k, v in st.items()))
print("  clamps by rule (real), peak, margin, clamped:")
for s, e in clamps.items():
    print("    %-16s 2^%-3d %s" % (s, e["clamp_log2"], "peak %.3f, margin 2^%.2f, clamped %d" % (
        e["peak"], e["margin_log2"], e["clamped"]) if "peak" in e else "(no peaks recorded)"))
print("  kernel intermediate: f64 partial sums < 2^53; f32 partial sums <= 2^24 per chunk; i8 uint8 x uint8, a pair "
      "2 x 255^2 = 130,050 (no int16 lane holds one product), any k products < 2^31 for k <= 33,025")
print("  int64: %d operations below their limits, largest 2^%.3f; wrote %s" % (
    len(rows), max(math.log2(v) for _, v, _, _ in rows), os.path.basename(path)))
