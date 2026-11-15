"""usage: python -I fork3d_theory.py
The opening a fork holds in three dimensions, for thin channels: a first reckoning.

Setting. A thin conducting channel (the parent) ends at a point and continues as two thin straight daughters of
length l, at half the opening h = alpha / 2 to each side of the parent's line, all in one plane. A thin channel
carries its charge as a line charge on its axis. A tip keeps its direction when the field at the tip has no
component across the tip's own axis; its own straight leg gives none there, so the question is the field across
daughter 1's tip from the parent and from daughter 2. Take the parent's charge per length as lambda0 near the
fork (it is nearly constant over distances short against the parent's length) and each daughter's as
kappa x lambda0, both uniform.

Closed form (checked here against direct summation), in units of lambda0 / (4 pi eps0 l):
    T(alpha, kappa) = -tan(alpha / 4) + kappa [cot(alpha) (sin(alpha/2) + cos(alpha)) - cos(alpha/2) + sin(alpha)]
The first term is the parent's charge, which pulls the tip back toward the parent's line (its field at the tip
points at half the tip's own angle); the bracket is the other daughter, which pushes the tip away.
T > 0 opens the fork, T < 0 closes it; the fork holds where T = 0.

Printed: the closed form against direct numerical summation of the line charges at five angles; the opening
that holds for kappa from 0.5 (the parent's charge per length shared between the daughters) to 1 (each daughter
as charged per length as the parent); the kappa at which 72 degrees holds.

Not in this file, and why: the charges were not solved for an equipotential fork. A first try (line segments on
the axes, potential matched on the surface) gave negative charges at the junction, where the pieces are shorter
than the channel is thick, and openings near 90 degrees for long thin forks; that needs a proper surface
solution before it is a number. The uniform outside field's own pull across the tip is left out: for a parent
long against the daughters it is small against the two terms kept.
"""
import math

import numpy as np


def T_closed(alpha, kappa):
    h = alpha / 2
    return -math.tan(h / 2) + kappa * ((math.cos(alpha) / math.sin(alpha)) * (math.sin(h) + math.cos(alpha)) - math.cos(h) + math.sin(alpha))


def field_of_segment(p, a, b, n=20000):
    """Field at p of a unit line charge density on the segment a..b (units 1 / (4 pi eps0)), by direct sum."""
    t = (np.arange(n) + 0.5) / n
    pts = a[None, :] + t[:, None] * (b - a)[None, :]
    r = p[None, :] - pts
    d = np.linalg.norm(r, axis=1)
    return (r / d[:, None] ** 3).sum(axis=0) * np.linalg.norm(b - a) / n


def T_direct(alpha, kappa, far=4000.0):
    h = alpha / 2
    u = np.array([math.sin(h), 0.0, math.cos(h)])
    n = np.array([math.cos(h), 0.0, -math.sin(h)])
    P = u.copy()                                          # l = 1
    Q = np.array([-math.sin(h), 0.0, math.cos(h)])
    E = np.zeros(3)
    edges = -np.concatenate([[0.0], np.geomspace(1e-3, far, 400)])
    for k in range(len(edges) - 1):
        E += field_of_segment(P, np.array([0.0, 0.0, edges[k + 1]]), np.array([0.0, 0.0, edges[k]]), 200)
    E += kappa * field_of_segment(P, np.zeros(3), Q)
    return float(E @ n)


def root(f, lo, hi):
    flo = f(lo)
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return 0.5 * (lo + hi)


print("1. closed form against direct summation (alpha in degrees, kappa): T closed, T direct")
for adeg, kap in ((50, 0.5), (60, 0.5), (72, 0.75), (80, 1.0), (100, 1.0)):
    al = math.radians(adeg)
    print("   %5.1f  %.2f   %+.5f   %+.5f" % (adeg, kap, T_closed(al, kap), T_direct(al, kap)))

print("2. the opening that holds, by kappa")
for kap in (0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 1.0):
    al = root(lambda x: T_closed(x, kap), math.radians(20), math.radians(140))
    print("   kappa %.2f   opening %.2f degrees" % (kap, math.degrees(al)))
al72 = math.radians(72)
h = al72 / 2
k72 = math.tan(h / 2) / ((math.cos(al72) / math.sin(al72)) * (math.sin(h) + math.cos(al72)) - math.cos(h) + math.sin(al72))
print("   72 degrees holds at kappa = %.5f" % k72)
