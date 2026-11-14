#!/usr/bin/env python3
"""Exact state count of rounding at a marked position, read least significant bit first.

A word is a list of letters (bit, mark). Exactly one letter is marked: its index r is the rounding position.
The word encodes x = sum(bit_i * 2**i). The rounded value y is the multiple of 2**r chosen by the mode.
Output: one bit of y per letter read (bits 0 .. L-1 of y), then a final pair (bit L of y, inexact).
The function is sequential (each output bit depends on the letters read so far), so it has a unique minimal
Mealy machine with final outputs. This script counts its states by Nerode equivalence of prefixes, with
continuations up to length K, and checks that the count is the same for K and K+1.

usage: round_states.py [P] [K]     P = longest prefix, K = longest continuation (defaults 7 and 5)
"""
import sys
from fractions import Fraction
from itertools import product

MODES = ("nearest-even", "nearest-away", "toward-zero", "away", "to-odd")


def rounded(x, r, mode):
    q, rem = divmod(x, 1 << r)
    half = Fraction(1 << r, 2)
    if rem == 0:
        return q << r
    if mode == "toward-zero":
        up = False
    elif mode == "away":
        up = True
    elif mode == "to-odd":
        up = (q % 2 == 0)
    elif mode == "nearest-away":
        up = rem >= half
    elif mode == "nearest-even":
        up = rem > half or (rem == half and q % 2 == 1)
    else:
        raise ValueError(mode)
    return (q + (1 if up else 0)) << r


def outputs(word, mode):
    """(tuple of output bits, final) for a complete word with exactly one mark."""
    r = [i for i, (_, m) in enumerate(word) if m][0]
    x = sum(b << i for i, (b, _) in enumerate(word))
    y = rounded(x, r, mode)
    L = len(word)
    assert y < (1 << (L + 1))
    return tuple((y >> i) & 1 for i in range(L)), ((y >> L) & 1, int(y != x))


def words(n, marks):
    """All words of length n with exactly `marks` marked letters (marks is 0 or 1)."""
    for bits in product((0, 1), repeat=n):
        if marks == 0:
            yield tuple((b, 0) for b in bits)
        else:
            for r in range(n):
                yield tuple((b, 1 if i == r else 0) for i, b in enumerate(bits))


def signature(prefix, mode, K):
    """Residual of the prefix on every valid continuation of length <= K."""
    seen = sum(m for _, m in prefix)
    sig = []
    for n in range(0, K + 1):
        for cont in words(n, 1 - seen):
            w = prefix + cont
            out, fin = outputs(w, mode)
            sig.append((cont, out[len(prefix):], fin))
    return tuple(sig)


def count_states(mode, P, K):
    classes = {}
    for n in range(0, P + 1):
        for marks in (0, 1):
            for u in words(n, marks):
                classes.setdefault((marks, signature(u, mode, K)), u)
    return classes


def describe(u):
    return "".join(("[%d]" % b) if m else str(b) for b, m in u) or "(empty)"


def main():
    P = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    K = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    for mode in MODES:
        a = count_states(mode, P, K)
        b = count_states(mode, P, K + 1)
        c = count_states(mode, P - 1, K)
        before = sum(1 for (marks, _) in a if marks == 0)
        after = sum(1 for (marks, _) in a if marks == 1)
        stable = (len(a) == len(b) == len(c))
        print("%-13s states %2d (before the mark %d, after it %d)  stable in P and K: %s"
              % (mode, len(a), before, after, stable))
        reps = sorted(a.values(), key=lambda u: (len(u), u))
        print("              shortest representatives, least significant bit first, mark in brackets: "
              + "  ".join(describe(u) for u in reps))


if __name__ == "__main__":
    main()
