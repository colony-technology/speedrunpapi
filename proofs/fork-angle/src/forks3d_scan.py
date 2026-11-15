"""usage: python -I forks3d_scan.py DIR_OF_DataExp_FILES
The angle a streamer fork is born with, found without choosing anything by eye.

Model with one free number p: along a fork the opening A falls as (distance left to the plate)^p, so
A0 = A(stretch) x ((Z - z_fork) / (Z - z_stretch))^p is the opening at the fork. For the 200 forks that have all
five stretches (1 to 3, 3 to 5, 5 to 8, 8 to 12, 12 to 16 mm), p is taken where the five medians of A0 agree
best (smallest spread between the largest and smallest), scanning p from 0.6 to 2.0 in steps of 0.01.
Printed: for the plate at Z = 66, 67.3 (the 99.5th percentile of stored z) and 69 mm: the best p, the spread
left, the five medians, and their mean (the birth angle); the same when the nearest stretch (inside the zone
where the two channels overlap) is left out; then a bootstrap of the forks (1,000 resamples, Z = 67.3, four
stretches): the birth angle and p with their 2.5th to 97.5th percentiles; and the birth angle by condition
and by place at that p."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from forks3d import ang, arclen, load, rows, window_dir

d = sys.argv[1]
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
        A, zs = [], []
        for lo, hi in wins:
            a, b = window_dir(T[1], lo, hi), window_dir(T[2], lo, hi)
            if a is None or b is None:
                A.append(np.nan)
                zs.append(np.nan)
                continue
            z2 = []
            for k in (1, 2):
                s = arclen(T[k])
                z2.append(T[k][(s >= lo) & (s <= hi)][:, 2].mean())
            A.append(ang(a, b))
            zs.append(float(np.mean(z2)))
        recs.append((cond, zf, A, zs))
cond = np.array([r[0] for r in recs])
zf = np.array([r[1] for r in recs])
A = np.array([r[2] for r in recs])
zs = np.array([r[3] for r in recs])
ps = np.arange(0.6, 2.0001, 0.01)


def carried(Z, p, idx, cols):
    return A[np.ix_(idx, cols)] * ((Z - zf[idx])[:, None] / np.maximum(1.0, Z - zs[np.ix_(idx, cols)])) ** p


def best(Z, idx, cols):
    out = []
    for p in ps:
        med = np.median(carried(Z, p, idx, cols), axis=0)
        out.append((med.max() - med.min(), p, med))
    return min(out, key=lambda t: t[0])


full5 = np.flatnonzero(np.isfinite(A).all(axis=1))
full4 = np.flatnonzero(np.isfinite(A[:, 1:]).all(axis=1))
print("forks with all five stretches: %d; with the four outer ones: %d" % (len(full5), len(full4)))
for Z in (66.0, 67.3, 69.0):
    sp, p, med = best(Z, full5, [0, 1, 2, 3, 4])
    print("plate at %.1f, five stretches: p %.2f, spread %.2f, medians %s, birth angle %.1f"
          % (Z, p, sp, " ".join("%.1f" % m for m in med), med.mean()))
    sp, p, med = best(Z, full4, [1, 2, 3, 4])
    print("plate at %.1f, four outer stretches (%d forks): p %.2f, spread %.2f, medians %s, birth angle %.1f"
          % (Z, len(full4), p, sp, " ".join("%.1f" % m for m in med), med.mean()))
rng = np.random.default_rng(4)
bs = []
for _ in range(1000):
    idx = rng.choice(full4, len(full4))
    sp, p, med = best(67.3, idx, [1, 2, 3, 4])
    bs.append((med.mean(), p))
bs = np.array(bs)
print("bootstrap, plate 67.3, four outer stretches: birth angle %.1f (%.1f to %.1f); p %.2f (%.2f to %.2f)"
      % (np.median(bs[:, 0]), np.percentile(bs[:, 0], 2.5), np.percentile(bs[:, 0], 97.5),
         np.median(bs[:, 1]), np.percentile(bs[:, 1], 2.5), np.percentile(bs[:, 1], 97.5)))
sp, p, med = best(67.3, full4, [1, 2, 3, 4])
C = carried(67.3, p, full4, [1, 2, 3, 4]).mean(axis=1)          # each fork's own birth angle: mean of its four
print("each fork's own birth angle (mean of its four stretches, p %.2f): median %.1f, quartiles %.1f %.1f, within 5 degrees of 72: %.3f, of 60: %.3f, of 90: %.3f"
      % (p, np.median(C), np.percentile(C, 25), np.percentile(C, 75), (abs(C - 72) <= 5).mean(), (abs(C - 60) <= 5).mean(), (abs(C - 90) <= 5).mean()))
for name in sorted(set(cond)):
    s = cond[full4] == name
    if s.sum() >= 15:
        print("  %-28s %3d forks, birth angle %.1f (%.1f, %.1f)" % (name, s.sum(), np.median(C[s]), np.percentile(C[s], 25), np.percentile(C[s], 75)))
for lo, hi, label in ((-99, 22, "z under 22"), (22, 30, "z 22 to 30"), (30, 99, "z over 30")):
    s = (zf[full4] >= lo) & (zf[full4] < hi)
    print("  %-28s %3d forks, birth angle %.1f (%.1f, %.1f)" % (label, s.sum(), np.median(C[s]), np.percentile(C[s], 25), np.percentile(C[s], 75)))
h, _ = np.histogram(C, bins=np.arange(40, 111, 5))
print("birth angle, counts in 5-degree bins from 40: " + " ".join(str(int(v)) for v in h))
