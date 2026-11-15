"""Independent check of the SEC-DED blocks of one code (n code bits, k data, r = n - k check bits).  Shares no code with the generators.  Standard library only.

    python3 proof/independent_secded_checker.py --source source/prim_secded_72_64_dec.sv
        --enc proof/colony_secded72_enc.blif --syn proof/colony_secded72_syn.blif --cor proof/colony_secded72_cor.blif

Accepts only if all of these hold, and then C1, C2 and C3 follow by the argument printed at the end.
 M. H read from the source text (the eight syndrome masks): H = [P | I]; the 72 columns non-zero, distinct, odd weight.
 E. Every LUT of the encoder is a parity LUT and output c[i] (y[i]) has the GF(2) form of row i of P over d (x).
 S. Every LUT of the syndrome generator is a parity LUT and s[i] (y[i]) has the form of row i of H over r (x).
 K. Corrector, exhaustive: q[j] reads only r[j] and s; on all 512 values of (r[j], s), q[j] = r[j] ^ (s == column j).
    corrected and uncorrectable read only s; on all 256 values of s: corrected = (weight of s is odd),
    uncorrectable = (s != 0 and weight of s is even).
"""
import argparse
import json
import re
from pathlib import Path


def parse(path):
    ins, outs, luts, cur = [], [], [], None
    for line in path.read_text().replace("\\\n", " ").splitlines():
        t = line.split()
        if not t or t[0].startswith("#"):
            continue
        if t[0] == ".inputs":
            ins += t[1:]
        elif t[0] == ".outputs":
            outs += t[1:]
        elif t[0] == ".names":
            cur = [t[-1], t[1:-1], set()]
            luts.append(cur)
        elif t[0] in (".model", ".end"):
            cur = None
        elif t[0].startswith("."):
            raise ValueError("unsupported construct " + t[0])
        else:
            if len(cur[1]) == 0:
                if t != ["1"]:
                    raise ValueError("row format")
                cur[2].add("")
            elif len(t) != 2 or t[1] != "1" or len(t[0]) != len(cur[1]) or set(t[0]) - {"0", "1"}:
                raise ValueError("row format")
            else:
                cur[2].add(t[0])
    return ins, outs, luts


def forms(path, n_in):
    """GF(2) forms of the outputs of a parity network; raises if a LUT is not a parity of its inputs."""
    ins, outs, luts = parse(path)
    if ins != ["x[%d]" % i for i in range(n_in)]:
        raise ValueError("inputs of " + path.name)
    f = {v: 1 << i for i, v in enumerate(ins)}
    for name, src, rows in luts:
        n = len(src)
        if name in f or any(v not in f for v in src):
            raise ValueError("structure at " + name)
        if n == 0:
            if rows:
                raise ValueError("constant one at " + name)
            f[name] = 0
            continue
        if not (n == 1 and rows == {"1"}) and rows != {format(r, "0%db" % n)[::-1] for r in range(1 << n) if bin(r).count("1") & 1}:
            raise ValueError("not a parity LUT: " + name)
        v = 0
        for u in src:
            v ^= f[u]
        f[name] = v
    return [f[o] for o in outs]


def simulate(luts, val):
    v = dict(val)
    for name, src, rows in luts:
        v[name] = 1 if "".join(str(v[u]) for u in src) in rows else 0
    return v


def cone(luts, out):
    drv = {n: s for n, s, _ in luts}
    seen, st, leaves = set(), [out], set()
    while st:
        x = st.pop()
        if x in seen:
            continue
        seen.add(x)
        if x in drv:
            st += drv[x]
        else:
            leaves.add(x)
    return leaves


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    for k in ("source", "enc", "syn", "cor"):
        ap.add_argument("--" + k, type=Path, required=True)
    a = ap.parse_args()
    res, ok = {}, True
    text = a.source.read_text()
    found = [(int(m.group(1)), int(m.group(2)), int(m.group(3), 16))
             for m in re.finditer(r"syndrome_o\[(\d+)\]\s*=\s*\^\(data_i\s*&\s*(\d+)'h([0-9A-Fa-f]+)\)", text)]
    n, nr = found[0][1], len(found)
    k = n - nr
    Hr = {i: v for i, _, v in found}
    H = [Hr[i] for i in range(nr)]
    col = [sum(((H[i] >> j) & 1) << i for i in range(nr)) for j in range(n)]
    M = all(col) and len(set(col)) == n and all(bin(c).count("1") & 1 for c in col) and col[k:] == [1 << i for i in range(nr)]
    res["code"] = "(%d, %d)" % (n, k)
    res["M"] = M
    P = [h & ((1 << k) - 1) for h in H]
    try:
        res["E"] = forms(a.enc, k) == P
    except ValueError as e:
        res["E"] = "rejected: %s" % e
    try:
        res["S"] = forms(a.syn, n) == H
    except ValueError as e:
        res["S"] = "rejected: %s" % e
    ins, outs, luts = parse(a.cor)
    K = ins == ["r[%d]" % j for j in range(k)] + ["s[%d]" % i for i in range(nr)] and \
        outs == ["q[%d]" % j for j in range(k)] + ["corrected", "uncorrectable"]
    cset = set(col)
    sbits = ["s[%d]" % i for i in range(nr)]
    for j in range(k):
        if not K:
            break
        if not cone(luts, "q[%d]" % j) <= {"r[%d]" % j} | set(sbits):
            K = False
            break
        for x in range(1 << (nr + 1)):
            val = {v: 0 for v in ins}
            val["r[%d]" % j] = x & 1
            for i in range(nr):
                val[sbits[i]] = (x >> (1 + i)) & 1
            if simulate(luts, val)["q[%d]" % j] != (x & 1) ^ int((x >> 1) == col[j]):
                K = False
                break
    for f in ("corrected", "uncorrectable"):
        if K and not cone(luts, f) <= set(sbits):
            K = False
    for sv in range(1 << nr):
        if not K:
            break
        val = {v: 0 for v in ins}
        for i in range(nr):
            val[sbits[i]] = (sv >> i) & 1
        o = simulate(luts, val)
        odd = bin(sv).count("1") & 1
        if o["corrected"] != odd or o["uncorrectable"] != int(sv != 0 and not odd):
            K = False
    res["K"] = K
    ok = res["M"] is True and res["E"] is True and res["S"] is True and K is True
    res["ok"] = ok
    if ok:
        res["C1"] = "s = H [d; P d] = P d + P d = 0 (S, E, M: H = [P | I]); K at s = 0: q = r, both flags 0"
        res["C2"] = "one bit j flipped: s = H(x + e_j) = 0 + column j (S, linearity); K at s = column j (odd weight, M): q[j] flipped back if j < k, corrected = 1, uncorrectable = 0; no other q[i] flips since columns are distinct (M)"
        res["C3"] = "bits i != j flipped: s = column i + column j: non-zero (distinct, M), even weight (two odd weights, M), so not a column (all odd, M): no q flips, and K gives uncorrectable = 1, corrected = 0"
    print(json.dumps(res, indent=1))
    raise SystemExit(0 if ok else 1)
