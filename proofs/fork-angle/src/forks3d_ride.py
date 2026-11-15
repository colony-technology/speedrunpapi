"""usage: python -I forks3d_ride.py DIR_OF_DataExp_FILES
A check of "after the split the two daughters ride the outside field's lines to the far plate": if so, a fork of
opening A at height z, with the plate at height Z, closes at about A / (Z - z') degrees per mm, z' being where
the closing is measured (here between 3 to 5 and 12 to 16 mm after the fork, so about 9 mm past it).
Z is taken from the record itself: the 99.5th percentile of all stored z. Printed: Z, and for every fork the
measured closing against A / (Z - z - 9): the median of their ratio, its quartiles, the rank correlation, and
the same in three bands of z."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from forks3d import ang, arclen, load, rows, window_dir

d = sys.argv[1]
recs, allz = [], []
for fn in sorted(os.listdir(d)):
    if not fn.endswith("DataExp.mat"):
        continue
    for c in load(os.path.join(d, fn))["DataExp"]:
        if not c:
            continue
        sg = c[0]["Segment"]
        T = [rows(s[0]["Traj"]) for s in sg]
        for t in T:
            allz.append(t[:, 2])
        if len(sg) != 3 or min(arclen(T[1])[-1], arclen(T[2])[-1]) < 16:
            continue
        a1, b1 = window_dir(T[1], 3, 5), window_dir(T[2], 3, 5)
        a2, b2 = window_dir(T[1], 12, 16), window_dir(T[2], 12, 16)
        if a1 is None or b1 is None or a2 is None or b2 is None:
            continue
        o1, o2 = ang(a1, b1), ang(a2, b2)
        recs.append((T[0][-1][2], o1, (o1 - o2) / 9.5))
allz = np.concatenate(allz)
Z = float(np.percentile(allz, 99.5))
A = np.array(recs)
pred = A[:, 1] / (Z - A[:, 0] - 9.0)
ratio = A[:, 2] / pred


def rank(v):
    out = np.empty(len(v))
    out[np.argsort(v)] = np.arange(len(v))
    return out


print("stored z: 0.5th percentile %.1f, median %.1f, 99.5th percentile %.1f mm (taken as the plate)" % (np.percentile(allz, 0.5), np.median(allz), Z))
print("%d forks: measured closing over opening / distance left: median %.2f, quartiles %.2f %.2f; rank correlation %.3f"
      % (len(A), np.median(ratio), np.percentile(ratio, 25), np.percentile(ratio, 75), np.corrcoef(rank(A[:, 2]), rank(pred))[0, 1]))
for lo, hi in ((-99, 22), (22, 30), (30, 99)):
    s = (A[:, 0] >= lo) & (A[:, 0] < hi)
    print("  z %4.0f to %4.0f: %3d forks, measured %.2f, opening / distance left %.2f, ratio %.2f"
          % (max(lo, A[:, 0].min()), min(hi, A[:, 0].max()), s.sum(), np.median(A[s, 2]), np.median(pred[s]), np.median(ratio[s])))
