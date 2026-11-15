#!/usr/bin/env python3
"""Rounding of a natural number x to a multiple of 2**r, by the five rules.

The integer definition the check scripts compare the bit-vector descriptions with:
the quotient q = x // 2**r and the remainder rem = x mod 2**r decide whether q is kept or incremented.
  nearest-even  up if rem > half, or rem = half and q is odd
  nearest-away  up if rem >= half
  toward-zero   never up
  away          up if rem != 0
  to-odd        up if rem != 0 and q is even (round toward zero, then set the last bit if inexact)
"""
from fractions import Fraction


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
