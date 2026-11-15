"""Feedback-tap tables of LFSRs: is every entry maximal (period 2^n - 1)? Standard library only.
Sources: Chisel LFSR.tapsMaxPeriod (FibonacciLFSR and GaloisLFSR read the same table),
OpenTitan prim_lfsr LFSR_COEFFS (GAL_XOR and FIB_XNOR read the same table), PULP common_cells cc_lfsr Masks (Galois)
and the fixed 8- and 16-bit registers.
Per entry and per update rule that reads it:
  1. the rule is written here as a map on the state (an int, bit i = state[i]); XNOR feedback adds a constant;
  2. the characteristic polynomial of its linear part is recovered by Berlekamp-Massey from 2n + 64 output bits
     (bit 0 of the state) from a random state; it must have degree n;
  3. n <= 20: the whole cycle structure of the map itself, every state, by brute force: maximal means one cycle of
     2^n - 1 states and one fixed state; this must agree with step 4;
  4. irreducibility by Rabin's test, then primitivity: x^((2^n-1)/r) != 1 mod P for every prime r of 2^n - 1, the
     factors read from Arndt's Cunningham extract and factordb (untrusted): their product must be 2^n - 1 exactly and
     each factor must pass Miller-Rabin to 24 bases and a strong Lucas test (Baillie-PSW).
Control: ten planted one-tap slips (a tap moved by one place), each must be reported non-maximal or, if it happens to
stay maximal, confirmed so (brute force where n <= 20).
usage: python3 audit_taps.py DATA_DIR OUT_DIR [control] [cc] [ot] [chisel]
(DATA_DIR holds tables.json, the entries extracted from the pinned sources, and factors.json, the factorisations of
2^n - 1, which are checked again on every run)
"""
import json
import os
import random
import re
import sys
import time

DL, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
rng = random.Random(2026)


# ---------------------------------------------------------------- number theory (standard library)
def is_sprp(n, a):
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    x = pow(a, d, n)
    if x in (1, n - 1):
        return True
    for _ in range(s - 1):
        x = x * x % n
        if x == n - 1:
            return True
    return False


def jacobi(a, n):
    a %= n
    r = 1
    while a:
        while a % 2 == 0:
            a //= 2
            if n % 8 in (3, 5):
                r = -r
        a, n = n, a
        if a % 4 == 3 and n % 4 == 3:
            r = -r
        a %= n
    return r if n == 1 else 0


