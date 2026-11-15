"""The certificate that every product in exact_embed.py is exact, and that no int64 overflows. Writes bounds.json.

Matrix products are done in float64 on integer-valued arrays. A float64 holds every integer of magnitude up to 2^53
exactly, so a dot product is exact in any summation order, with or without fused multiply-add, if the sum of the
magnitudes of its terms is at most 2^53: then every term and every partial sum is such an integer.
For y = x W with x clamped to [-C, C] (C = CLAMP, integer units), the sum of magnitudes for output j is at most
C * sum_i |W[j, i]|. This script computes the largest such row sum for every weight matrix, from the integer
weights the model actually uses, and asserts C times it is below 2^53. The two products of activations with
activations are bounded the same way: scores q.k over 32 terms, each at most C^2; context p.v, where the
probabilities of a row are integers whose sum is at most 2^16 (a sum of floors of numbers summing to 2^16).

It also checks the folded query weights exactly: n = round(p sqrt2 / q) holds when (2n - 1)^2 q^2 < 8 p^2 <
(2n + 1)^2 q^2, an integer inequality, for every element. And it lists the element-wise int64 operations with
their largest possible magnitude, each below 2^63 (and the two isqrt inputs below 2^62).

usage: python bounds.py
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import exact_embed as X  # noqa: E402

P = X.load_params()
ex = X.Exact(P, keep_int=True)
C = X.CLAMP
LIM = 1 << 53
out = {"scales": {"activation_fraction_bits": X.A, "weight_fraction_bits": X.WB,
                  "bias_fraction_bits": X.A + X.WB, "clamp_real": C / 2.0 ** X.A, "clamp_int": C,
                  "layernorm_clamp_real": X.CLAMP_LN / 2.0 ** X.A, "output_fraction_bits": X.OUT},
       "limit": "2^53 = %d" % LIM, "weight_products": [], "activation_products": [], "int64": []}

worst = 0
for name, w in ex.int_weights.items():
    row = int(np.abs(w).sum(axis=1).max())          # w is [out, in]: output j sums over row j
    bound = C * row
    assert bound < LIM, name
    worst = max(worst, bound)
    out["weight_products"].append({"matrix": name, "shape": list(w.shape), "max_row_sum_abs_int": row,
                                   "clamp_times_row_sum": bound, "log2": round(math.log2(bound), 3)})
qk = X.HEAD * C * C
pv = (1 << X.A) * C
assert qk < LIM and pv < LIM
out["activation_products"] = [
    {"product": "scores q.k", "terms": X.HEAD, "bound": "32 * C * C", "value": qk, "log2": round(math.log2(qk), 3)},
    {"product": "context p.v", "bound": "2^16 * C (probabilities of a row sum to at most 2^16)", "value": pv,
     "log2": round(math.log2(pv), 3)}]

# the folded query weights, checked exactly
checked = 0
for i in range(6):
    for part, k in (("weight", X.WB), ("bias", X.A + X.WB)):
        a = P["encoder.layer.%d.attention.self.query.%s" % (i, part)]
        n_all = (ex.int_weights["encoder.layer.%d.attention.self.query.weight" % i] if part == "weight"
                 else ex.layers[i]["q"][1])
        m = k - 3
        for v, n in zip(a.astype(np.float64).ravel().tolist(), n_all.ravel().tolist()):
            num, den = v.as_integer_ratio()
            p, q = (abs(num) << m, den) if m >= 0 else (abs(num), den << -m)
            if num == 0:
                assert n == 0
            else:
                assert (n >= 0) == (num > 0) or n == 0          # the sign follows the weight
                n = abs(n)
                lower = (2 * n - 1) ** 2 * q * q if n > 0 else -1
                assert lower < 8 * p * p < (2 * n + 1) ** 2 * q * q
            checked += 1

big_bias = max(int(np.abs(lay[key][1]).max()) for lay in ex.layers for key in ("q", "k", "v", "o", "i", "o2"))
big_gamma = max([int(np.abs(ex.emb_ln[0]).max())] + [int(np.abs(lay[l][0]).max()) for lay in ex.layers
                                                       for l in ("ln1", "ln2")])
d_max = 2 * X.CLAMP_LN
y_max = d_max << X.A                                  # std >= 1
rows = [
    ("linear: product plus bias plus rounding constant", worst + big_bias + (1 << (X.WB - 1))),
    ("layernorm: sum of squares (isqrt input, below 2^62)", X.HIDDEN * d_max * d_max),
    ("layernorm: d * 2^16", y_max),
    ("layernorm: y * gamma plus rounding constant", y_max * big_gamma + (1 << (X.A - 1))),
    ("scores: max minus score", 2 * qk),
    ("exp interpolation: E * 256", (1 << X.EXP_ONE) << X.EXP_STEP),
    ("softmax: e * 2^16", (1 << X.EXP_ONE) << X.A),
    ("gelu interpolation: G * 256", int(np.abs(ex.G).max()) << X.GELU_STEP),
    ("pooling: sum over at most 256 tokens", 256 * C),
    ("normalisation: sum of squares (isqrt input, below 2^62)", X.HIDDEN * C * C),
    ("normalisation: pooled * 2^15", C << X.OUT),
]
for what, v in rows:
    limit = (1 << 62) if "isqrt" in what else (1 << 63)
    assert v < limit, what
    out["int64"].append({"operation": what, "largest_magnitude": v, "log2": round(math.log2(v), 3)})
out["jax_int64_path"] = {
    "what": "jax_runner.py computes the same integers with every product an int64 einsum: no floating point",
    "bound": "a product or a sum in that path is at most the bound of the same product above, which is below 2^53, "
             "so below 2^63; the element-wise operations are those listed under int64",
    "largest_product_sum_log2": round(math.log2(max(worst, qk, pv)), 3),
    "isqrt": "digit by digit on n < 2^62; every intermediate value is at most n",
}
out["brackets"] = {
    "isqrt": "every returned s is asserted s^2 <= n < (s + 1)^2 (exact_embed.isqrt), on every call",
    "floor division": "every returned q is asserted q d <= n < (q + 1) d (exact_embed.fdiv), on every call: "
                      "LayerNorm mean, variance and normalised value; softmax probabilities; pooling mean; output",
    "layernorm": "the square root of LayerNorm is s = isqrt(v + 1) with s^2 <= v + 1 < (s + 1)^2",
}
out["largest_weight_product_bound_log2"] = round(math.log2(worst), 3)
out["folded_query_values_checked"] = checked
json.dump(out, open(os.path.join(HERE, "bounds.json"), "w"), indent=1)
print("bounds: %d weight matrices; largest C * row sum = 2^%.3f; scores 2^%.3f; context 2^%.3f; all below 2^53"
      % (len(ex.int_weights), math.log2(worst), math.log2(qk), math.log2(pv)))
print("        %d folded query values checked exactly; %d int64 operations below their limits; wrote bounds.json"
      % (checked, len(rows)))
