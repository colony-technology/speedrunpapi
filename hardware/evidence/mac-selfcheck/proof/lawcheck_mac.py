# usage: python3 lawcheck_mac.py DIR        (DIR holds mul.blif and law.json)
# Multiply-accumulate copy of lawcheck2.py: a term may also be an addend bit c[k] (kind "in"), used once, in
# column k; p has 2N + 1 bits and a * b + c < 2^(2N+1), so the wires left in columns 2N + 1 and up are zero.
#
# An independent check that the netlist in mul.blif multiplies, for every input, at whatever size it is.
# It trusts nothing in law.json: the file only says where to look. Everything is checked against the netlist's
# own lookup tables.
#
# The invariant:   sum of 2^k * (live wire in column k)  +  sum of 2^(i+j) * a[i] * b[j] over the partial
#                  products not yet used   =   a * b.
# It holds at the start: no wire is live and no partial product is used.
#
#   1. A cell names terms and outputs, each with a column. A term is a live wire in that column, or an unused
#      partial product a[i]*b[j] with i + j equal to that column. Each output is a new wire whose lookup table
#      reads only the cell's own variables. On every assignment of those variables (64 at most):
#          sum of 2^k * term  =  sum of 2^k * output.
#      So using up the terms and making the outputs live leaves the invariant as it was.
#   2. At the end every partial product has been used once, and the live wires are one per output bit k < 2N,
#      wired to p[k], plus wires in columns 2N and above. Every term is zero or positive and a * b < 2^(2N),
#      so those top wires are 0 on every input, and  sum of 2^k * p[k] = a * b.
#
# Two cells with the same tables, wired the same way, are the same check; it is done once and remembered.
# Exit 0 and the line "PROVED" only if every step holds. Otherwise the first failing statement is printed.
import json
import os
import sys

d = sys.argv[1]
law = json.load(open(os.path.join(d, "law.json")))
n = law["n"]

table = {}          # wire -> (input names, set of on-rows)
blif_outputs = []
cur = None
for line in open(os.path.join(d, "mul.blif")):
    t = line.split()
    if not t:
        continue
    if t[0] == ".names":
        cur = t[-1]
        if cur in table:
            sys.exit("FAILED: wire %s is driven twice" % cur)
        table[cur] = (t[1:-1], set())
    elif t[0] == ".outputs":
        blif_outputs = t[1:]
    elif t[0].startswith("."):
        cur = None
    elif cur is not None:
        if len(t) == 2 and t[1] == "1" and set(t[0]) <= set("01") and len(t[0]) == len(table[cur][0]):
            table[cur][1].add(t[0])
        else:
            sys.exit("FAILED: a table row of %s is not a plain 0/1 row" % cur)


def fail(msg):
    print("FAILED: " + msg)
    sys.exit(1)


alive = {}          # live wire -> column
made = set()
seen = set()        # partial products used
seen_c = set()      # addend bits used
known = set()       # cell shapes already checked
rows = 0
for idx, c in enumerate(law["cells"]):
    support, terms = [], []

    def var(name):
        if name not in support:
            support.append(name)
        return support.index(name)

    for t in c["in"]:
        k = t[0]
        if t[1] == "w":
            w = t[2]
            if alive.get(w) != k:
                fail("cell %d: wire %s is not live in column %d" % (idx, w, k))
            del alive[w]
            terms.append((k, var(w), None))
        elif t[1] == "pp":
            i, j = t[2], t[3]
            if not (0 <= i < n and 0 <= j < n) or i + j != k or (i, j) in seen:
                fail("cell %d: partial product (%d, %d) in column %d" % (idx, i, j, k))
            seen.add((i, j))
            terms.append((k, var("a[%d]" % i), var("b[%d]" % j)))
        elif t[1] == "in":
            nm = t[2]
            if nm != "c[%d]" % k or not (0 <= k < 2 * n) or nm in seen_c:
                fail("cell %d: addend bit %s in column %d" % (idx, nm, k))
            seen_c.add(nm)
            terms.append((k, var(nm), None))
        else:
            fail("cell %d: unknown term %s" % (idx, t))
    if len(support) > 12:
        fail("cell %d reads %d variables" % (idx, len(support)))
    base = min(t[0] for t in terms)
    outs = []
    for k, o in c["out"]:
        if o not in table or o in made or k < base:
            fail("cell %d: output %s" % (idx, o))
        ins, on = table[o]
        if not set(ins) <= set(support):
            fail("cell %d: the table of %s reads a wire that is not one of the cell's variables" % (idx, o))
        made.add(o)
        outs.append((k - base, tuple(support.index(x) for x in ins), frozenset(on)))
    shape = (tuple((k - base, x, y) for k, x, y in terms), tuple(outs), len(support))
    if shape not in known:
        for m in range(1 << len(support)):
            bit = [(m >> t) & 1 for t in range(len(support))]
            left = sum((bit[x] if y is None else bit[x] & bit[y]) << k for k, x, y in shape[0])
            right = sum((1 if "".join(str(bit[x]) for x in ins) in on else 0) << k for k, ins, on in outs)
            if left != right:
                fail("cell %d (columns from %d): the terms add up to %d and the outputs to %d on the row %s"
                     % (idx, base, left, right, dict(zip(support, bit))))
            rows += 1
        known.add(shape)
    for k, o in c["out"]:
        alive[o] = k

if len(seen_c) != 2 * n:
    fail("%d of %d addend bits used" % (len(seen_c), 2 * n))
if len(seen) != n * n:
    fail("%d of %d partial products used" % (len(seen), n * n))
top = set(law["above_the_top"])
for k in range(2 * n + 1):
    w = law["outputs"][k]
    name = "p[%d]" % k
    if name not in table:
        fail("output %s is not driven" % name)
    if w is None:
        if table[name][1]:
            fail("output %s should be the constant 0" % name)
        continue
    if alive.get(w) != k:
        fail("output bit %d: wire %s is not live in column %d" % (k, w, k))
    if table[name] != ([w], {"1"}):
        fail("output %s is not wired to %s" % (name, w))
    del alive[w]
for w, k in alive.items():
    if k < 2 * n + 1 or w not in top:
        fail("wire %s in column %d is left over and is not an output" % (w, k))
if sorted(blif_outputs) != sorted("p[%d]" % k for k in range(2 * n + 1)):
    fail("the netlist's outputs are not p[0] .. p[%d]" % (2 * n))

print("PROVED: p = a * b + c for every a, b below 2^%d and c below 2^%d." % (n, 2 * n))
print("  %d cells over %d lookup tables; %d different cell shapes, %d truth-table rows; %d wires above the top are zero"
      % (len(law["cells"]), len(made), len(known), rows, len(top)))
