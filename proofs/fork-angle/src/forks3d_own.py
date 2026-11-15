"""usage: python -I forks3d_own.py DIR_OF_DataExp_FILES
The record's own branching angle beside ours, fork by fork.

Every stored path of the record is an exact circular arc in a plane (forks3d_arc.py), and every forked discharge
carries the authors' own entry Branchplane with Angle = Gamma1 - Gamma2 (degrees). Here, for the forks with both
daughters at least 16 mm: the absolute value of the stored Angle; the angle between the two stored arcs at
their first points (tangent of each arc at its own first point); the same carried along the arcs to the height
of the parent's last point; the distance between the two daughters' first points; and how far back along the
arcs (in mm of path, both arcs by the same amount) one must go from their first points for the angle between
them to equal the stored Angle.
Printed: medians by condition and overall, and the rank correlation between the stored Angle and ours."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from forks3d import ang, arclen, load, rows


def tangent_and_turn(T):
    """Unit tangent at the first point and the signed turning vector per mm of a circular arc (from its chords)."""
    d = np.diff(T, axis=0)
    L = np.linalg.norm(d, axis=1)
    u = d / L[:, None]
    # tangent at the first point: first chord turned back by half its own turning
    k = (u[1] - u[0]) / (0.5 * (L[0] + L[1]))          # d(tangent)/ds, constant on a circle
    t0 = u[0] - k * (0.5 * L[0])
    t0 = t0 / np.linalg.norm(t0)
    return t0, k


def rank(v):
    out = np.empty(len(v))
    out[np.argsort(v)] = np.arange(len(v))
    return out


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
        bp = [x for x in c[0]["Branchplane"] if x]
        if not bp or bp[0][0].get("Angle") is None:
            continue
        own = abs(float(np.array(bp[0][0]["Angle"][2], float).ravel()[0]))
        (t1, k1), (t2, k2) = tangent_and_turn(T[1]), tangent_and_turn(T[2])
        a_first = ang(t1, t2)

        def at(s):                                           # angle between the arcs s mm before their first points
            u1, u2 = t1 - k1 * s, t2 - k2 * s
            return ang(u1 / np.linalg.norm(u1), u2 / np.linalg.norm(u2))
        lo, hi = 0.0, 40.0
        if at(hi) < own:
            back = float("nan")
        else:
            for _ in range(40):
                mid = 0.5 * (lo + hi)
                if at(mid) < own:
                    lo = mid
                else:
                    hi = mid
            back = 0.5 * (lo + hi)
        recs.append((cond, own, a_first, float(np.linalg.norm(T[1][0] - T[2][0])), back, at(1.0) - a_first))
conds = sorted(set(r[0] for r in recs))
A = np.array([r[1:] for r in recs], float)
print("%d forks" % len(A))
print("%-28s forks  stored Angle  arcs at their first points  first points apart, mm  mm back to reach the stored Angle" % "condition")
for cnd in conds + ["all"]:
    s = np.array([r[0] == cnd for r in recs]) if cnd != "all" else np.ones(len(recs), bool)
    if s.sum() < 15:
        continue
    print("%-28s %5d  %6.1f (%5.1f, %5.1f)   %6.1f (%5.1f, %5.1f)        %5.2f                  %5.2f"
          % (cnd, s.sum(), np.median(A[s, 0]), np.percentile(A[s, 0], 25), np.percentile(A[s, 0], 75),
             np.median(A[s, 1]), np.percentile(A[s, 1], 25), np.percentile(A[s, 1], 75), np.median(A[s, 2]), np.nanmedian(A[s, 3])))
print("opening gained per mm back along the arcs: median %.2f degrees" % np.median(A[:, 4]))
print("stored Angle against the arcs at their first points: rank correlation %.3f; median difference %.1f (quartiles %.1f, %.1f)"
      % (np.corrcoef(rank(A[:, 0]), rank(A[:, 1]))[0, 1], np.median(A[:, 0] - A[:, 1]), np.percentile(A[:, 0] - A[:, 1], 25), np.percentile(A[:, 0] - A[:, 1], 75)))
h, _ = np.histogram(A[:, 0], bins=np.arange(40, 131, 10))
print("stored Angle, counts in 10-degree bins from 40: " + " ".join(str(int(v)) for v in h))
