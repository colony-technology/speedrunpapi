#!/usr/bin/env python3
"""Rename the ports of a BLIF, by position, to the port names of a reference BLIF.
usage: rename_ports.py IN.blif REF.blif OUT.blif [model]"""
import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from resub import read_blif

src, ref, out = sys.argv[1], sys.argv[2], sys.argv[3]
model = sys.argv[4] if len(sys.argv) > 4 else None
i1, o1, _ = read_blif(src)
i2, o2, _ = read_blif(ref)
assert len(i1) == len(i2) and len(o1) == len(o2)
mp = dict(zip(i1, i2)); mp.update(zip(o1, o2))
used = set()
text = open(src).read().replace("\\\n", " ")
lines = []
for line in text.splitlines():
    if line.startswith("#") or not line.strip(): continue
    if line.startswith(".model") and model:
        lines.append(".model " + model); continue
    if line.startswith((".inputs", ".outputs", ".names")):
        toks = line.split()
        new = [toks[0]] + [mp.get(t, t) for t in toks[1:]]
        for t in toks[1:]:
            if t not in mp: used.add(t)
        lines.append(" ".join(new))
    else:
        lines.append(line)
assert not (used & set(mp.values())), "an internal name collides with a port name"
open(out, "w").write("\n".join(lines) + "\n")
print("renamed", len(i1), "inputs and", len(o1), "outputs ->", out)
