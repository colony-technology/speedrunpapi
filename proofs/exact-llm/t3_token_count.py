"""The t3 token kernel (t3_token.c) on the first 64 tokens of the evaluation text, one lane, token by token: its
logits at every position against exact-16 on the f64 route (one prefill of the 64 tokens), and its counters for
the last token (position 63, context 64; the census window), by site and class.

usage: python t3_token_count.py [OUT.json]
"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exact_llm as X  # noqa: E402

L = 64


def main(argv):
    ids = np.array(X.tokenizer().encode(X.text())[:L], dtype=np.int64)
    m = X.T3Token(lanes=1)
    m.open(1, L)
    lg, nxt, secs = [], [], []
    before = None
    for t in range(L):
        if t == L - 1:
            before = m.counters()
        t0 = time.time()
        a, b = m.step([0], [int(ids[t])], [t])
        secs.append(time.time() - t0)
        lg.append(a[0].copy())
        nxt.append(int(b[0]))
    after = m.counters()
    lg = np.stack(lg)
    ref = X.Exact16("f64")
    pos = np.arange(L)[None]
    kv = np.tril(np.ones((L, L), dtype=bool))[None]
    r, _ = ref.forward(ids[None], pos, None, kv)
    r = np.asarray(r[0], dtype=np.int32)
    same = int((lg == r).all(axis=1).sum())
    greedy = int((np.array(nxt) == r.argmax(-1)).sum())
    sites = [s for s in after if isinstance(after[s], dict)]
    per = {s: {k: after[s][k] - before[s][k] for k in after[s] if k != "spare"} for s in sites}
    tot = {k: sum(per[s][k] for s in sites if s != "checks") for k in per[sites[0]]}
    out = {"tokens": "first %d of the evaluation text" % L, "positions equal to exact16-f64": "%d of %d" % (same, L),
           "greedy equal": "%d of %d" % (greedy, L),
           "last token (position %d), per site" % (L - 1): per,
           "last token, all sites but the checks": tot,
           "last token: operations": sum(tot.values()),
           "seconds per token, last 8": [round(s, 3) for s in secs[-8:]],
           "clamped, held, failed (whole run)": [after["clamped"], after["held"], after["failed"]]}
    s = json.dumps(out, indent=1)
    print(s)
    if len(argv) > 1:
        open(argv[1], "w").write(s + "\n")
    return 0 if same == L else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
