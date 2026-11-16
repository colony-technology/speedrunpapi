"""Helper functions for psqrt_check.py: BLIF cones, sub-netlists, ABC cec, and polynomial arithmetic over wires."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from independent_mul_checker import parse_blif, lut_poly, atom_poly, BitPoly  # noqa: E402

safe = lambda v: re.sub(r"[\[\]!]", "_", v)
ap = lambda a: atom_poly(None if a == 0 and not isinstance(a, str) else a)


def wire(a):
    return None if a in (0, 1) else a.lstrip("!")


def cone(tables, targets, sources):
    """LUTs on paths from sources to targets; every leaf must be a source."""
    seen, order, stack = set(), [], [t for t in targets if t not in sources]
    while stack:
        o = stack.pop()
        if o in seen or o in sources:
            continue
        if o not in tables:
            raise ValueError("cone leaves the sources at " + o)
        seen.add(o)
        order.append(o)
        stack += [v for v in tables[o][0] if v not in sources]
    return seen


def topo(tables, names):
    names = set(names)
    out, done = [], set()

    def visit(o):
        stack = [(o, False)]
        while stack:
            x, exp = stack.pop()
            if x in done or x not in names:
                continue
            if exp:
                done.add(x)
                out.append(x)
                continue
            stack.append((x, True))
            for v in tables[x][0]:
                if v in names and v not in done:
                    stack.append((v, False))
    for o in sorted(names):
        visit(o)
    return out


def write_blif(path, ins, outs, luts):
    L = [".model m", ".inputs " + " ".join(ins), ".outputs " + " ".join(outs)]
    for o, vs, rows in luts:
        if not rows:
            L.append(".names " + o)                     # constant 0
            continue
        L.append(".names " + " ".join(vs + [o]))
        L += [(r + " 1") if vs else "1" for r in rows]
    L.append(".end")
    open(path, "w").write("\n".join(L) + "\n")


def sub_blif(tables, names, ins, outs, path, alias):
    """the LUTs `names` as a BLIF over `ins` with outputs `outs` (alias: output port -> driving wire or atom)."""
    luts = [(safe(o), [safe(v) for v in tables[o][0]], sorted(tables[o][1])) for o in topo(tables, names)]
    for port, a in alias.items():
        if a == 0:
            luts.append((port, [], []))
        elif a == 1:
            luts.append((port, [], [""]))
        elif a.startswith("!"):
            luts.append((port, [safe(a[1:])], ["0"]))
        else:
            luts.append((port, [safe(a)], ["1"]))
    write_blif(path, [safe(v) for v in ins], outs, luts)


def cec(abc, a, b):
    p = subprocess.run([abc, "-c", "cec -n %s %s" % (a, b)], capture_output=True, text=True, timeout=1700)
    if "Networks are equivalent" not in p.stdout:
        print(p.stdout[-800:], p.stderr[-400:])
    return "Networks are equivalent" in p.stdout


def lit(a):
    """reference-BLIF literal for an atom: (wire, polarity) or constant."""
    if a in (0, 1):
        return a
    return (safe(a.lstrip("!")), 0 if a.startswith("!") else 1)


def eval_cone(tables, names, env):
    order = topo(tables, names)
    env = dict(env)
    for o in order:
        vs, rows = tables[o]
        key = "".join(str(env[v]) for v in vs)
        env[o] = 1 if key in rows or (not vs and "" in rows) else 0
    return env


def aval(a, env):
    if a in (0, 1):
        return a
    return 1 - env[a[1:]] if a.startswith("!") else env[a]


def poly_of_word(bits, mod, weight=lambda i: 1 << i):
    p = BitPoly(mod)
    for i, a in enumerate(bits):
        for mono, k in ap(a).items():
            p.add(mono, k * weight(i))
    return p


def mul_poly(p, q, mod):
    r = {}
    for m1, c1 in p.items():
        for m2, c2 in q.items():
            m = m1 | m2
            r[m] = (r.get(m, 0) + c1 * c2) % mod
    return {m: c for m, c in r.items() if c}


def add_into(bp, poly, k=1):
    for m, c in poly.items():
        bp.add(m, c * k)
