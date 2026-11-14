#!/usr/bin/env python3
"""Checks the integer model of expstage.py against concrete data.
For every line of a Verilator dump of stage 1 (every valid finite nonzero input of one format):
  1. computes the model's quantities with Python integers by the same formulas as expstage.py;
  2. checks every fact the model asserts about rho (i, c, z at the three positions, equal positions,
     monotonicity, lemma L1) on the true rho;
  3. compares the model's prediction of HardFloat (result kind, exponent field, overflow, underflow,
     inexact) with HardFloat's actual output.
usage: factcheck.py W P DUMP
"""
import importlib.util
import os
import sys

spec = importlib.util.spec_from_file_location(
    "round_states", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "common", "round_states.py"))
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)
NAME = {"ne": "nearest-even", "na": "nearest-away", "tz": "toward-zero", "aw": "away", "odd": "to-odd"}


def rule_of(mode, sign):
    return {0: "ne", 4: "na", 1: "tz", 2: "aw" if sign else "tz", 3: "tz" if sign else "aw", 6: "odd"}[mode]


def main():
    W, P, path = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    H = 1 << (W - 2)
    B = 2 * H
    p = P
    nexp = 1 << (W + 2)
    n = factbad = predbad = 0
    for line in open(path):
        ctl, mode, sign, ucode, sig, out, flags = line.split()
        ctl, mode, sign, ucode, sig = map(int, (ctl, mode, sign, ucode, sig))
        out, flags = int(out, 16), int(flags, 16)
        sExp = ucode if ucode < (1 << (W + 1)) else ucode - nexp
        rule = rule_of(mode, sign)
        d = (sig >> (p + 2)) & 1
        m = p + 1 + d
        T = p + 3
        E = B + p + 3 - sExp
        O = 3 * B + p + 1 - sExp
        Sq = B + 4 - sExp
        Ru = 2 + d
        RS = max(Ru, Sq)
        u = sExp if sExp >= 0 else sExp + 4 * B
        k = min(max(B + 2 - u, 0), p + 1)
        RHF = 2 + max(d, k)
        pos = {"HF": RHF, "S": RS, "U": Ru}
        y, i, c, z = {}, {}, {}, {}
        for nm, r in pos.items():
            y[nm] = rs.rounded(sig, r, NAME[rule])
            i[nm] = sig % (1 << r) != 0
            c[nm] = r <= m and y[nm] >= (1 << (m + 1))
            z[nm] = r > m and y[nm] != 0
        facts = []
        for nm, r in pos.items():
            facts.append(not (r > m) or i[nm])
            facts.append(not (r <= m and not i[nm]) or not c[nm])
            facts.append(not (r <= m and rule in ("tz", "odd")) or not c[nm])
            facts.append(not (r >= m + 2) or z[nm] == (rule in ("aw", "odd")))
            facts.append(not (r == m + 1) or ((rule != "tz" or not z[nm]) and (rule not in ("aw", "odd") or z[nm])))
            if r <= m:   # the top of y is m + c
                top = y[nm].bit_length() - 1
                facts.append(top == m + int(c[nm]))
            else:
                facts.append(y[nm] in (0, 1 << r))
        for a, ra in pos.items():
            for b, rb in pos.items():
                if a != b and ra <= rb and i[a]:
                    facts.append(i[b])
        rpb = (sig >> (RHF - 1)) & 1
        carryHF = (y["HF"] >> (m + 1)) & 1
        unb = ((rule in ("ne", "na")) and ((sig >> (Ru - 1)) & 1)) or (rule == "aw" and sig % (1 << Ru) != 0)
        if RHF == Ru + 1:
            facts.append(c["U"] == bool(rpb and carryHF and unb))
        n += 1
        if not all(facts):
            factbad += 1
            if factbad <= 5:
                print("FACT FAILS w=%d p=%d sExp=%d sig=%#x rule=%s" % (W, p, sExp, sig, rule))
        # model prediction of HardFloat
        t = (d + int(c["HF"])) if RHF <= m else ((2 if z["HF"] else 0) if RHF == T else int(z["HF"]))
        assert t == ((y["HF"] >> (T - 1)) & 3)          # t really is the top two bits of y
        sRE = sExp + t
        ovf = sRE >= 3 * B
        tu = sRE < B + 3 - p
        tiny1, tiny2 = RHF > Ru, RHF > Ru + 1
        uf = tu or (i["HF"] and sExp < 2 * B and tiny1 and not (ctl and not tiny2 and carryHF and rpb and unb))
        ix = ovf or tu or i["HF"]
        kind = (2 if rule in ("ne", "na", "aw") else 3) if ovf else ((1 if rule in ("aw", "odd") else 0) if tu else 1)
        eHF = (B + 3 - p) if tu else sRE
        # HardFloat's actual output
        exp = (out >> (p - 1)) & ((1 << (W + 1)) - 1)
        fract = out & ((1 << (p - 1)) - 1)
        top3 = exp >> (W - 2)
        if top3 == 0:
            akind = 0
        elif top3 == 6:
            akind = 2
        elif exp == 3 * B - 1 and fract == (1 << (p - 1)) - 1 and ovf:
            akind = 3
        else:
            akind = 1
        good = (akind == kind and (kind != 1 or exp == eHF) and
                (flags >> 2 & 1) == ovf and (flags >> 1 & 1) == uf and (flags & 1) == ix)
        if not good:
            predbad += 1
            if predbad <= 5:
                print("PREDICTION DIFFERS w=%d p=%d sExp=%d sig=%#x rule=%s ctl=%d: model kind %d exp %d flags o%d u%d x%d;"
                      " HardFloat out %#x flags %02x" % (W, p, sExp, sig, rule, ctl, kind, eHF, ovf, uf, ix, out, flags))
    print("w=%d p=%d inputs %d: model facts false on %d, model predictions of HardFloat wrong on %d"
          % (W, p, n, factbad, predbad))
    return 1 if factbad or predbad else 0


if __name__ == "__main__":
    sys.exit(main())
