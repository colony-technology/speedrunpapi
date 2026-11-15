"""usage: python -I det_planes2.py DIR_OF_StreamerFinal_in3D_FILES
Three forks in a row on one path, from the raw detections: does the quarter turn compose?

For every chain of forks A -> B -> C (B on a daughter of A, C on a daughter of B):
  1. the rotation of C's plane against A's plane, folded to 0..90. If each fork is a quarter turn from the last,
     every second plane lies along the first: the rotation A to C is small. Random: 45 in the middle.
  2. handedness. Along a chain take the path's own direction as the axis and, at B and at C, the side to which
     the daughter that does NOT carry the chain goes off. The signed turn of that side from B to C about the axis
     (-180..180): quarter turns give +90 or -90. Chains need three forks for one signed turn and four forks for two;
     for chains with two signed turns: do they have the same sign (a screw) or opposite signs (a zigzag)?
  3. the signed turn's histogram in 30-degree bins, to see +-90 directly.
Control for 1: C's plane against the first fork of another tree."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "geometry-tools"))
import numpy as np

from det_planes import angle, fold, segments_of, unit
from mat5load import load


def trees(d):
    for fn in sorted(os.listdir(d)):
        if not fn.endswith("StreamerFinal_in3D.mat"):
            continue
        for s in load(os.path.join(d, fn))["Streamer"]:
            segs = segments_of(s)
            if not segs:
                continue
            starts, ends = {}, {}
            for k, (ids, xyz) in enumerate(segs):
                starts.setdefault(int(ids[0]), []).append(k)
                ends[int(ids[-1])] = k
            forks = {}
            for b, ks in starts.items():
                if len(ks) != 2 or b not in ends:
                    continue
                a, c = segs[ks[0]], segs[ks[1]]
                at = a[1][0]
                u = [unit(a[1][1] - at), unit(c[1][1] - at)]
                n = np.cross(u[0], u[1])
                if np.linalg.norm(n) < 1e-9:
                    continue
                forks[b] = {"at": at, "u": u, "n": unit(n), "kids": ks, "ends": [int(a[0][-1]), int(c[0][-1])]}
            yield forks


def side(f, carrying):
    """direction of the daughter that does not carry the chain, as a unit vector."""
    other = 1 - carrying
    return f["u"][other]


def signed_about(axis, v1, v2):
    p1 = unit(v1 - np.dot(v1, axis) * axis)
    p2 = unit(v2 - np.dot(v2, axis) * axis)
    s = float(np.dot(np.cross(p1, p2), axis))
    c = float(np.dot(p1, p2))
    return math.degrees(math.atan2(s, c))


def main():
    d = sys.argv[1]
    ac, firsts, thirds, turns, pairs_of_turns = [], [], [], [], []
    for forks in trees(d):
        # chains: A -(kid i)-> B -(kid j)-> C
        for a, fa in forks.items():
            for i, e in enumerate(fa["ends"]):
                if e not in forks or e == a:
                    continue
                fb = forks[e]
                for j, e2 in enumerate(fb["ends"]):
                    if e2 not in forks or e2 in (a, e):
                        continue
                    fc = forks[e2]
                    leg = unit(fc["at"] - fa["at"])
                    pa, pc = fa["n"] - np.dot(fa["n"], leg) * leg, fc["n"] - np.dot(fc["n"], leg) * leg
                    if np.linalg.norm(pa) > 1e-6 and np.linalg.norm(pc) > 1e-6:
                        ac.append(fold(angle(unit(pa), unit(pc))))
                        firsts.append((fa["n"], leg))
                        thirds.append(fc["n"])
                    # signed turn of the shed side from B to C about the path's axis B -> C
                    axis = unit(fc["at"] - fb["at"])
                    sb = side(fb, j)
                    for k, e3 in enumerate(fc["ends"]):
                        sc = side(fc, k)
                        t1 = signed_about(axis, sb, sc)
                        turns.append(t1)
                        if e3 in forks and e3 not in (a, e, e2):
                            fd = forks[e3]
                            axis2 = unit(fd["at"] - fc["at"])
                            for m in range(2):
                                t2 = signed_about(axis2, sc, side(fd, m))
                                pairs_of_turns.append((t1, t2))
                        break   # one shed side per fork C is enough for the single turns
    ac = np.array(ac)
    print("chains of three forks on one path: %d" % len(ac))
    if len(ac):
        print("1. rotation of the third fork's plane against the first: median %.1f, quartiles %.1f %.1f; below 30: %.3f; above 60: %.3f; bins of 15 from 0: %s"
              % (np.median(ac), np.percentile(ac, 25), np.percentile(ac, 75), np.mean(ac < 30), np.mean(ac > 60),
                 " ".join(str(int(x)) for x in np.histogram(ac, bins=np.arange(0, 91, 15))[0])))
        rng = np.random.default_rng(13)
        cm = []
        n = len(thirds)
        for _ in range(2000):
            perm = rng.permutation(n)
            v = []
            for (na, leg), q in zip(firsts, perm):
                nc = thirds[q]
                pa, pc = na - np.dot(na, leg) * leg, nc - np.dot(nc, leg) * leg
                if np.linalg.norm(pa) > 1e-6 and np.linalg.norm(pc) > 1e-6:
                    v.append(fold(angle(unit(pa), unit(pc))))
            cm.append(np.median(v))
        cm = np.array(cm)
        print("   control, third forks with other trees' first forks: median %.1f (2.5 to 97.5: %.1f to %.1f); pairings as far as measured: %.4f"
              % (np.median(cm), np.percentile(cm, 2.5), np.percentile(cm, 97.5), np.mean(np.abs(cm - np.median(cm)) >= abs(np.median(ac) - np.median(cm)))))
    t = np.array(turns)
    if len(t):
        print("2. signed turn of the shed side from one fork to the next about the path (%d): bins of 30 from -180: %s"
              % (len(t), " ".join(str(int(x)) for x in np.histogram(t, bins=np.arange(-180, 181, 30))[0])))
        print("   share turning one way (positive): %.3f; median of the size of the turn %.1f" % (np.mean(t > 0), np.median(np.abs(t))))
    p = np.array(pairs_of_turns)
    if len(p):
        same = np.mean(np.sign(p[:, 0]) == np.sign(p[:, 1]))
        print("3. chains with two signed turns in a row (%d): same hand twice %.3f (0.5 if the hand is drawn afresh at each fork)" % (len(p), same))


main()
