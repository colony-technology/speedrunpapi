"""usage: python -I planes_azimuth.py DIR_OF_DataExp_FILES
Is the quarter turn between successive fork planes a relation between the two forks, or the instrument's axes?
In the record x is across the cameras' view, y is depth (away from the cameras), z along the gap.

For every fork the spread direction is the line in which its two daughters part (d1 - d2 of their first chords),
taken in the horizontal plane; its azimuth is folded to 0..180 (0 = along x, across the view; 90 = along y, depth).
Printed: azimuth counts in 30-degree bins for all forks, for first forks of pairs, for second forks of pairs;
the rotation between the pair split by the first fork's azimuth (so a preference tied to the cameras would show
as a dependence on it); and the rotation for pairs whose two forks are both well away from the depth axis."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from forks3d import load
from planes import angle, fold, forks_of, unit


def spread(f):
    d1 = unit(f["A"][1] - f["A"][0])
    d2 = unit(f["B"][1] - f["B"][0])
    return d1, d2, d1 - d2


def azim(v):
    a = math.degrees(math.atan2(v[1], v[0])) % 180.0
    return a


def bins(v):
    return " ".join("%4d" % int(x) for x in np.histogram(np.array(v), bins=np.arange(0, 181, 30))[0])


def main():
    d = sys.argv[1]
    az_all, rows_ = [], []
    for fn in sorted(os.listdir(d)):
        if not fn.endswith("DataExp.mat"):
            continue
        for c in load(os.path.join(d, fn))["DataExp"]:
            if not c:
                continue
            F = forks_of(c[0])
            for f in F:
                az_all.append(azim(spread(f)[2]))
            for j, fb in enumerate(F):
                best = None
                for i, fa in enumerate(F):
                    if i == j:
                        continue
                    for key in ("A", "B"):
                        dist = float(np.linalg.norm(fb["P"][0] - fa[key][0]))
                        ahead = float(np.dot(fb["P"][-1] - fa[key][0], unit(fa[key][-1] - fa[key][0])))
                        if ahead > 1.0 and (best is None or dist < best[0]):
                            best = (dist, i)
                if best is None or best[0] > 4.0:
                    continue
                fa = F[best[1]]
                a1, a2, sa = spread(fa)
                b1, b2, sb = spread(fb)
                leg = unit(0.5 * (fb["A"][0] + fb["B"][0]) - 0.5 * (fa["A"][0] + fa["B"][0]))
                na, nb = unit(np.cross(a1, a2)), unit(np.cross(b1, b2))
                pa, pb = na - np.dot(na, leg) * leg, nb - np.dot(nb, leg) * leg
                if np.linalg.norm(pa) < 1e-6 or np.linalg.norm(pb) < 1e-6:
                    continue
                rot = fold(angle(unit(pa), unit(pb)))
                rows_.append((azim(sa), azim(sb), rot, float(np.linalg.norm(0.5 * (fb["A"][0] + fb["B"][0]) - 0.5 * (fa["A"][0] + fa["B"][0])))))
    R = np.array(rows_)
    print("azimuth of the spread, counts in 30-degree bins from 0 (0 and 180 = across the view, 90 = depth)")
    print("   all forks (%d):            %s" % (len(az_all), bins(az_all)))
    print("   first forks of pairs (%d):  %s" % (len(R), bins(R[:, 0])))
    print("   second forks of pairs (%d): %s" % (len(R), bins(R[:, 1])))
    print("")
    print("rotation between the pair, by the first fork's azimuth")
    for lo, hi in ((0, 30), (30, 60), (60, 90), (90, 120), (120, 150), (150, 180)):
        m = (R[:, 0] >= lo) & (R[:, 0] < hi)
        if m.sum() >= 8:
            print("   first fork at %3d to %3d: %3d pairs, rotation median %.1f, share above 60: %.3f; second fork's azimuth bins: %s"
                  % (lo, hi, m.sum(), np.median(R[m, 2]), np.mean(R[m, 2] > 60), bins(R[m, 1])))
    off = lambda a: np.minimum(np.abs(a - 90), 90)   # distance from the depth axis
    for cut in (30, 45):
        m = (off(R[:, 0]) >= cut) & (off(R[:, 1]) >= cut)
        if m.sum() >= 8:
            print("both forks at least %d degrees from the depth axis: %d pairs, rotation median %.1f, share above 60: %.3f" % (cut, m.sum(), np.median(R[m, 2]), np.mean(R[m, 2] > 60)))
    m = R[:, 3] >= 12
    print("connecting leg of 12 mm or more: %d pairs, rotation median %.1f, quartiles %.1f %.1f, share above 60: %.3f"
          % (m.sum(), np.median(R[m, 2]), np.percentile(R[m, 2], 25), np.percentile(R[m, 2], 75), np.mean(R[m, 2] > 60)))


main()
