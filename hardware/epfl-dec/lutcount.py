# Table-convention count of a BLIF: nodes with >= 2 fanins, levels over those nodes.
import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from aig import read_blif, lut_stats
c, d, k = lut_stats(read_blif(sys.argv[1]))
print(f"table count: LUTs(>=2 inputs) {c}  levels {d}  max fanin {k}")
