#!/usr/bin/env python3
"""design1.bv (direct evaluation) against the design-I contract computed with round_states.rounded():
every valid design-I word of length 2..10, five rules. Also checks that design1.bv's assumptions accept
exactly the valid words."""
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
RULE = {"ne": "nearest-even", "na": "nearest-away", "tz": "toward-zero", "aw": "away", "odd": "to-odd"}
d = bvfsm.Desc(os.path.join(HERE, sys.argv[1] if len(sys.argv) > 1 else "design1.bv"))
n = bad = nvalid = 0
for N in range(2, 11):
    for x in range(1, 1 << N):
        m = x.bit_length() - 1
        for R in range(N):
            valid = R >= 1 and ((R <= m and N - m == 1) or (R > m and N - R == 1))
            for r, name in RULE.items():
                sin = {k: int(k == r) for k in RULE}
                ok, o = bvfsm.evaluate(d, N, {"x": x, "mark": 1 << R}, sin)
                n += 1
                if ok != valid:
                    bad += 1
                    print("validity differs N=%d x=%d R=%d" % (N, x, R))
                    continue
                if not valid:
                    continue
                nvalid += 1
                y = rs.rounded(x, R, name)
                cp = int(rs.rounded(x, R - 1, name) >= 1 << (m + 1))
                want = (y & ((1 << N) - 1), (y >> N) & 1, int(y != x), cp)
                got = (o["y"], o["carry"], o["inexact"], o["cprime"])
                if got != want:
                    bad += 1
                    if bad < 5:
                        print("DIFF N=%d x=%d R=%d %s got %s want %s" % (N, x, R, r, got, want))
print(os.path.basename(d.path) + " vs definition: %d cases (%d valid), %d differences" % (n, nvalid, bad))
sys.exit(1 if bad else 0)
