#!/usr/bin/env python3
"""round_mark.bv (direct evaluation) against round_states.rounded() of the measured anchor, every word with
one mark, lengths 1..9, five rules."""
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
d = bvfsm.Desc(os.path.join(HERE, "round_mark.bv"))
n = bad = 0
for N in range(1, 10):
    for x in range(1 << N):
        for R in range(N):
            for r, name in RULE.items():
                sin = {k: int(k == r) for k in RULE}
                ok, o = bvfsm.evaluate(d, N, {"x": x, "mark": 1 << R}, sin)
                y = rs.rounded(x, R, name)
                want = (y & ((1 << N) - 1), (y >> N) & 1, int(y != x))
                n += 1
                if not ok or (o["y"], o["carry"], o["inexact"]) != want:
                    bad += 1
                    if bad < 5:
                        print("DIFF N=%d x=%d R=%d %s got %s want %s ok=%s" % (N, x, R, r, o, want, ok))
print("round_mark.bv vs round_states.rounded: %d cases, %d differences" % (n, bad))
sys.exit(1 if bad else 0)
