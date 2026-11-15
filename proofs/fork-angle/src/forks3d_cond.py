"""usage: python -I forks3d_cond.py DIR_OF_DataExp_FILES
The closing of streamer forks with distance, by condition, and the two turns along the way.

For every condition of the record (gas, pressure, voltage): the median opening between the daughters in
stretches of path 1 to 3, 3 to 5, 5 to 8, 8 to 12 and 12 to 16 mm from the fork (forks with both daughters at
least 16 mm), the straight line through those five medians (opening at 0 and closing in degrees per mm), and the
same closing per unit of distance times pressure (degrees per mm at 100 mbar), which should be one number for
all pressures if the fork closes on the scale the gas sets.
Then, over all forks: each daughter's turn from the parent's line of travel in the same stretches."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from forks3d import ang, arclen, axis, load, rows, window_dir

d = sys.argv[1]
wins = [(1, 3), (3, 5), (5, 8), (8, 12), (12, 16)]
mid = np.array([(a + b) / 2 for a, b in wins])
by = {}
turns = {w: [] for w in wins}
for fn in sorted(os.listdir(d)):
    if not fn.endswith("DataExp.mat"):
        continue
    cond = "_".join(fn.split("_")[:3])
    for c in load(os.path.join(d, fn))["DataExp"]:
        if not c or len(c[0]["Segment"]) != 3:
            continue
        T = [rows(s[0]["Traj"]) for s in c[0]["Segment"]]
        if min(arclen(T[1])[-1], arclen(T[2])[-1]) < 16 or arclen(T[0])[-1] < 6:
            continue
        sp = arclen(T[0])
        tail = T[0][sp >= sp[-1] - 6.0]
        travel = axis(tail, tail[-1] - tail[0])
        rec = []
        for w in wins:
            a, b = window_dir(T[1], *w), window_dir(T[2], *w)
            if a is None or b is None:
                rec.append(float("nan"))
                continue
            rec.append(ang(a, b))
            turns[w].append(sorted((ang(travel, a), ang(travel, b))))
        by.setdefault(cond, []).append(rec)
print("condition                      forks   " + "  ".join("%4.0f-%-2.0f" % w for w in wins) + "   at 0   closing/mm   closing/mm at 100 mbar")
for cond in sorted(by):
    A = np.array(by[cond])
    if len(A) < 20:
        continue
    med = np.nanmedian(A, axis=0)
    slope, icpt = np.polyfit(mid, med, 1)
    p = float(cond.split("_")[1].replace("mbar", ""))
    print("%-28s %5d   " % (cond, len(A)) + "  ".join("%7.1f" % v for v in med) + "   %5.1f   %6.2f   %6.2f" % (icpt, -slope, -slope * 100.0 / p))
print("turns from the parent's line of travel, all forks: stretch, smaller turn, larger turn (medians)")
for w in wins:
    t = np.array(turns[w])
    print("  %4.0f to %2.0f mm   %5.1f   %5.1f   (n %d)" % (w[0], w[1], np.median(t[:, 0]), np.median(t[:, 1]), len(t)))
