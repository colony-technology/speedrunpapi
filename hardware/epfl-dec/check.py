# Exhaustive truth-table comparison of a BLIF netlist against an EPFL reference AIG
# (inputs matched by name, else by position), plus the table-convention LUT count.
# Usage: check.py ref.aig netlist.blif
import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from aig import read_aig, read_blif, input_patterns, sim_aig, sim_blif, lut_stats
import numpy as np

ref = read_aig(sys.argv[1]); net = read_blif(sys.argv[2])
n = ref["I"]
assert n <= 22, "too many inputs for exhaustive check"
assert len(net["ins"]) == n and len(net["outs"]) == ref["O"]
byname = sorted(net["ins"]) == sorted(ref["inames"]) and sorted(net["outs"]) == sorted(ref["onames"])
X = input_patterns(n)
Yr = sim_aig(ref, X)
if byname:
    Yn = sim_blif(net, X, order=ref["inames"])
    idx = {o: k for k, o in enumerate(net["outs"])}
    Yn = Yn[[idx[o] for o in ref["onames"]]]
else:
    Yn = sim_blif(net, X)
diff = int(np.sum(np.any(Yr != Yn, axis=0)))
c, d, k = lut_stats(net)
print(f"inputs {n}, rows {1<<n}, outputs {ref['O']}, matched by {'name' if byname else 'position'}")
print(f"rows that differ from the reference: {diff}")
print(f"LUTs with >= 2 inputs: {c}; levels over those: {d}; largest LUT: {k} inputs")
