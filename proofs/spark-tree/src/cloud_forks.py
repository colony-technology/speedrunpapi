"""usage: python -I cloud_forks.py FILE FORMAT OUT_PREFIX [LINK] [REACH] [SKIP]
Fork angles of lightning channels from a radio map: located sources in three dimensions with their times.

FORMAT  wu      columns ID, east [m], north [m], up [m], time [s]; tab separated (Zenodo 19726305)
        scholten  two header lines, then label, time [ms], east [km], north [km], height [km], power, ...
                  (DataverseNL doi:10.34894/MGLPXM)
The growth tree: sources taken in order of time; each is tied to the nearest earlier source if that is within
LINK metres (default 50), else it starts a new tree. A tip that advances leaves a trail tied end to end.
A node's reach is the longest path (metres, summed link lengths) from it to a later end. A fork is a node with
two children whose reach is at least REACH metres (default 150) and with at least REACH metres of trail behind it.
Each daughter's main path follows the child of longest reach. Directions are lines fitted through the main
path's sources whose straight distance from the fork lies in a window; the first SKIP metres (default 15) are
never used, because the tie point is only near the true split. Windows: SKIP to 60 m, 40 to 100 m, 100 to 200 m.
The parent's line of travel: the trail behind the fork between SKIP and 60 m.
Written: OUT_PREFIX.forks.tsv and a summary on the screen.
Prediction to compare: 72 degrees (2 pi / 5) for a tip that splits while following a harmonic field (planar theory).
"""
import math
import sys

import numpy as np


def read(path, fmt):
    rows = []
    with open(path, errors="replace") as f:
        lines = f.read().replace("\r", "").split("\n")
    if fmt == "wu":
        for l in lines:
            p = l.split("\t")
            if len(p) >= 5 and p[0].strip():
                try:
                    rows.append((float(p[4]), float(p[1]), float(p[2]), float(p[3])))
                except ValueError:
                    pass
    else:
        for l in lines[2:]:
            p = l.split()
            if len(p) >= 5:
                try:
                    rows.append((float(p[1]) * 1e-3, float(p[2]) * 1e3, float(p[3]) * 1e3, float(p[4]) * 1e3))
                except ValueError:
                    pass
    a = np.array(rows, float)
    return a[np.argsort(a[:, 0], kind="stable")]


def axis(pts, forward):
    m = pts.mean(axis=0)
    _, _, vt = np.linalg.svd(pts - m, full_matrices=False)
    d = vt[0]
    return d if np.dot(d, forward) >= 0 else -d


def ang(u, v):
    return math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(u, v))))))


