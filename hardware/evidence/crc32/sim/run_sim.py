"""Builds and runs sim/tb_rand.sv: both forms of all four blocks against the bit-serial reference.

    python3 sim/run_sim.py --verilator PATH/verilator --cells PATH/xilinx/cells_sim.v --work BUILD_DIR [--n N] [--seed S]
"""
import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verilator", default="verilator")
    ap.add_argument("--cells", required=True)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--n", type=int, default=1000000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    a.work.mkdir(parents=True, exist_ok=True)
    srcs = [a.cells, str(ROOT / "proof" / "reference.v")] + sorted(str(p) for p in (ROOT / "block").glob("*.v")) + [str(ROOT / "sim" / "tb_rand.sv")]
    r = subprocess.run([a.verilator, "--binary", "--timing", "-Wno-fatal", "-Wno-lint", "-Wno-style", "--top-module", "tb_rand",
                        "-Mdir", str(a.work / "obj_rand"), "-o", "tb_rand"] + srcs, capture_output=True, text=True)
    if r.returncode:
        print(r.stdout[-3000:], r.stderr[-3000:])
        raise SystemExit(2)
    r = subprocess.run([str(a.work / "obj_rand" / "tb_rand"), "+n=%d" % a.n, "+seed=%d" % a.seed], capture_output=True, text=True)
    print(r.stdout.strip())
    last = [l for l in r.stdout.splitlines() if l.startswith("RAND ")]
    ok = r.returncode == 0 and last and last[0].endswith("d8 0  d32 0  d64 0  be64 0 mismatches")
    raise SystemExit(0 if ok else 1)
