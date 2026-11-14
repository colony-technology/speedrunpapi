#!/usr/bin/env python3
"""Lemma L1 sides (lemma_cu_c_lhs.bv, lemma_cu_c_rhs.bv), direct evaluation, against the definition:
every x of N bits with the top bit set, every U in 1..N-1, five rules, N = 2..11.
lhs must be [rho(x, U) >= 2^N]; rhs must be bit U of x & bit N of rho(x, U+1) & unbIncr (HardFloat's formula).
Also reports how often the lemma itself holds (it must, everywhere)."""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bvfsm  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "round_states", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "common", "round_states.py"))
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)
NAME = {"ne": "nearest-even", "na": "nearest-away", "tz": "toward-zero", "aw": "away", "odd": "to-odd"}
A = bvfsm.Desc(os.path.join(HERE, "lemma_cu_c_lhs.bv"))
B = bvfsm.Desc(os.path.join(HERE, "lemma_cu_c_rhs.bv"))
n = bad = lem = 0
for N in range(2, 12):
    for x in range(1 << (N - 1), 1 << N):
        for U in range(1, N):
            for r in NAME:
                sin = {k: int(k == r) for k in NAME}
                oka, oa = A.__class__ and bvfsm.evaluate(A, N, {"x": x, "markU": 1 << U}, sin)
                okb, ob = bvfsm.evaluate(B, N, {"x": x, "markU": 1 << U}, sin)
                lhs = int(rs.rounded(x, U, NAME[r]) >= 1 << N)
                unb = int((r in ("ne", "na") and (x >> (U - 1)) & 1 == 1) or (r == "aw" and x % (1 << U) != 0))
                rhs = ((x >> U) & 1) & ((rs.rounded(x, U + 1, NAME[r]) >> N) & 1) & unb
                n += 1
                lem += int(lhs == rhs)
                if not (oka and okb) or oa["v"] != lhs or ob["v"] != rhs:
                    bad += 1
                    if bad <= 5:
                        print("DIFF N=%d x=%d U=%d %s: lhs %s/%d rhs %s/%d ok %s %s" % (N, x, U, r, oa["v"], lhs, ob["v"], rhs, oka, okb))
print("lemma sides vs the definition: %d cases, %d differences; lemma true on %d of %d" % (n, bad, lem, n))
sys.exit(1 if bad or lem != n else 0)