def main(a):
    src = read(a[1], a[2])
    out = a[3]
    link = float(a[4]) if len(a) > 4 else 50.0
    reach_min = float(a[5]) if len(a) > 5 else 150.0
    skip = float(a[6]) if len(a) > 6 else 15.0
    t, X = src[:, 0], src[:, 1:4]
    n = len(X)
    parent = np.full(n, -1)
    plen = np.zeros(n)
    from scipy.spatial import cKDTree
    kk = min(n, 48)
    dist, idx = cKDTree(X).query(X, k=kk, distance_upper_bound=link)
    for i in range(1, n):
        earlier = np.flatnonzero(idx[i] < i)          # neighbours come sorted by distance; missing ones carry index n
        if len(earlier):
            parent[i] = idx[i][earlier[0]]
            plen[i] = dist[i][earlier[0]]
        elif np.isfinite(dist[i][-1]):                # all 48 nearest are later sources: look at every earlier one
            d = np.linalg.norm(X[:i] - X[i], axis=1)
            j = int(np.argmin(d))
            if d[j] <= link:
                parent[i] = j
                plen[i] = d[j]
    kids = [[] for _ in range(n)]
    for i in range(n):
        if parent[i] >= 0:
            kids[parent[i]].append(i)
    reach = np.zeros(n)
    best = np.full(n, -1)
    for i in range(n - 1, -1, -1):
        for k in kids[i]:
            r = reach[k] + plen[k]
            if r > reach[i]:
                reach[i] = r
                best[i] = k
    back = np.zeros(n)
    for i in range(n):
        if parent[i] >= 0:
            back[i] = back[parent[i]] + plen[i]
    wins = [(skip, 60.0), (40.0, 100.0), (100.0, 200.0)]
    rows = []
    for i in range(n):
        ks = sorted((k for k in kids[i] if reach[k] + plen[k] >= reach_min), key=lambda k: -(reach[k] + plen[k]))
        if len(ks) < 2 or back[i] < reach_min:
            continue
        trail, j = [], parent[i]
        while j >= 0 and np.linalg.norm(X[j] - X[i]) <= 70:
            trail.append(j)
            j = parent[j]
        tp = np.array([X[q] for q in trail if skip <= np.linalg.norm(X[q] - X[i]) <= 60])
        if len(tp) < 4:
            continue
        travel = -axis(tp, tp[-1] - tp[0])          # trail runs backward in time; travel points forward
        paths, dts = [], []
        for k in ks[:2]:
            p, j = [], k
            while j >= 0 and np.linalg.norm(X[j] - X[i]) <= 210:
                p.append(j)
                j = best[j]
            paths.append(np.array([X[q] for q in p]))
            near = [q for q in p if skip <= np.linalg.norm(X[q] - X[i]) <= 60]
            dts.append(1e3 * (float(np.median(t[near])) - t[i]) if near else float("nan"))
        tback = [q for q in trail if skip <= np.linalg.norm(X[q] - X[i]) <= 60]
        rec = [t[i], X[i][0], X[i][1], X[i][2], 1e3 * (float(np.median(t[tback])) - t[i]), min(dts), max(dts)]
        ok = True
        for lo, hi in wins:
            ds = []
            for p in paths:
                dist = np.linalg.norm(p - X[i], axis=1)
                sel = p[(dist >= lo) & (dist <= hi)]
                ds.append(axis(sel, sel[-1] - sel[0]) if len(sel) >= 4 else None)
            if ds[0] is None or ds[1] is None:
                rec += [float("nan")] * 3
                if lo == skip:
                    ok = False
                continue
            turns = sorted((ang(travel, ds[0]), ang(travel, ds[1])))
            rec += [ang(ds[0], ds[1]), turns[0], turns[1]]
        if ok:
            rows.append(rec)
    head = ["t", "east", "north", "up", "ms_parent", "ms_first_daughter", "ms_second_daughter"]
    for lo, hi in wins:
        head += ["open_%d_%d" % (lo, hi), "turn_small_%d_%d" % (lo, hi), "turn_large_%d_%d" % (lo, hi)]
    with open(out + ".forks.tsv", "w") as f:
        f.write("\t".join(head) + "\n")
        for r in rows:
            f.write("\t".join("%.3f" % v for v in r) + "\n")
    A = np.array(rows, float) if rows else np.zeros((0, len(head)))
    print("%d sources over %.3f s; tied %d (link %.0f m), trees %d; forks kept %d (reach %.0f m, skip %.0f m)"
          % (n, t[-1] - t[0], int((parent >= 0).sum()), link, int((parent < 0).sum()), len(A), reach_min, skip))
    def table(B, title):
        print(title % len(B))
        for c in range(4, len(head)):
            v = B[:, c][np.isfinite(B[:, c])] if len(B) else np.array([])
            if len(v):
                print("  %-22s n %4d  median %5.1f  mean %5.1f  quartiles %5.1f %5.1f"
                      % (head[c], len(v), np.median(v), v.mean(), np.percentile(v, 25), np.percentile(v, 75)))

    table(A, "all forks (%d)")
    if len(A):
        # a split in step: the trail arrives within 5 ms before the node, and both daughters' first 60 m
        # are laid within 5 ms after it and within 2 ms of each other
        step = (A[:, 4] < 0) & (A[:, 4] > -5) & (A[:, 5] > 0) & (A[:, 6] < 5) & (A[:, 6] - A[:, 5] < 2)
        table(A[step], "splits in step: both daughters grow at once, right after the parent arrives (%d)")
        table(A[~step], "the rest: one branch laid later, or a channel used again (%d)")


if __name__ == "__main__":
    main(sys.argv)
