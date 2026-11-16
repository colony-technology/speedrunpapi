"""Edge vectors for a square-root netlist: X in {q^2 - 1, q^2, q^2 + 1, (q+1)^2 - 1} for q of every bit length,
table-cell edges of the normalised radicand at every shift, 0, 1, all ones.  Checked against math.isqrt and,
when given, against the EPFL reference netlist on the same vectors.

python edge_test.py NETLIST M [REF]      (M = root width; inputs a[0..2M-1], outputs asqrt[0..M-1])
"""
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blif_sim  # noqa: E402

net, m = sys.argv[1], int(sys.argv[2])
ref = sys.argv[3] if len(sys.argv) > 3 else None
rnd = random.Random(9)
xs = [0, 1, 2, 3, (1 << (2 * m)) - 1]
for L in range(1, m + 1):
    for _ in range(24):
        q = rnd.getrandbits(L) | (1 << (L - 1))
        for X in (q * q - 1, q * q, q * q + 1, (q + 1) * (q + 1) - 1, (q + 1) * (q + 1) - 2):
            if 0 <= X < 1 << (2 * m):
                xs.append(X)
for sh in range(0, 2 * m - 12, 2):
    for i in range(1 << 10, 1 << 12, 37):
        base = i << (2 * m - 12 - sh)
        xs += [base >> 0, (base + (1 << (2 * m - 12 - sh))) - 1]
xs = [x for x in xs if 0 <= x < 1 << (2 * m)]
S = len(xs)
ins = ["a[%d]" % i for i in range(2 * m)]
env = {x: sum(((X >> i) & 1) << s for s, X in enumerate(xs)) for i, x in enumerate(ins)}
I, O, N = blif_sim.load(net)
e1 = blif_sim.run(I, O, N, dict(env), S)
bad = 0
for s, X in enumerate(xs):
    got = sum(((e1["asqrt[%d]" % i] >> s) & 1) << i for i in range(m))
    bad += got != math.isqrt(X)
badref = None
if ref:
    R = blif_sim.load(ref)
    e2 = blif_sim.run(R[0], R[1], R[2], dict(env), S)
    badref = sum(1 for o in O if e1[o] != e2[o])
print({"vectors": S, "wrong_vs_isqrt": bad, "outputs_differing_from_reference": badref})
sys.exit(1 if bad or badref else 0)
