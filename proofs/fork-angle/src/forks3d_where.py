"""usage: python -I forks3d_where.py DIR_OF_DataExp_FILES
Does the voltage change how fast a streamer fork closes, or only where in the gap the forks happen?
For each condition: the median height z of its forks (the parent's last point), and the median closing
(opening at 3 to 5 mm minus opening at 12 to 16 mm, per mm) and opening at 3 to 5 mm inside three bands of z
(under 22, 22 to 30, over 30 mm). If the bands agree across voltages, the voltage acts through the place."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from forks3d import ang, arclen, load, rows, window_dir

d = sys.argv[1]
by = {}
for fn in sorted(os.listdir(d)):
    if not fn.endswith("DataExp.mat"):
        continue
    cond = "_".join(fn.split("_")[:3])
    for c in load(os.path.join(d, fn))["DataExp"]:
        if not c or len(c[0]["Segment"]) != 3:
            continue
        T = [rows(s[0]["Traj"]) for s in c[0]["Segment"]]
        if min(arclen(T[1])[-1], arclen(T[2])[-1]) < 16:
            continue
        a1, b1 = window_dir(T[1], 3, 5), window_dir(T[2], 3, 5)
        a2, b2 = window_dir(T[1], 12, 16), window_dir(T[2], 12, 16)
        if a1 is None or b1 is None or a2 is None or b2 is None:
            continue
        o1, o2 = ang(a1, b1), ang(a2, b2)
        by.setdefault(cond, []).append((T[0][-1][2], o1, (o1 - o2) / 9.5))
bands = ((-99, 22), (22, 30), (30, 99))
print("%-28s forks  median z   " % "condition" + "   ".join("z %s: n, opening, closing" % ("under 22" if b[0] < 0 else ("22 to 30" if b[0] == 22 else "over 30")) for b in bands))
for cond in sorted(by):
    A = np.array(by[cond])
    if len(A) < 15:
        continue
    line = "%-28s %5d  %7.1f   " % (cond, len(A), np.median(A[:, 0]))
    for lo, hi in bands:
        s = A[(A[:, 0] >= lo) & (A[:, 0] < hi)]
        line += ("   %3d, %5.1f, %5.2f        " % (len(s), np.median(s[:, 1]), np.median(s[:, 2]))) if len(s) >= 4 else "     (under 4 forks)        "
    print(line)
allA = np.concatenate([np.array(v) for v in by.values()])
z, close = allA[:, 0], allA[:, 2]
slope, icpt = np.polyfit(z, close, 1)
print("all conditions, closing against z: %.3f + %.4f z degrees per mm (z in mm); residual spread %.2f" % (icpt, slope, np.std(close - (icpt + slope * z))))
for cond in sorted(by):
    A = np.array(by[cond])
    if len(A) >= 15:
        res = A[:, 2] - (icpt + slope * A[:, 0])
        print("  %-28s closing left over after the place is taken out: median %+.2f degrees per mm" % (cond, np.median(res)))
