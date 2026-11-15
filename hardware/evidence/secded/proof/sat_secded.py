"""Proof 2: SAT in Yosys over the whole chain, encoder -> error -> syndrome -> corrector.

    python3 proof/sat_secded.py --code 72_64 --yosys PATH/yosys --work BUILD_DIR [--form lut6|v] [--split-c3] [--seconds N]

Code (n, k), r = n - k check bits.  Chain: x = {c, d} with c = enc(d); e an error pattern; r = x ^ e;
s = syn(r); (q, corrected, uncorrectable) = cor(r[k-1:0], s).
  C1  e = 0:                                   prove  q == d, corrected = 0, uncorrectable = 0
  C2  e = one bit at position p, p free < n:   prove  q == d, corrected = 1, uncorrectable = 0
  C3  e = bits p1 < p2 < n, both free:         prove  uncorrectable = 1
      --split-c3: one miter for each p1 = 0 .. n-2 with p2 free above it; together they cover every pair once
      (for (72, 64) a single miter with both positions free did not finish in 300 s)
d and the positions are free inputs: one miter per claim covers every data word and every position.
Control: the false claim "two flipped bits give corrected = 1" must give a counterexample.
--form lut6 reads the LUT6 files (primitives as Yosys $lut through proof/lut_to_dollar_lut.v), --form v the plain files.
"""
import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TOP = """module chain (input [%(km)d:0] d, input [7:0] p1, input [7:0] p2, output bad);
  wire [%(rm)d:0] c; wire [%(nm)d:0] x = {c, d}; wire [%(nm)d:0] e; wire [%(nm)d:0] r = x ^ e; wire [%(rm)d:0] s;
  wire [%(km)d:0] q; wire corr, unc;
  colony_secded%(n)d_enc%(f)s E (.d(d), .c(c));
  colony_secded%(n)d_syn%(f)s S (.r(r), .s(s));
  colony_secded%(n)d_cor%(f)s K (.r(r[%(km)d:0]), .s(s), .q(q), .corrected(corr), .uncorrectable(unc));
  assign e = %(e)s;
  assign bad = %(bad)s;
endmodule
"""


def cases(n, split):
    one = lambda p: "(%d'd1 << %s)" % (n, p)
    c = {"C1": ("%d'd0" % n, "1'b1", "(q != d) | corr | unc"),
         "C2": (one("p1"), "(p1 < 8'd%d)" % n, "(q != d) | ~corr | unc")}
    if split:
        for p1 in range(n - 1):
            c["C3.p1=%d" % p1] = ("%s | %s" % (one("8'd%d" % p1), one("p2")), "(p2 > 8'd%d) & (p2 < 8'd%d)" % (p1, n), "~unc")
    else:
        c["C3"] = ("%s | %s" % (one("p1"), one("p2")), "(p1 < p2) & (p2 < 8'd%d)" % n, "~unc")
    c["C3-control"] = ("%s | %s" % (one("p1"), one("p2")), "(p1 < p2) & (p2 < 8'd%d)" % n, "~corr")
    return c


def run(yosys, work, tag, form, n, k, e, assume, bad, seconds):
    top = work / ("chain_%s.v" % tag)
    top.write_text(TOP % {"n": n, "km": k - 1, "rm": n - k - 1, "nm": n - 1, "f": "_lut6" if form == "lut6" else "", "e": e,
                          "bad": "(%s) & (%s)" % (assume, bad)})
    reads = ["read_verilog %s" % (ROOT / "block" / ("colony_secded%d_%s%s.v" % (n, b, "_lut6" if form == "lut6" else ""))) for b in ("enc", "syn", "cor")]
    if form == "lut6":
        reads = ["read_verilog -lib +/xilinx/cells_sim.v"] + reads
    lines = reads + ["read_verilog %s" % top, "hierarchy -top chain", "proc"] + \
        (["techmap -map %s" % (ROOT / "proof" / "lut_to_dollar_lut.v")] if form == "lut6" else []) + \
        ["flatten", "opt_clean", "sat -prove bad 0 -timeout %d" % seconds]
    ys = work / ("chain_%s.ys" % tag)
    ys.write_text("\n".join(lines) + "\n")
    log = work / ("chain_%s.log" % tag)
    subprocess.run([yosys, "-q", "-l", str(log), "-s", str(ys)], capture_output=True, text=True)
    t = log.read_text()
    if "SAT proof finished - no model found: SUCCESS!" in t:
        return "PROVED"
    if "SAT proof finished - model found: FAIL!" in t:
        return "COUNTEREXAMPLE"
    if "TIMEOUT" in t:
        return "TIMEOUT %d s" % seconds
    return "ERROR " + t[-200:].replace("\n", " ")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", default="72_64")
    ap.add_argument("--yosys", default="yosys")
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--form", default="lut6", choices=("lut6", "v"))
    ap.add_argument("--seconds", type=int, default=600)
    ap.add_argument("--split-c3", action="store_true")
    a = ap.parse_args()
    n, k = (int(x) for x in a.code.split("_"))
    a.work.mkdir(parents=True, exist_ok=True)
    bad, split = 0, {}
    for tag, (e, assume, cond) in cases(n, a.split_c3).items():
        r = run(a.yosys, a.work, tag, a.form, n, k, e, assume, cond, a.seconds)
        want = "COUNTEREXAMPLE" if tag == "C3-control" else "PROVED"
        bad += r != want
        if tag.startswith("C3.p1="):
            split[r] = split.get(r, 0) + 1
            if r != want:
                print("%-11s %-5s %s   <-- expected %s" % (tag, a.form, r, want), flush=True)
            continue
        print("%-11s %-5s %s%s" % (tag, a.form, r, "" if r == want else "   <-- expected " + want), flush=True)
    if split:
        print("%-11s %-5s %s (%d miters: p1 = 0..%d fixed, p2 free, p1 < p2 < %d; every pair once)" % (
            "C3", a.form, ", ".join("%s %d" % kv for kv in sorted(split.items())), n - 1, n - 2, n))
    raise SystemExit(1 if bad else 0)
