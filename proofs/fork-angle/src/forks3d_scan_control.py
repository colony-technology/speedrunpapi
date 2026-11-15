"""usage: python -I forks3d_scan_control.py
A control for forks3d_scan.py: does the carry-back return the angle a drawn fork was born with?

400 drawn forks per case in a gap with the plate at 67.3 mm. A fork sits at a height between 5 and 50 mm, its
parent runs straight along the gap, its two daughters leave at half the birth angle to each side (birth angle
drawn from a bell of the given mean and 6 degrees of spread) in a random plane, and then close by a rule the
reader is not told:
  power q     half-angle = half birth angle x ((Z - z) / (Z - z_fork))^q        (q = 0.8, 1.3, 1.8)
  late        straight for the first 4 mm, then power 1.3
  linear      half-angle falls by a fixed 1.2 degrees per mm of path, down to zero
Points every 0.7 mm with 0.1 mm of scatter. Read exactly as the real forks: the four stretches from 3 to 16 mm,
one free number p fixed where the four medians agree best, the birth angle as their mean."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from forks3d import ang, arclen, window_dir

Z = 67.3
wins = [(3, 5), (5, 8), (8, 12), (12, 16)]
ps = np.arange(0.4, 2.6001, 0.01)
rng = np.random.default_rng(8)


def daughter(zf, half0, rule, sign, phi):
    ds = 0.05
    x = y = 0.0
    z = zf
    pts = []
    s = 0.0
    while s <= 20.0 and z < Z - 0.5:
        if rule[0] == "power":
            h = half0 * ((Z - z) / (Z - zf)) ** rule[1]
        elif rule[0] == "late":
            h = half0 if s < 4 else half0 * ((Z - z) / (Z - zf4[0])) ** 1.3
            if s < 4:
                zf4[0] = z
        else:
            h = max(0.0, half0 - math.radians(1.2 / 2) * s)
        if int(round(s / ds)) % 14 == 0:
            pts.append((x, y, z))
        r = math.sin(h) * ds
        x += sign * r * math.cos(phi)
        y += sign * r * math.sin(phi)
        z += math.cos(h) * ds
        s += ds
    return np.array(pts) + rng.normal(0, 0.1, (len(pts), 3))


zf4 = [0.0]
for mean in (60.0, 72.0, 85.0):
    for rule in (("power", 0.8), ("power", 1.3), ("power", 1.8), ("late",), ("linear",)):
        A, zs, zfs, born = [], [], [], []
        for _ in range(400):
            zf = rng.uniform(5, 50)
            a0 = rng.normal(mean, 6.0)
            phi = rng.uniform(0, math.pi)
            d1 = daughter(zf, math.radians(a0 / 2), rule, +1, phi)
            d2 = daughter(zf, math.radians(a0 / 2), rule, -1, phi)
            if min(arclen(d1)[-1], arclen(d2)[-1]) < 16:
                continue
            row, zr = [], []
            for lo, hi in wins:
                a, b = window_dir(d1, lo, hi), window_dir(d2, lo, hi)
                if a is None or b is None:
                    row = None
                    break
                z2 = []
                for dd in (d1, d2):
                    s = arclen(dd)
                    z2.append(dd[(s >= lo) & (s <= hi)][:, 2].mean())
                row.append(ang(a, b))
                zr.append(float(np.mean(z2)))
            if row is None:
                continue
            A.append(row)
            zs.append(zr)
            zfs.append(zf)
            born.append(a0)
        A, zs, zfs = np.array(A), np.array(zs), np.array(zfs)
        best = None
        for p in ps:
            med = np.median(A * ((Z - zfs)[:, None] / np.maximum(1.0, Z - zs)) ** p, axis=0)
            sp = med.max() - med.min()
            if best is None or sp < best[0]:
                best = (sp, p, med)
        # the second way (forks3d_line.py): a straight line through each fork's four openings against path distance
        mids = np.array([(lo + hi) / 2 for lo, hi in wins])
        line0 = np.median([np.polyfit(mids, r, 1)[1] for r in A])
        print("drawn %2.0f (median of those kept %.1f), rule %-12s: %3d forks, p %.2f, spread %.2f, read %.1f; straight-line way reads %.1f"
              % (mean, np.median(born), " ".join(str(v) for v in rule), len(A), best[1], best[0], best[2].mean(), line0))
