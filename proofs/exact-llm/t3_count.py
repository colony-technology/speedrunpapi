"""The t3 route's own counters, per token at the last position (context 64), as the census counts it: a prefill of
63 tokens, then one forward of one token with the key-value cache; the counters of that one forward.

usage: python t3_count.py [OUT.json]

Tokens: the first 64 of the evaluation text (text()). The weights' counts do not depend on the tokens (every stream
word runs once per token); the attention's and the element-wise counts do (the digits of activations).
Kinds (T3.KINDS): weights (the 16-bit matrix products, from the streams), peeled (the 2 whole inputs per product
input vector times their 16-bit weight rows), attention (q16.k16, p.vh, p.vl: one operand recoded at run time),
element-wise (norm squares, norm weight, rotary, the exp and SiLU interpolations, SiLU(gate) times up).
Per kind: digit adds and subtracts, Horner adds (acc + acc, then + s), values recoded, recoding operations.
"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exact_llm as X  # noqa: E402


def streams_digits(k):
    """Nonzero digits and output rows over every weight stream compiled so far."""
    digits = rows = 0
    for key, ro in k.rowoffs.items():
        rows += ro.shape[0] - 1
        digits += int(ro[-1]) - (X.TOP16 + 1) * (ro.shape[0] - 1)
    return digits, rows


def main(argv):
    t0 = time.time()
    m = X.Exact16("t3")
    k = m.t3
    L = 64
    ids = np.array(X.tokenizer().encode(X.text())[:L], dtype=np.int64)[None]
    pos = np.arange(L)[None]
    i = np.arange(L)
    kvalid = (i[None, None, :] <= i[None, :, None])
    _, cache = m.forward(ids[:, :L - 1], pos[:, :L - 1], None, kvalid[:, :L - 1, :L - 1])
    t1 = time.time()
    before = {kind: c.copy() for kind, c in k.cnt.items()}
    k.log = []
    t2 = time.time()
    logits, _ = m.forward(ids[:, L - 1:], pos[:, L - 1:], cache, kvalid[:, L - 1:, :])
    t3 = time.time()
    d = {kind: [int(v) for v in (k.cnt[kind] - before[kind])] for kind in k.KINDS}
    att = [e for e in k.log if e[0] == "attention"]
    per = 3 * X.KV                                      # per layer: KV scores, KV p.vh, KV p.vl, in that order
    assert len(att) == per * X.LAYERS
    split = {"scores q16.k16": [0, 0], "context p.vh": [0, 0], "context p.vl": [0, 0]}
    for j, e in enumerate(att):
        name = list(split)[(j % per) // X.KV]
        split[name][0] += e[4]
        split[name][1] += e[5]
    digits, rows = streams_digits(k)
    names = ["digit adds and subtracts", "Horner adds", "values recoded", "recoding operations"]
    out = {"model": X.MODEL, "window": "last position, context %d, batch 1" % L,
           "next token": int(np.argmax(logits[0, 0])),
           "per kind": {kind: dict(zip(names, d[kind])) for kind in k.KINDS if kind != "weight streams, built once"},
           "attention split": {n: {"digit adds and subtracts": v[0], "Horner adds": v[1]} for n, v in split.items()},
           "weight streams": {"nonzero digits": digits, "output rows": rows,
                              "words": digits + (X.TOP16 + 1) * rows, "bytes": 2 * (digits + (X.TOP16 + 1) * rows)},
           "weight streams, built once (this run)": dict(zip(names, [int(v) for v in k.cnt["weight streams, built once"]])),
           "seconds": {"load and prefill of 63": round(t1 - t0, 1), "the counted forward": round(t3 - t2, 2)}}
    w, p, a, e = (d[x] for x in ("weights", "peeled", "attention", "element-wise"))
    out["totals"] = {
        "weight products: digit adds": w[0], "weight products: Horner adds": w[1],
        "peeled terms: digit adds": p[0], "peeled terms: Horner adds": p[1],
        "variable by variable (attention): digit adds": a[0], "variable by variable (attention): Horner adds": a[1],
        "element-wise: digit adds": e[0], "element-wise: Horner adds": e[1],
        "adds and subtracts in all products": w[0] + w[1] + p[0] + p[1] + a[0] + a[1] + e[0] + e[1],
        "values recoded at run time (a sign look each)": p[2] + a[2] + e[2]}
    s = json.dumps(out, indent=1)
    print(s)
    if len(argv) > 1:
        open(argv[1], "w").write(s + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
