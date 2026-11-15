"""usage: python -I det_planes.py DIR_OF_StreamerFinal_in3D_FILES
The quarter turn between successive forks, read from the raw detections alone: no fitted arc, no fitted plane.

Each discharge's FINAL.segment list gives, per segment, its dots in order (column 1 the dot's id, columns 6 to 8
its x, y, z in mm). A fork is a dot that ends one segment and starts two. Its plane is spanned by the two chords
from the fork dot to each daughter's next dot (one strobe period on). A second fork hangs on a first when one of
the first fork's daughter segments ends at the second fork's dot.

Printed: counts; the opening of every fork by those chords (the angle seen over the first strobe period); the
rotation of the second fork's plane against the first about the line joining the two fork dots, folded to 0..90,
with the control of second forks paired with other trees' first forks; and the same split by the length of the
connecting leg in dots."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "geometry-tools"))
import numpy as np

from mat5load import load


def arr(v):
    kind, shape, vals = v
    a = np.array(vals, float)
    if shape and len(shape) == 2 and a.size == shape[0] * shape[1]:
        return a.reshape(shape, order="F")
    return a


def first_dict(x):
    while isinstance(x, list):
        if not x:
            return None
        x = x[0]
    return x if isinstance(x, dict) else None


def unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def angle(u, v):
    return math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(u, v))))))


def fold(a):
    a = abs(a) % 180.0
    return 180.0 - a if a > 90.0 else a


def segments_of(s):
    s = first_dict(s)
    if s is None or "FINAL" not in s:
        return []
    F = first_dict(s["FINAL"])
    if F is None or F.get("segment") is None:
        return []
    out = []
    seg = F["segment"]
    seg = seg if isinstance(seg, list) else [seg]
    for g in seg:
        g = first_dict(g)
        if g is None or g.get("points") is None:
            continue
        P = arr(g["points"])
        if P.ndim != 2 or P.shape[1] < 8 or len(P) < 2:
            continue
        out.append((P[:, 0].astype(int), P[:, 5:8]))
    return out


def main():
    d = sys.argv[1]
    openings, pairs, nforks, ndis = [], [], 0, 0
    firsts, seconds = [], []
    for fn in sorted(os.listdir(d)):
        if not fn.endswith("StreamerFinal_in3D.mat"):
            continue
        S = load(os.path.join(d, fn))["Streamer"]
        for s in S:
            segs = segments_of(s)
            if not segs:
                continue
            ndis += 1
            starts, ends = {}, {}
            for k, (ids, xyz) in enumerate(segs):
                starts.setdefault(int(ids[0]), []).append(k)
                ends[int(ids[-1])] = k
            forks = {}
            for b, ks in starts.items():
                if len(ks) != 2 or b not in ends:
                    continue
                p = segs[ends[b]]
                a, c = segs[ks[0]], segs[ks[1]]
                at = a[1][0]
                u1, u2 = unit(a[1][1] - at), unit(c[1][1] - at)
                n = np.cross(u1, u2)
                if np.linalg.norm(n) < 1e-9:
                    continue
                forks[b] = {"at": at, "u1": u1, "u2": u2, "n": unit(n), "kids": ks, "open": angle(u1, u2),
                            "back": unit(at - p[1][-2])}
                openings.append(angle(u1, u2))
            nforks += len(forks)
            for b, f in forks.items():
                for k in f["kids"]:
                    e = int(segs[k][0][-1])
                    if e in forks and e != b:
                        g = forks[e]
                        leg = unit(g["at"] - f["at"])
                        pa, pb = f["n"] - np.dot(f["n"], leg) * leg, g["n"] - np.dot(g["n"], leg) * leg
                        if np.linalg.norm(pa) < 1e-6 or np.linalg.norm(pb) < 1e-6:
                            continue
                        pairs.append((fold(angle(unit(pa), unit(pb))), len(segs[k][0]) - 1, float(np.linalg.norm(g["at"] - f["at"]))))
                        firsts.append((f["n"], leg))
                        seconds.append(g["n"])
    openings = np.array(openings)
    print("%d discharges with segments, %d forks (a dot that ends one segment and starts two)" % (ndis, nforks))
    print("opening by the chords of the first strobe period: median %.1f, quartiles %.1f %.1f (n %d)"
          % (np.median(openings), np.percentile(openings, 25), np.percentile(openings, 75), len(openings)))
    P = np.array(pairs)
    if not len(P):
        print("no pairs")
        return
    r = P[:, 0]
    print("pairs of a fork and the next fork on one of its daughters: %d; connecting leg %.1f mm (median), %.0f strobe periods (median)"
          % (len(P), np.median(P[:, 2]), np.median(P[:, 1])))
    print("rotation of the second fork's plane against the first: median %.1f, quartiles %.1f %.1f; above 60: %.3f; below 30: %.3f; bins of 15 from 0: %s"
          % (np.median(r), np.percentile(r, 25), np.percentile(r, 75), np.mean(r > 60), np.mean(r < 30),
             " ".join(str(int(x)) for x in np.histogram(r, bins=np.arange(0, 91, 15))[0])))
    rng = np.random.default_rng(9)
    cm, c60 = [], []
    n = len(seconds)
    for _ in range(2000):
        perm = rng.permutation(n)
        v = []
        for (na, leg), q in zip(firsts, perm):
            nb = seconds[q]
            pa, pb = na - np.dot(na, leg) * leg, nb - np.dot(nb, leg) * leg
            if np.linalg.norm(pa) < 1e-6 or np.linalg.norm(pb) < 1e-6:
                continue
            v.append(fold(angle(unit(pa), unit(pb))))
        cm.append(np.median(v))
        c60.append(np.mean(np.array(v) > 60))
    cm, c60 = np.array(cm), np.array(c60)
    print("control, second forks with other trees' first forks (2,000 pairings): median %.1f (2.5 to 97.5: %.1f to %.1f); above 60: %.3f (%.3f to %.3f); pairings as far as the measured median: %.4f"
          % (np.median(cm), np.percentile(cm, 2.5), np.percentile(cm, 97.5), np.median(c60), np.percentile(c60, 2.5), np.percentile(c60, 97.5),
             np.mean(np.abs(cm - np.median(cm)) >= abs(np.median(r) - np.median(cm)))))
    for lo, hi in ((1, 2), (2, 3), (3, 5), (5, 99)):
        m = (P[:, 1] >= lo) & (P[:, 1] < hi)
        if m.sum() >= 8:
            print("   connecting leg of %d to %d strobe periods: %3d pairs, rotation median %.1f, above 60: %.3f" % (lo, hi - 1, m.sum(), np.median(r[m]), np.mean(r[m] > 60)))


if __name__ == "__main__":
    main()
