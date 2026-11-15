"""Two readers shared by heat_fork.py's reckoning and triangle.py: a leg's stored thickness over a stretch of its
path, and its stored speed. Same definitions as in heat_fork.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from forks3d import arclen


def dmed(seg, T, lo, hi, from_end=False):
    a = seg[0].get("D")
    if a is None or not len(a[2]):
        return float("nan")
    v = np.array(a[2], float).ravel()
    s = arclen(T)
    n = min(len(v), len(s))
    s = s[:n]
    if from_end:
        s = s[-1] - s
    sel = v[:n][(s >= lo) & (s <= hi)]
    return float(np.nanmedian(sel)) if len(sel) else float("nan")


def vel(seg):
    a = seg[0].get("V")
    return float(np.array(a[2], float).ravel()[0]) if a is not None and len(a[2]) else float("nan")
