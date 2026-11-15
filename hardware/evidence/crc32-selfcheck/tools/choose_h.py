"""Chooses H (2 x 32) that covers every fault vector and makes predictor plus checker small.

    python3 tools/choose_h.py --blif BLOCK.blif --faults proof/NAME_faults.json --r 2 --linear PATH/hardware/linear
                              --work DIR --out proof/NAME_H.json [--restarts N --walk N --measure N --seed S]

Constraint: H e_w != 0 for every e_w in the faults file.  With r = 2 each column of H is 01, 10 or 11.
Search: start from the feasible H that z3 found in tools/fault_vectors.py; each restart takes a random walk of
feasible single-column changes, then descends on the number of ones in the predictor rows (H L, masks over the
block's inputs) plus the ones in H (the checker rows).  The best distinct results are compiled with the linear
compiler and the smallest LUT-6 total is kept.  This is a search, not a proven optimum; z3 Optimize on the
same objective did not finish in 60 s.  L is read from the netlist (forward GF(2) forms of o).
"""
import argparse
import json
import re
import subprocess
from pathlib import Path


def forms(blif):
    ins, outs, form = [], [], {}
    lines = blif.read_text().replace("\\\n", " ").splitlines()
    for line in lines:
        t = line.split()
        if t and t[0] == ".inputs":
            ins += t[1:]
        elif t and t[0] == ".outputs":
            outs += t[1:]
    for i, v in enumerate(ins):
        form[v] = 1 << i
    for line in lines:
        t = line.split()
        if t and t[0] == ".names":
            v = 0
            for u in t[1:-1]:
                v ^= form[u]
            form[t[-1]] = v                                   # all LUTs are parity LUTs (checked in fault_vectors.py)
    return ins, [form[o] for o in outs]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--blif", type=Path, required=True)
    ap.add_argument("--faults", type=Path, required=True)
    ap.add_argument("--r", type=int, required=True)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--linear", type=Path, required=True, help="speedrunpapi/hardware/linear")
    ap.add_argument("--restarts", type=int, default=300)
    ap.add_argument("--measure", type=int, default=12)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--walk", type=int, default=64)
    a = ap.parse_args()
    ins, L = forms(a.blif)
    n = len(ins)
    vecs = sorted(set(int(v, 16) for v in json.loads(a.faults.read_text())["vectors"].values()) - {0})
    if a.r != 2:
        raise SystemExit("this search is written for r = 2: each column of H is one of 01, 10, 11")
    import random
    pc = lambda x: bin(x).count("1")

    def rows_of(col):
        return [sum(1 << i for i in range(32) if (col[i] >> j) & 1) for j in range(2)]

    def ok(H):
        return all(any(pc(h & v) & 1 for h in H) for v in vecs)

    def cost(H):
        c = 0
        for h in H:
            m = 0
            for i in range(32):
                if (h >> i) & 1:
                    m ^= L[i]
            c += pc(m) + pc(h)
        return c
    rng = random.Random(a.seed)
    V = [sum(1 << t for t, v in enumerate(vecs) if (v >> i) & 1) for i in range(32)]   # vectors holding bit i
    ALL = (1 << len(vecs)) - 1
    H0 = [int(h, 16) for h in json.loads(a.faults.read_text())["H"]]
    start = [((H0[0] >> i) & 1) | (((H0[1] >> i) & 1) << 1) for i in range(32)]

    def feasible(col):
        P = [0, 0]
        for i in range(32):
            for jj in range(2):
                if (col[i] >> jj) & 1:
                    P[jj] ^= V[i]
        return P[0] | P[1] == ALL
    assert feasible(start)
    seen, pool = set(), []
    for restart in range(a.restarts):
        col = list(start)                                     # the solver's feasible H, then a random feasible walk
        for _ in range(a.walk):
            i, v = rng.randrange(32), rng.choice((1, 2, 3))
            old, col[i] = col[i], v
            if not feasible(col):
                col[i] = old
        P, M = [0, 0], [0, 0]                                 # parities over the vectors; predictor masks
        for i in range(32):
            for jj in range(2):
                if (col[i] >> jj) & 1:
                    P[jj] ^= V[i]
                    M[jj] ^= L[i]
        cur = pc(M[0]) + pc(M[1]) + sum(pc(c) for c in col)
        improved = True
        while improved:
            improved = False
            for i in rng.sample(range(32), 32):
                for v in (1, 2, 3):
                    if v == col[i]:
                        continue
                    d = col[i] ^ v
                    P2 = [P[jj] ^ (V[i] if (d >> jj) & 1 else 0) for jj in range(2)]
                    if P2[0] | P2[1] != ALL:
                        continue
                    M2 = [M[jj] ^ (L[i] if (d >> jj) & 1 else 0) for jj in range(2)]
                    c2 = cur - pc(M[0]) - pc(M[1]) - pc(col[i]) + pc(M2[0]) + pc(M2[1]) + pc(v)
                    if c2 < cur:
                        col[i], P, M, cur, improved = v, P2, M2, c2, True
        H = tuple(sorted(rows_of(col)))
        if H not in seen:
            seen.add(H)
            pool.append((cur, list(H)))
    pool.sort()
    # measure the real LUT count of the best candidates with the linear compiler
    import sys
    sys.path.insert(0, str(a.linear.resolve()))
    import linear_compiler as LC
    measured = []
    for c, H in pool[:a.measure]:
        pred = []
        for h in H:
            m = 0
            for i in range(32):
                if (h >> i) & 1:
                    m ^= L[i]
            pred.append(m)
        pn, _, pl = LC.compile_linear(pred, n, 6, None)
        cn, _, cl = LC.compile_linear(H, 32, 6, None)
        measured.append((len(pn) + len(cn), max(pl, cl), c, H))
    measured.sort()
    luts, lev, best_cost, H = measured[0]
    search = {"method": "local search from the solver H: %d restarts of a %d-step random feasible walk then descent, seed %d; not a proven optimum" % (a.restarts, a.walk, a.seed),
              "distinct_local_optima": len(pool), "best_ones": pool[0][0], "measured": a.measure,
              "chosen_predictor_plus_checker_lut6": luts}
    pred = []
    for h in H:
        m = 0
        for i in range(32):
            if (h >> i) & 1:
                m ^= L[i]
        pred.append(m)
    res = {"r": a.r, "H": ["%08x" % h for h in H], "checker_weights": [bin(h).count("1") for h in H],
           "predictor_rows": ["%x" % m for m in pred], "predictor_weights": [bin(m).count("1") for m in pred],
           "inputs": ins, "objective": sum(bin(h).count("1") for h in H) + sum(bin(m).count("1") for m in pred), "search": search}
    a.out.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: res[k] for k in ("r", "H", "checker_weights", "predictor_weights", "objective", "search")}))
