"""usage: python -I forks3d_arc.py DIR_OF_DataExp_FILES
Are the stored paths of the streamer record circular arcs? For every daughter of at least 16 mm: the turning of
the path per mm, measured between successive chords, in its first third, middle third and last third; the
spread of that turning along the path relative to its mean; the path's distance from the plane through its
first, middle and last point (planarity); and the stored number Curv beside the measured turning.
Printed: medians over all daughters, and the rank correlation between the measured turning (radians per mm) and
the stored Curv with the straight-line fit between them (to find Curv's unit)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from forks3d import arclen, load, rows


def turning(p):
    """Turning angle per unit length at each interior point (radians per mm), from successive chords."""
    d = np.diff(p, axis=0)
    L = np.linalg.norm(d, axis=1)
    u = d / L[:, None]
    c = np.clip((u[:-1] * u[1:]).sum(axis=1), -1, 1)
    return np.arccos(c) / (0.5 * (L[:-1] + L[1:]))


def rank(v):
    out = np.empty(len(v))
    out[np.argsort(v)] = np.arange(len(v))
    return out


d = sys.argv[1]
recs = []
for fn in sorted(os.listdir(d)):
    if not fn.endswith("DataExp.mat"):
        continue
    for c in load(os.path.join(d, fn))["DataExp"]:
        if not c or len(c[0]["Segment"]) != 3:
            continue
        sg = c[0]["Segment"]
        for k in (1, 2):
            T = rows(sg[k][0]["Traj"])
            if arclen(T)[-1] < 16 or len(T) < 12:
                continue
            t = turning(T)
            n = len(t) // 3
            a, b, e = np.median(t[:n]), np.median(t[n:2 * n]), np.median(t[2 * n:])
            p0, p1, p2 = T[0], T[len(T) // 2], T[-1]
            nrm = np.cross(p1 - p0, p2 - p0)
            nn = np.linalg.norm(nrm)
            off = np.abs((T - p0) @ (nrm / nn)).max() if nn > 1e-9 else 0.0
            cv = sg[k][0].get("Curv")
            cv = float(np.array(cv[2], float).ravel()[0]) if cv is not None and len(cv[2]) else np.nan
            recs.append((a, b, e, t.std() / max(t.mean(), 1e-12), off, cv, t.mean()))
R = np.array(recs)
print("%d daughters of at least 16 mm" % len(R))
print("turning, radians per mm: first third %.5f, middle third %.5f, last third %.5f (medians); in degrees per mm %.3f, %.3f, %.3f"
      % (np.median(R[:, 0]), np.median(R[:, 1]), np.median(R[:, 2]), *(np.degrees(np.median(R[:, k])) for k in (0, 1, 2))))
print("spread of the turning along a path over its mean: median %.4f, 90th percentile %.4f (0 for a circle)" % (np.median(R[:, 3]), np.percentile(R[:, 3], 90)))
print("largest distance of a path from its own plane: median %.5f mm, 90th percentile %.5f mm" % (np.median(R[:, 4]), np.percentile(R[:, 4], 90)))
ok = np.isfinite(R[:, 5])
x, y = np.abs(R[ok, 5]), R[ok, 6]
r = float(np.corrcoef(rank(x), rank(y))[0, 1])
slope = float((x * y).sum() / (x * x).sum())
print("stored Curv (absolute) against measured turning: rank correlation %.4f; measured = %.5f x Curv (so Curv is in 1 / %.1f mm); median of measured / (%.5f x Curv): %.4f"
      % (r, slope, 1 / slope, slope, np.median(y / (slope * x))))
