"""Runs every check of the package and writes the printed output to results/.

    python3 tools/run_all.py --bin DIR --work BUILD_DIR [--skip-yosys] [--n N]

DIR holds yosys and verilator (for example oss-cad-suite/bin).  The Xilinx LUT models are taken from
DIR/../share/yosys/xilinx/cells_sim.v.  Each check is a separate program; this file only runs them in order.
Exit status 0 only if every check passes.
"""
import argparse
import hashlib
import platform
import subprocess
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAMES = []                                                   # (local path, name written in the record)


def run(name, cmd, out):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    text = "$ " + " ".join(str(c) for c in cmd) + "\n" + (r.stdout + (("\n" + r.stderr) if r.returncode and r.stderr else "")).rstrip()
    for local, shown in NAMES:                                # no local paths in the record
        text = text.replace(local, shown)
    text = text.replace(str(ROOT), ".").replace(str(Path.home()), "~")
    (out / (name + ".txt")).write_text(text + "\nexit %d\n" % r.returncode)
    print("%-14s exit %d" % (name, r.returncode), flush=True)
    return r.returncode == 0


def manifest():
    """SHA-256 of every file of the package, results included, except the manifest itself."""
    files = sorted(p for p in ROOT.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256"
                   and "__pycache__" not in p.parts and not p.name.startswith("."))
    (ROOT / "MANIFEST.sha256").write_text("".join("%s  %s\n" % (hashlib.sha256(p.read_bytes()).hexdigest(), p.relative_to(ROOT)) for p in files))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", type=Path)
    ap.add_argument("--work", type=Path)
    ap.add_argument("--n", type=int, default=1000000)
    ap.add_argument("--skip-yosys", action="store_true")
    ap.add_argument("--manifest-only", action="store_true", help="rewrite MANIFEST.sha256 and stop")
    a = ap.parse_args()
    if a.manifest_only:
        manifest()
        raise SystemExit(0)
    if not (a.bin and a.work):
        ap.error("--bin and --work are required")
    py = [sys.executable, "-I"]
    a.bin = a.bin.resolve()
    ys, vl = str(a.bin / "yosys"), str(a.bin / "verilator")
    cells = str((a.bin / ".." / "share" / "yosys" / "xilinx" / "cells_sim.v").resolve())
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    w = a.work.resolve()
    NAMES[:] = sorted([(cells, "$BIN/../share/yosys/xilinx/cells_sim.v"), (ys, "$BIN/yosys"), (vl, "$BIN/verilator"),
                       (str(w), "$WORK"), (sys.executable, "python3")], key=lambda t: -len(t[0]))
    ok = True
    for n in ("d8", "d32", "d64"):
        ok &= run("checker_" + n, py + ["proof/independent_linear_checker.py", "--netlist", "proof/colony_crc32_%s.blif" % n,
                                        "--derivation", "proof/colony_crc32_%s.json" % n], out)
    ok &= run("checker_be64", py + ["proof/independent_crc_checker.py", "--netlist", "proof/colony_crc32_be64.blif",
                                    "--derivation", "proof/colony_crc32_be64.json"], out)
    ok &= run("checker_mutants", py + ["proof/mutate_checkers.py"], out)
    ok &= run("lut6_vs_blif", py + ["proof/lut6_vs_blif.py"], out)
    if not a.skip_yosys:
        ok &= run("yosys_equiv", py + ["proof/sat_equiv.py", "--yosys", ys, "--work", str(w / "equiv")], out)
    ok &= run("structure", py + ["proof/structure.py", "--yosys", ys, "--verilator", vl, "--work", str(w / "structure")], out)
    ok &= run("sim_random", py + ["sim/run_sim.py", "--verilator", vl, "--cells", cells, "--work", str(w / "sim"), "--n", str(a.n)], out)
    ok &= run("vectors", py + ["vectors/replay.py", "--verilator", vl, "--cells", cells, "--work", str(w / "kat")], out)
    ver = [subprocess.run([ys, "-V"], capture_output=True, text=True).stdout.strip(),
           subprocess.run([vl, "--version"], capture_output=True, text=True).stdout.strip(),
           "Python " + platform.python_version(), "zlib " + zlib.ZLIB_RUNTIME_VERSION, platform.platform()]
    (out / "tools.txt").write_text("\n".join(ver) + "\n")
    manifest()
    print("ALL PASS" if ok else "FAILURES")
    raise SystemExit(0 if ok else 1)
