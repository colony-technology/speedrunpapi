"""Structural checks on the delivered Verilog.

    python3 proof/structure.py --yosys PATH/yosys --verilator PATH/verilator --work BUILD_DIR

For each block:
  NAME.v       Yosys: proc; no flip-flop, latch, memory or process remains (select -assert-none);
               counts the kept wires (one per LUT of the netlist).
  NAME_lut6.v  Yosys with the Xilinx LUT models as black boxes: every cell is LUT1..LUT6; counts them.
  both         Verilator --lint-only -Wall: number of warnings printed.
The counts are compared with proof/NAME.json (lut_count).
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAMES = ["colony_crc32_d8", "colony_crc32_d32", "colony_crc32_d64", "colony_crc32_be64"]


def ys(exe, work, tag, lines):
    p = work / (tag + ".ys")
    p.write_text("\n".join(lines) + "\n")
    r = subprocess.run([exe, "-q", "-l", str(work / (tag + ".log")), "-s", str(p)], capture_output=True, text=True, timeout=600)
    return r.returncode, (work / (tag + ".log")).read_text()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--yosys", default="yosys")
    ap.add_argument("--verilator", default="verilator")
    ap.add_argument("--work", type=Path, required=True)
    a = ap.parse_args()
    a.work.mkdir(parents=True, exist_ok=True)
    bad = 0
    for n in NAMES:
        want = json.loads((ROOT / "proof" / (n + ".json")).read_text())["lut_count"]
        v = (ROOT / "block" / (n + ".v")).read_text()
        kept = len(re.findall(r'\(\* keep = "true" \*\) wire ', v))
        rc1, _ = ys(a.yosys, a.work, n + "_plain", ["read_verilog %s" % (ROOT / "block" / (n + ".v")), "hierarchy -top " + n, "proc",
                                                  "select -assert-none t:$dff t:$adff t:$sdff t:$dffe t:$dlatch t:$adlatch t:$sr t:$mem* t:$memrd t:$memwr",
                                                  "select -assert-none p:*"])
        rc2, log = ys(a.yosys, a.work, n + "_lut6", ["read_verilog -lib +/xilinx/cells_sim.v", "read_verilog %s" % (ROOT / "block" / (n + "_lut6.v")),
                                                   "hierarchy -top %s_lut6" % n,
                                                   "select -assert-none %s_lut6/t:* %s_lut6/t:LUT? %%d" % (n, n), "stat"])
        luts = sum(int(m.group(1)) for m in re.finditer(r"^\s+(\d+)\s+(?:\S+\s+)?LUT[1-6]\s*$", log, re.M))
        if luts == 0:
            luts = sum(int(m.group(2)) for m in re.finditer(r"^\s+LUT([1-6])\s+(\d+)\s*$", log, re.M))
        warn = []
        for f in (n + ".v", n + "_lut6.v"):
            srcs = ([str(a.work / "waive.vlt"), str(a.work / "lut_bb.v")] if f.endswith("_lut6.v") else []) + [str(ROOT / "block" / f)]
            if f.endswith("_lut6.v"):                         # LUT models for elaboration; their own lint is waived
                (a.work / "waive.vlt").write_text("`verilator_config\nlint_off -file \"*lut_bb.v\"\n")
                (a.work / "lut_bb.v").write_text("".join(
                    "module LUT%d #(parameter [%d:0] INIT = 0) (output O, %s); assign O = INIT[{%s}]; endmodule\n" % (
                        k, (1 << k) - 1, ", ".join("input I%d" % i for i in range(k)), ", ".join("I%d" % i for i in reversed(range(k)))) for k in range(1, 7)))
            r = subprocess.run([a.verilator, "--lint-only", "-Wall", "--top-module", f[:-2]] + srcs, capture_output=True, text=True)
            warn.append(len(re.findall(r"^%Warning-", r.stderr, re.M)))
            if re.search(r"^%Error(?!: Exiting due to)", r.stderr, re.M):
                warn[-1] = -1
        ok = rc1 == 0 and rc2 == 0 and kept == want and luts == want
        bad += not ok
        print("%-18s netlist %3d  kept wires %3d  LUT cells %3d  no state/process %s  lut-only %s  verilator -Wall warnings %d / %d" % (
            n, want, kept, luts, rc1 == 0, rc2 == 0, warn[0], warn[1]), flush=True)
    raise SystemExit(1 if bad else 0)
