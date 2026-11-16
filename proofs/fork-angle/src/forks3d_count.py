"""usage: python -I forks3d_count.py DIR_OF_DataExp_FILES
How many of the forks followed close, fork by fork. A fork is followed when both daughters are at least 16 mm
long and each has stored points at 3 to 5 mm and at 12 to 16 mm from the fork. Its closing is the opening at
3 to 5 mm less the opening at 12 to 16 mm, per mm, the closing of forks3d_where.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from forks3d import ang, arclen, load, rows, window_dir

d = sys.argv[1]
closing, n16 = [], 0
for fn in sorted(os.listdir(d)):
    if not fn.endswith("DataExp.mat"):
        continue
    for c in load(os.path.join(d, fn))["DataExp"]:
        if not c or len(c[0]["Segment"]) != 3:
            continue
        T = [rows(s[0]["Traj"]) for s in c[0]["Segment"]]
        if min(arclen(T[1])[-1], arclen(T[2])[-1]) < 16:
            continue
        n16 += 1
        a1, b1 = window_dir(T[1], 3, 5), window_dir(T[2], 3, 5)
        a2, b2 = window_dir(T[1], 12, 16), window_dir(T[2], 12, 16)
        if a1 is None or b1 is None or a2 is None or b2 is None:
            continue
        closing.append((ang(a1, b1) - ang(a2, b2)) / 9.5)
C = np.array(closing)
print("forks with both daughters at least 16 mm: %d; followed through both stretches: %d" % (n16, len(C)))
print("close: %d; open: %d; neither: %d" % ((C > 0).sum(), (C < 0).sum(), (C == 0).sum()))
print("closing, degrees per mm: median %.2f, quartiles %.2f and %.2f; the one that opens %.2f" % (np.median(C), *np.percentile(C, [25, 75]), C.min()))
