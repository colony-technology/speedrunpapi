"""Compares the escape lists of the negative control (one check bit removed) across the methods that ran.

    python3 tools/compare_drops.py --name NAME --results results

Reads results/checker_T_dropJ.txt, results/sim_T_dropJ.txt and, if present, results/sat_T_dropJ.txt, takes the
set of net names each reports, and requires the sets to be equal for each J.
"""
import argparse
import re
from pathlib import Path

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--results", type=Path, required=True)
    a = ap.parse_args()
    t = a.name.split("_")[-1]
    bad = 0
    for j in (0, 1):
        sets = {}
        for method in ("checker", "sim", "sat"):
            p = a.results / ("%s_%s_drop%d.txt" % (method, t, j))
            if not p.exists():
                continue
            text = p.read_text()
            if method == "checker":
                m = re.search(r"uncovered nets: (.*)", text)
                nets = set(m.group(1).split()) if m else set()
            elif method == "sim":
                m = re.search(r"ESCAPES \d+: (.*)", text)
                nets = {w for w in (m.group(1).split() if m else []) if w.startswith("b_")}
            else:
                m = re.search(r"escape: (.*)", text)
                nets = set(m.group(1).split()) if m else set()
            sets[method] = nets
        same = len({frozenset(s) for s in sets.values()}) == 1 and all(sets.values())
        bad += not same
        print("check bit %d removed: %s  %s" % (j, "  ".join("%s %d" % (k, len(v)) for k, v in sets.items()), "equal" if same else "DIFFER"))
    raise SystemExit(1 if bad else 0)
