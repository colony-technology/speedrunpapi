#!/usr/bin/env python3
"""The law in its oldest form, checked on the named sets. For each set: the reading-back constants
c_i = (M/m_i) * (M/m_i)^-1 mod m_i reduced to (-M/2, M/2], whether each is +-M/m_i, and if so the signed sum of unit
fractions sum e_i/m_i as an exact fraction (must be 1/M). Also the vernier pairs (n, n + 1) for n = 2..60 and
Vernier's own 30 / 31.
usage: oldest.py
"""
from fractions import Fraction
from math import prod

SETS = [(3, 5, 7), (5, 8, 13), (7, 9, 32), (15, 17, 128), (7, 8, 9), (15, 16, 17), (3, 7, 10, 11), (8, 9, 11, 13)]


def row(ms):
    M = prod(ms)
    cs, es = [], []
    for m in ms:
        q = M // m
        c = q * pow(q, -1, m) % M
        if c > M // 2:
            c -= M
        cs.append(c)
        es.append(1 if c == q else -1 if c == -q else 0)
    if 0 in es:
        return "%s M %d constants %s: not a unit set" % (ms, M, cs)
    f = sum(Fraction(e, m) for e, m in zip(es, ms))
    terms = " ".join(("+" if e > 0 else "-") + "1/%d" % m for e, m in zip(es, ms))
    return "%s M %d constants %s: %s = %s (1/M: %s)" % (ms, M, cs, terms, f, f == Fraction(1, M))


def main():
    for ms in SETS:
        print(row(ms))
    ok = all(Fraction(1, n) - Fraction(1, n + 1) == Fraction(1, n * (n + 1)) for n in range(2, 61))
    print("vernier: 1/n - 1/(n+1) = 1/(n(n+1)) for n = 2..60: %s; Vernier's 30 and 31: 1/30 - 1/31 = %s"
          % (ok, Fraction(1, 30) - Fraction(1, 31)))
    print("Sunzi's constants 70, 21, 15 mod 105, reduced to (-52, 52]: %s"
          % [((c + 52) % 105) - 52 for c in (70, 21, 15)])


if __name__ == "__main__":
    main()
