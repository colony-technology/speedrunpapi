"""usage: python -I heat_fork.py DIR_OF_DataExp_FILES
The fork read as three legs with one number each, and that number checked against what the record stores.

The reckoning of fork3d_theory.py, taken with two unequal daughters: each tip keeps its direction when
    tan(h_1 / 2) = kappa_2 G(alpha),   tan(h_2 / 2) = kappa_1 G(alpha),   alpha = h_1 + h_2,
    G(alpha) = cot(alpha) (sin(alpha/2) + cos(alpha)) - cos(alpha/2) + sin(alpha),
h_i being daughter i's turn from the parent's line and kappa_i its charge per length over the parent's. So each
daughter's turn is set by the other daughter's charge: the less charged one is pushed further out. Read
backwards, two measured turns give two charges.

Here, for every fork with both daughters at least 16 mm: the turns at 3 to 5 mm from the parent's line (its last
6 mm), the two kappas read from them, and beside them what the record stores independently: each leg's
thickness D (median over 3 to 8 mm from the fork for the daughters, 3 to 8 mm before its end for the parent)
and speed V (one number per leg). "Strong" is the daughter that turns less.
Printed: medians; how often the strong daughter is the thicker and the faster one; rank correlations between
the charges read from the angles and the stored thickness and speed ratios; and whether the parent's own
thickness and speed (the move before the fork) go with the opening and with forking at all.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from forks3d import ang, arclen, axis, load, rows, window_dir


def G(al):
    return (math.cos(al) / math.sin(al)) * (math.sin(al / 2) + math.cos(al)) - math.cos(al / 2) + math.sin(al)


def rank(v):
    out = np.empty(len(v))
    out[np.argsort(v)] = np.arange(len(v))
    return out


def corr(x, y, rng, n=2000):
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    r = float(np.corrcoef(rank(x), rank(y))[0, 1])
    sh = np.array([np.corrcoef(rank(x), rank(rng.permutation(y)))[0, 1] for _ in range(n)])
    return r, float((np.abs(sh) >= abs(r)).mean()), len(x)


def dmed(seg, T, lo, hi, from_end=False):
    a = seg[0].get("D")
    if a is None or not len(a[2]):
        return float("nan")
    v = np.array(a[2], float).ravel()
    s = arclen(T)
    n = min(len(v), len(s))
    s = s[:n]
    if from_end:
        s = s[-1] - s
    sel = v[:n][(s >= lo) & (s <= hi)]
    return float(np.nanmedian(sel)) if len(sel) else float("nan")


def vel(seg):
    a = seg[0].get("V")
    return float(np.array(a[2], float).ravel()[0]) if a is not None and len(a[2]) else float("nan")


d = sys.argv[1]
forks, singles = [], []
for fn in sorted(os.listdir(d)):
    if not fn.endswith("DataExp.mat"):
        continue
    cond = "_".join(fn.split("_")[:3])
    for c in load(os.path.join(d, fn))["DataExp"]:
        if not c:
            continue
        sg = c[0]["Segment"]
        T = [rows(s[0]["Traj"]) for s in sg]
        if len(sg) == 1:
            singles.append((cond, dmed(sg[0], T[0], 0, 1e9), vel(sg[0])))
            continue
        if len(sg) != 3 or min(arclen(T[1])[-1], arclen(T[2])[-1]) < 16 or arclen(T[0])[-1] < 8:
            continue
        sp = arclen(T[0])
        tail = T[0][sp >= sp[-1] - 6.0]
        travel = axis(tail, tail[-1] - tail[0])
        a, b = window_dir(T[1], 3, 5), window_dir(T[2], 3, 5)
        if a is None or b is None:
            continue
        h = [math.radians(ang(travel, a)), math.radians(ang(travel, b))]
        al = math.radians(ang(a, b))
        Dd = [dmed(sg[1], T[1], 3, 8), dmed(sg[2], T[2], 3, 8)]
        Vd = [vel(sg[1]), vel(sg[2])]
        Dp, Vp = dmed(sg[0], T[0], 3, 8, from_end=True), vel(sg[0])
        s_, w_ = (0, 1) if h[0] <= h[1] else (1, 0)          # strong turns less
        g = G(h[0] + h[1])
        if g <= 0:
            continue
        ks, kw = math.tan(h[w_] / 2) / g, math.tan(h[s_] / 2) / g
        forks.append((cond, math.degrees(h[s_]), math.degrees(h[w_]), math.degrees(al), ks, kw,
                      Dd[s_] / Dp, Dd[w_] / Dp, Vd[s_] / Vp, Vd[w_] / Vp, Dp, Vp, math.degrees(h[0] + h[1])))
F = np.array([f[1:] for f in forks], float)
rng = np.random.default_rng(12)
names = ["turn strong", "turn weak", "opening", "kappa strong (from angles)", "kappa weak (from angles)",
         "D strong / D parent", "D weak / D parent", "V strong / V parent", "V weak / V parent", "D parent", "V parent", "sum of turns"]
print("%d forks" % len(F))
for k, nm in enumerate(names):
    v = F[:, k][np.isfinite(F[:, k])]
    print("  %-28s median %6.3f  quartiles %6.3f %6.3f" % (nm, np.median(v), np.percentile(v, 25), np.percentile(v, 75)))
print("the strong daughter (smaller turn) is the thicker one in %.3f of forks, the faster one in %.3f"
      % ((F[:, 5] > F[:, 6]).mean(), (F[:, 7] > F[:, 8]).mean()))
print("in-plane check: sum of the two turns over the opening, median %.3f (1 when the parent's line lies between the daughters)" % np.median(F[:, 11] / F[:, 2]))
tests = [("kappa strong (angles) vs D strong / D parent", 3, 5), ("kappa weak (angles) vs D weak / D parent", 4, 6),
         ("kappa weak / kappa strong vs D weak / D strong", None, None), ("kappa strong vs V strong / V parent", 3, 7),
         ("kappa weak vs V weak / V parent", 4, 8), ("opening vs D parent (the move before)", 2, 9), ("opening vs V parent (the move before)", 2, 10),
         ("turn weak vs D weak / D strong", None, None)]
for nm, i, j in tests:
    if nm.startswith("kappa weak / kappa strong"):
        x, y = F[:, 4] / F[:, 3], F[:, 6] / F[:, 5]
    elif nm.startswith("turn weak vs"):
        x, y = F[:, 1], F[:, 6] / F[:, 5]
    else:
        x, y = F[:, i], F[:, j]
    r, p, n = corr(x, y, rng)
    print("  rank correlation %-48s %+.3f  (shuffles as far: %.3f, n %d)" % (nm, r, p, n))
# forking against not forking, by condition: thickness and speed of the leg before the fork against unforked discharges
S = {}
for cond, Dm, Vm in singles:
    S.setdefault(cond, []).append((Dm, Vm))
print("the move before: forked parents against unforked discharges of the same condition (share of pairs in which the forked one is larger)")
for cond in sorted(set(f[0] for f in forks)):
    P = np.array([(f[10], f[11]) for f in forks if f[0] == cond])   # D parent, V parent
    Q = np.array(S.get(cond, []))
    if len(P) < 15 or len(Q) < 15:
        continue
    out = []
    for k in (0, 1):
        a, b = P[:, k][np.isfinite(P[:, k])], Q[:, k][np.isfinite(Q[:, k])]
        out.append(float((a[:, None] > b[None, :]).mean()))
    print("  %-28s forked %3d, unforked %4d: thicker %.3f, faster %.3f" % (cond, len(P), len(Q), out[0], out[1]))
