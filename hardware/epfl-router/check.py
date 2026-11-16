"""Check a netlist against the suite's reference circuit and count it.

usage: python -I check.py REF.blif OURS.blif [--cec-seconds N]

1. Simulation: 16 x 2048 random vectors plus the all-zero and all-one vectors, every output compared by name.
2. ABC: read_blif OURS; print_stats  (the count used on the table).
3. ABC: cec REF OURS  (ports matched by name).
"""
import os
import random
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from blifkit import Blif, compare  # noqa: E402

ABC = os.environ.get("ABC", "yosys-abc")


def main():
    ref_path, ours_path = sys.argv[1], sys.argv[2]
    secs = 120
    if "--cec-seconds" in sys.argv:
        secs = int(sys.argv[sys.argv.index("--cec-seconds") + 1])
    ref = Blif.read(ref_path)
    ours = Blif.read(ours_path)
    assert sorted(ref.inputs) == sorted(ours.inputs), "input names differ"
    assert sorted(ref.outputs) == sorted(ours.outputs), "output names differ"
    W = 2048
    mask = (1 << W) - 1
    extra = [{n: 0 for n in ref.inputs}, {n: mask for n in ref.inputs}]
    bad, total = compare(ref, ours, width=W, rounds=16, seed=11, extra=extra)
    print("simulation: %d vectors, %d batches with a mismatch" % (total, bad))
    out = subprocess.run([ABC, "-c", "read_blif %s; print_stats" % ours_path], capture_output=True, text=True).stdout
    line = [l for l in out.splitlines() if "nd =" in l][-1]
    print("print_stats:", " ".join(line.split(":", 1)[1].split()))
    out = subprocess.run([ABC, "-c", "cec -T %d %s %s" % (secs, ref_path, ours_path)], capture_output=True, text=True).stdout
    print("cec:", [l for l in out.splitlines() if "equivalent" in l or "Networks" in l or "UNDECIDED" in l.upper()] or out[-400:])


if __name__ == "__main__":
    main()
