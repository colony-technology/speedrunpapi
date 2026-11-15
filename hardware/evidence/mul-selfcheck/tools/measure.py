# usage: python3 measure.py NETDIR OUT.json N [N ...]
# Lookup tables and levels through the flow of the multiplier's own measurements: Yosys
#   synth -top TOP; abc -lut 6; opt_clean; stat; ltp -noff
#   the detector alone (NETDIR/scN_mM/detector.blif), m = 3 and m = 15
#   the multiplier's own table count (the tables of NETDIR/scN_m3/selfcheck.blif that are not the detector's,
#   less the 2N buffers to p[k]), and the same multiplier part through the flow
#   the usual baseline: a second multiplier and a 2N-bit comparison (the comparison through the same flow)
import json
import os
import re
import subprocess
import sys
import tempfile

netdir, outp = sys.argv[1], sys.argv[2]


def yosys(read, top):
    log = subprocess.run(["yosys", "-p", "%s; synth -top %s; abc -lut 6; opt_clean; stat; ltp -noff" % (read, top)],
                         capture_output=True, text=True).stdout
    luts = re.findall(r"^\s+(\d+)\s+\$lut\s*$", log, re.M) or re.findall(r"\$lut\s+(\d+)", log)
    lev = re.findall(r"length=(\d+)", log)
    return (int(luts[-1]) if luts else None), (int(lev[-1]) if lev else None)


res = {}
with tempfile.TemporaryDirectory() as td:
    for n in map(int, sys.argv[3:]):
        lines = open(os.path.join(netdir, "sc%d_m3" % n, "selfcheck.blif")).read().splitlines()
        heads = [l.split() for l in lines if l.startswith(".names")]
        mulnames = [h for h in heads if not (h[-1].startswith("d_") or h[-1].startswith("t[") or h[-1] == "alarm")]
        own = len(mulnames) - 2 * n
        # the multiplier part as its own BLIF, for the flow
        mb = os.path.join(td, "mul%d.blif" % n)
        with open(mb, "w") as f:
            f.write(".model mul\n.inputs %s\n.outputs %s\n" % (" ".join(["a[%d]" % i for i in range(n)] + ["b[%d]" % i for i in range(n)]),
                                                                " ".join("p[%d]" % k for k in range(2 * n))))
            keep = False
            for l in lines:
                if l.startswith(".names"):
                    o = l.split()[-1]
                    keep = not (o.startswith("d_") or o.startswith("t[") or o == "alarm")
                elif l.startswith("."):
                    keep = False
                    continue
                if keep:
                    f.write(l + "\n")
            f.write(".end\n")
        ml, mv = yosys("read_blif %s" % mb, "mul")
        cmpv = os.path.join(td, "cmp%d.v" % n)
        open(cmpv, "w").write("module cmp (input [%d:0] x, input [%d:0] y, output ne); assign ne = x != y; endmodule\n" % (2 * n - 1, 2 * n - 1))
        cl, cv = yosys("read_verilog %s" % cmpv, "cmp")
        row = dict(mul_own_tables=own, mul_yosys=[ml, mv], cmp_2n=[cl, cv], baseline_extra=own + cl)
        for m in (3, 15):
            dl, dv = yosys("read_blif %s" % os.path.join(netdir, "sc%d_m%d" % (n, m), "detector.blif"), "detector")
            row["det_m%d" % m] = [dl, dv]
            row["share_m%d_of_own" % m] = round(100.0 * dl / own, 2)
        res[n] = row
        print("N = %d: multiplier %d tables (Yosys %s LUTs, %s levels); detector m = 3: %s LUTs, %s levels (%.2f %%); "
              "m = 15: %s LUTs, %s levels (%.2f %%); second multiplier and compare: %d + %s = %d"
              % (n, own, ml, mv, row["det_m3"][0], row["det_m3"][1], row["share_m3_of_own"], row["det_m15"][0],
                 row["det_m15"][1], row["share_m15_of_own"], own, cl, own + cl), flush=True)
json.dump(res, open(outp, "w"), indent=1)
