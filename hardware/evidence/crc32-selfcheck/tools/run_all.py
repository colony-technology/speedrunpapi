"""Runs every check of the self-check package and writes the printed output to results/.

    python3 tools/run_all.py --bin DIR --work BUILD_DIR [--sat] [--n N]

DIR holds yosys and z3 (for example oss-cad-suite/bin).  --sat adds the per-fault SAT run (about 10,000 small
proofs, about an hour on one core).  Exit status 0 only if every check passes.
"""
import argparse
import hashlib
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOCKS = sorted(p.name[:-len("_sc.blif")] for p in (ROOT / "proof").glob("*_sc.blif"))   # every block built here
NAMES = []


def run(name, cmd, out, want=0):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    text = "$ " + " ".join(str(c) for c in cmd) + "\n" + (r.stdout + (("\n" + r.stderr) if r.returncode != want and r.stderr else "")).rstrip()
    for local, shown in NAMES:
        text = text.replace(local, shown)
    text = text.replace(str(ROOT), ".").replace(str(Path.home()), "~")
    (out / (name + ".txt")).write_text(text + "\nexit %d\n" % r.returncode)
    print("%-16s exit %d" % (name, r.returncode), flush=True)
    return r.returncode == want


def manifest():
    files = sorted(p for p in ROOT.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256"
                   and "__pycache__" not in p.parts and not p.name.startswith("."))
    (ROOT / "MANIFEST.sha256").write_text("".join("%s  %s\n" % (hashlib.sha256(p.read_bytes()).hexdigest(), p.relative_to(ROOT)) for p in files))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", type=Path, required=True)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--sat", action="store_true")
    ap.add_argument("--n", type=int, default=4096)
    ap.add_argument("--blocks", nargs="*", help="block names; default every block with a proof/NAME_sc.blif")
    a = ap.parse_args()
    b, w = a.bin.resolve(), a.work.resolve()
    ys, z3 = str(b / "yosys"), str(b / "z3")
    NAMES[:] = sorted([(ys, "$BIN/yosys"), (z3, "$BIN/z3"), (str(w), "$WORK"), (sys.executable, "python3")], key=lambda t: -len(t[0]))
    py = [sys.executable, "-I"]
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    P = lambda f: "proof/" + f
    ok = True
    for NAME in (a.blocks or BLOCKS):
        t = NAME.split("_")[-1]
        ok &= run("fault_vectors_" + t, py + ["tools/fault_vectors.py", "--blif", P(NAME + ".blif"), "--out", str(w / (t + "_faults.json")),
                                              "--solver", z3, "--work", str(w / ("fv_" + t)), "--rmax", "4"], out)
        chk = py + [P("independent_selfcheck_checker.py"), "--netlist", P(NAME + "_sc.blif"), "--block", P(NAME + ".blif"), "--H", P(NAME + "_H.json")]
        ok &= run("checker_" + t, chk, out)
        for j in (0, 1):
            ok &= run("checker_%s_drop%d" % (t, j), chk + ["--drop", str(j)], out)
        ok &= run("sim_faults_" + t, py + ["sim/sim_faults.py", "--name", NAME, "--n", str(a.n), "--init"], out)
        for j in (0, 1):
            ok &= run("sim_%s_drop%d" % (t, j), py + ["sim/sim_faults.py", "--name", NAME, "--n", str(a.n), "--drop", str(j)], out)
        ok &= run("cost_" + t, py + ["tools/cost.py", "--name", NAME, "--yosys", ys, "--work", str(w / ("cost_" + t))], out)
        if a.sat:
            for j in (0, 1):
                ok &= run("sat_%s_drop%d" % (t, j), py + [P("sat_faults.py"), "--name", NAME, "--yosys", ys, "--work", str(w / ("satd_%s_%d" % (t, j))), "--drop", str(j)], out)
            ok &= run("sat_faults_" + t, py + [P("sat_faults.py"), "--name", NAME, "--yosys", ys, "--work", str(w / ("sat_" + t)), "--pins", "--init", "--batch", "200"], out)
        ok &= run("drops_" + t, py + ["tools/compare_drops.py", "--name", NAME, "--results", "results"], out)
    ver = [subprocess.run([ys, "-V"], capture_output=True, text=True).stdout.strip(),
           subprocess.run([z3, "--version"], capture_output=True, text=True).stdout.strip(),
           "Python " + platform.python_version(), platform.platform()]
    (out / "tools.txt").write_text("\n".join(ver) + "\n")
    manifest()
    print("ALL PASS" if ok else "FAILURES")
    raise SystemExit(0 if ok else 1)