def strong_lucas(n):
    import math
    if math.isqrt(n) ** 2 == n:
        return False
    D = 5
    while True:
        j = jacobi(D, n)
        if j == -1:
            break
        if j == 0 and abs(D) != n:
            return False
        D = -D - 2 if D > 0 else -D + 2
    P, Q = 1, (1 - D) // 4
    d, s = n + 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    # Lucas sequences U_d, V_d by binary method
    U, V, Qk = 1, P, Q % n
    for bit in bin(d)[3:]:
        U, V = U * V % n, (V * V - 2 * Qk) % n
        Qk = Qk * Qk % n
        if bit == "1":
            U, V = (P * U + V), (D * U + P * V)
            U = (U * (n + 1) // 2) % n if U % 2 == 0 else ((U + n) * ((n + 1) // 2)) % n
            V = (V * (n + 1) // 2) % n if V % 2 == 0 else ((V + n) * ((n + 1) // 2)) % n
            Qk = Qk * Q % n
    if U == 0 or V == 0:
        return True
    for _ in range(s - 1):
        V = (V * V - 2 * Qk) % n
        Qk = Qk * Qk % n
        if V == 0:
            return True
    return False


SMALL = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89]


def probable_prime(n):
    if n < 2:
        return False
    for p in SMALL:
        if n % p == 0:
            return n == p
    return all(is_sprp(n, a) for a in SMALL) and strong_lucas(n)


# ---------------------------------------------------------------- GF(2)[x], polynomials as ints
def deg(p):
    return p.bit_length() - 1


def pmod(a, m):
    dm = deg(m)
    while a and deg(a) >= dm:
        a ^= m << (deg(a) - dm)
    return a


_SPREAD = [sum(((b >> i) & 1) << (2 * i) for i in range(8)) for b in range(256)]


def psquare(a):
    out, sh = 0, 0
    while a:
        out |= _SPREAD[a & 0xFF] << sh
        a >>= 8
        sh += 16
    return out


def pmul(a, b):
    if bin(a).count("1") > bin(b).count("1"):
        a, b = b, a
    r = 0
    while a:
        low = a & -a
        r ^= b << (low.bit_length() - 1)
        a ^= low
    return r


def ppowmod(base, e, m):
    r, b = 1, pmod(base, m)
    for bit in bin(e)[2:]:
        r = pmod(psquare(r), m)
        if bit == "1":
            r = pmod(pmul(r, b), m)
    return r


def pgcd(a, b):
    while b:
        a, b = b, pmod(a, b)
    return a


def prime_factors_small(n):
    f, d = [], 2
    while d * d <= n:
        if n % d == 0:
            f.append(d)
            while n % d == 0:
                n //= d
        d += 1
    if n > 1:
        f.append(n)
    return f


def x_pow_2k(k, m):
    r = 2  # x
    for _ in range(k):
        r = pmod(psquare(r), m)
    return r


def irreducible(P):
    n = deg(P)
    if n < 1 or not (P & 1):
        return n == 1
    if x_pow_2k(n, P) != pmod(2, P):
        return False
    for q in prime_factors_small(n):
        if pgcd(P, x_pow_2k(n // q, P) ^ 2) != 1:
            return False
    return True


def berlekamp_massey(s):
    n = len(s)
    C, B = [1] + [0] * n, [1] + [0] * n
    L, m = 0, 1
    for i in range(n):
        d = s[i]
        for j in range(1, L + 1):
            d ^= C[j] & s[i - j]
        if d == 0:
            m += 1
        elif 2 * L <= i:
            T = C[:]
            for j in range(n + 1 - m):
                C[j + m] ^= B[j]
            L, B, m = i + 1 - L, T, 1
        else:
            for j in range(n + 1 - m):
                C[j + m] ^= B[j]
            m += 1
    # connection polynomial C(z) = 1 + c1 z + ... + cL z^L; the characteristic polynomial is its reciprocal
    return sum(C[j] << (L - j) for j in range(L + 1)), L


# ---------------------------------------------------------------- factorisations of 2^n - 1
FACTORS = json.load(open(os.path.join(DL, "factors.json")))
FACT_CACHE = {}


def factors_of(n):
    """Prime factors of 2^n - 1 from factors.json (untrusted), accepted only if their product is 2^n - 1 exactly and
    every factor passes the probable-prime test."""
    if n in FACT_CACHE:
        return FACT_CACHE[n]
    target = (1 << n) - 1
    cands = []
    if str(n) in FACTORS:
        cands.append((FACTORS[str(n)]["source"], [int(x) for x in FACTORS[str(n)]["factors"]]))
    res = None
    for src, fl in cands:
        prod = 1
        for f in fl:
            prod *= f
        if prod == target and all(probable_prime(f) for f in set(fl)):
            res = dict(source=src, primes=sorted(set(fl)), primes_with_mult=fl)
            break
    FACT_CACHE[n] = res
    return res


VERDICTS = {}


def primitive(P, n):
    """Cached on the pair {P, reciprocal of P}, which are primitive together or not at all."""
    key = min(P, reciprocal(P, n)) if deg(P) == n else P
    if key not in VERDICTS:
        VERDICTS[key] = _primitive(P, n)
    return VERDICTS[key]


def _primitive(P, n):
    """(verdict, detail): 'primitive', 'irreducible, not primitive', 'reducible', or 'irreducible, primitivity open'."""
    if deg(P) != n:
        return "wrong degree", "degree %d" % deg(P)
    if not irreducible(P):
        return "reducible", ""
    fac = factors_of(n)
    if fac is None:
        return "irreducible, primitivity open", "no verified factorisation of 2^%d - 1" % n
    for r in fac["primes"]:
        if ppowmod(2, ((1 << n) - 1) // r, P) == 1:
            return "irreducible, not primitive", "order divides (2^n - 1)/%d" % r
    return "primitive", fac["source"]


# ---------------------------------------------------------------- update rules (bit i of the int = state[i])
def rule(kind, n, spec):
    mask = (1 << n) - 1
    if kind == "chisel_fib":       # FibonacciLFSR.delta: new s0 = XOR of s(i-1) over taps; the rest shift up
        taps = sorted(spec)
        def f(s):
            b = 0
            for i in taps:
                b ^= (s >> (i - 1)) & 1
            return ((s << 1) & mask) | b
        return f, 0
    if kind == "chisel_gal":       # GaloisLFSR.delta: rotate down by one; positions i with taps(i+1), i+1 != n, XOR s.head
        tmask = sum(1 << (i - 1) for i in spec if i != n)
        def f(s):
            first = s & 1
            t = (s >> 1) | (first << (n - 1))
            return t ^ (tmask if first else 0)
        return f, 0
    if kind == "gal_right":        # OpenTitan GAL_XOR, common_cells cc_lfsr: (s >> 1) ^ (s[0] ? coeffs : 0)
        c = spec
        return (lambda s: (s >> 1) ^ (c if s & 1 else 0)), 0
    if kind == "fib_xnor_left":    # OpenTitan FIB_XNOR: {s[n-2:0], ~^(s & coeffs)}; linear part, constant 1 into bit 0
        c = spec
        return (lambda s: ((s << 1) & mask) | (bin(s & c).count("1") & 1)), 1
    if kind == "fib_xnor_taps":    # cc_lfsr_8bit / 16bit: shift_in = !(XOR of listed bits); {s[n-2:0], shift_in}
        tm = sum(1 << i for i in spec)
        return (lambda s: ((s << 1) & mask) | (bin(s & tm).count("1") & 1)), 1
    raise ValueError(kind)


def char_poly(f, n):
    s0 = rng.getrandbits(n) or 1
    seq, s = [], s0
    for _ in range(2 * n + 64):
        seq.append(s & 1)
        s = f(s)
    P, L = berlekamp_massey(seq)
    return P, L


def brute_cycles(f, const, n):
    """Cycle lengths of the full map (linear part with the XNOR constant into bit 0) over all 2^n states."""
    g = (lambda s: f(s) ^ const) if const else f
    seen = bytearray(1 << n)
    lengths = {}
    for start in range(1 << n):
        if seen[start]:
            continue
        path, s = [], start
        while not seen[s]:
            seen[s] = 1
            path.append(s)
            s = g(s)
        if s in path:
            L = len(path) - path.index(s)
            lengths[L] = lengths.get(L, 0) + 1
    return lengths


# ---------------------------------------------------------------- tables
TABLES = json.load(open(os.path.join(DL, "tables.json")))


def chisel_table():
    tab = {}
    for w, s in TABLES["chisel"]["entries"]:
        tab.setdefault(w, []).append(tuple(s))
    return tab


def ot_table():
    return {w: int(h, 16) for w, h in TABLES["opentitan"]["entries"]}


def cc_table():
    return {w: int(h, 16) for w, h in TABLES["common_cells"]["entries"]}


def cc_fixed():
    return {(name, n): taps for n, taps, name in TABLES["common_cells_fixed"]["entries"]}


def closed_form(kind, n, spec):
    """The polynomial read off the rule by hand, compared with Berlekamp-Massey (either it or its reciprocal)."""
    if kind == "chisel_fib":
        return 1 | sum(1 << i for i in spec)
    if kind in ("fib_xnor_left",):
        return 1 | sum(1 << (i + 1) for i in range(n) if (spec >> i) & 1)
    if kind == "fib_xnor_taps":
        return 1 | sum(1 << (i + 1) for i in spec)
    if kind == "gal_right":
        return 1 | sum(1 << (i + 1) for i in range(n) if (spec >> i) & 1)   # same form as the Fibonacci table: c[n-1] gives x^n
    return None


def reciprocal(p, n):
    return sum(((p >> i) & 1) << (n - i) for i in range(n + 1))


def audit(entries, tag):
    rows, counts = [], {}
    t0 = time.time()
    for lib, kind, n, spec, label in entries:
        f, const = rule(kind, n, spec)
        P, L = char_poly(f, n)
        cf = closed_form(kind, n, spec)
        cf_ok = None if cf is None else (cf in (P, reciprocal(P, n)))
        verdict, detail = primitive(P, n) if L == n else ("linear complexity %d < n" % L, "")
        brute = None
        if n <= 20:
            cyc = brute_cycles(f, const, n)
            maximal = cyc.get((1 << n) - 1, 0) == 1 and sum(k * v for k, v in cyc.items()) == (1 << n)
            brute = dict(cycles=sorted(cyc.items(), reverse=True)[:4], maximal=maximal,
                         agrees=(maximal == (verdict == "primitive")))
        row = dict(lib=lib, rule=kind, width=n, entry=label, poly="%x" % P, closed_form_matches=cf_ok,
                   verdict=verdict, detail=detail, brute=brute)
        rows.append(row)
        counts[verdict] = counts.get(verdict, 0) + 1
        if verdict != "primitive" or (brute and not brute["agrees"]) or cf_ok is False:
            print("NOTE %s" % json.dumps(row), flush=True)
    json.dump(rows, open(os.path.join(OUT, "%s.json" % tag), "w"), indent=0)
    s = "%s: %d entries; %s; brute force agreed on %d of %d entries up to width 20; closed form matched %d of %d; %.0f s" % (
        tag, len(rows), ", ".join("%s %d" % kv for kv in sorted(counts.items())),
        sum(1 for r in rows if r["brute"] and r["brute"]["agrees"]), sum(1 for r in rows if r["brute"]),
        sum(1 for r in rows if r["closed_form_matches"]), sum(1 for r in rows if r["closed_form_matches"] is not None), time.time() - t0)
    print(s, flush=True)
    open(os.path.join(OUT, "%s.txt" % tag), "w").write(s + "\n")
    return rows


def main():
    which = sys.argv[3:] or ["control", "cc", "ot", "chisel"]
    ch, ot, cc, fx = chisel_table(), ot_table(), cc_table(), cc_fixed()
    print("tables: chisel %d widths (%d tap sets), opentitan %d widths, common_cells %d widths + 2 fixed"
          % (len(ch), sum(len(v) for v in ch.values()), len(ot), len(cc)), flush=True)
    if "control" in which:
        ctl = []
        picks = [(w, ch[w][0]) for w in (5, 9, 12, 16, 19)] + [(w, ch[w][0]) for w in (31, 64, 100, 168, 255)]
        for w, taps in picks:
            t = sorted(taps)
            j = [i for i in t if i != w][0]          # move one tap that is not the top one
            slip = tuple(sorted(set(t) - {j} | {j + 1 if (j + 1) not in t and j + 1 < w else j - 1}))
            ctl.append(("control", "chisel_fib", w, slip, "Chisel %d %s with one tap moved: %s" % (w, t, list(slip))))
        audit(ctl, "control")
    if "cc" in which:
        audit([("common_cells", "gal_right", w, v, "Masks[%d] = %x" % (w, v)) for w, v in sorted(cc.items())]
              + [("common_cells", "fib_xnor_taps", n, taps, "%s taps %s" % (name, taps)) for (name, n), taps in fx.items()], "common_cells")
    if "ot" in which:
        audit([("opentitan", k, w, v, "LFSR_COEFFS[%d] = %x" % (w - 3, v)) for w, v in sorted(ot.items()) for k in ("gal_right", "fib_xnor_left")], "opentitan")
    if "chisel" in which:
        audit([("chisel", k, w, tuple(s), "%d -> Set%s" % (w, tuple(s))) for w, sets in sorted(ch.items()) for s in sets
               for k in ("chisel_fib", "chisel_gal")], "chisel")


if __name__ == "__main__":
    main()
