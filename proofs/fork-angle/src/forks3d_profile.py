"""usage: python -I forks3d_profile.py DIR_OF_DataExp_FILES
How the opening between the two daughters of a streamer fork changes with distance from the fork: the same
forks read in successive stretches of path (line fitted through each stretch), medians over all forks whose
daughters are at least 16 mm long. Also the points per millimetre near the fork, the streamer diameter stored
with each path (field D), and how far each daughter's first point sits from the parent's last point."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from forks3d import ang, arclen, load, rows, window_dir

d = sys.argv[1]
wins = [(0.5, 2), (1, 3), (2, 4), (3, 5), (4, 6), (5, 8), (6, 10), (8, 12), (10, 14), (12, 16)]
vals = {w: [] for w in wins}
gap, dia, dens = [], [], []
n = 0
for fn in sorted(os.listdir(d)):
    if not fn.endswith("DataExp.mat"):
        continue
    for c in load(os.path.join(d, fn))["DataExp"]:
        if not c or len(c[0]["Segment"]) != 3:
            continue
        sg = c[0]["Segment"]
        T = [rows(s[0]["Traj"]) for s in sg]
        if min(arclen(T[1])[-1], arclen(T[2])[-1]) < 16:
            continue
        n += 1
        for k in (1, 2):
            gap.append(float(np.linalg.norm(T[k][0] - T[0][-1])))
            s = arclen(T[k])
            dens.append(float((s <= 4).sum() / 4.0))
            Dv = sg[k][0].get("D")
            if Dv is not None and len(Dv[2]):
                dia.append(float(np.nanmedian(np.array(Dv[2], float)[:8])))
        for w in wins:
            a, b = window_dir(T[1], *w), window_dir(T[2], *w)
            if a is not None and b is not None:
                vals[w].append(ang(a, b))
print("forks with both daughters at least 16 mm: %d" % n)
print("daughter's first point to parent's last point: median %.2f mm, 90th percentile %.2f mm" % (np.median(gap), np.percentile(gap, 90)))
print("points per mm in a daughter's first 4 mm: median %.2f" % np.median(dens))
if dia:
    print("stored diameter near the fork (field D, first 8 points): median %.2f, quartiles %.2f %.2f" % (np.median(dia), np.percentile(dia, 25), np.percentile(dia, 75)))
for w in wins:
    v = np.array(vals[w])
    print("stretch %4.1f to %4.1f mm: n %4d  median %5.1f  quartiles %5.1f %5.1f" % (w[0], w[1], len(v), np.median(v), np.percentile(v, 25), np.percentile(v, 75)))
