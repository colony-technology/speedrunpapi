"""usage: python -I cloud_planes.py FILE FORMAT [LINK] [REACH] [SKIP]
The quarter turn between successive forks, asked of lightning itself: located radio sources of a flash in three
dimensions (LOFAR). Same growth tree and the same forks as cloud_forks.py (sources in order of time, each tied to
the nearest earlier one within LINK metres; a fork is a node with two onward trails of at least REACH metres and
REACH metres behind it; directions are lines through a trail's sources between SKIP and 60 m from the fork).

A second fork hangs on a first when it lies on the main onward trail of one of the first fork's two daughters.
For each such pair: the rotation of the second fork's plane (spanned by its two daughters' directions) against the
first's, about the line joining the two forks, folded to 0..90. Control: second forks paired with the first forks
of other pairs (2,000 pairings). Also printed by the length of the connecting trail."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from cloud_forks import ang, axis, read


def unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def fold(a):
    a = abs(a) % 180.0
    return 180.0 - a if a > 90.0 else a


def main(a):
    src = read(a[1], a[2])
    link = float(a[3]) if len(a) > 3 else 50.0
    reach_min = float(a[4]) if len(a) > 4 else 150.0
    skip = float(a[5]) if len(a) > 5 else 15.0
    t, X = src[:, 0], src[:, 1:4]
    n = len(X)
    parent = np.full(n, -1)
    plen = np.zeros(n)
    from scipy.spatial import cKDTree
    kk = min(n, 48)
    dist, idx = cKDTree(X).query(X, k=kk, distance_upper_bound=link)
    for i in range(1, n):
        earlier = np.flatnonzero(idx[i] < i)
        if len(earlier):
            parent[i] = idx[i][earlier[0]]
            plen[i] = dist[i][earlier[0]]
        elif np.isfinite(dist[i][-1]):
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
    forks = {}
    for i in range(n):
        ks = sorted((k for k in kids[i] if reach[k] + plen[k] >= reach_min), key=lambda k: -(reach[k] + plen[k]))
        if len(ks) < 2 or back[i] < reach_min:
            continue
        ds, step_t = [], []
        for k in ks[:2]:
            p, j = [], k
            while j >= 0 and np.linalg.norm(X[j] - X[i]) <= 210:
                p.append(j)
                j = best[j]
            P = np.array([X[q] for q in p])
            dd = np.linalg.norm(P - X[i], axis=1)
            sel = P[(dd >= skip) & (dd <= 60)]
            ds.append(axis(sel, sel[-1] - sel[0]) if len(sel) >= 4 else None)
            near = [q for q in p if skip <= np.linalg.norm(X[q] - X[i]) <= 60]
            step_t.append(1e3 * (float(np.median(t[near])) - t[i]) if near else float("nan"))
        if ds[0] is None or ds[1] is None:
            continue
        nrm = np.cross(ds[0], ds[1])
        if np.linalg.norm(nrm) < 1e-6:
            continue
        forks[i] = {"n": unit(nrm), "kids": ks[:2], "open": ang(ds[0], ds[1]), "dt": step_t}
    print("%d sources, %d forks with both directions at %d to 60 m; opening median %.1f"
          % (n, len(forks), skip, np.median([f["open"] for f in forks.values()]) if forks else float("nan")))
    if forks:
        nz = np.array([abs(f["n"][2]) for f in forks.values()])
        up = np.array([X[i][2] for i in forks])
        print("how the fork planes lie: |vertical part of the plane's normal| median %.3f, quartiles %.3f %.3f (0.5 for planes turned at random; 1 = a level plane, 0 = an upright one); share above 0.8: %.3f; height of the forks %.0f to %.0f m (5th to 95th percentile)"
              % (np.median(nz), np.percentile(nz, 25), np.percentile(nz, 75), np.mean(nz > 0.8), np.percentile(up, 5), np.percentile(up, 95)))
    pairs, firsts, seconds = [], [], []
    for i, f in forks.items():
        for k in f["kids"]:
            j, run = k, plen[k]
            while j >= 0 and run < 2000:
                if j in forks and j != i:
                    g = forks[j]
                    leg = unit(X[j] - X[i])
                    pa, pb = f["n"] - np.dot(f["n"], leg) * leg, g["n"] - np.dot(g["n"], leg) * leg
                    if np.linalg.norm(pa) > 1e-6 and np.linalg.norm(pb) > 1e-6:
                        pairs.append((fold(ang(unit(pa), unit(pb))), run, float(np.linalg.norm(X[j] - X[i]))))
                        firsts.append((f["n"], leg))
                        seconds.append(g["n"])
                    break
                nj = best[j]
                if nj < 0:
                    break
                run += plen[nj]
                j = nj
    P = np.array(pairs)
    if len(P) < 5:
        print("pairs: %d (too few)" % len(P))
        return
    r = P[:, 0]
    print("pairs of a fork and the next fork on a daughter's main trail: %d; trail between them %.0f m (median), straight %.0f m"
          % (len(P), np.median(P[:, 1]), np.median(P[:, 2])))
    print("rotation of the second fork's plane against the first: median %.1f, quartiles %.1f %.1f; above 60: %.3f; below 30: %.3f; bins of 15 from 0: %s"
          % (np.median(r), np.percentile(r, 25), np.percentile(r, 75), np.mean(r > 60), np.mean(r < 30),
             " ".join(str(int(x)) for x in np.histogram(r, bins=np.arange(0, 91, 15))[0])))
    rng = np.random.default_rng(3)
    cm, c60 = [], []
    m = len(seconds)
    for _ in range(2000):
        perm = rng.permutation(m)
        v = []
        for (na, leg), q in zip(firsts, perm):
            nb = seconds[q]
            pa, pb = na - np.dot(na, leg) * leg, nb - np.dot(nb, leg) * leg
            if np.linalg.norm(pa) > 1e-6 and np.linalg.norm(pb) > 1e-6:
                v.append(fold(ang(unit(pa), unit(pb))))
        cm.append(np.median(v))
        c60.append(np.mean(np.array(v) > 60))
    cm, c60 = np.array(cm), np.array(c60)
    print("control, second forks with other pairs' first forks (2,000 pairings): median %.1f (2.5 to 97.5: %.1f to %.1f); above 60: %.3f (%.3f to %.3f); pairings as far as measured: %.4f"
          % (np.median(cm), np.percentile(cm, 2.5), np.percentile(cm, 97.5), np.median(c60), np.percentile(c60, 2.5), np.percentile(c60, 97.5),
             np.mean(np.abs(cm - np.median(cm)) >= abs(np.median(r) - np.median(cm)))))
    for lo, hi in ((0, 60), (60, 150), (150, 400), (400, 2000)):
        q = (P[:, 1] >= lo) & (P[:, 1] < hi)
        if q.sum() >= 6:
            print("   trail of %4d to %4d m: %3d pairs, rotation median %.1f, above 60: %.3f" % (lo, hi, q.sum(), np.median(r[q]), np.mean(r[q] > 60)))


if __name__ == "__main__":
    main(sys.argv)
