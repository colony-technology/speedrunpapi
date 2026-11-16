"""usage: python3 ctrl_facts.py random_control/ctrl.blif
The facts the ctrl floor rests on, from the full 128-row truth table: constant outputs, the support of each
other output, whether any output is an input or its complement, and whether any two outputs are equal or
complementary. Reads blifkit.py beside it."""
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from blifkit import Blif

b = Blif.read(sys.argv[1])
n = len(b.inputs)
W = 1 << n
M = (1 << W) - 1
vals = {x: 0 for x in b.inputs}
for r in range(W):
    for k, x in enumerate(b.inputs):
        if (r >> k) & 1:
            vals[x] |= 1 << r
out = b.simulate(vals, W)
tt = {o: out[o] for o in b.outputs}


def support(t):
    return sum(any(((t >> r) & 1) != ((t >> (r ^ (1 << k))) & 1) for r in range(W)) for k in range(n))


print("ctrl: %d inputs, %d outputs, %d truth-table rows" % (n, len(b.outputs), W))
const = [o for o in b.outputs if tt[o] in (0, M)]
print("constant outputs:", ", ".join("%s = %d" % (o, 1 if tt[o] == M else 0) for o in const) or "none")
nc = [o for o in b.outputs if o not in const]
sup = {o: support(tt[o]) for o in nc}
print("non-constant outputs: %d; smallest support %d inputs" % (len(nc), min(sup.values())))
print("outputs on all %d inputs: %s" % (n, ", ".join(sorted(o for o in nc if sup[o] == n))))
lits = {vals[x] for x in b.inputs} | {M ^ vals[x] for x in b.inputs}
print("outputs equal to an input or its complement:", [o for o in nc if tt[o] in lits] or "none")
pairs = [(p, q) for p, q in itertools.combinations(nc, 2) if tt[p] in (tt[q], M ^ tt[q])]
print("pairs of outputs equal or complementary:", pairs or "none")
