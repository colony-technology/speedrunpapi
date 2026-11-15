"""usage: python -I forks3d_birth.py DIR_OF_DataExp_FILES [POWER]
The angle a streamer fork is born with, after the closing by the outside field is taken off.

forks3d_ride.py: after the split the opening A closes at POWER x A / (distance left to the plate) per mm of advance
(POWER = 0.87 measured between 4 and 14 mm). If that holds all the way, then A x (distance left)^(-POWER) is
constant along a fork, and the opening at the fork itself is
    A0 = A(stretch) x ((Z - z_fork) / (Z - z_stretch)) ^ POWER,
z_stretch being the mean height of the two daughters in that stretch and Z = 67.3 mm the plate.
Printed: A0 from five stretches of the same forks (1 to 3, 3 to 5, 5 to 8, 8 to 12, 12 to 16 mm). If the rule
is right the five agree; where they part, the rule or the stored paths fail. Then A0 from the 3 to 5 mm
stretch by place in the gap and by condition, with quartiles, and the share within 5 degrees of 72."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from forks3d import ang, arclen, load, rows, window_dir

d = sys.argv[1]
power = float(sys.argv[2]) if len(sys.argv) > 2 else 0.87
Z = 67.3
wins = [(1, 3), (3, 5), (5, 8), (8, 12), (12, 16)]
recs = []
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
        zf = T[0][-1][2]
        row = [zf]
        raw = []
        for lo, hi in wins:
            a, b = window_dir(T[1], lo, hi), window_dir(T[2], lo, hi)
            if a is None or b is None:
                row.append(float("nan"))
                raw.append(float("nan"))
                continue
            zs = []
            for k in (1, 2):
                s = arclen(T[k])
                sel = T[k][(s >= lo) & (s <= hi)]
                zs.append(sel[:, 2].mean())
            zst = float(np.mean(zs))
            A = ang(a, b)
            raw.append(A)
            row.append(A * ((Z - zf) / max(1.0, Z - zst)) ** power)
        recs.append((cond, row, raw))
A0 = np.array([r[1] for r in recs])
RAW = np.array([r[2] for r in recs])
full = np.isfinite(A0).all(axis=1)
print("%d forks; %d have all five stretches. Power %.2f, plate at %.1f mm." % (len(A0), full.sum(), power, Z))
print("the same %d forks, stretch by stretch: opening as stored, and carried back to the fork" % full.sum())
for k, (lo, hi) in enumerate(wins):
    print("  %2d to %2d mm   stored %5.1f   at the fork %5.1f  (quartiles %5.1f %5.1f)"
          % (lo, hi, np.median(RAW[full, k]), np.median(A0[full, k + 1]), np.percentile(A0[full, k + 1], 25), np.percentile(A0[full, k + 1], 75)))
b = A0[:, 2]              # column 0 is z, so this is the 3 to 5 mm stretch: the channels are just apart
z = A0[:, 0]
ok = np.isfinite(b)
print("opening at the fork, from the 3 to 5 mm stretch, %d forks: median %.1f, quartiles %.1f %.1f; within 5 degrees of 72: %.3f"
      % (ok.sum(), np.median(b[ok]), np.percentile(b[ok], 25), np.percentile(b[ok], 75), (np.abs(b[ok] - 72) <= 5).mean()))
for lo, hi in ((-99, 22), (22, 30), (30, 99)):
    s = ok & (z >= lo) & (z < hi)
    print("  z %s: %3d forks, at the fork %.1f (%.1f, %.1f)" % ("under 22" if lo < 0 else ("22 to 30" if lo == 22 else "over 30"), s.sum(), np.median(b[s]), np.percentile(b[s], 25), np.percentile(b[s], 75)))
conds = sorted(set(r[0] for r in recs))
for cnd in conds:
    s = ok & np.array([r[0] == cnd for r in recs])
    if s.sum() >= 15:
        print("  %-28s %3d forks, at the fork %.1f (%.1f, %.1f)" % (cnd, s.sum(), np.median(b[s]), np.percentile(b[s], 25), np.percentile(b[s], 75)))
