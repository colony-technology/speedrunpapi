"""usage: python -I det_current.py DIR_OF_StreamerFinal_in3D_FILES DIR_OF_DataExp_FILES
Is the current conserved at the junction itself? Speeds from the raw dots next to the fork, thickness from the
stored paths.

One dot per strobe period, so within a run the distance between two successive dots of a leg is its speed in
millimetres per period. At each fork (a dot that ends one segment and starts two):
  parent's speed at the fork     = distance from the dot before the fork dot to the fork dot
  a daughter's speed, first step = distance from the fork dot to its next dot (holds a stretch before the split)
  a daughter's speed, second step = distance between its next two dots (its own travel)
The stored thickness of the three legs comes from the DataExp file of the same run and discharge: the stored fork
whose daughters' first points lie nearest the raw fork dot (within 6 mm), thickness per leg as in section 15
(median of D over 3 to 8 mm from the fork). Daughters are matched by the nearer end direction.
Printed: speed ratios daughter over parent by the first and by the second step, for the thicker and the thinner
daughter; the current-like sum (D1^2 v1 + D2^2 v2) / (D0^2 v0) with each; and the exponent k of speed against
thickness between sister daughters from the raw speeds."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "geometry-tools"))
import numpy as np

from det_planes import segments_of, unit
from forks3d import arclen, rows
from heat_fork_lib import dmed
from mat5load import load


def stored_forks(c):
    sg = c["Segment"]
    out = []
    if len(sg) % 3:
        return out
    for k in range(0, len(sg), 3):
        T = [rows(s[0]["Traj"]) for s in sg[k:k + 3]]
        if min(len(t) for t in T) < 3:
            continue
        if min(arclen(T[1])[-1], arclen(T[2])[-1]) < 10 or arclen(T[0])[-1] < 8:
            continue
        D0 = dmed(sg[k], T[0], 3, 8, from_end=True)
        D1, D2 = dmed(sg[k + 1], T[1], 3, 8), dmed(sg[k + 2], T[2], 3, 8)
        if not all(math.isfinite(x) and x > 0 for x in (D0, D1, D2)):
            continue
        out.append({"at": 0.5 * (T[1][0] + T[2][0]), "D": (D0, D1, D2), "e": (unit(T[1][-1] - T[1][0]), unit(T[2][-1] - T[2][0]))})
    return out


def main():
    ddet, dfit = sys.argv[1], sys.argv[2]
    R = []
    for fn in sorted(os.listdir(ddet)):
        if not fn.endswith("StreamerFinal_in3D.mat"):
            continue
        fit_name = fn.replace("StreamerFinal_in3D.mat", "DataExp.mat")
        if not os.path.exists(os.path.join(dfit, fit_name)):
            continue
        S = load(os.path.join(ddet, fn))["Streamer"]
        Dx = load(os.path.join(dfit, fit_name))["DataExp"]
        for i in range(min(len(S), len(Dx))):
            if not Dx[i]:
                continue
            segs = segments_of(S[i])
            if not segs:
                continue
            SF = stored_forks(Dx[i][0])
            if not SF:
                continue
            starts, ends = {}, {}
            for k, (ids, xyz) in enumerate(segs):
                starts.setdefault(int(ids[0]), []).append(k)
                ends[int(ids[-1])] = k
            for b, ks in starts.items():
                if len(ks) != 2 or b not in ends:
                    continue
                p = segs[ends[b]][1]
                a, c = segs[ks[0]][1], segs[ks[1]][1]
                if len(p) < 2 or len(a) < 3 or len(c) < 3:
                    continue
                at = a[0]
                j = int(np.argmin([np.linalg.norm(f["at"] - at) for f in SF]))
                f = SF[j]
                if np.linalg.norm(f["at"] - at) > 6.0:
                    continue
                ea, ec = unit(a[-1] - a[0]), unit(c[-1] - c[0])
                # match raw daughters to stored daughters by direction
                if np.dot(ea, f["e"][0]) + np.dot(ec, f["e"][1]) >= np.dot(ea, f["e"][1]) + np.dot(ec, f["e"][0]):
                    Da, Dc = f["D"][1], f["D"][2]
                else:
                    Da, Dc = f["D"][2], f["D"][1]
                v0 = float(np.linalg.norm(p[-1] - p[-2]))
                va1, vc1 = float(np.linalg.norm(a[1] - a[0])), float(np.linalg.norm(c[1] - c[0]))
                va2, vc2 = float(np.linalg.norm(a[2] - a[1])), float(np.linalg.norm(c[2] - c[1]))
                if min(v0, va1, vc1, va2, vc2) <= 0:
                    continue
                R.append((f["D"][0], Da, Dc, v0, va1, vc1, va2, vc2))
    A = np.array(R, float)
    D0, Da, Dc, v0, va1, vc1, va2, vc2 = A.T
    thick = Da >= Dc
    Dt, Dn = np.where(thick, Da, Dc), np.where(thick, Dc, Da)
    print("%d forks with raw dots on all three legs and a stored fork within 6 mm" % len(A))
    print("parent's last step %.2f mm per strobe period (median)" % np.median(v0))
    rng = np.random.default_rng(17)
    for label, va, vc in (("first step after the fork dot", va1, vc1), ("second step", va2, vc2)):
        vt, vn = np.where(thick, va, vc), np.where(thick, vc, va)
        cur = (Da ** 2 * va + Dc ** 2 * vc) / (D0 ** 2 * v0)
        bs = np.array([np.median(cur[rng.integers(0, len(cur), len(cur))]) for _ in range(1000)])
        x, y = np.log(Dt / Dn), np.log(vt / vn)
        k = float((x * y).sum() / (x * x).sum())
        print("%s: speed over the parent's, thicker daughter %.3f, thinner %.3f (medians); current-like sum %.3f (bootstrap %.3f to %.3f; quartiles %.3f %.3f); speed against thickness between sisters k = %.2f; thicker is faster in %.3f"
              % (label, np.median(vt / v0), np.median(vn / v0), np.median(cur), np.percentile(bs, 2.5), np.percentile(bs, 97.5),
                 np.percentile(cur, 25), np.percentile(cur, 75), k, float(np.mean(vt > vn))))
    area = (Da ** 2 + Dc ** 2) / D0 ** 2
    print("for these forks the cross-sections alone: (D1^2 + D2^2) / D0^2 median %.3f" % np.median(area))


if __name__ == "__main__":
    main()
