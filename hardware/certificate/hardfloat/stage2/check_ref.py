#!/usr/bin/env python3
"""ref_round.bv (direct evaluation) against the arithmetic definition (round_states.rounded of the measured
anchor): every sig of N-1 bits, every mask 2^R - 1 with 2 <= R <= N-1, the six modes, both signs, N = 6..11.
Compared: roundedSig = y >> 2, roundPosBit = bit R-1 of x, anyRoundExtra = [x mod 2^(R-1) != 0],
anyRound = [x mod 2^R != 0]."""
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
RULE = {0: lambda s: "nearest-even", 4: lambda s: "nearest-away", 1: lambda s: "toward-zero",
        2: lambda s: "away" if s else "toward-zero", 3: lambda s: "toward-zero" if s else "away",
        6: lambda s: "to-odd"}
path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "ref_round.bv")
d = bvfsm.Desc(path)
n = bad = 0
for N in range(6, 12):
    for x in range(1 << (N - 1)):
        for R in range(2, N):
            for mode, rf in RULE.items():
                for sign in (0, 1):
                    ok, o = bvfsm.evaluate(d, N, {"sig": x, "mask": (1 << R) - 1},
                                           {"m2": mode >> 2 & 1, "m1": mode >> 1 & 1, "m0": mode & 1, "sign": sign})
                    y = rs.rounded(x, R, rf(sign))
                    want = (y >> 2, (x >> (R - 1)) & 1, int(x % (1 << (R - 1)) != 0), int(x % (1 << R) != 0))
                    got = (o["roundedSig"], o["roundPosBit"], o["anyRoundExtra"], o["anyRound"])
                    n += 1
                    if not ok or got != want:
                        bad += 1
                        if bad <= 5:
                            print("DIFF N=%d x=%d R=%d mode=%d sign=%d got %s want %s ok=%s" % (N, x, R, mode, sign, got, want, ok))
print("%s vs the definition: %d cases, %d differences" % (os.path.basename(path), n, bad))
sys.exit(1 if bad else 0)
