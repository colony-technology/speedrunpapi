"""usage: python -I triangle2.py DIR_OF_DataExp_FILES
The junction balance of a fork, tested in the direction that the noise of the stored thickness allows.

If a leg pulls on the junction with weight T = D^a along its own line, rest means two equations, with h_k the
turn of daughter k from the parent's line:
    across the parent's line:   T1 sin h1 = T2 sin h2         (the sines of the turns are as the other's weight)
    along the parent's line:    T0 = T1 cos h1 + T2 cos h2     (the parent's weight is the daughters' pulls forward)
One unknown, a. The law holds if ONE a satisfies BOTH. For each of three readings of the turns (3 to 5 mm; the
stored arcs' first chords; the record's own Gamma1, Gamma2) this prints, for a from 0.5 to 4:
    across(a) = median of  D_thick^a sin h_thick / (D_thin^a sin h_thin)
    along(a)  = median of  (D1^a cos h1 + D2^a cos h2) / D0^a
then the a at which each is 1, with a bootstrap interval (1,000 resamples of the forks), and the same after each
fork is given another fork's three thicknesses (control: the turns then do not belong to the thicknesses).
Also the slope of log(sin h_thin / sin h_thick) on log(D_thick / D_thin), fork by fork (through the origin, and
the rank correlation), which is a read off the across equation alone.
Thickness and turns as in triangle.py."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from forks3d import ang, arclen, axis, load, rows, window_dir
from heat_fork_lib import dmed


def unit(v):
    return v / np.linalg.norm(v)


def rank(v):
    out = np.empty(len(v))
    out[np.argsort(v)] = np.arange(len(v))
    return out


GRID = np.arange(0.5, 4.001, 0.02)


def curves(D0, D1, D2, h1, h2):
    """across(a), along(a) on GRID; h in degrees."""
    s1, s2 = np.sin(np.radians(h1)), np.sin(np.radians(h2))
    c1, c2 = np.cos(np.radians(h1)), np.cos(np.radians(h2))
    thick = D1 >= D2
    Dt, Dn = np.where(thick, D1, D2), np.where(thick, D2, D1)
    st, sn = np.where(thick, s1, s2), np.where(thick, s2, s1)
    across = np.array([np.median((Dt ** a * st) / (Dn ** a * sn)) for a in GRID])
    along = np.array([np.median((D1 ** a * c1 + D2 ** a * c2) / D0 ** a) for a in GRID])
    return across, along


def crossing(curve):
    """the a on GRID where the curve passes 1 (first crossing); nan if it never does."""
    d = curve - 1
    for i in range(len(d) - 1):
        if d[i] == 0:
            return GRID[i]
        if d[i] * d[i + 1] < 0:
            return GRID[i] + (GRID[i + 1] - GRID[i]) * (-d[i]) / (d[i + 1] - d[i])
    return float("nan")


def main():
    d = sys.argv[1]
    R = []
    for fn in sorted(os.listdir(d)):
        if not fn.endswith("DataExp.mat"):
            continue
        for c in load(os.path.join(d, fn))["DataExp"]:
            if not c:
                continue
            sg = c[0]["Segment"]
            if len(sg) != 3:
                continue
            T = [rows(s[0]["Traj"]) for s in sg]
            if min(arclen(T[1])[-1], arclen(T[2])[-1]) < 16 or arclen(T[0])[-1] < 8:
                continue
            sp = arclen(T[0])
            tail = T[0][sp >= sp[-1] - 6.0]
            travel = axis(tail, tail[-1] - tail[0])
            a, b = window_dir(T[1], 3, 5), window_dir(T[2], 3, 5)
            D0 = dmed(sg[0], T[0], 3, 8, from_end=True)
            D1, D2 = dmed(sg[1], T[1], 3, 8), dmed(sg[2], T[2], 3, 8)
            if not all(math.isfinite(x) and x > 0 for x in (D0, D1, D2)):
                continue
            h35 = (ang(travel, a), ang(travel, b)) if a is not None and b is not None else (float("nan"), float("nan"))
            p = unit(T[0][-1] - T[0][-2])
            h0 = (ang(p, unit(T[1][1] - T[1][0])), ang(p, unit(T[2][1] - T[2][0])))
            g = (float("nan"), float("nan"))
            bp = [x for x in c[0]["Branchplane"] if x]
            if bp:
                try:
                    g = (abs(float(np.array(bp[0][0]["Gamma1"][2], float).ravel()[0])),
                         abs(float(np.array(bp[0][0]["Gamma2"][2], float).ravel()[0])))
                except Exception:
                    pass
            R.append((D0, D1, D2, h35[0], h35[1], h0[0], h0[1], g[0], g[1]))
    R = np.array(R, float)
    print("%d forks with the three thicknesses" % len(R))
    rng = np.random.default_rng(21)
    for label, i, j in (("turns at 3 to 5 mm", 3, 4), ("stored arcs' first chords", 5, 6), ("record's Gamma1, Gamma2", 7, 8)):
        ok = np.isfinite(R[:, i]) & np.isfinite(R[:, j]) & (R[:, i] > 0.5) & (R[:, j] > 0.5) & (R[:, i] < 89.5) & (R[:, j] < 89.5)
        D0, D1, D2, h1, h2 = R[ok, 0], R[ok, 1], R[ok, 2], R[ok, i], R[ok, j]
        n = len(D0)
        across, along = curves(D0, D1, D2, h1, h2)
        aa, al = crossing(across), crossing(along)
        ba, bl = [], []
        for _ in range(1000):
            k = rng.integers(0, n, n)
            x, y = curves(D0[k], D1[k], D2[k], h1[k], h2[k])
            ba.append(crossing(x))
            bl.append(crossing(y))
        ba, bl = np.array(ba), np.array(bl)
        ca, cl = [], []
        for _ in range(300):
            k = rng.permutation(n)
            x, y = curves(D0[k], D1[k], D2[k], h1, h2)
            ca.append(crossing(x))
            cl.append(crossing(y))
        ca, cl = np.array(ca), np.array(cl)
        print("")
        print("%s, %d forks (both turns between 0.5 and 89.5 degrees)" % (label, n))
        print("   a      across   along")
        for a in (1.0, 1.5, 2.0, 2.5, 3.0):
            k = int(round((a - GRID[0]) / 0.02))
            print("   %.1f    %6.3f  %6.3f" % (a, across[k], along[k]))
        print("   across is 1 at a = %.2f (bootstrap 2.5 to 97.5: %.2f to %.2f; no crossing in %d of 1000)"
              % (aa, np.nanpercentile(ba, 2.5), np.nanpercentile(ba, 97.5), int(np.isnan(ba).sum())))
        print("   along  is 1 at a = %.2f (bootstrap 2.5 to 97.5: %.2f to %.2f; no crossing in %d of 1000)"
              % (al, np.nanpercentile(bl, 2.5), np.nanpercentile(bl, 97.5), int(np.isnan(bl).sum())))
        print("   with another fork's thicknesses: across is 1 at a = %s (no crossing in %d of 300); along is 1 at a = %s (no crossing in %d of 300)"
              % ("%.2f, 2.5 to 97.5: %.2f to %.2f" % (np.nanmedian(ca), np.nanpercentile(ca, 2.5), np.nanpercentile(ca, 97.5)) if np.isfinite(ca).any() else "never",
                 int(np.isnan(ca).sum()),
                 "%.2f, 2.5 to 97.5: %.2f to %.2f" % (np.nanmedian(cl), np.nanpercentile(cl, 2.5), np.nanpercentile(cl, 97.5)) if np.isfinite(cl).any() else "never",
                 int(np.isnan(cl).sum())))
        thick = D1 >= D2
        x = np.log(np.where(thick, D1, D2) / np.where(thick, D2, D1))
        y = np.log(np.where(thick, np.sin(np.radians(h2)), np.sin(np.radians(h1))) / np.where(thick, np.sin(np.radians(h1)), np.sin(np.radians(h2))))
        slope = float((x * y).sum() / (x * x).sum())
        r = float(np.corrcoef(rank(x), rank(y))[0, 1])
        print("   log(sin turn thin / sin turn thick) on log(D thick / D thin): slope through the origin %.2f, rank correlation %+.3f; the thicker daughter turns less in %.3f"
              % (slope, r, float(np.mean(np.where(thick, h1, h2) < np.where(thick, h2, h1)))))
        at = aa if np.isfinite(aa) else 2.0
        pred = (D1 ** at * np.cos(np.radians(h1)) + D2 ** at * np.cos(np.radians(h2))) ** (1 / at)
        print("   the parent's thickness reckoned from the two daughters at a = %.2f: median of reckoned over stored %.3f, quartiles %.3f %.3f; rank correlation %+.3f"
              % (at, np.median(pred / D0), np.percentile(pred / D0, 25), np.percentile(pred / D0, 75), float(np.corrcoef(rank(pred), rank(D0))[0, 1])))


main()
