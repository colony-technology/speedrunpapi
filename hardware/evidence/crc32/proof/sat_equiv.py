"""Yosys checks that tie the delivered Verilog files to the netlist the independent checker accepted.

    python3 proof/sat_equiv.py --yosys PATH/yosys --work BUILD_DIR

1. struct: for each block, each Verilog form (NAME.v, NAME_lut6.v) against proof/NAME.blif.
   equiv_make pairs every net of the same name in the two designs (the LUT outputs n0.., f0.., u.., x..,
   and the ports); equiv_simple proves each pair by SAT on its local cone; equiv_status -assert fails if
   any pair is unproven.  All pairs proven = the Verilog file computes the BLIF function on every input.
2. ref: colony_crc32_d8 only, each form (NAME.v, NAME_lut6.v, NAME.blif) against the bit-serial reference
   model proof/reference.v as one SAT miter over all 40 inputs.  (For d32 the same miter did not finish
   within 600 s; the reference link for d32, d64, be64 is the independent checker.)
3. Negative controls: one LUT INIT bit flipped in NAME_lut6.v must fail check 1 for every block, and must
   give a counterexample in check 2 for d8.

In check 1 the LUT primitives are mapped to Yosys $lut cells by proof/lut_to_dollar_lut.v (O = INIT[{I(k-1)..I0}]);
with Yosys's mux-tree models the per-net SAT for be64 did not finish in 10 minutes, with $lut cells it takes
seconds.  Check 2 and both simulations use Yosys's own Xilinx models (+/xilinx/cells_sim.v), which anchors that
convention independently of the techmap file.
"""
import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOCKS = [("colony_crc32_d8", 8, False), ("colony_crc32_d32", 32, False), ("colony_crc32_d64", 64, False),
          ("colony_crc32_be64", 64, True)]
CELLS = "read_verilog +/xilinx/cells_sim.v"
BAD = []


def yosys(exe, work, tag, lines):
    ys = work / (tag + ".ys")
    ys.write_text("\n".join(lines) + "\n")
    log = work / (tag + ".log")
    r = subprocess.run([exe, "-q", "-l", str(log), "-s", str(ys)], capture_output=True, text=True, timeout=600)
    return r.returncode, log.read_text()


def struct(exe, work, tag, name, vfile, lut6):
    stf = work / (tag + ".status")
    if stf.exists():
        stf.unlink()
    rc, log = yosys(exe, work, tag, [
        "read_blif -wideports %s" % (ROOT / "proof" / (name + ".blif")), "rename crc gold"] +
        (["read_verilog -lib +/xilinx/cells_sim.v"] if lut6 else []) +
        ["read_verilog %s" % vfile, "rename %s gate" % (name + ("_lut6" if lut6 else "")),
         "hierarchy -check", "proc"] +
        (["techmap -map %s gate" % (ROOT / "proof" / "lut_to_dollar_lut.v")] if lut6 else ["flatten gate"]) +
        ["opt_clean", "equiv_make gold gate eq", "hierarchy -top eq",
         "equiv_simple", "tee -o %s equiv_status" % stf, "equiv_status -assert"])
    st = stf.read_text() if stf.exists() else ""
    m = re.search(r"Of those cells (\d+) are proven and (\d+) are unproven", st)
    if rc == 0 and m and m.group(2) == "0":
        return "PROVED (%s of %s net pairs)" % (m.group(1), m.group(1))
    if m:
        return "UNPROVEN (%s proven, %s unproven)" % (m.group(1), m.group(2))
    if "Found" in st and "unproven $equiv" in st:
        return "UNPROVEN " + st.strip().splitlines()[-1]
    return "ERROR rc=%d %s" % (rc, (st or log)[-300:])


def ref(exe, work, tag, reads, mod):
    m = work / (tag + "_miter.v")
    m.write_text("module miter (input [31:0] s, input [7:0] d, output bad);\n  wire [31:0] a, b;\n"
                 "  %s u (.s(s), .d(d), .o(a));\n  ref_crc32_fixed #(.W(8)) r (.s(s), .d(d), .o(b));\n"
                 "  assign bad = a != b;\nendmodule\n" % mod)
    rc, log = yosys(exe, work, tag, reads + ["read_verilog %s" % (ROOT / "proof" / "reference.v"), "read_verilog %s" % m,
                                             "hierarchy -top miter", "proc", "flatten", "opt_clean", "sat -prove bad 0"])
    if "SAT proof finished - no model found: SUCCESS!" in log:
        return "PROVED"
    if "SAT proof finished - model found: FAIL!" in log:
        return "COUNTEREXAMPLE"
    return "ERROR rc=%d %s" % (rc, log[-300:])


def mutant(name, work):
    src = (ROOT / "block" / (name + "_lut6.v")).read_text()
    mm = re.search(r"INIT\((\d+)'h([0-9a-f]+)\)", src)
    bits, val = int(mm.group(1)), int(mm.group(2), 16) ^ 2
    p = work / (name + "_lut6_mutant.v")
    p.write_text(src[:mm.start()] + "INIT(%d'h%0*x)" % (bits, bits // 4, val) + src[mm.end():])
    return p


def show(name, check, form, res, want):
    ok = res.startswith(want)
    if not ok:
        BAD.append((name, check, form))
    print("%-18s %-6s %-11s %s%s" % (name, check, form, res, "" if ok else "   <-- expected " + want), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--yosys", default="yosys")
    ap.add_argument("--work", type=Path, required=True)
    a = ap.parse_args()
    a.work.mkdir(parents=True, exist_ok=True)
    for name, W, be in BLOCKS:
        for form, lut6 in (("v", False), ("lut6", True)):
            f = ROOT / "block" / (name + ("_lut6.v" if lut6 else ".v"))
            show(name, "struct", form, struct(a.yosys, a.work, "%s_struct_%s" % (name, form), name, f, lut6), "PROVED")
        show(name, "struct", "lut6-mutant", struct(a.yosys, a.work, "%s_struct_mut" % name, name, mutant(name, a.work), True), "UNPROVEN")
    name = "colony_crc32_d8"
    for form, reads, mod in (("v", ["read_verilog %s" % (ROOT / "block" / (name + ".v"))], name),
                             ("lut6", [CELLS, "read_verilog %s" % (ROOT / "block" / (name + "_lut6.v"))], name + "_lut6"),
                             ("blif", ["read_blif -wideports %s" % (ROOT / "proof" / (name + ".blif")), "rename crc %s_blif" % name], name + "_blif"),
                             ("lut6-mutant", [CELLS, "read_verilog %s" % mutant(name, a.work)], name + "_lut6")):
        show(name, "ref", form, ref(a.yosys, a.work, "%s_ref_%s" % (name, form), reads, mod), "COUNTEREXAMPLE" if "mutant" in form else "PROVED")
    print("FAILURES %d" % len(BAD))
    raise SystemExit(1 if BAD else 0)
