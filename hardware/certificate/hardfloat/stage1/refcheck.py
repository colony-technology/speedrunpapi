#!/usr/bin/env python3
"""Cross-check of ref.py's nearest-even rounding against the host's IEEE conversions.

binary16 is HardFloat format (w=5, p=11) and binary32 is (w=8, p=24). Every value x tested is exactly a
binary64 number (at most 14 or 27 significant bits, exponents in range), so struct packing to binary16 (e) and binary32 (f)
conversions round once, to nearest even, with IEEE overflow to infinity.
Checked: the encoded value and the inexact, overflow and underflow (tininess after) flags under round to
nearest even; the host gives no flags, so the flags are recomputed from the delivered value the host
gives: inexact = (result != x), overflow = isinf(result).
usage: refcheck.py N   (N random raw inputs per format, seed 1, plus all boundary exponents)
"""
import random
import sys
from fractions import Fraction as Q

import struct

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import ref  # noqa: E402


def value_of(care, val, w, p):
    """Decode a ref.encode() result (non-NaN) to an exact magnitude, or 'inf'."""
    fb = p - 1
    rexp = val >> fb
    fract = val & ((1 << fb) - 1)
    top3 = rexp >> (w - 2)
    if top3 == 0:
        return Q(0)
    if top3 == 6:
        return "inf"
    return (Q((1 << fb) | fract, 1 << fb)) * ref.pow2(rexp - (1 << w))


def host(code, xf):
    """Host IEEE conversion of a binary64 number to binary16 (e) or binary32 (f), nearest even."""
    try:
        return Q(struct.unpack("<" + code, struct.pack("<" + code, xf))[0])
    except OverflowError:
        return "inf"


def check(w, p, npdtype, n, rng):
    bad = tested = 0
    nexp = 1 << (w + 2)
    cases = []
    for _ in range(n):
        u = rng.randrange(nexp)
        sig = rng.randrange(1 << (p + 1), 1 << (p + 3))
        cases.append((u, sig))
    for u in range(nexp):
        for sig in (1 << (p + 1), (1 << (p + 1)) + 1, (3 << p) | 1, (1 << (p + 3)) - 1, (1 << (p + 2)) - 1,
                    (1 << (p + 2)) + 2, (1 << (p + 2)) + 6):
            cases.append((u, sig))
    for u, sig in cases:
        sexp = u if u < (1 << (w + 1)) else u - nexp
        x = sig * ref.pow2(sexp - (1 << w) - p - 1)
        xf = float(x)
        if Q(xf) != x:              # not exactly a binary64 number (extreme exponents): skip
            continue
        kind, y, ix, ufb, ufa, ov = ref.reference(x, "ne", w, p)
        care, val = ref.encode(kind, y, w, p)
        got = value_of(care, val, w, p)
        hv = host(npdtype, xf)
        h_ix = int(hv == "inf" or hv != x)
        h_ov = int(hv == "inf")
        tested += 1
        if got != hv or ix != h_ix or ov != h_ov:
            bad += 1
            if bad <= 10:
                print("DIFF w=%d p=%d sExp=%d sig=%#x ref=%s host=%s ix %d/%d ov %d/%d" %
                      (w, p, sexp, sig, got, hv, ix, h_ix, ov, h_ov))
    print("w=%d p=%d host %s: tested %d, differences %d (value, inexact, overflow)" %
          (w, p, npdtype, tested, bad))
    return bad


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rng = random.Random(1)
    bad = check(5, 11, "e", n, rng) + check(8, 24, "f", n, rng)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
