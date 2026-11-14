"""Negative controls for the independent checkers.

    python3 proof/mutate_checkers.py [--stride K]

For each block, every K-th LUT of proof/NAME.blif (K = 1: every LUT) gets one mutant: the first on-set row of
that LUT is removed (one minterm of its truth table changes).  The derivation is copied with the netlist digest
recomputed, so a rejection comes from the function check, not the digest.  Every mutant must be rejected.
The unmodified files must be accepted.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOCKS = [("colony_crc32_d8", "independent_linear_checker.py"), ("colony_crc32_d32", "independent_linear_checker.py"),
          ("colony_crc32_d64", "independent_linear_checker.py"), ("colony_crc32_be64", "independent_crc_checker.py")]


def load(fn):
    spec = importlib.util.spec_from_file_location(fn[:-3], ROOT / "proof" / fn)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stride", type=int, default=1)
    a = ap.parse_args()
    fail = 0
    for name, fn in BLOCKS:
        chk = load(fn)
        raw = (ROOT / "proof" / (name + ".blif")).read_bytes()
        cert = json.loads((ROOT / "proof" / (name + ".json")).read_text())
        base = chk.verify(raw, cert)["ok"]
        lines = raw.decode().split("\n")
        heads = [i for i, l in enumerate(lines) if l.startswith(".names ") and len(l.split()) > 2]
        heads = [i for i in heads if not lines[i].split()[-1].startswith("o[")]   # LUTs, not output buffers
        tried = rejected = 0
        for h in heads[::a.stride]:
            mut = lines[:h + 1] + lines[h + 2:]                                    # drop the first on-set row
            m = "\n".join(mut).encode()
            c = dict(cert, netlist_digest="sha256:" + hashlib.sha256(m).hexdigest())
            tried += 1
            rejected += not chk.verify(m, c)["ok"]
        ok = base and rejected == tried
        fail += not ok
        print("%-18s original accepted %-5s  mutants %d  rejected %d" % (name, base, tried, rejected), flush=True)
    raise SystemExit(1 if fail else 0)
