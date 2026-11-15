#!/usr/bin/env python3
"""The cheap moduli far beyond 2,000: every set of four (and of three and five) drawn from
C = {2, ..., 16} and {2^k, 2^k - 1, 2^k + 1 : k <= K}, pairwise coprime, largest / smallest <= R, tested against the
definition (M/m_i = +-1 mod m_i). Prints every unit set found.
usage: cheap4.py K R
"""
import sys
from itertools import combinations
from math import gcd, prod


def main():
    K, R = int(sys.argv[1]), float(sys.argv[2])
    C = sorted(set(range(2, 17)) | {v for k in range(1, K + 1) for v in (2 ** k, 2 ** k - 1, 2 ** k + 1)} - {1})
    out = []
    for size in (3, 4, 5):
        n = found = 0
        for ms in combinations(C, size):
            if ms[-1] > R * ms[0]:
                continue
            if any(gcd(a, b) != 1 for a, b in combinations(ms, 2)):
                continue
            n += 1
            M = prod(ms)
            if all((M // m) % m in (1 % m, m - 1) for m in ms):
                found += 1
                out.append((size, ms))
        print("size %d: %d pairwise coprime candidate sets with ratio <= %g from %d cheap moduli (k <= %d); unit: %d"
              % (size, n, R, len(C), K, found))
    for size, ms in out:
        print("  %d: %s ratio %.3f" % (size, ms, ms[-1] / ms[0]))


if __name__ == "__main__":
    main()
