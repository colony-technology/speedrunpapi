# usage: python3 gen_detector_mac.py MACDIR M OUTDIR [--no-top]
# Multiply-accumulate copy of gen_detector.py: residues of a, b and c from the pins, the residue of p (2N + 1 bits),
# x = (a mod q)(b mod q) mod q, s = (x + c mod q) mod q, and mismatch = (s != p mod q).
#
# The detector beside the multiplier in MULDIR (mul.blif, law.json; their tables are copied unchanged).
#   residues of a and of b modulo q, from the pins only; the residue of the output word p modulo q;
#   mis_q = 1 when (a mod q)(b mod q) mod q differs from p mod q;
#   alarm = OR of every mis_q and of every wire above the top column (they are brought out as t[i] too).
# M = 3: q = 3.  M = 15: q = 3 and q = 5 (15 = 3 x 5, so a mismatch modulo 15 is a mismatch modulo 3 or modulo 5).
# A residue node reads at most six bits: either pin or p bits, each with its weight 2^i mod q, or the residue bits
# of earlier nodes (weight 1). Its outputs are the binary digits of (sum of weight x value) mod q, one table each.
# --no-top leaves the wires above the top out of the alarm (a negative control).
#
#   selfcheck.blif   multiplier tables + detector tables; outputs p[*], t[*], alarm
#   detector.blif    the detector alone; inputs a, b, p and the top wires; output alarm
#   det.json         one statement per detector node, for the checker to verify against the tables
import json
import os
import sys

muldir, M, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
notop = "--no-top" in sys.argv
os.makedirs(out, exist_ok=True)
law = json.load(open(os.path.join(muldir, "law.json")))
n = law["n"]
mods = {3: [3], 15: [3, 5]}[M]
mul_lines = [l for l in open(os.path.join(muldir, "mul.blif")) if not l.startswith((".model", ".inputs", ".outputs", ".end"))]

tables = []         # (output, inputs, on-set rows)
nodes = []          # statements for det.json
cnt = [0]


def new(prefix):
    cnt[0] += 1
    return "d_%s%d" % (prefix, cnt[0])


def width(q):
    return (q - 1).bit_length()


def table_of(ins, fn, nout):
    """fn(values of ins) -> integer; returns nout lists of on-rows (row string: ins[0] first)."""
    rows = [[] for _ in range(nout)]
    for r in range(1 << len(ins)):
        v = [(r >> i) & 1 for i in range(len(ins))]
        y = fn(v)
        for b in range(nout):
            if (y >> b) & 1:
                rows[b].append("".join(map(str, v)))
    return rows


def node(q, groups, tag):
    """groups: list of (bit names LSB first, weight). Output: residue bits of sum(weight * value) mod q."""
    ins = [x for g, _ in groups for x in g]
    assert len(ins) <= 6 and len(set(ins)) == len(ins)
    nout = width(q)
    outs = [new(tag) for _ in range(nout)]

    def fn(v):
        s, pos = 0, 0
        for g, w in groups:
            s += w * sum(v[pos + i] << i for i in range(len(g)))
            pos += len(g)
        return s % q
    for o, rows in zip(outs, table_of(ins, fn, nout)):
        tables.append((o, ins, rows))
    nodes.append({"kind": "residue", "mod": q, "in": [[g, w] for g, w in groups], "out": outs})
    return outs


def residue(q, bits, tag):
    """bits: list of (name, weight). A tree of nodes; returns the root's residue bits."""
    k = width(q)
    level = []
    for i in range(0, len(bits), 6):
        level.append(node(q, [([b], w % q) for b, w in bits[i:i + 6]], tag))
    per = 6 // k
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), per):
            grp = level[i:i + per]
            nxt.append(grp[0] if len(grp) == 1 else node(q, [(g, 1) for g in grp], tag))
        level = nxt
    return level[0]


def lut(ins, fn, tag, kind, extra):
    o = new(tag)
    tables.append((o, ins, table_of(ins, fn, 1)[0]))
    nodes.append(dict(kind=kind, out=o, **extra))
    return o


