#!/usr/bin/env python3
"""Reference for HardFloat roundRawFNToRecFN#(w, p), written from the definitions, exact rationals only.

Input value (HardFloat doc 5.3 and 10.4): a finite nonzero raw value is
    x = (-1)^sign * in_sig * 2^(sExp - 2^w - p - 1)
with in_sig a (p+3)-bit unsigned integer whose two top bits are not 00, sExp a (w+2)-bit signed integer
(doc 5.3: range -2^(w+1) .. 2^(w+1)-1). The bias is that of the recoded format: a recoded exponent field r
denotes 2^(r - 2^w) times a significand in [1, 2) (doc 5.2 table: normal E -> E + 2^k + 1, k = w-1,
and the standard bias 2^k - 1).

Format (IEEE 754-2019 3.3, 3.4): precision p, bias 2^(w-1)-1, emin = 1 - bias, emax = bias.
Rounding (IEEE 4.3): to the multiple of the quantum 2^(max(e, emin) - p + 1), e = floor(log2 |x|).
Rules on the magnitude: ne (ties to even), na (ties away), tz (toward zero), aw (away from zero),
odd (HardFloat doc 6.2: round toward zero, then if inexact set the least significant bit).
HardFloat mode + sign -> rule: near_even ne, near_maxMag na, minMag tz, min (+:tz, -:aw), max (+:aw, -:tz), odd odd.
Overflow (IEEE 7.4): the result rounded with unbounded exponent range exceeds the largest finite number
Omega = (2^p - 1) * 2^(emax - p + 1); delivered: ne, na, aw -> infinity; tz, odd -> Omega. Overflow is inexact.
Underflow (IEEE 7.5, default handling): tiny and inexact. Tiny before rounding: |x| < 2^emin.
Tiny after rounding: |x| rounded with unbounded exponent range (quantum 2^(e - p + 1)) is < 2^emin.
Output encoding: the standard encoding (sign, E, F), then the recoding table of doc 5.2:
    zero      E = 0, F = 0  -> exponent 000x..x, fraction 0
    subnormal E = 0, F != 0 -> exponent 2^k + 2 - n, fraction = F << n with its leading 1 dropped
    normal    E, F          -> exponent E + 2^k + 1, fraction F
    infinity                -> exponent 110x..x, fraction x..x
    NaN                     -> exponent 111x..x, fraction F (default NaN of the RISCV specialization: 10..0, sign 0)
x marks a bit the documentation leaves free; the table carries a care mask.

usage: ref.py W P OUTFILE      writes the expected table for every valid finite nonzero input
record per (sExp code u, in_sig - 2^(p+1), rule): <I care> <I value> <B flags>, little endian, 9 bytes
    value/care: the out bits without the sign, {exp[w:0], fract[p-2:0]}
    flags bit0 inexact, bit1 underflow (tininess before), bit2 underflow (tininess after), bit3 overflow
"""
import struct
import sys
from fractions import Fraction as Q

RULES = ("ne", "na", "tz", "aw", "odd")


def pow2(e):
    return Q(1 << e) if e >= 0 else Q(1, 1 << -e)


def floor_log2(x):
    n, d = x.numerator, x.denominator
    e = n.bit_length() - d.bit_length()
    if pow2(e) > x:
        e -= 1
    assert pow2(e) <= x < pow2(e + 1)
    return e


def round_quantum(x, q, rule):
    """x > 0 rounded to a multiple of 2^q by the rule; returns the multiple's integer M."""
    n = x / pow2(q)
    fl = n.numerator // n.denominator
    r = n - fl
    if r == 0:
        return fl
    if rule == "tz":
        return fl
    if rule == "aw":
        return fl + 1
    if rule == "odd":
        return fl | 1
    half = Q(1, 2)
    if rule == "na":
        return fl + 1 if r >= half else fl
    if rule == "ne":
        if r > half or (r == half and fl % 2 == 1):
            return fl + 1
        return fl
    raise ValueError(rule)


def round_value(x, rule, p, emin, bounded_below):
    e = floor_log2(x)
    if bounded_below:
        e = max(e, emin)
    q = e - p + 1
    return round_quantum(x, q, rule) * pow2(q)


def reference(x, rule, w, p):
    """x > 0 exact. Returns (kind, value, inexact, uf_before, uf_after, overflow); kind 'fin' or 'inf'."""
    bias = (1 << (w - 1)) - 1
    emin, emax = 1 - bias, bias
    y = round_value(x, rule, p, emin, True)
    omega = ((1 << p) - 1) * pow2(emax - p + 1)
    if y > omega:
        if rule in ("ne", "na", "aw"):
            return ("inf", None, 1, 0, 0, 1)
        return ("fin", omega, 1, 0, 0, 1)
    inexact = int(y != x)
    tiny_before = x < pow2(emin)
    yu = round_value(x, rule, p, emin, False)
    tiny_after = yu < pow2(emin)
    return ("fin", y, inexact, int(tiny_before and inexact), int(tiny_after and inexact), 0)


def encode(kind, y, w, p):
    """(care, value) of {exp[w:0], fract[p-2:0]} for a non-NaN result magnitude."""
    k = w - 1
    bias = (1 << k) - 1
    emin = 1 - bias
    fbits = p - 1
    fmask = (1 << fbits) - 1
    top3 = 0b111 << (w - 2)          # the three most significant bits of the (w+1)-bit exponent field
    if kind == "inf":
        return (top3 << fbits, (0b110 << (w - 2)) << fbits)
    if y == 0:
        return ((top3 << fbits) | fmask, 0)
    if y < pow2(emin):                       # standard: E = 0, F = y / 2^(emin - p + 1)
        F = y / pow2(emin - p + 1)
        assert F.denominator == 1 and 0 < F < (1 << fbits)
        F = F.numerator
        n = (p - 1) - (F.bit_length() - 1)   # shift that brings the leading 1 to bit p-1
        rexp = (1 << k) + 2 - n
        fract = (F << n) & fmask
    else:
        e = floor_log2(y)
        E = e + bias
        M = y / pow2(e - p + 1)
        assert M.denominator == 1 and (1 << (p - 1)) <= M < (1 << p) and 1 <= E <= 2 * bias
        F = M.numerator - (1 << (p - 1))
        rexp = E + (1 << k) + 1
        fract = F
    assert 0 <= rexp < (1 << (w + 1))
    return (((1 << (w + 1)) - 1) << fbits | fmask, (rexp << fbits) | fract)


def table(w, p):
    out = bytearray()
    nexp = 1 << (w + 2)
    for u in range(nexp):
        sexp = u if u < (1 << (w + 1)) else u - nexp
        scale = sexp - (1 << w) - p - 1
        for sig in range(1 << (p + 1), 1 << (p + 3)):
            x = sig * pow2(scale)
            for rule in RULES:
                kind, y, ix, ufb, ufa, ov = reference(x, rule, w, p)
                care, val = encode(kind, y, w, p)
                out += struct.pack("<IIB", care, val, ix | ufb << 1 | ufa << 2 | ov << 3)
    return out


def main():
    w, p, path = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    data = table(w, p)
    with open(path, "wb") as f:
        f.write(data)
    print("w=%d p=%d records %d" % (w, p, len(data) // 9))


if __name__ == "__main__":
    main()
