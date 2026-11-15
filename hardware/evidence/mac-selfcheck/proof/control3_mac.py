# usage: python3 control3_mac.py MACDIR OUTDIR
# Multiply-accumulate copy of control3.py: N = 4, inputs a (4 bits), b (4 bits), c (8 bits), all 65,536 of them.
# Negative control 3: a cell that is correct only on the rows that occur.
# All 65,536 inputs, bit-parallel (one Python integer of 65,536 bits per wire).
#  1. The rows each cell meets without a fault.
#  2. For each single-table fault (inverted), the first later cell that meets a row it never meets without a fault.
#  3. That cell's tables are changed on that row only, so that the cell's error there turns the fault's error
#     e x 2^k into a nonzero multiple of 3. Every other row is left as it was.
# The changed netlist is written to OUTDIR (mul.blif, law.json). Without a fault it computes a * b + c correctly on all
# inputs (macsim.py shows it); lawcheck_mac.py must refuse it; with the fault the value is wrong on an input where the
# residues agree and no wire is above the top: an escape.
import json
import os
import sys

muldir, out = sys.argv[1], sys.argv[2]
law = json.load(open(os.path.join(muldir, "law.json")))
n = law["n"]
assert n == 4
NPAIR = 1 << (4 * n)
ALL = (1 << NPAIR) - 1
tables, order = {}, []
cur = None
for line in open(os.path.join(muldir, "mul.blif")):
    t = line.split()
    if not t:
        continue
    if t[0] == ".names":
        cur = t[-1]
        tables[cur] = [t[1:-1], set()]
        order.append(cur)
    elif t[0].startswith("."):
        cur = None
    elif cur is not None:
        tables[cur][1].add(t[0] if tables[cur][0] else "")
pin = {}
for i in range(n):
    pin["a[%d]" % i] = sum(1 << x for x in range(NPAIR) if (x >> i) & 1)
    pin["b[%d]" % i] = sum(1 << x for x in range(NPAIR) if (x >> (n + i)) & 1)
for k in range(2 * n):
    pin["c[%d]" % k] = sum(1 << x for x in range(NPAIR) if (x >> (2 * n + k)) & 1)


def lit(v, bit):
    return v if bit == "1" else ALL ^ v


def run(tabs, fault=None):
    v = dict(pin)
    for o in order:
        ins, on = tabs[o]
        acc = 0
        for r in on:
            term = ALL
            for x, b in zip(ins, r):
                term &= lit(v[x], b)
            acc |= term
        if fault == o:
            acc ^= ALL
        v[o] = acc
    return v


def cell_rows(v, c):
    """For a cell: {row string over its variables: indicator of the pairs where it occurs}."""
    sup = []
    for t in c["in"]:
        for x in (["a[%d]" % t[2], "b[%d]" % t[3]] if t[1] == "pp" else [t[2]]):
            if x not in sup:
                sup.append(x)
    rows = {}
    for r in range(1 << len(sup)):
        bits = "".join(str((r >> i) & 1) for i in range(len(sup)))
        ind = ALL
        for x, b in zip(sup, bits):
            ind &= lit(v[x], b)
        if ind:
            rows[bits] = ind
    return sup, rows


base = run(tables)
seen = {ci: cell_rows(base, c)[1] for ci, c in enumerate(law["cells"])}
col = {o: k for c in law["cells"] for k, o in c["out"]}
cellof = {o: ci for ci, c in enumerate(law["cells"]) for _, o in c["out"]}
pick = None
for f in order:
    if f not in cellof:
        continue
    vf = run(tables, f)
    for ci in range(cellof[f] + 1, len(law["cells"])):
        sup, rows = cell_rows(vf, law["cells"][ci])
        new = [r for r in rows if r not in seen[ci]]
        if new:
            pick = (f, ci, sup, new[0], rows[new[0]], vf)
            break
    if pick:
        break
f, ci, sup, row, ind, vf = pick
c = law["cells"][ci]
basecol = min(t[0] for t in c["in"])
val = dict(zip(sup, map(int, row)))
terms = sum((val["a[%d]" % t[2]] & val["b[%d]" % t[3]] if t[1] == "pp" else val[t[2]]) << (t[0] - basecol) for t in c["in"])
omax = sum(1 << (k - basecol) for k, _ in c["out"])
x = (ind & -ind).bit_length() - 1
a, b, cc = x & ((1 << n) - 1), (x >> n) & ((1 << n) - 1), x >> (2 * n)
ef = ((vf[f] >> x) & 1) - ((base[f] >> x) & 1)
choice = None
for newval in range(omax + 1):
    d = newval - terms
    tot = ef * (1 << col[f]) + d * (1 << basecol)
    if d != 0 and tot != 0 and tot % 3 == 0 and 0 <= a * b + cc + tot < (1 << (2 * n + 1)):
        choice = newval
        break
assert choice is not None, "no change of this cell gives a multiple of 3"
mod = {o: [list(ins), set(on)] for o, (ins, on) in tables.items()}
for k, o in c["out"]:
    ins, on = mod[o]
    rr = "".join(str(val[x_]) for x_ in ins)
    bit = (choice >> (k - basecol)) & 1
    (on.add if bit else on.discard)(rr)
os.makedirs(out, exist_ok=True)
with open(os.path.join(out, "mul.blif"), "w") as fh:
    for line in open(os.path.join(muldir, "mul.blif")):
        if line.startswith(".names"):
            break
        fh.write(line)
    for o in order:
        ins, on = mod[o]
        fh.write(".names %s %s\n" % (" ".join(ins), o))
        for r in sorted(on):
            fh.write(("%s 1\n" % r) if ins else "1\n")
    fh.write(".end\n")
json.dump(law, open(os.path.join(out, "law.json"), "w"))
vm = run(mod, f)
p = sum(((vm["p[%d]" % k] >> x) & 1) << k for k in range(2 * n + 1))
top = [(vm[w] >> x) & 1 for w in law["above_the_top"]]
info = dict(fault="%s inverted (column %d)" % (f, col[f]), cell=ci, cell_column=basecol, row=dict(val),
            terms_value=terms, outputs_value_set_to=choice, inputs=[a, b, cc], ab_plus_c=a * b + cc, p_with_fault=p,
            residues=[((a % 3) * (b % 3) + cc % 3) % 3, p % 3], top_wires=top)
json.dump(info, open(os.path.join(out, "control3.json"), "w"), indent=1)
print(json.dumps(info))
