"""usage: python3 adder_step.py [N]   (default N = 8; needs NumPy)
The step of the adder argument, checked exhaustively on an N-bit adder (2^(2N) rows): for every i from 3 to
N-1, no 6-input LUT that reads a_i, b_i and any four other wires, taken from all the other inputs and the
outputs s_0 .. s_(i-2), computes s_i; and none that reads a_(N-1), b_(N-1) and four wires from the other inputs
and s_0 .. s_(N-3) computes the carry out. Control: with s_(i-1) among the wires, both are computable."""
import itertools
import sys

import numpy as np

N = int(sys.argv[1]) if len(sys.argv) > 1 else 8
rows = np.arange(1 << (2 * N), dtype=np.int64)
a = [(rows >> i) & 1 for i in range(N)]
b = [(rows >> (N + i)) & 1 for i in range(N)]
S = sum(a[i] << i for i in range(N)) + sum(b[i] << i for i in range(N))
s = [(S >> i) & 1 for i in range(N)]
cout = (S >> N) & 1


def computable(target, wires):
    key = np.zeros_like(rows)
    for k, w in enumerate(wires):
        key |= w << k
    z = np.zeros(1 << len(wires), bool)
    o = z.copy()
    z[key[target == 0]] = True
    o[key[target == 1]] = True
    return not (z & o).any()


ins = [("a%d" % i, a[i]) for i in range(N)] + [("b%d" % i, b[i]) for i in range(N)]
for i in list(range(3, N)) + ["cout"]:
    if i == "cout":
        tgt, top, low, name = cout, N - 1, N - 2, "carry out"
    else:
        tgt, top, low, name = s[i], i, i - 1, "s_%d" % i
    pool = [x for x in ins if x[0] not in ("a%d" % top, "b%d" % top)] + [("s%d" % j, s[j]) for j in range(low)]
    hits = sum(computable(tgt, [a[top], b[top]] + [w for _, w in c]) for c in itertools.combinations(pool, 4))
    ctrl = computable(tgt, [a[top], b[top], a[top - 1], b[top - 1], s[top - 1]])
    print("%-9s %2d wires to choose from, %5d sets of four: %d give it; with s_%d: %s"
          % (name, len(pool), len(list(itertools.combinations(pool, 4))), hits, top - 1, "computable" if ctrl else "not"))
