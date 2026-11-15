"""Fault effect vectors e_w of a CRC block netlist, and the smallest r with an H (r x 32) such that H e_w != 0.

    python3 tools/fault_vectors.py --blif BLOCK.blif --out proof/NAME_faults.json [--solver PATH/z3 --rmax 8 --work DIR]

e_w: the netlist is a network of XOR LUTs (checked here: every LUT table is the parity of all its inputs).
Flipping net w flips every LUT that reads it, and an output o[i] flips when the number of paths from w to o[i]
is odd.  So e_w[i] = parity of the number of paths from w to o[i], computed backward from the outputs:
e_w = XOR of e_c over the readers c of w, plus bit i for each output buffer o[i] = w.

Minimum r: r = 1 is decided by Gaussian elimination (h . e_w = 1 for all w).  For r >= 2 the question
"exists H with H e_w != 0 for all w" is written as an SMT-LIB problem over the r x 32 bits of H and given to z3;
sat gives an H, unsat proves no H of that r exists.
"""
import argparse
import json
import subprocess
from pathlib import Path


def parse(path):
    ins, outs, luts, cur = [], [], [], None
    for line in path.read_text().replace("\\\n", " ").splitlines():
        t = line.split()
        if not t:
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
        else:
            cur[2].add(t[0])
    return ins, outs, luts


def effect_vectors(ins, outs, luts):
    bufs = {}
    nets = []
    for name, src, rows in luts:
        n = len(src)
        if name in outs and n == 1 and rows == {"1"}:
            bufs.setdefault(src[0], []).append(outs.index(name))
            continue
        if rows != {format(r, "0%db" % n) for r in range(1 << n) if bin(r).count("1") & 1}:
            raise ValueError("not a parity LUT: " + name)
        nets.append((name, src))
    readers = {}
    for name, src in nets:
        for v in src:
            readers.setdefault(v, []).append(name)
    e = {}
    for name, src in reversed(nets):                          # nets are in topological order
        v = 0
        for c in readers.get(name, []):
            v ^= e[c]
        for i in bufs.get(name, []):
            v ^= 1 << i
        e[name] = v
    return [(name, e[name]) for name, _ in nets], bufs


def r1(vecs):
    """Is there h with h . v = 1 for every v?  Gauss-Jordan over GF(2) on rows [v | 1]; None if inconsistent."""
    M = (1 << 32) - 1
    piv = {}                                                  # pivot column -> row
    for v in set(vecs):
        r = v | (1 << 32)
        for c, b in piv.items():
            if (r >> c) & 1:
                r ^= b
        if r & M == 0:
            if r >> 32:
                return None                                   # 0 = 1
            continue
        c = (r & M).bit_length() - 1
        for c2 in list(piv):
            if (piv[c2] >> c) & 1:
                piv[c2] ^= r
        piv[c] = r
    h = sum(1 << c for c, b in piv.items() if b >> 32)       # free variables 0
    assert all(bin(h & v).count("1") & 1 for v in vecs)
    return h


def smt(vecs, r):
    """Variables h_j_i (row j, column i of H).  For each vector v: OR over rows j of (XOR of h_j_i, i in v)."""
    L = ["(set-logic QF_UF)"]
    for j in range(r):
        for i in range(32):
            L.append("(declare-const h_%d_%d Bool)" % (j, i))

    def par(j, v):
        t = ["h_%d_%d" % (j, i) for i in range(32) if (v >> i) & 1]
        return t[0] if len(t) == 1 else "(xor %s)" % " ".join(t)
    for v in sorted(set(vecs)):
        L.append("(assert (or %s))" % " ".join(par(j, v) for j in range(r)))
    L += ["(check-sat)", "(get-model)"]
    return "\n".join(L) + "\n"


def solve(solver, work, vecs, r):
    p = work / ("h_r%d.smt2" % r)
    p.write_text(smt(vecs, r))
    out = subprocess.run([solver, str(p)], capture_output=True, text=True, timeout=3600).stdout
    if out.startswith("unsat"):
        return "unsat", None
    if not out.startswith("sat"):
        return "unknown: " + out[:200], None
    import re
    H = [0] * r
    for m in re.finditer(r"define-fun h_(\d+)_(\d+) \(\) Bool\s+(true|false)", out):
        if m.group(3) == "true":
            H[int(m.group(1))] |= 1 << int(m.group(2))
    assert all(any(bin(h & v).count("1") & 1 for h in H) for v in vecs)
    return "sat", H


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--blif", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--solver")
    ap.add_argument("--work", type=Path)
    ap.add_argument("--rmax", type=int, default=8)
    a = ap.parse_args()
    ins, outs, luts = parse(a.blif)
    ev, bufs = effect_vectors(ins, outs, luts)
    vecs = [v for _, v in ev]
    zero = [n for n, v in ev if v == 0]
    res = {"nets": len(ev), "distinct_nonzero_vectors": len(set(v for v in vecs if v)), "zero_vectors": zero,
           "weights": sorted(set(bin(v).count("1") for v in vecs)), "vectors": {n: "%08x" % v for n, v in ev}}
    live = [v for v in vecs if v]
    h = r1(live)
    res["r1"] = None if h is None else "%08x" % h
    trail = ["r=1: %s" % ("solution h=%08x" % h if h is not None else "no solution (Gaussian elimination)")]
    if h is None and a.solver:
        a.work.mkdir(parents=True, exist_ok=True)
        for r in range(2, a.rmax + 1):
            st, H = solve(a.solver, a.work, live, r)
            trail.append("r=%d: %s%s" % (r, st, "" if H is None else " H=" + ",".join("%08x" % x for x in H)))
            if st == "sat":
                res["r_min"], res["H"] = r, ["%08x" % x for x in H]
                break
    elif h is not None:
        res["r_min"], res["H"] = 1, ["%08x" % h]
    res["trail"] = trail
    a.out.write_text(json.dumps(res, indent=1) + "\n")
    print("\n".join(trail))
    print("nets %d, distinct nonzero e_w %d, zero e_w %d, weights %s" % (res["nets"], res["distinct_nonzero_vectors"], len(zero), res["weights"]))
