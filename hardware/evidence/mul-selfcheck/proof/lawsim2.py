# usage: python3 lawsim2.py DIR [PAIRS]
# Runs the netlist in DIR/mul.blif as it stands, table by table, on every input pair when N is 8 or less and on
# PAIRS random pairs plus the corner pairs otherwise, and compares p with a * b. It reads no law.
import os
import random
import sys

d = sys.argv[1]
tables = []
ins_a, outs = [], []
cur = None
for line in open(os.path.join(d, "mul.blif")):
    t = line.split()
    if not t:
        continue
    if t[0] == ".inputs":
        ins_a = t[1:]
    elif t[0] == ".outputs":
        outs = t[1:]
    elif t[0] == ".names":
        cur = (t[-1], t[1:-1], set())
        tables.append(cur)
    elif t[0].startswith("."):
        cur = None
    elif cur is not None:
        cur[2].add(t[0])
n = len(ins_a) // 2


def run(a, b):
    v = {}
    for i in range(n):
        v["a[%d]" % i] = (a >> i) & 1
        v["b[%d]" % i] = (b >> i) & 1
    for o, ins, on in tables:
        v[o] = 1 if "".join(str(v[x]) for x in ins) in on else 0
    return sum(v["p[%d]" % k] << k for k in range(2 * n))


full = (1 << n) - 1
if n <= 8:
    pairs = [(a, b) for a in range(1 << n) for b in range(1 << n)]
else:
    rng = random.Random(2026)
    pairs = [(0, 0), (full, full), (full, 1), (1, full), (full, 0)]
    pairs += [(rng.getrandbits(n), rng.getrandbits(n)) for _ in range(int(sys.argv[2]) if len(sys.argv) > 2 else 200)]
wrong = sum(1 for a, b in pairs if run(a, b) != a * b)
print("N = %d: %d input pairs simulated, %d wrong" % (n, len(pairs), wrong))
sys.exit(1 if wrong else 0)
