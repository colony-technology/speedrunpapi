#!/usr/bin/env python3
"""Compare a dump of anchor.cpp (HardFloat's own internal signals) with direct evaluation of hf_datapath.bv.
usage: anchor_check.py BVFILE P DUMP"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bvfsm  # noqa: E402


def main():
    d = bvfsm.Desc(sys.argv[1])
    P = int(sys.argv[2])
    N = P + 4
    n = bad = 0
    masks = set()
    for line in open(sys.argv[3]):
        mask, sig, mode, sign, rs, rpb, ext = map(int, line.split())
        masks.add(mask)
        ok, o = bvfsm.evaluate(d, N, {"sig": sig, "mask": mask},
                               {"m2": mode >> 2 & 1, "m1": mode >> 1 & 1, "m0": mode & 1, "sign": sign})
        n += 1
        if not ok or (o["roundedSig"], o["roundPosBit"], o["anyRoundExtra"]) != (rs, rpb, ext):
            bad += 1
            if bad <= 5:
                print("DIFF p=%d mask=%#x sig=%#x mode=%d sign=%d verilog=(%#x,%d,%d) bv=(%#x,%d,%d) assume=%s" %
                      (P, mask, sig, mode, sign, rs, rpb, ext, o["roundedSig"], o["roundPosBit"], o["anyRoundExtra"], ok))
    print("p=%d distinct (mask, sig, mode, sign) %d, distinct masks %d, differences %d" % (P, n, len(masks), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
