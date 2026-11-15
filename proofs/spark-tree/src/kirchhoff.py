"""usage: python -I kirchhoff.py DIR_OF_DataExp_FILES
Does the exponent a fork conserves follow from the conservation of current?

Per fork with both daughters at least 16 mm (thickness D per leg: median over 3 to 8 mm from the fork; speed V: the
stored one number per leg):
  1. n with median of (D1^n + D2^n) / D0^n equal to 1, with a bootstrap interval;
  2. the current-like sum (D1^2 V1 + D2^2 V2) / (D0^2 V0), median with a bootstrap interval;
  3. the exponent k of speed against thickness, V ~ D^k, three ways: between the two daughters of one fork
     (slope of log(V1/V2) on log(D1/D2) through the origin and by the median of ratios of logs), between each
     daughter and its parent, and across all legs of a condition (rank correlation and least-squares slope of log V
     on log D with the condition's mean taken off);
  4. the closure: if current D^2 V is conserved and V ~ D^k, then D^(2+k) is conserved, so n should be 2 + k.
Read as data."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from forks3d import arclen, load, rows
from heat_fork_lib import dmed, vel

GRID = np.arange(0.5, 6.001, 0.02)


def n_of(r1, r2):
    med = np.array([np.median(r1 ** n + r2 ** n) for n in GRID])
    d = med - 1
    for i in range(len(d) - 1):
        if d[i] * d[i + 1] <= 0:
            return GRID[i] + 0.02 * (-d[i]) / (d[i + 1] - d[i]) if d[i + 1] != d[i] else GRID[i]
    return float("nan")


def main():
    d = sys.argv[1]
    R = []
    for fn in sorted(os.listdir(d)):
        if not fn.endswith("DataExp.mat"):
            continue
        cond = "_".join(fn.split("_")[:3])
        for c in load(os.path.join(d, fn))["DataExp"]:
            if not c:
                continue
            sg = c[0]["Segment"]
            if len(sg) != 3:
                continue
            T = [rows(s[0]["Traj"]) for s in sg]
            if min(arclen(T[1])[-1], arclen(T[2])[-1]) < 16 or arclen(T[0])[-1] < 8:
                continue
            D0 = dmed(sg[0], T[0], 3, 8, from_end=True)
            D1, D2 = dmed(sg[1], T[1], 3, 8), dmed(sg[2], T[2], 3, 8)
            V0, V1, V2 = vel(sg[0]), vel(sg[1]), vel(sg[2])
            if not all(math.isfinite(x) and x > 0 for x in (D0, D1, D2, V0, V1, V2)):
                continue
            R.append((cond, D0, D1, D2, V0, V1, V2))
    conds = [r[0] for r in R]
    A = np.array([r[1:] for r in R], float)
    D0, D1, D2, V0, V1, V2 = A.T
    N = len(A)
    rng = np.random.default_rng(31)
    print("%d forks with thickness and speed of all three legs" % N)
    r1, r2 = D1 / D0, D2 / D0
    n0 = n_of(r1, r2)
    bs = []
    for _ in range(1000):
        k = rng.integers(0, N, N)
        bs.append(n_of(r1[k], r2[k]))
    bs = np.array(bs)
    print("1. n with median (D1^n + D2^n) / D0^n = 1: %.2f (bootstrap 2.5 to 97.5: %.2f to %.2f)" % (n0, np.nanpercentile(bs, 2.5), np.nanpercentile(bs, 97.5)))
    cur = (D1 ** 2 * V1 + D2 ** 2 * V2) / (D0 ** 2 * V0)
    bc = np.array([np.median(cur[rng.integers(0, N, N)]) for _ in range(1000)])
    print("2. current-like sum (D1^2 V1 + D2^2 V2) / (D0^2 V0): median %.3f (bootstrap %.3f to %.3f); quartiles %.3f %.3f"
          % (np.median(cur), np.percentile(bc, 2.5), np.percentile(bc, 97.5), np.percentile(cur, 25), np.percentile(cur, 75)))
    area = (D1 ** 2 + D2 ** 2) / D0 ** 2
    print("   beside it, the cross-sections alone (D1^2 + D2^2) / D0^2: median %.3f; and the speeds, thicker daughter over parent %.3f, thinner %.3f"
          % (np.median(area), np.median(np.where(D1 >= D2, V1, V2) / V0), np.median(np.where(D1 >= D2, V2, V1) / V0)))
    x = np.log(D1 / D2)
    y = np.log(V1 / V2)
    m = np.abs(x) > 0.15
    k_slope = float((x * y).sum() / (x * x).sum())
    k_med = float(np.median(y[m] / x[m]))
    bk = []
    for _ in range(1000):
        q = rng.integers(0, N, N)
        bk.append(float((x[q] * y[q]).sum() / (x[q] * x[q]).sum()))
    bk = np.array(bk)
    print("3. speed against thickness, V ~ D^k")
    print("   between the two daughters of a fork: slope through the origin %.2f (bootstrap %.2f to %.2f); median of log-ratio over log-ratio where the thicknesses differ by 16 percent or more: %.2f (n %d); the thicker is the faster in %.3f"
          % (k_slope, np.percentile(bk, 2.5), np.percentile(bk, 97.5), k_med, int(m.sum()), float(np.mean((x * y) > 0))))
    for label, Dd, Vd in (("thicker daughter against parent", np.where(D1 >= D2, D1, D2), np.where(D1 >= D2, V1, V2)),
                          ("thinner daughter against parent", np.where(D1 >= D2, D2, D1), np.where(D1 >= D2, V2, V1))):
        xx, yy = np.log(Dd / D0), np.log(Vd / V0)
        print("   %s: slope through the origin %.2f; medians D ratio %.3f, V ratio %.3f" % (label, float((xx * yy).sum() / (xx * xx).sum()), np.median(Dd / D0), np.median(Vd / V0)))
    lx, ly = [], []
    for cnd in sorted(set(conds)):
        idx = np.array([i for i, cc in enumerate(conds) if cc == cnd])
        if len(idx) < 15:
            continue
        ld = np.log(np.concatenate([D0[idx], D1[idx], D2[idx]]))
        lv = np.log(np.concatenate([V0[idx], V1[idx], V2[idx]]))
        lx.append(ld - ld.mean())
        ly.append(lv - lv.mean())
    lx, ly = np.concatenate(lx), np.concatenate(ly)
    slope_all = float((lx * ly).sum() / (lx * lx).sum())
    rk = lambda v: np.argsort(np.argsort(v)).astype(float)
    print("   across all legs within a condition (%d legs): least-squares slope of log V on log D %.2f, rank correlation %+.3f" % (len(lx), slope_all, float(np.corrcoef(rk(lx), rk(ly))[0, 1])))
    print("4. closure: 2 + k = %.2f (daughter against daughter) against n = %.2f measured" % (2 + k_slope, n0))
    for kk in (k_slope, k_med, slope_all):
        s = (D1 ** (2 + kk) + D2 ** (2 + kk)) / D0 ** (2 + kk)
        print("   with k = %.2f: median of (D1^(2+k) + D2^(2+k)) / D0^(2+k) = %.3f" % (kk, np.median(s)))


main()
