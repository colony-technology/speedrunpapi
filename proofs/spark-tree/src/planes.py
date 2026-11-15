"""usage: python -I planes.py DIR_OF_DataExp_FILES
How the second fork of a tree turns its plane against the first. Only a record in three dimensions can say.

A discharge with two or three forks is stored as one triple of paths per fork (parent, two daughters; fields
SegP, SegD1, SegD2 when present, otherwise consecutive triples). A later fork B hangs on an earlier fork A when
B's parent path starts near the start of one of A's daughters (the stored paths repeat that leg).

For every such pair:
  plane of a fork        = spanned by its two daughters' first chords (normal n = d1 x d2)
  rotation               = angle between the two planes about the connecting leg: both normals projected on the
                           plane across the leg's direction, angle between them folded to 0..90
  raw angle              = angle between the two normals, folded to 0..90
  toward the sibling     = for fork B, the share of its daughters' sideways lean (across the leg) that points at
                           A's other daughter: +1 both lean toward the sibling, -1 both away; and which of B's
                           daughters (the thicker or the thinner) is the one nearer the sibling
Control: each fork B paired with the fork A of another tree (2,000 random pairings): what the instrument and the
gap give without any relation between the forks. Planes containing a common line and turned at random give a
rotation uniform on 0..90 (median 45); isotropic normals give a raw angle with median 60."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from forks3d import arclen, load, rows
from heat_fork_lib import dmed


def unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def fold(a):
    a = abs(a) % 180.0
    return 180.0 - a if a > 90.0 else a


def angle(u, v):
    return math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(u, v))))))


def forks_of(c):
    """list of forks of one discharge: dict with parent, d1, d2 paths (n x 3 arrays) and segment structs."""
    sg = c["Segment"]
    T = [rows(s[0]["Traj"]) for s in sg]
    out = []
    if len(sg) % 3 != 0:
        return out
    for k in range(0, len(sg), 3):
        P, A, B = T[k], T[k + 1], T[k + 2]
        if min(len(P), len(A), len(B)) < 3:
            continue
        out.append({"P": P, "A": A, "B": B, "sP": sg[k], "sA": sg[k + 1], "sB": sg[k + 2]})
    return out


def describe(f):
    d1 = unit(f["A"][1] - f["A"][0])
    d2 = unit(f["B"][1] - f["B"][0])
    n = unit(np.cross(d1, d2))
    at = 0.5 * (f["A"][0] + f["B"][0])
    return d1, d2, n, at


def main():
    d = sys.argv[1]
    pairs = []
    allforks = []
    ntrees = {}
    for fn in sorted(os.listdir(d)):
        if not fn.endswith("DataExp.mat"):
            continue
        for c in load(os.path.join(d, fn))["DataExp"]:
            if not c:
                continue
            F = forks_of(c[0])
            ntrees[len(F)] = ntrees.get(len(F), 0) + 1
            for f in F:
                allforks.append(f)
            if len(F) < 2:
                continue
            for j, fb in enumerate(F):
                best = None
                for i, fa in enumerate(F):
                    if i == j:
                        continue
                    for key, other in (("A", "B"), ("B", "A")):
                        dist = float(np.linalg.norm(fb["P"][0] - fa[key][0]))
                        # the later fork must lie further along that daughter than its start
                        ahead = float(np.dot(fb["P"][-1] - fa[key][0], unit(fa[key][-1] - fa[key][0])))
                        if ahead > 1.0 and (best is None or dist < best[0]):
                            best = (dist, i, key, other)
                if best is None or best[0] > 4.0:
                    continue
                fa = F[best[1]]
                pairs.append((fa, fb, best[2], best[3], best[0]))
    print("discharges by number of stored forks: %s" % dict(sorted(ntrees.items())))
    print("pairs of a first fork and a fork hanging on one of its daughters: %d (the second fork's parent path starts within 4 mm of that daughter's start)" % len(pairs))
    if not pairs:
        return
    rot, raw, lean, legs, thick_near, sep = [], [], [], [], [], []
    A_desc, B_desc = [], []
    for fa, fb, key, other, dist in pairs:
        a1, a2, na, at_a = describe(fa)
        b1, b2, nb, at_b = describe(fb)
        leg = unit(at_b - at_a)                       # the connecting leg, from the first fork to the second
        pa, pb = na - np.dot(na, leg) * leg, nb - np.dot(nb, leg) * leg
        if np.linalg.norm(pa) < 1e-6 or np.linalg.norm(pb) < 1e-6:
            continue
        rot.append(fold(angle(unit(pa), unit(pb))))
        raw.append(fold(angle(na, nb)))
        legs.append(float(np.linalg.norm(at_b - at_a)))
        # the sibling: the other daughter of the first fork, where it is at the height of the second fork
        S = fa[other]
        k = int(np.argmin(np.linalg.norm(S - at_b, axis=1)))
        to_sib = S[k] - at_b
        sep.append(float(np.linalg.norm(to_sib)))
        to_sib = unit(to_sib - np.dot(to_sib, leg) * leg)
        l1 = float(np.dot(b1 - np.dot(b1, leg) * leg, to_sib))
        l2 = float(np.dot(b2 - np.dot(b2, leg) * leg, to_sib))
        lean.append((l1, l2))
        D1, D2 = dmed(fb["sA"], fb["A"], 3, 8), dmed(fb["sB"], fb["B"], 3, 8)
        if math.isfinite(D1) and math.isfinite(D2) and D1 != D2:
            near_is_1 = l1 > l2
            thick_near.append(1.0 if (near_is_1 and D1 > D2) or ((not near_is_1) and D2 > D1) else 0.0)
        A_desc.append((na, leg))
        B_desc.append(nb)
    rot, raw, lean, legs, sep = np.array(rot), np.array(raw), np.array(lean), np.array(legs), np.array(sep)
    print("")
    print("length of the connecting leg: median %.1f mm (quartiles %.1f, %.1f); the sibling is %.1f mm away at the second fork (median)"
          % (np.median(legs), np.percentile(legs, 25), np.percentile(legs, 75), np.median(sep)))
    print("rotation of the second fork's plane against the first, about the leg: median %.1f, quartiles %.1f %.1f (n %d)"
          % (np.median(rot), np.percentile(rot, 25), np.percentile(rot, 75), len(rot)))
    print("   counts in 15-degree bins from 0: %s" % " ".join(str(int(x)) for x in np.histogram(rot, bins=np.arange(0, 91, 15))[0]))
    print("   share above 60 degrees %.3f; share below 30 degrees %.3f" % (np.mean(rot > 60), np.mean(rot < 30)))
    print("raw angle between the two planes' normals: median %.1f, quartiles %.1f %.1f" % (np.median(raw), np.percentile(raw, 25), np.percentile(raw, 75)))
    rng = np.random.default_rng(5)
    crot, craw = [], []
    nB = len(B_desc)
    for _ in range(2000):
        perm = rng.permutation(nB)
        r = []
        w = []
        for (na, leg), q in zip(A_desc, perm):
            nb = B_desc[q]
            pa, pb = na - np.dot(na, leg) * leg, nb - np.dot(nb, leg) * leg
            if np.linalg.norm(pa) < 1e-6 or np.linalg.norm(pb) < 1e-6:
                continue
            r.append(fold(angle(unit(pa), unit(pb))))
            w.append(fold(angle(na, nb)))
        crot.append((np.median(r), np.mean(np.array(r) > 60), np.mean(np.array(r) < 30)))
        craw.append(np.median(w))
    crot, craw = np.array(crot), np.array(craw)
    print("control, each second fork with another tree's first fork (2,000 pairings): rotation median %.1f (2.5 to 97.5: %.1f to %.1f); share above 60: %.3f (%.3f to %.3f); below 30: %.3f (%.3f to %.3f); raw median %.1f (%.1f to %.1f)"
          % (np.median(crot[:, 0]), np.percentile(crot[:, 0], 2.5), np.percentile(crot[:, 0], 97.5),
             np.median(crot[:, 1]), np.percentile(crot[:, 1], 2.5), np.percentile(crot[:, 1], 97.5),
             np.median(crot[:, 2]), np.percentile(crot[:, 2], 2.5), np.percentile(crot[:, 2], 97.5),
             np.median(craw), np.percentile(craw, 2.5), np.percentile(craw, 97.5)))
    print("   pairings with a rotation median at least as far from the control's as the measured one: %.4f"
          % np.mean(np.abs(crot[:, 0] - np.median(crot[:, 0])) >= abs(np.median(rot) - np.median(crot[:, 0]))))
    both_away = np.mean((lean[:, 0] < 0) & (lean[:, 1] < 0))
    both_toward = np.mean((lean[:, 0] > 0) & (lean[:, 1] > 0))
    print("")
    print("lean of the second fork's daughters, across the leg, against the direction to the sibling:")
    print("   both away from the sibling %.3f; both toward %.3f; one each %.3f; mean lean of the pair %+.3f (0 if the sibling does not matter)"
          % (both_away, both_toward, 1 - both_away - both_toward, float(np.mean(lean.sum(axis=1) / 2))))
    if thick_near:
        print("   the daughter nearer the sibling is the thicker one in %.3f of %d second forks (0.5 if the sibling does not matter)" % (float(np.mean(thick_near)), len(thick_near)))
    for lo, hi in ((0, 8), (8, 16), (16, 80)):
        m = (legs >= lo) & (legs < hi)
        if m.sum() >= 8:
            print("   connecting leg %2d to %2d mm: %3d pairs, rotation median %.1f, mean lean %+.3f" % (lo, hi, m.sum(), np.median(rot[m]), float(np.mean(lean[m].sum(axis=1) / 2))))


if __name__ == "__main__":
    main()
