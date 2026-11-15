"""usage: python -I forks3d_line.py DIR_OF_DataExp_FILES
The birth angle of the streamer forks by a second way that uses no law for the closing: for each fork, a
straight line through its openings in the stretches 3 to 5, 5 to 8, 8 to 12 and 12 to 16 mm against the mean
distance along the path of each stretch, carried back to distance 0. Also the same with a curve of second degree
(four points, three numbers: noisy fork by fork, so only the median is read), and with the 1 to 3 mm stretch
added where a fork has it. Printed: medians with quartiles, and a bootstrap interval for the straight-line median."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from forks3d import ang, arclen, load, rows, window_dir

d = sys.argv[1]
wins = [(1, 3), (3, 5), (5, 8), (8, 12), (12, 16)]
mid = np.array([(a + b) / 2 for a, b in wins])
A = []
for fn in sorted(os.listdir(d)):
    if not fn.endswith("DataExp.mat"):
        continue
    for c in load(os.path.join(d, fn))["DataExp"]:
        if not c or len(c[0]["Segment"]) != 3:
            continue
        T = [rows(s[0]["Traj"]) for s in c[0]["Segment"]]
        if min(arclen(T[1])[-1], arclen(T[2])[-1]) < 16:
            continue
        row = []
        for lo, hi in wins:
            a, b = window_dir(T[1], lo, hi), window_dir(T[2], lo, hi)
            row.append(ang(a, b) if a is not None and b is not None else np.nan)
        A.append(row)
A = np.array(A)
four = np.isfinite(A[:, 1:]).all(axis=1)
five = np.isfinite(A).all(axis=1)
lin = np.array([np.polyfit(mid[1:], r[1:], 1)[1] for r in A[four]])
quad = np.array([np.polyfit(mid[1:], r[1:], 2)[2] for r in A[four]])
lin5 = np.array([np.polyfit(mid, r, 1)[1] for r in A[five]])
quad5 = np.array([np.polyfit(mid, r, 2)[2] for r in A[five]])


def q(v):
    return "median %.1f, quartiles %.1f %.1f" % (np.median(v), np.percentile(v, 25), np.percentile(v, 75))


print("straight line through four stretches (3 to 16 mm), %d forks: %s" % (len(lin), q(lin)))
print("second degree through four stretches, %d forks: %s" % (len(quad), q(quad)))
print("straight line through five stretches (1 to 16 mm), %d forks: %s" % (len(lin5), q(lin5)))
print("second degree through five stretches, %d forks: %s" % (len(quad5), q(quad5)))
rng = np.random.default_rng(6)
bs = [np.median(rng.choice(lin, len(lin))) for _ in range(2000)]
print("bootstrap of the straight-line median (four stretches): %.1f to %.1f" % (np.percentile(bs, 2.5), np.percentile(bs, 97.5)))
bs = [np.median(rng.choice(quad5, len(quad5))) for _ in range(2000)]
print("bootstrap of the second-degree median (five stretches): %.1f to %.1f" % (np.percentile(bs, 2.5), np.percentile(bs, 97.5)))
