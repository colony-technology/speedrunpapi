"""usage: python -I heat_kernel.py DIR_OF_DataExp_FILES
The fork as a kernel: the heats of the three legs in, the geometry of the fork out, no free number.

Heat of a leg: its charge per length, taken proportional to its stored thickness D to the power n (n = 1: the
field at a streamer's head being about the same for all, charge per length goes with the radius; n = 2: with
the cross-section). kappa_strong and kappa_weak are the daughters' heats over the parent's, "strong" being the
thicker daughter here (so the kernel never sees an angle). The reckoning of fork3d_theory.py with two unequal
daughters then fixes both turns:
    tan(h_weak / 2) = kappa_strong G(alpha),  tan(h_strong / 2) = kappa_weak G(alpha),  alpha = h_strong + h_weak.
Solved for every fork and set beside what is measured: the opening at 3 to 5 mm, the opening carried back to
the parent's last point and to the daughters' first points (forks3d_line2.py), and the two turns at 3 to 5 mm.
Printed for n = 1 and n = 2: medians predicted and measured, the median of (predicted - measured) with its
quartiles, the rank correlation fork by fork with the share of 2,000 shuffles as far from zero, and how often
the thicker daughter is the one that turns less.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from forks3d import ang, arclen, axis, load, rows, window_dir

Z, P = 67.3, 1.28


def G(al):
    return (math.cos(al) / math.sin(al)) * (math.sin(al / 2) + math.cos(al)) - math.cos(al / 2) + math.sin(al)


def solve(ks, kw):
    """Opening and the two turns for daughters' heats ks (strong) and kw (weak); bisection on alpha."""
    f = lambda al: 2 * math.atan(ks * G(al)) + 2 * math.atan(kw * G(al)) - al
    lo, hi = math.radians(5), math.radians(175)
    if f(lo) < 0 or f(hi) > 0:
        return None
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        if f(mid) > 0:
            lo = mid
        else:
            hi = mid
    al = 0.5 * (lo + hi)
    g = G(al)
    return math.degrees(al), math.degrees(2 * math.atan(kw * g)), math.degrees(2 * math.atan(ks * g))   # alpha, h_strong, h_weak


def dmed(seg, T, lo, hi, from_end=False):
    a = seg[0].get("D")
    v = np.array(a[2], float).ravel()
    s = arclen(T)
    n = min(len(v), len(s))
    s = s[:n]
    if from_end:
        s = s[-1] - s
    sel = v[:n][(s >= lo) & (s <= hi)]
    return float(np.nanmedian(sel)) if len(sel) else float("nan")


def rank(v):
    out = np.empty(len(v))
    out[np.argsort(v)] = np.arange(len(v))
    return out


d = sys.argv[1]
recs = []
for fn in sorted(os.listdir(d)):
    if not fn.endswith("DataExp.mat"):
        continue
    for c in load(os.path.join(d, fn))["DataExp"]:
        if not c or len(c[0]["Segment"]) != 3:
            continue
        sg = c[0]["Segment"]
        T = [rows(s[0]["Traj"]) for s in sg]
        if min(arclen(T[1])[-1], arclen(T[2])[-1]) < 16 or arclen(T[0])[-1] < 8:
            continue
        sp = arclen(T[0])
        tail = T[0][sp >= sp[-1] - 6.0]
        travel = axis(tail, tail[-1] - tail[0])
        a, b = window_dir(T[1], 3, 5), window_dir(T[2], 3, 5)
        if a is None or b is None:
            continue
        Dd = [dmed(sg[1], T[1], 3, 8), dmed(sg[2], T[2], 3, 8)]
        Dp = dmed(sg[0], T[0], 3, 8, from_end=True)
        if not np.isfinite(Dd + [Dp]).all():
            continue
        s_, w_ = (0, 1) if Dd[0] >= Dd[1] else (1, 0)        # strong = thicker
        dirs = [a, b]
        h_s, h_w = ang(travel, dirs[s_]), ang(travel, dirs[w_])
        A = ang(a, b)
        zf = T[0][-1][2]
        z0 = 0.5 * (T[1][0][2] + T[2][0][2])
        zst = np.mean([T[k][(arclen(T[k]) >= 3) & (arclen(T[k]) <= 5)][:, 2].mean() for k in (1, 2)])
        A_parent = A * ((Z - zf) / max(1.0, Z - zst)) ** P
        A_first = A * ((Z - z0) / max(1.0, Z - zst)) ** P
        recs.append((Dd[s_] / Dp, Dd[w_] / Dp, h_s, h_w, A, A_parent, A_first))
R = np.array(recs)
print("%d forks; thicker daughter over parent %.3f, thinner over parent %.3f (medians)" % (len(R), np.median(R[:, 0]), np.median(R[:, 1])))
print("measured (medians): opening at 3 to 5 mm %.1f; carried to the parent's last point %.1f; to the daughters' first points %.1f; turn of the thicker %.1f, of the thinner %.1f"
      % tuple(np.median(R[:, k]) for k in (4, 5, 6, 2, 3)))
print("the thicker daughter turns less in %.3f of forks" % (R[:, 2] < R[:, 3]).mean())
rng = np.random.default_rng(14)
for n in (1.0, 2.0):
    pred = []
    keep = []
    for i, r in enumerate(R):
        out = solve(r[0] ** n, r[1] ** n)
        if out is not None:
            pred.append(out)
            keep.append(i)
    Pd = np.array(pred)
    M = R[keep]
    print("heat = thickness^%g: %d forks solved. predicted (medians): opening %.1f, turn of the thicker %.1f, of the thinner %.1f"
          % (n, len(Pd), np.median(Pd[:, 0]), np.median(Pd[:, 1]), np.median(Pd[:, 2])))
    for name, col, pc in (("opening against the one carried to the parent's last point", 5, 0), ("opening against the one carried to the daughters' first points", 6, 0),
                          ("opening against the one at 3 to 5 mm", 4, 0), ("turn of the thicker against measured", 2, 1), ("turn of the thinner against measured", 3, 2)):
        diff = Pd[:, pc] - M[:, col]
        r = float(np.corrcoef(rank(Pd[:, pc]), rank(M[:, col]))[0, 1])
        sh = np.array([np.corrcoef(rank(Pd[:, pc]), rank(rng.permutation(M[:, col])))[0, 1] for _ in range(2000)])
        print("   %-62s predicted - measured: median %+5.1f (quartiles %+5.1f %+5.1f); rank correlation %+.3f (%.3f)"
              % (name, np.median(diff), np.percentile(diff, 25), np.percentile(diff, 75), r, (np.abs(sh) >= abs(r)).mean()))
