# usage: python3 shapes.py MULDIR [MULDIR ...]
# The cell shapes of each multiplier (as lawcheck2.py counts them: terms with their columns relative to the lowest,
# partial product or wire, outputs with their offsets), with the number of cells of each shape per N.
# For each shape: T = largest value of its terms (all terms 1), the output offsets (every output has sign +1),
# B = sum of 2^offset over the outputs (|d0| <= B for a cell whose outputs are all wrong), and the range of d0
# that can occur: from -T (right value T, all outputs 0) to B (right value 0, all outputs 1).
import json
import os
import sys

shapes = {}
for d in sys.argv[1:]:
    law = json.load(open(os.path.join(d, "law.json")))
    n = law["n"]
    for c in law["cells"]:
        base = min(t[0] for t in c["in"])
        terms = tuple(sorted((t[0] - base, t[1]) for t in c["in"]))
        outs = tuple(k - base for k, _ in c["out"])
        key = (terms, outs)
        shapes.setdefault(key, {})
        shapes[key][n] = shapes[key].get(n, 0) + 1
ns = sorted({n for v in shapes.values() for n in v})
print("| # | terms (offset: kind x count) | outputs (offset, sign) | T | B | d0 range | %s |" % " | ".join("cells at N = %d" % n for n in ns))
print("| --- | --- | --- | --- | --- | --- | %s |" % " | ".join("---" for _ in ns))
for i, ((terms, outs), cnt) in enumerate(sorted(shapes.items(), key=lambda kv: (len(kv[0][1]), kv[0]))):
    groups = {}
    for off, kind in terms:
        groups[(off, kind)] = groups.get((off, kind), 0) + 1
    tdesc = ", ".join("%d: %s x %d" % (off, "pp" if kind == "pp" else "wire", c) for (off, kind), c in sorted(groups.items()))
    T = sum(1 << off for off, _ in terms)
    B = sum(1 << o for o in outs)
    print("| %d | %s | %s | %d | %d | %d..%d | %s |" % (i + 1, tdesc, ", ".join("%d +" % o for o in outs), T, B, -T, B,
                                                     " | ".join(str(cnt.get(n, 0)) for n in ns)))
print("shapes: %d; largest number of outputs: %d; largest B: %d" % (
    len(shapes), max(len(k[1]) for k in shapes), max(sum(1 << o for o in k[1]) for k in shapes)))
