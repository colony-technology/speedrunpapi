"""Random simulation of a candidate BLIF against the EPFL reference BLIF, bit-parallel.

python simcmp.py REF CAND [--words W] [--seed S]
Each word is 4096 vectors; the first word also holds all-zero, all-one and one-hot / one-cold patterns.
Inputs and outputs are matched by name.  Prints one JSON line; exit 1 on any mismatch.
"""
import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blif_sim  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("ref")
p.add_argument("cand")
p.add_argument("--words", type=int, default=16)
p.add_argument("--seed", type=int, default=7)
p.add_argument("--lengths", action="store_true", help="odd words: random operand bit lengths")
a = p.parse_args()
R = blif_sim.load(a.ref)
C = blif_sim.load(a.cand)
assert sorted(R[0]) == sorted(C[0]), "inputs differ"
assert sorted(R[1]) == sorted(C[1]), "outputs differ"
ins = R[0]
S = 4096
rnd = random.Random(a.seed)
bad = 0
for w in range(a.words):
    env = {x: rnd.getrandbits(S) for x in ins}
    if a.lengths and w % 2 == 1:
        # every operand (inputs grouped by name before '[') gets a random bit length per vector
        groups = {}
        for x in ins:
            groups.setdefault(x.split("[")[0], []).append(x)
        for g, xs in groups.items():
            idx = {x: int(x.split("[")[1].rstrip("]")) for x in xs}
            lens = [rnd.randint(0, len(xs)) for _ in range(S)]
            for x in xs:
                keep = sum(1 << s for s in range(S) if idx[x] < lens[s])
                env[x] &= keep
    if w == 0:
        # vector 0: zeros, 1: ones, then one-hot and one-cold
        for i, x in enumerate(ins):
            v = env[x] & ~3
            v |= 2
            if 2 + i < S:
                v |= 1 << (2 + i)
            if 2 + len(ins) + i < S:
                v &= ~(1 << (2 + len(ins) + i))
            for j in range(len(ins)):
                if j != i and 2 + len(ins) + j < S:
                    v |= 1 << (2 + len(ins) + j)
                if j != i and 2 + j < S:
                    v &= ~(1 << (2 + j))
            env[x] = v
    e1 = blif_sim.run(R[0], R[1], R[2], dict(env), S)
    e2 = blif_sim.run(C[0], C[1], C[2], dict(env), S)
    for o in R[1]:
        if e1[o] != e2[o]:
            bad += 1
            break
print(json.dumps({"ref": a.ref, "cand": a.cand, "vectors": a.words * S, "mismatching_words": bad}))
raise SystemExit(1 if bad else 0)
