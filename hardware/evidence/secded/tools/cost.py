"""C4: LUT-6 and levels of the delivered blocks beside the plain description of the same code, one Yosys flow.

    python3 tools/cost.py --code 72_64 --yosys PATH/yosys --work BUILD_DIR

Flow for every design: `synth_xilinx -top TOP -flatten -noiopad`, `stat` (LUT1..LUT6), `ltp -noff` (levels).
  ours:      colony_secded72_enc_lut6; colony_secded72_syn_lut6; colony_secded72_cor_lut6; decoder = syn + cor
  plain:     source/prim_secded_72_64_enc.sv and source/prim_secded_72_64_dec.sv (OpenTitan, read as RTL only)
The OpenTitan decoder computes the same syndrome, correction and flags (err_o[0] odd syndrome weight,
err_o[1] even non-zero weight).  --code selects the code (72_64, 39_32).
"""
import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEC = """module ours_dec (input [%(nm)d:0] r, output [%(km)d:0] q, output corrected, output uncorrectable);
  wire [%(rm)d:0] s;
  colony_secded%(n)d_syn_lut6 S (.r(r), .s(s));
  colony_secded%(n)d_cor_lut6 K (.r(r[%(km)d:0]), .s(s), .q(q), .corrected(corrected), .uncorrectable(uncorrectable));
endmodule
"""


def measure(yosys, work, tag, files, top):
    cmd = "; ".join(["read_verilog -sv %s" % f for f in files] + ["synth_xilinx -top %s -flatten -noiopad" % top,
                     "tee -o %s stat" % (work / (tag + "_stat.txt")), "tee -o %s ltp -noff" % (work / (tag + "_ltp.txt"))])
    r = subprocess.run([yosys, "-q", "-l", str(work / (tag + ".log")), "-p", cmd], capture_output=True, text=True, timeout=1800)
    if r.returncode:
        raise SystemExit(r.stderr[-1500:])
    st = (work / (tag + "_stat.txt")).read_text()
    luts = sum(int(m.group(1)) for m in re.finditer(r"^\s+(\d+)\s+(?:\S+\s+)?LUT[1-6]\s*$", st, re.M))
    other = [l.strip() for l in st.splitlines() if re.match(r"^\s+\d+\s+(?:\S+\s+)?(MUXF|CARRY)", l)]
    lp = re.search(r"length=(\d+)", (work / (tag + "_ltp.txt")).read_text())
    return luts, int(lp.group(1)) if lp else -1, other


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--yosys", default="yosys")
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--code", default="72_64")
    a = ap.parse_args()
    n, k = (int(x) for x in a.code.split("_"))
    N, C = "colony_secded%d" % n, a.code
    a.work.mkdir(parents=True, exist_ok=True)
    B = lambda n: ROOT / "block" / (n + ".v")
    (a.work / "ours_dec.v").write_text(DEC % {"n": n, "nm": n - 1, "km": k - 1, "rm": n - k - 1})
    rows = [("encoder", "ours", [B(N + "_enc_lut6")], N + "_enc_lut6"),
            ("encoder", "OpenTitan RTL", [ROOT / "source" / ("prim_secded_%s_enc.sv" % C)], "prim_secded_%s_enc" % C),
            ("syndrome", "ours", [B(N + "_syn_lut6")], N + "_syn_lut6"),
            ("corrector", "ours", [B(N + "_cor_lut6")], N + "_cor_lut6"),
            ("decoder", "ours (syndrome + corrector)", [B(N + "_syn_lut6"), B(N + "_cor_lut6"), a.work / "ours_dec.v"], "ours_dec"),
            ("decoder", "OpenTitan RTL", [ROOT / "source" / ("prim_secded_%s_dec.sv" % C)], "prim_secded_%s_dec" % C)]
    print("code (%d, %d)" % (n, k))
    print("%-10s %-30s %6s %7s  %s" % ("block", "design", "LUT-6", "levels", "other cells"))
    for i, (blk, who, files, top) in enumerate(rows):
        luts, lev, other = measure(a.yosys, a.work, "c%d" % i, files, top)
        print("%-10s %-30s %6d %7d  %s" % (blk, who, luts, lev, ", ".join(other) or "-"))
