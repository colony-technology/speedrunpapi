"""Operation counts per token from the formulas, for SmolLM2-135M (checked against the measured counters) and for a
7-billion-parameter model (width 4096, feed-forward 11008, 32 layers, vocabulary 32000, 32 heads of 128, no grouped
keys): an estimate, arithmetic only.

Counting rules, the same as check.py's counters:
  run       : one multiply-add per weight per token (the seven matrices of each layer and the logits), plus the
              attention products: heads * T * head for the scores and the same for the contexts, T = keys seen.
  check     : per product of x [in] by W [in, out] with the hint S [out]: 4 * (in + out) multiply-adds
              (2 primes x 2 random vectors; S r and x (W r)); attention: 4 * (heads*T + heads*head) for the scores
              and the same for the contexts; plus the K^T r and V r updates, 4 * 2 * kv*head per new key.
  prep      : 4 multiply-adds per weight, once per model (W r), not per token.
  elem      : check.py's element-wise counter: 16*d (two RMS norms) + 6*(d + kv*head) (rotary step) + 6*ff (SiLU and
              product) + 8*heads*T (softmax), per layer; clamps and shifts not counted.
  trace     : 8 bytes per hinted integer: every product's output, heads*T scores and heads*head contexts per layer,
              and the logits when they are hinted.
    python3 estimate.py [results.jsonl]
"""
import json
import sys

M = {
    "SmolLM2-135M": dict(d=576, ff=1536, L=30, V=49152, heads=9, kv=3, head=64),
    "7B (estimate)": dict(d=4096, ff=11008, L=32, V=32000, heads=32, kv=32, head=128),
}


def per_token(m, T, logits_hinted=True):
    d, ff, L, V, H, kv, hd = (m[k] for k in ("d", "ff", "L", "V", "heads", "kv", "head"))
    mats = [(d, H * hd), (d, kv * hd), (d, kv * hd), (H * hd, d), (d, ff), (d, ff), (ff, d)]   # q k v o gate up down
    weights = L * sum(i * o for i, o in mats) + d * V
    run = weights + L * 2 * H * T * hd
    check = L * (sum(4 * (i + o) for i, o in mats) + 2 * 4 * (H * T + H * hd) + 8 * kv * hd)
    check += 4 * (d + V) if logits_hinted else d * V
    elem = L * (16 * d + 6 * (d + kv * hd) + 6 * ff + 8 * H * T)
    hints = L * (sum(o for _, o in mats) + H * T + H * hd) + (V if logits_hinted else 0)
    return dict(weights=weights, run=run, check=check, elem=elem, prep=4 * weights, trace_bytes=8 * hints)


if __name__ == "__main__":
    for name, m in M.items():
        for T in ((32, 64) if name.startswith("Smol") else (512, 2048, 4096)):
            for lh in (True, False):
                r = per_token(m, T, lh)
                r["ratio_run_to_check_plus_elem"] = round(r["run"] / (r["check"] + r["elem"]), 1)
                print(json.dumps({"model": name, "T": T, "logits": "hinted" if lh else "direct", **r}))
    if len(sys.argv) > 1:
        for l in open(sys.argv[1]):
            rec = json.loads(l)
            for mode in ("check_freivalds", "check_direct"):
                c = rec[mode]
                t = c["tokens"]
                print(json.dumps({"batch": rec["batch"], "mode": mode, "tokens": t,
                                  "check_macs_per_token": round(c["check_macs"] / t), "elem_per_token": round(c["elem_ops"] / t),
                                  "prep_macs": c["prep_macs"]}))
