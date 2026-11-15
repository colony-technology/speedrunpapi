"""usage: python -I forks3d_balance.py DIR_OF_DataExp_FILES
A test, inside the streamer record, of the reading "a fork is opened by its two tips pushing apart and closed
by the field from outside". If it holds, a fork should close more slowly where its tips carry more charge
(thicker, faster streamers) and faster where the outside field is stronger (nearer the pin).

For every fork with both daughters at least 16 mm: the opening at 3 to 5 mm and at 12 to 16 mm, the closing
between them (degrees per mm over 9.5 mm), and three things known at the fork: its height in the gap (the z of
the parent's last point; the discharges start near z = -5 and run toward larger z), the daughters' stored
diameter (field D, mean of the two, median over their first 6 mm), and their stored speed (field V, same).
Printed: the forks split in three equal groups by each of the three, with the medians, and the rank
correlation of each with the closing and with the opening at 3 to 5 mm (share of 4,000 shuffles at least as far
from zero). Air at 133 mbar and 9 kV alone (the largest condition) and all conditions together."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from forks3d import ang, arclen, load, rows, window_dir


def rank(v):
    out = np.empty(len(v))
    out[np.argsort(v)] = np.arange(len(v))
    return out


def corr(x, y, rng):
    r = float(np.corrcoef(rank(x), rank(y))[0, 1])
    sh = np.array([np.corrcoef(rank(x), rank(rng.permutation(y)))[0, 1] for _ in range(4000)])
    return r, float((np.abs(sh) >= abs(r)).mean())


def field(seg, name, s, hi=6.0):
    a = seg[0].get(name)
    if a is None or not len(a[2]):
        return float("nan")
    v = np.array(a[2], float).ravel()
    n = min(len(v), len(s))
    sel = v[:n][s[:n] <= hi]
    return float(np.nanmedian(sel)) if len(sel) else float("nan")


d = sys.argv[1]
recs = []
for fn in sorted(os.listdir(d)):
    if not fn.endswith("DataExp.mat"):
        continue
    cond = "_".join(fn.split("_")[:3])
    for c in load(os.path.join(d, fn))["DataExp"]:
        if not c or len(c[0]["Segment"]) != 3:
            continue
        sg = c[0]["Segment"]
        T = [rows(s[0]["Traj"]) for s in sg]
        if min(arclen(T[1])[-1], arclen(T[2])[-1]) < 16:
            continue
        a1, b1 = window_dir(T[1], 3, 5), window_dir(T[2], 3, 5)
        a2, b2 = window_dir(T[1], 12, 16), window_dir(T[2], 12, 16)
        if a1 is None or b1 is None or a2 is None or b2 is None:
            continue
        o1, o2 = ang(a1, b1), ang(a2, b2)
        dia = np.nanmean([field(sg[k], "D", arclen(T[k])) for k in (1, 2)])
        vel = np.nanmean([field(sg[k], "V", arclen(T[k])) for k in (1, 2)])
        recs.append((cond, T[0][-1][2], dia, vel, o1, (o1 - o2) / 9.5))
rng = np.random.default_rng(2)
for title, sel in (("air, 133 mbar, 9 kV", [r for r in recs if r[0] == "Air_133mbar_9kV"]), ("all conditions", recs)):
    A = np.array([r[1:] for r in sel], float)
    A = A[np.isfinite(A).all(axis=1)]
    print("%s: %d forks; opening at 3 to 5 mm median %.1f; closing median %.2f degrees per mm" % (title, len(A), np.median(A[:, 3]), np.median(A[:, 4])))
    for name, col in (("height z of the fork, mm", 0), ("daughters' diameter", 1), ("daughters' speed", 2)):
        order = np.argsort(A[:, col])
        parts = np.array_split(order, 3)
        line = "  by %-26s" % name
        for p in parts:
            line += "  [%.3g to %.3g: opening %.1f, closing %.2f]" % (A[p, col].min(), A[p, col].max(), np.median(A[p, 3]), np.median(A[p, 4]))
        print(line)
        r1, p1 = corr(A[:, col], A[:, 4], rng)
        r2, p2 = corr(A[:, col], A[:, 3], rng)
        print("     rank correlation with the closing %+.3f (%.3f); with the opening at 3 to 5 mm %+.3f (%.3f)" % (r1, p1, r2, p2))
