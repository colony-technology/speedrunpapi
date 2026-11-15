# usage: python3 macsim.py DIR [PAIRS]
# Runs DIR/mul.blif (multiply-accumulate) table by table and compares p with a * b + c. Every input when N <= 4,
# otherwise the corners and PAIRS random inputs. Reads no law.
import os
import random
import sys

d = sys.argv[1]
tables, ins, outs = [], [], []
cur = None
for line in open(os.path.join(d, "mul.blif")):
    t = line.split()
    if not t:
        continue
    if t[0] == ".inputs":
        ins = t[1:]
    elif t[0] == ".outputs":
        outs = t[1:]
    elif t[0] == ".names":
        cur = (t[-1], t[1:-1], set())
        tables.append(cur)
    elif t[0].startswith("."):
        cur = None
    elif cur is not None:
        cur[2].add(t[0] if cur[1] else "")
n = sum(1 for x in ins if x.startswith("a["))
assert len(outs) == 2 * n + 1


def run(a, b, c):
    v = {}
    for i in range(n):
        v["a[%d]" % i] = (a >> i) & 1
        v["b[%d]" % i] = (b >> i) & 1
    for k in range(2 * n):
        v["c[%d]" % k] = (c >> k) & 1
    for o, ii, on in tables:
        v[o] = 1 if "".join(str(v[x]) for x in ii) in on else 0
    return sum(v["p[%d]" % k] << k for k in range(2 * n + 1))


fa, fc = (1 << n) - 1, (1 << (2 * n)) - 1
if n <= 4:
    cases = [(a, b, c) for a in range(1 << n) for b in range(1 << n) for c in range(1 << (2 * n))]
else:
    rng = random.Random(2026)
    cases = [(x, y, z) for x in (0, 1, fa) for y in (0, 1, fa) for z in (0, 1, fc)]
    cases += [(rng.getrandbits(n), rng.getrandbits(n), rng.getrandbits(2 * n)) for _ in range(int(sys.argv[2]) if len(sys.argv) > 2 else 2000)]
wrong = sum(1 for a, b, c in cases if run(a, b, c) != a * b + c)
print("N = %d: %d inputs simulated, %d wrong" % (n, len(cases), wrong))
sys.exit(1 if wrong else 0)
