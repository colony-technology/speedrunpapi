"""usage: python -I forks3d.py DIR_OF_DataExp_FILES OUT.tsv
       python -I forks3d.py --control
Opening angles of streamer forks measured in three dimensions (Guo and Nijdam 2024, Zenodo 10534905: every
discharge is one segment, or a parent and two daughters, each a path of points in millimetres).

A direction is always a line fitted through a stretch of a path (its principal axis), pointing along the growth.
For the two daughters of a fork, four readings of the opening between them:
  w2_6    the stretch from 2 to 6 mm of path after the daughter's first point
  w4_10   from 4 to 10 mm
  w8_16   from 8 to 16 mm
  at0     the tangent at the daughter's first point, from a curve of second degree in path length fitted to the
          stretch from 1.5 to 12 mm and carried back to 0 (the angle at the split itself, if the path bends)
The parent's line of travel is fitted to its last 6 mm. Turns: each daughter's w2_6 direction against it.
out_of_plane: the angle between the parent's line of travel and the plane of the two daughters (w2_6).
A fork is kept when both daughters are at least 10 mm long (16 mm for w8_16) and the parent at least 6 mm.
Prediction to compare: 72 degrees (2 pi / 5), 36 to each side, derived for growth in a plane.
--control: drawn forks of 43, 60, 72 and 90 degrees, straight and bent back by 20 degrees over 15 mm, points
every 0.8 mm with 0.15 mm of scatter, through the same four readings.
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "geometry-tools"))
import numpy as np

from mat5load import load


def rows(a):
    (n, m), v = a[1], a[2]
    return np.array(v, float).reshape(m, n).T


def arclen(p):
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])


def axis(pts, forward):
    m = pts.mean(axis=0)
    _, _, vt = np.linalg.svd(pts - m, full_matrices=False)
    d = vt[0]
    return d if np.dot(d, forward) >= 0 else -d


def window_dir(p, lo, hi):
    s = arclen(p)
    sel = p[(s >= lo) & (s <= hi)]
    if len(sel) < 3:
        return None
    return axis(sel, sel[-1] - sel[0])


def tangent0(p, lo=1.5, hi=12.0):
    s = arclen(p)
    k = (s >= lo) & (s <= hi)
    if k.sum() < 5:
        return None
    c = np.polyfit(s[k], p[k], 2)          # rows: s^2, s^1, s^0 for each coordinate
    t = c[1]
    return t / np.linalg.norm(t)


def ang(u, v):
    return math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(u, v))))))


def read_fork(parent, d1, d2):
    L1, L2, Lp = arclen(d1)[-1], arclen(d2)[-1], arclen(parent)[-1]
    if min(L1, L2) < 10 or Lp < 6:
        return None
    sp = arclen(parent)
    tail = parent[sp >= sp[-1] - 6.0]
    travel = axis(tail, tail[-1] - tail[0])
    out = {"len1": L1, "len2": L2, "lenp": Lp}
    for name, lo, hi in (("w2_6", 2, 6), ("w4_10", 4, 10), ("w8_16", 8, 16)):
        a, b = window_dir(d1, lo, hi), window_dir(d2, lo, hi)
        ok = a is not None and b is not None and (name != "w8_16" or min(L1, L2) >= 16)
        out[name] = ang(a, b) if ok else float("nan")
    a, b = tangent0(d1), tangent0(d2)
    out["at0"] = ang(a, b) if a is not None and b is not None else float("nan")
    a, b = window_dir(d1, 2, 6), window_dir(d2, 2, 6)
    if a is None or b is None:
        return None
    t = sorted((ang(travel, a), ang(travel, b)))
    out["turn_small"], out["turn_large"] = t
    n = np.cross(a, b)
    nn = np.linalg.norm(n)
    out["out_of_plane"] = math.degrees(math.asin(min(1.0, abs(float(np.dot(travel, n / nn)))))) if nn > 1e-9 else float("nan")
    return out


def summary(name, v):
    v = np.array([x for x in v if np.isfinite(x)])
    if len(v) == 0:
        return "%-12s none" % name
    return ("%-12s n %4d  median %5.1f  mean %5.1f  quartiles %5.1f %5.1f"
            % (name, len(v), np.median(v), v.mean(), np.percentile(v, 25), np.percentile(v, 75)))


def control():
    rng = np.random.default_rng(3)
    for true in (43, 60, 72, 90):
        for bend in (0.0, 20.0):
            res = []
            for _ in range(300):
                R = np.linalg.qr(rng.normal(size=(3, 3)))[0]
                s = np.arange(0, 20.01, 0.8)

                def path(sign):
                    h = math.radians(true / 2) * sign
                    th = h * (1 - (bend / (true / 2)) * np.clip(s / 15.0, 0, 1) * 0.5) if bend else np.full(len(s), h)
                    # direction turns back toward the parent line by `bend` degrees over 15 mm (half of it per unit shown)
                    dx, dz = np.sin(th), np.cos(th)
                    x = np.concatenate([[0], np.cumsum(0.8 * dx[:-1])])
                    z = np.concatenate([[0], np.cumsum(0.8 * dz[:-1])])
                    return np.stack([x, np.zeros(len(s)), z], axis=1)
                par = np.stack([np.zeros(12), np.zeros(12), np.arange(-11, 1) * 0.8], axis=1)
                P = [(q + rng.normal(0, 0.15, q.shape)) @ R.T for q in (par, path(+1), path(-1))]
                f = read_fork(*P)
                if f:
                    res.append(f)
            print("drawn %2d, bent back %2.0f:  " % (true, bend)
                  + "  ".join("%s %5.1f" % (k, np.nanmedian([r[k] for r in res])) for k in ("w2_6", "w4_10", "w8_16", "at0", "turn_small", "turn_large", "out_of_plane")))


def main(a):
    if a[1] == "--control":
        control()
        return
    d, out = a[1], a[2]
    rows_out = []
    counts = {}
    for fn in sorted(os.listdir(d)):
        if not fn.endswith("DataExp.mat"):
            continue
        cond = "_".join(fn.split("_")[:3])
        D = load(os.path.join(d, fn))["DataExp"]
        nd = nf = 0
        for i, c in enumerate(D):
            if not c:
                continue
            nd += 1
            sg = c[0]["Segment"]
            if len(sg) != 3:
                continue
            T = [rows(s[0]["Traj"]) for s in sg]
            f = read_fork(T[0], T[1], T[2])
            if f is None:
                continue
            nf += 1
            f.update(cond=cond, run=fn.split("__")[0], discharge=i)
            rows_out.append(f)
        c0 = counts.setdefault(cond, [0, 0])
        c0[0] += nd
        c0[1] += nf
    keys = ["w2_6", "w4_10", "w8_16", "at0", "turn_small", "turn_large", "out_of_plane", "len1", "len2", "lenp"]
    with open(out, "w") as f:
        f.write("cond\trun\tdischarge\t" + "\t".join(keys) + "\n")
        for r in rows_out:
            f.write("%s\t%s\t%d\t" % (r["cond"], r["run"], r["discharge"]) + "\t".join("%.2f" % r[k] for k in keys) + "\n")
    print("discharges and forks kept, by condition:")
    for cond, (nd, nf) in sorted(counts.items()):
        print("  %-28s %5d discharges  %4d forks" % (cond, nd, nf))
    print("all forks:")
    for k in keys[:7]:
        print("  " + summary(k, [r[k] for r in rows_out]))
    for cond in sorted(counts):
        sel = [r for r in rows_out if r["cond"] == cond]
        if len(sel) >= 5:
            print(cond)
            for k in ("w2_6", "w4_10", "at0", "turn_small", "turn_large"):
                print("  " + summary(k, [r[k] for r in sel]))
    for k in ("w2_6", "at0"):
        v = np.array([r[k] for r in rows_out if np.isfinite(r[k])])
        h, _ = np.histogram(v, bins=np.arange(0, 181, 12))
        print("%s, counts in 12-degree bins from 0: %s" % (k, " ".join(str(int(x)) for x in h)))
        print("%s within 6 degrees of 72: %.3f; of 60: %.3f; of 90: %.3f" % (k, (abs(v - 72) <= 6).mean(), (abs(v - 60) <= 6).mean(), (abs(v - 90) <= 6).mean()))


if __name__ == "__main__":
    main(sys.argv)
