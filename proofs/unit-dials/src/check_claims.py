#!/usr/bin/env python3
"""Every statement of the README, by direct computation from the definition.

Unit set: pairwise coprime moduli >= 2 with M/m_i = e_i (mod m_i), e_i = +1 or -1, for every i.
  claim 1  unit with signs e  <=>  sum_i e_i M/m_i = 1 (mod M); checked on every pairwise coprime triple with all
           moduli <= L3 and every quadruple with all moduli <= L4 (both directions, every sign vector)
  claim 2  pairs: unit <=> |m2 - m1| = 1, every pair <= L2
  claim 3  triples: unit <=> for some labelling z(x + y) = xy + 1 or xy - 1, every triple <= L3; the exceptions are
           listed; then: the two-parameter family (s, x with x^2 = +-1 mod s), the Fibonacci line, the delta lines,
           (2^k - 1, 2^k + 1, 2^(2k-1)) with signs (+1, -1, -1), and (2^n - 1, 2^n, 2^n + 1)
  claim 4  (Ay - p)(Az - p) = p^2 + s A  <=>  yz(w + x) - wx(y + z) = s, for every quadruple <= L4
usage: check_claims.py L2 L3 L4
"""
import sys
from itertools import combinations, product
from math import gcd


def coprime(ms):
    return all(gcd(a, b) == 1 for a, b in combinations(ms, 2))