top = list(law["above_the_top"])
alarm_in = []
roots = {}
for q in mods:
    ra = residue(q, [("a[%d]" % i, pow(2, i, q)) for i in range(n)], "a%d_" % q)
    rb = residue(q, [("b[%d]" % i, pow(2, i, q)) for i in range(n)], "b%d_" % q)
    rc = residue(q, [("c[%d]" % k, pow(2, k, q)) for k in range(2 * n)], "c%d_" % q)
    rp = residue(q, [("p[%d]" % k, pow(2, k, q)) for k in range(2 * n + 1)], "p%d_" % q)
    roots[q] = dict(a=ra, b=rb, c=rc, p=rp)
    k = width(q)
    val = lambda v, off: sum(v[off + i] << i for i in range(k))
    # every q: x = (a mod q)(b mod q) mod q; s = (x + c mod q) mod q (a residue node); mismatch = s != p mod q
    prod = []
    rows = table_of(ra + rb, lambda v: (val(v, 0) * val(v, k)) % q, k)
    for b in range(k):
        o = new("x%d_" % q)
        tables.append((o, ra + rb, rows[b]))
        prod.append(o)
    nodes.append({"kind": "product", "mod": q, "a": ra, "b": rb, "out": prod})
    s = node(q, [(prod, 1), (rc, 1)], "s%d_" % q)
    roots[q]["s"] = s
    mis = lut(s + rp, lambda v: int(val(v, 0) % q != val(v, k) % q), "m%d_" % q, "compare", dict(mod=q, x=s, p=rp))
    alarm_in.append(mis)
leaves = alarm_in + ([] if notop else top)
level = leaves
while len(level) > 1:
    nxt = []
    for i in range(0, len(level), 6):
        g = level[i:i + 6]
        nxt.append(g[0] if len(g) == 1 else lut(g, lambda v: int(any(v)), "or", "or", dict(**{"in": g})))
    level = nxt
alarm_src = level[0]


def wr(f, o, ins, rows):
    f.write(".names %s %s\n" % (" ".join(ins), o))
    for r in rows:
        f.write(("%s 1\n" % r) if ins else "1\n")


pins = " ".join(["a[%d]" % i for i in range(n)] + ["b[%d]" % i for i in range(n)] + ["c[%d]" % k for k in range(2 * n)])
pouts = " ".join("p[%d]" % k for k in range(2 * n + 1))
touts = " ".join("t[%d]" % i for i in range(len(top)))
with open(os.path.join(out, "selfcheck.blif"), "w") as f:
    f.write(".model selfcheck\n.inputs %s\n.outputs %s %s alarm\n" % (pins, pouts, touts))
    f.writelines(mul_lines)
    for o, ins, rows in tables:
        wr(f, o, ins, rows)
    for i, w in enumerate(top):
        f.write(".names %s t[%d]\n1 1\n" % (w, i))
    f.write(".names %s alarm\n1 1\n.end\n" % alarm_src)
with open(os.path.join(out, "detector.blif"), "w") as f:
    f.write(".model detector\n.inputs %s %s %s\n.outputs alarm\n" % (pins, pouts, " ".join(top)))
    for o, ins, rows in tables:
        wr(f, o, ins, rows)
    f.write(".names %s alarm\n1 1\n.end\n" % alarm_src)
json.dump({"n": n, "m": M, "mods": mods, "nodes": nodes, "roots": roots, "alarm_leaves": leaves, "alarm": alarm_src,
           "top": top, "no_top": notop}, open(os.path.join(out, "det.json"), "w"), indent=0)
lv = {}
for o, ins, rows in tables:
    lv[o] = 1 + max([lv.get(x, 0) for x in ins] + [0])
print("N = %d, m = %d%s: detector %d lookup tables, %d levels from its inputs; alarm leaves %d"
      % (n, M, " (no top wires)" if notop else "", len(tables), lv[alarm_src], len(leaves)))
