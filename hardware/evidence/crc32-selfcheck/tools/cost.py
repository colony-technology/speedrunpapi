"""Cost table: LUT-6 and logic levels, one Yosys flow for every design.

    python3 tools/cost.py --name colony_crc32_d64 --yosys PATH/yosys --work BUILD_DIR

Designs, all built from the LUT6 primitive form of the block (the network as delivered):
  block     NAME_lut6
  detector  NAME_sc_lut6: block + predictor + checker + alarm
  dmr       two NAME_lut6 instances, alarm = OR of the 32 output XORs (written as RTL, mapped by Yosys)
  tmr       three NAME_lut6 instances, o = bitwise majority, alarm = any disagreement (RTL, mapped by Yosys)
Flow: `synth_xilinx -top TOP -flatten -noiopad`, then `stat` (LUT1..LUT6 cells) and `ltp -noff` (longest path in cells,
which for LUT-only logic is the number of LUT levels).  keep_hierarchy is not used; each copy is kept by `keep`
on its instance so that Yosys does not merge the identical copies.
"""
import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def wrap(name, kind, W):
    io = "input [31:0] s, input [%d:0] d, output [31:0] o, output alarm" % (W - 1)
    if kind == "dmr":
        return ("module top (%s);\n  wire [31:0] o2;\n  (* keep *) %s_lut6 a (.s(s), .d(d), .o(o));\n"
                "  (* keep *) %s_lut6 b (.s(s), .d(d), .o(o2));\n  assign alarm = |(o ^ o2);\nendmodule\n" % (io, name, name))
    if kind == "tmr":
        return ("module top (%s);\n  wire [31:0] x, y, z;\n  (* keep *) %s_lut6 a (.s(s), .d(d), .o(x));\n"
                "  (* keep *) %s_lut6 b (.s(s), .d(d), .o(y));\n  (* keep *) %s_lut6 c (.s(s), .d(d), .o(z));\n"
                "  assign o = (x & y) | (y & z) | (x & z);\n  assign alarm = |((x ^ y) | (y ^ z));\nendmodule\n" % (io, name, name, name))
    if kind == "detector":
        return "module top (%s);\n  (* keep *) %s_sc_lut6 a (.s(s), .d(d), .o(o), .alarm(alarm));\nendmodule\n" % (io, name)
    return "module top (%s);\n  (* keep *) %s_lut6 a (.s(s), .d(d), .o(o));\n  assign alarm = 1'b0;\nendmodule\n" % (io, name)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--yosys", default="yosys")
    ap.add_argument("--work", type=Path, required=True)
    a = ap.parse_args()
    a.work.mkdir(parents=True, exist_ok=True)
    src = (ROOT / "block" / (a.name + "_lut6.v")).read_text()
    W = int(re.search(r"input  wire \[(\d+):0\] d", src).group(1)) + 1
    rows = []
    for kind in ("block", "detector", "dmr", "tmr"):
        top = a.work / ("top_%s.v" % kind)
        top.write_text(wrap(a.name, kind, W))
        files = [ROOT / "block" / (a.name + "_lut6.v")] + ([ROOT / "block" / (a.name + "_sc_lut6.v")] if kind == "detector" else []) + [top]
        log = a.work / ("cost_%s.log" % kind)
        cmd = "; ".join(["read_verilog %s" % f for f in files] + ["synth_xilinx -top top -flatten -noiopad", "tee -o %s stat" % (a.work / ("stat_%s.txt" % kind)),
                                                                  "tee -o %s ltp -noff" % (a.work / ("ltp_%s.txt" % kind))])
        r = subprocess.run([a.yosys, "-q", "-l", str(log), "-p", cmd], capture_output=True, text=True, timeout=1800)
        if r.returncode:
            raise SystemExit(r.stderr[-1500:])
        st = (a.work / ("stat_%s.txt" % kind)).read_text()
        luts = sum(int(m.group(1)) for m in re.finditer(r"^\s+(\d+)\s+(?:\S+\s+)?LUT[1-6]\s*$", st, re.M))
        other = [l.strip() for l in st.splitlines() if re.match(r"^\s+\d+\s+(?:\S+\s+)?(MUXF|CARRY|FD|SRL)", l)]
        lp = re.search(r"Longest topological path in \S+ \(length=(\d+)\)", (a.work / ("ltp_%s.txt" % kind)).read_text())
        rows.append((kind, luts, int(lp.group(1)) if lp else -1, other))
    base = rows[0][1]
    print("%-9s %6s %8s %8s  %s" % ("design", "LUT-6", "x block", "levels", "other cells"))
    for kind, luts, lev, other in rows:
        print("%-9s %6d %8.2f %8d  %s" % (kind, luts, luts / base, lev, ", ".join(other) or "-"))
