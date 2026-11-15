"""Runs every check of the SEC-DED package and writes the printed output to results/.

    python3 tools/run_all.py --bin DIR --work BUILD_DIR

DIR holds yosys and z3.  Exit status 0 only if every check passes.
"""
import argparse
import hashlib
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAMES = []
CONTROLS = ("C1-control-c0s0", "C1-control-cTs1", "C3-control")


def run(name, cmd, out):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    text = "$ " + " ".join(str(c) for c in cmd) + "\n" + (r.stdout + (("\n" + r.stderr) if r.returncode and r.stderr else "")).rstrip()
    for local, shown in NAMES:
        text = text.replace(local, shown)
    text = text.replace(str(ROOT), ".").replace(str(Path.home()), "~")
    (out / (name + ".txt")).write_text(text + "\nexit %d\n" % r.returncode)
    print("%-16s exit %d" % (name, r.returncode), flush=True)
    return r.returncode == 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", type=Path, required=True)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--codes", nargs="*", default=["72_64", "39_32"])
    a = ap.parse_args()
    b, w = a.bin.resolve(), a.work.resolve()
    ys, z3 = str(b / "yosys"), str(b / "z3")
    NAMES[:] = sorted([(ys, "$BIN/yosys"), (z3, "$BIN/z3"), (str(w), "$WORK"), (sys.executable, "python3")], key=lambda t: -len(t[0]))
    py = [sys.executable, "-I"]
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    ok = True
    for C in a.codes:
        N = "colony_secded" + C.split("_")[0]
        src = "source/prim_secded_%s_dec.sv" % C
        ok &= run("matrix_" + C, py + ["tools/matrix.py", "--source", src, "--out", str(w / ("H_%s.json" % C))], out)
        for blk in ("enc", "syn"):
            ok &= run("linear_%s_%s" % (C, blk), py + ["proof/independent_linear_checker.py", "--netlist", "proof/%s_%s.blif" % (N, blk),
                                                       "--derivation", "proof/%s_%s.json" % (N, blk)], out)
        ok &= run("checker_" + C, py + ["proof/independent_secded_checker.py", "--source", src, "--enc", "proof/%s_enc.blif" % N,
                                        "--syn", "proof/%s_syn.blif" % N, "--cor", "proof/%s_cor.blif" % N], out)
        ok &= run("checker_mutants_" + C, py + ["proof/mutate_secded.py", C], out)
        for form in ("lut6", "v"):
            ok &= run("sat_%s_%s" % (C, form), py + ["proof/sat_secded.py", "--code", C, "--yosys", ys, "--work", str(w / ("sat_%s_%s" % (C, form))),
                                                     "--form", form, "--split-c3"], out)
            text = (out / ("sat_%s_%s.txt" % (C, form))).read_text().split("\n")
            for ctl in CONTROLS:                                         # each planted fault must give a counterexample
                ok &= any(l.split()[:3] == [ctl, form, "COUNTEREXAMPLE"] for l in text)
        ok &= run("cost_" + C, py + ["tools/cost.py", "--code", C, "--yosys", ys, "--work", str(w / ("cost_" + C))], out)
        for blk in ("enc", "syn"):
            ok &= run("detector_r_%s_%s" % (C, blk), py + ["tools/detector_r.py", "--blif", "proof/%s_%s.blif" % (N, blk),
                                                           "--out", str(w / ("%s_%s_detector_r.json" % (C, blk))), "--rmax", "2", "--solver", z3], out)
    ver = [subprocess.run([ys, "-V"], capture_output=True, text=True).stdout.strip(),
           subprocess.run([z3, "--version"], capture_output=True, text=True).stdout.strip(),
           "Python " + platform.python_version(), platform.platform()]
    (out / "tools.txt").write_text("\n".join(ver) + "\n")
    files = sorted(p for p in ROOT.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256"
                   and "__pycache__" not in p.parts and not p.name.startswith("."))
    (ROOT / "MANIFEST.sha256").write_text("".join("%s  %s\n" % (hashlib.sha256(p.read_bytes()).hexdigest(), p.relative_to(ROOT)) for p in files))
    print("ALL PASS" if ok else "FAILURES")
    raise SystemExit(0 if ok else 1)