def signs_of(ms):
    """the sign vectors e with M/m_i = e_i (mod m_i) for all i (two for a modulus 2), or [] if not unit"""
    M = 1
    for m in ms:
        M *= m
    opts = []
    for m in ms:
        r = (M // m) % m
        o = [e for e in (1, -1) if (r - e) % m == 0]
        if not o:
            return []
        opts.append(o)
    return list(product(*opts))


def eq1(ms, e):
    M = 1
    for m in ms:
        M *= m
    return sum(ei * (M // m) for ei, m in zip(e, ms)) % M == 1 % M


def main():
    L2, L3, L4 = (int(a) for a in sys.argv[1:4])
    out = []
    # claim 2
    bad2 = n2 = 0
    for a in range(2, L2 + 1):
        for b in range(a + 1, L2 + 1):
            if gcd(a, b) != 1:
                continue
            n2 += 1
            if bool(signs_of((a, b))) != (b - a == 1):
                bad2 += 1
    out.append("claim 2: coprime pairs <= %d: %d; unit <=> |b - a| = 1 fails on %d" % (L2, n2, bad2))
    # claims 1 and 3 on triples
    bad1 = n3 = units = 0
    bad3 = []
    unitset = set()
    for a in range(2, L3 + 1):
        for b in range(a + 1, L3 + 1):
            if gcd(a, b) != 1:
                continue
            for c in range(b + 1, L3 + 1):
                if gcd(a, c) != 1 or gcd(b, c) != 1:
                    continue
                n3 += 1
                ms = (a, b, c)
                S = signs_of(ms)
                # claim 1: for every sign vector, unit-with-e <=> equation
                for e in product((1, -1), repeat=3):
                    if (e in S) != eq1(ms, e):
                        bad1 += 1
                is_unit = bool(S)
                eqn = any(z * (x + y) in (x * y + 1, x * y - 1) for z, x, y in ((a, b, c), (b, a, c), (c, a, b)))
                if is_unit:
                    units += 1
                    unitset.add(ms)
                if is_unit != eqn:
                    bad3.append(ms)
    out.append("claim 1, triples <= %d: %d pairwise coprime, %d sign vectors each; disagreements %d" % (L3, n3, 8, bad1))
    out.append("claim 3, triples <= %d: %d unit triples; unit <=> some z(x+y) = xy +- 1 fails on %d: %s"
               % (L3, units, len(bad3), bad3[:20]))
    # also: does the equation imply pairwise coprimality? every triple <= L3 satisfying it
    nc = 0
    for a in range(2, L3 + 1):
        for b in range(a + 1, L3 + 1):
            for c in range(b + 1, L3 + 1):
                if any(z * (x + y) in (x * y + 1, x * y - 1) for z, x, y in ((a, b, c), (b, a, c), (c, a, b))):
                    if not coprime((a, b, c)):
                        nc += 1
    out.append("claim 3: triples <= %d satisfying the equation that are not pairwise coprime: %d" % (L3, nc))
    # the all-plus-sign sets (sum of fractions above one turn)
    allplus = sorted(ms for ms in unitset if any(all(ei == 1 for ei in e) for e in signs_of(ms)))
    out.append("claim 3: unit triples with an all-plus sign vector (sum of the fractions past a whole turn): %s" % allplus)
    # two-parameter family: s, x with x^2 = +-1 mod s, z = (x(s-x) +- 1)/s
    fam = set()
    for s in range(3, 2 * L3 + 1):
        for x in range(2, s - 1):
            y = s - x
            if y < 2:
                continue
            for sg in (1, -1):
                if (x * x - sg) % s == 0:
                    num = x * y + sg              # z s = x y + sg, and x y = -x^2 (mod s): x^2 = sg (mod s)
                    if num % s == 0:
                        z = num // s
                        if z >= 2:
                            t = tuple(sorted((x, y, z)))
                            if len(set(t)) == 3 and max(t) <= L3:
                                fam.add(t)
    out.append("claim 3 family: triples <= %d from (s, x): %d; equal to the unit triples: %s; missing %d, extra %d"
               % (L3, len(fam), fam == unitset, len(unitset - fam), len(fam - unitset)))
    # Fibonacci line
    F = [0, 1, 1]                                  # standard: F_0 = 0, F_1 = F_2 = 1
    while len(F) < 60:
        F.append(F[-1] + F[-2])
    fb = [(F[n], F[n + 1], F[n + 2]) for n in range(3, 56)]
    out.append("Fibonacci line (F_n, F_n+1, F_n+2), n = 3..55 (F_1 = F_2 = 1): unit %d of %d; F_n F_n+3 - F_n+1 F_n+2 = (-1)^(n+1): %s"
               % (sum(1 for t in fb if signs_of(t)), len(fb),
                  all(F[n] * F[n + 3] - F[n + 1] * F[n + 2] == (-1) ** (n + 1) for n in range(1, 55))))
    # delta lines
    dl = []
    for d in range(3, 200, 2):
        for t in (((d * d - 5) // 4, (d * d - d - 4) // 2, (d * d + d - 4) // 2),
                  ((d * d + 3) // 4, (d * d - d + 4) // 2, (d * d + d + 4) // 2)):
            if min(t) >= 2 and len(set(t)) == 3:
                dl.append((d, t, bool(signs_of(tuple(sorted(t))))))
    out.append("delta lines, odd delta 3..199: %d triples with all moduli >= 2, unit %d; first: %s"
               % (len(dl), sum(1 for x in dl if x[2]), [x[1] for x in dl[:9]]))
    # (2^k - 1, 2^k + 1, 2^(2k-1))
    okk = []
    for k in range(2, 129):
        ms = (2 ** k - 1, 2 ** k + 1, 2 ** (2 * k - 1))
        okk.append(coprime(ms) and (1, -1, -1) in signs_of(ms))
    out.append("(2^k - 1, 2^k + 1, 2^(2k-1)), k = 2..128: unit with signs (+1, -1, -1): %d of %d" % (sum(okk), len(okk)))
    # (2^n - 1, 2^n, 2^n + 1)
    tb = []
    for n in range(2, 129):
        ms = (2 ** n - 1, 2 ** n, 2 ** n + 1)
        M = ms[0] * ms[1] * ms[2]
        inv = [pow(M // m, -1, m) for m in ms]
        tb.append((not signs_of(ms), inv[0] == 2 ** (n - 1) % ms[0], (inv[2] - (-(2 ** (n - 1)))) % ms[2] == 0, inv[1] == ms[1] - 1))
    out.append("(2^n - 1, 2^n, 2^n + 1), n = 2..128: not unit %d; inverses 2^(n-1), -1, -2^(n-1): %d, %d, %d of %d"
               % (sum(t[0] for t in tb), sum(t[1] for t in tb), sum(t[3] for t in tb), sum(t[2] for t in tb), len(tb)))
    # claim 1 and 4 on quadruples
    bad1q = nq = bad4 = units4 = 0
    for ms in combinations(range(2, L4 + 1), 4):
        if not coprime(ms):
            continue
        nq += 1
        S = signs_of(ms)
        units4 += bool(S)
        for e in product((1, -1), repeat=4):
            if (e in S) != eq1(ms, e):
                bad1q += 1
        w, x, y, z = ms
        A, p = w + x, w * x
        for s in (1, -1):
            if ((A * y - p) * (A * z - p) == p * p + s * A) != (y * z * (w + x) - w * x * (y + z) == s):
                bad4 += 1
    out.append("claim 1, quadruples <= %d: %d pairwise coprime, %d unit; disagreements %d" % (L4, nq, units4, bad1q))
    out.append("claim 4, quadruples <= %d: factor form <=> equation fails on %d" % (L4, bad4))
    print("\n".join(out))


if __name__ == "__main__":
    main()
