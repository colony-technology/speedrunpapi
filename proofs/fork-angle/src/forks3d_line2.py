"""usage: python -I forks3d_line2.py DIR_OF_DataExp_FILES
Is the closing of a streamer fork a straight line in path distance? If it were, carrying the opening back to
the fork by a straight line would give the same answer from any stretches. Printed, for the 398 forks with the
four stretches from 3 to 16 mm (medians): the opening by stretch; the straight-line carry-back from the three
nearer stretches, from the three farther ones, and from all four; and the same test for the law of forks3d_scan.py
(opening proportional to the distance left to the plate to the power 1.28), from the same subsets."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from forks3d import ang, arclen, load, rows, window_dir

d = sys.argv[1]
Z, p = 67.3, 1.28
wins = [(3, 5), (5, 8), (8, 12), (12, 16)]
mid = np.array([(a + b) / 2 for a, b in wins])
A, ZS, ZF, Z0 = [], [], [], []
for fn in sorted(os.listdir(d)):
    if not fn.endswith("DataExp.mat"):
        continue
    for c in load(os.path.join(d, fn))["DataExp"]:
        if not c or len(c[0]["Segment"]) != 3:
            continue
        T = [rows(s[0]["Traj"]) for s in c[0]["Segment"]]
        if min(arclen(T[1])[-1], arclen(T[2])[-1]) < 16:
            continue
        row, zr = [], []
        for lo, hi in wins:
            a, b = window_dir(T[1], lo, hi), window_dir(T[2], lo, hi)
            if a is None or b is None:
                row = None
                break
            z2 = []
            for k in (1, 2):
                s = arclen(T[k])
                z2.append(T[k][(s >= lo) & (s <= hi)][:, 2].mean())
            row.append(ang(a, b))
            zr.append(float(np.mean(z2)))
        if row is None:
            continue
        A.append(row)
        ZS.append(zr)
        ZF.append(T[0][-1][2])
        Z0.append(0.5 * (T[1][0][2] + T[2][0][2]))
A, ZS, ZF, Z0 = np.array(A), np.array(ZS), np.array(ZF), np.array(Z0)
print("%d forks; opening by stretch (medians): %s" % (len(A), " ".join("%.1f" % v for v in np.median(A, axis=0))))
for name, cols in (("three nearer stretches", [0, 1, 2]), ("three farther stretches", [1, 2, 3]), ("all four", [0, 1, 2, 3])):
    line = np.median([np.polyfit(mid[cols], r[cols], 1)[1] for r in A])
    law = np.median(A[:, cols] * ((Z - ZF)[:, None] / np.maximum(1.0, Z - ZS[:, cols])) ** p, axis=0)
    print("  %-24s straight line carried to the fork: %.1f    power law carried to the fork: %s (mean %.1f)"
          % (name, line, " ".join("%.1f" % v for v in law), law.mean()))
# curvature of the closing in path distance: second differences of the medians
m = np.median(A, axis=0)
s1 = (m[1] - m[0]) / (mid[1] - mid[0])
s2 = (m[2] - m[1]) / (mid[2] - mid[1])
s3 = (m[3] - m[2]) / (mid[3] - mid[2])
print("closing between neighbouring stretches, degrees per mm of path: %.2f, %.2f, %.2f" % (-s1, -s2, -s3))
off = ZF - Z0
print("height of the parent's last point above the mean height of the two daughters' first points: median %.2f mm, quartiles %.2f %.2f, mean %.2f" % (np.median(off), np.percentile(off, 25), np.percentile(off, 75), off.mean()))
law0 = np.median(A * ((Z - Z0)[:, None] / np.maximum(1.0, Z - ZS)) ** p, axis=0)
print("power law carried back to the daughters' first points instead of the parent's last point: %s (mean %.1f)" % (" ".join("%.1f" % v for v in law0), law0.mean()))
