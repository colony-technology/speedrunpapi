"""usage: python -I planes_check.py DIR_OF_DataExp_FILES
Two checks on planes.py before its numbers are used.
1. Grouping: for every discharge with two or more forks, do the stored fields SegP, SegD1, SegD2 name consecutive
   triples (parent 3k+1, daughters 3k+2 and 3k+3, counted from 1)? Printed: how many discharges agree, and the first
   few that do not.
2. The same rotation with the planes taken from lines fitted along each daughter between 2 and 6 mm (not from the
   first chords of the fitted arcs), and with the plane of the second fork taken from its daughters' end-to-end
   lines: if the result lives in the first chords only, it shows here."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from forks3d import load, rows, window_dir
from planes import angle, fold, forks_of, unit


def ints(v):
    if v is None:
        return None
    if isinstance(v, tuple) and len(v) == 3:
        return [int(round(float(x))) for x in np.array(v[2], float).ravel()]
    if isinstance(v, list):
        out = []
        for x in v:
            r = ints(x)
            if r is None:
                continue
            out.extend(r)
        return out
    return None


def main():
    d = sys.argv[1]
    agree = disagree = nofield = 0
    shown = 0
    rot = {"first chords": [], "lines 2 to 6 mm": [], "end-to-end lines": []}
    for fn in sorted(os.listdir(d)):
        if not fn.endswith("DataExp.mat"):
            continue
        for ci, c in enumerate(load(os.path.join(d, fn))["DataExp"]):
            if not c:
                continue
            sg = c[0]["Segment"]
            if len(sg) < 6:
                continue
            P, A, B = ints(c[0].get("SegP")), ints(c[0].get("SegD1")), ints(c[0].get("SegD2"))
            if not P or not A or not B:
                nofield += 1
            else:
                want = [(3 * k + 1, 3 * k + 2, 3 * k + 3) for k in range(len(sg) // 3)]
                got = sorted(zip(P, A, B))
                if got == want:
                    agree += 1
                else:
                    disagree += 1
                    if shown < 4:
                        shown += 1
                        print("   not consecutive: %s discharge %d: %d segments, SegP %s SegD1 %s SegD2 %s" % (fn[:28], ci, len(sg), P, A, B))
            F = forks_of(c[0])
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
                leg = unit(0.5 * (fb["A"][0] + fb["B"][0]) - 0.5 * (fa["A"][0] + fa["B"][0]))
                ways = {
                    "first chords": lambda f: (unit(f["A"][1] - f["A"][0]), unit(f["B"][1] - f["B"][0])),
                    "lines 2 to 6 mm": lambda f: (window_dir(f["A"], 2, 6), window_dir(f["B"], 2, 6)),
                    "end-to-end lines": lambda f: (unit(f["A"][-1] - f["A"][0]), unit(f["B"][-1] - f["B"][0])),
                }
                for name, way in ways.items():
                    a1, a2 = way(fa)
                    b1, b2 = way(fb)
                    if a1 is None or a2 is None or b1 is None or b2 is None:
                        continue
                    na, nb = np.cross(a1, a2), np.cross(b1, b2)
                    if np.linalg.norm(na) < 1e-6 or np.linalg.norm(nb) < 1e-6:
                        continue
                    na, nb = unit(na), unit(nb)
                    pa, pb = na - np.dot(na, leg) * leg, nb - np.dot(nb, leg) * leg
                    if np.linalg.norm(pa) < 1e-6 or np.linalg.norm(pb) < 1e-6:
                        continue
                    rot[name].append(fold(angle(unit(pa), unit(pb))))
    print("grouping: SegP, SegD1, SegD2 name consecutive triples in %d discharges with two or more forks, not in %d; fields absent in %d" % (agree, disagree, nofield))
    for name, v in rot.items():
        v = np.array(v)
        if len(v):
            print("rotation, planes from %-18s n %d: median %.1f, quartiles %.1f %.1f; share above 60: %.3f; below 30: %.3f; bins of 15 from 0: %s"
                  % (name + ",", len(v), np.median(v), np.percentile(v, 25), np.percentile(v, 75), np.mean(v > 60), np.mean(v < 30),
                     " ".join(str(int(x)) for x in np.histogram(v, bins=np.arange(0, 91, 15))[0])))


if __name__ == "__main__":
    main()
