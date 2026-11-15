#!/usr/bin/env python3
"""The analysis of the searches (record/four.txt, record/five.txt):
count, sign patterns, the most balanced sets (smallest largest/smallest), the sets whose moduli are all of the forms
2^k, 2^k - 1, 2^k + 1 or at most 16, and for four dials: whether each set with signs (+, +, -, -) (in some order of
the moduli) satisfies the factor criterion (A y - p)(A z - p) = p^2 + s A. Also the bits of range per set (log2 M).
usage: analyse.py FILE K
"""
import math
import sys
from itertools import permutations
from collections import Counter


def cheap(m):
    if m <= 16:
        return True
    for k in range(1, 64):
        if m in (2 ** k, 2 ** k - 1, 2 ** k + 1):
            return True
    return False


def main():
    path, K = sys.argv[1], int(sys.argv[2])
    rows = []
    for line in open(path):
        f = line.split()
        ms = tuple(map(int, f[:K]))
        sg = tuple(int(x) for x in f[K:2 * K])
        rows.append((ms, sg))
    print("%s: %d unit sets of %d" % (path, len(rows), K))
    pat = Counter(tuple(sorted(sg)) for _, sg in rows)
    print("sign multisets (of M/m_i mod m_i):", dict(pat))
    bal = sorted(rows, key=lambda r: (r[0][-1] / r[0][0], r[0]))
    print("most balanced (largest / smallest):")
    for ms, sg in bal[:8]:
        M = math.prod(ms)
        print("  %s signs %s ratio %.4f range %.1f bits" % (ms, sg, ms[-1] / ms[0], math.log2(M)))
    ch = [(ms, sg) for ms, sg in rows if all(cheap(m) for m in ms)]
    print("all moduli cheap (2^k, 2^k +- 1 or <= 16): %d" % len(ch))
    for ms, sg in ch:
        print("  %s signs %s ratio %.3f" % (ms, sg, ms[-1] / ms[0]))
    if K == 4:
        # the factor criterion on the sets whose signs are two + and two -
        n22 = bad = 0
        for ms, sg in rows:
            if sorted(sg) != [-1, -1, 1, 1]:
                continue
            n22 += 1
            ok = False
            for w, x, y, z in permutations(ms):
                A, p = w + x, w * x
                for s in (1, -1):
                    if (A * y - p) * (A * z - p) == p * p + s * A and y * z * (w + x) - w * x * (y + z) == s:
                        ok = True
            bad += not ok
        print("sets with two + and two - signs: %d; the factor criterion holds for %d" % (n22, n22 - bad))
    # largest range per number of moduli bits, for the record
    big = max(rows, key=lambda r: math.prod(r[0]))
    print("largest M: %s, %.1f bits" % (big[0], math.log2(math.prod(big[0]))))


if __name__ == "__main__":
    main()
