"""Builds the detector for an unchanged CRC block: predictor, checker, alarm.

    python3 tools/build_selfcheck.py --name colony_crc32_d64 --evidence ../crc32 --H proof/NAME_H.json
                                     --linear PATH/speedrunpapi/hardware/linear --out .

predictor  p[j] = row j of H L over the block's inputs (s, d)     network from linear_compiler, its own nets
checker    c[j] = row j of H over the block's outputs o           network from linear_compiler, its own nets
alarm      = OR over j of (p[j] ^ c[j])                            LUT(s) written here

Writes
  block/NAME.v, block/NAME_lut6.v       copies of the block, unchanged (byte-identical to ../crc32/block/)
  block/NAME_sc.v                       top: the block instance, predictor, checker, alarm (XOR assigns)
  block/NAME_sc_lut6.v                  the same with Xilinx LUT primitives (the block instance is NAME_lut6)
  proof/NAME_sc.blif                    flat netlist of the top: block nets b_*, predictor p_*, checker c_*, alarm a_*
"""
import argparse
import json
import shutil
import sys
from pathlib import Path


def parity(n):
    return sum(1 << r for r in range(1 << n) if bin(r).count("1") & 1)


def read_blif(path):
    ins, outs, luts, cur = [], [], [], None
    for line in path.read_text().splitlines():
        t = line.split()
        if not t:
            continue
        if t[0] == ".inputs":
            ins += t[1:]
        elif t[0] == ".outputs":
            outs += t[1:]
        elif t[0] == ".names":
            cur = [t[-1], t[1:-1], []]
            luts.append(cur)
        elif t[0] in (".model", ".end"):
            cur = None
        else:
            cur[2].append(" ".join(t))
    return ins, outs, luts


def or_tree(xs, prefix, nets):
    """alarm = OR of the pairs (p ^ c): pairs packed 3 to a LUT-6, then ORs of up to 6."""
    level, q = [], 0
    for i in range(0, len(xs), 3):
        grp = xs[i:i + 3]
        src = [v for pc in grp for v in pc]
        n = len(src)
        tt = sum(1 << r for r in range(1 << n) if any(((r >> (2 * t)) & 1) != ((r >> (2 * t + 1)) & 1) for t in range(len(grp))))
        nm = "%s%d" % (prefix, q)
        q += 1
        nets.append((nm, src, tt))
        level.append(nm)
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 6):
            src = level[i:i + 6]
            nm = "%s%d" % (prefix, q)
            q += 1
            nets.append((nm, src, (1 << (1 << len(src))) - 2))
            nxt.append(nm)
        level = nxt
    return level[0]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--H", type=Path, required=True)
    ap.add_argument("--linear", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    sys.path.insert(0, str(a.linear.resolve()))
    import linear_compiler as LC
    for sub in ("block", "proof"):
        (a.out / sub).mkdir(parents=True, exist_ok=True)
    for f in (a.name + ".v", a.name + "_lut6.v"):
        shutil.copyfile(a.evidence / "block" / f, a.out / "block" / f)
    Hs = json.loads(a.H.read_text())
    H = [int(h, 16) for h in Hs["H"]]
    pred_rows = [int(m, 16) for m in Hs["predictor_rows"]]
    ins, outs, luts = read_blif(a.evidence / "proof" / (a.name + ".blif"))
    nin, r = len(ins), len(H)

    def compiled(rows, n, src_names, prefix):
        best = None
        for depth in (None, 3, 2):
            try:
                c = LC.compile_linear(rows, n, 6, depth)
            except ValueError:
                continue
            if best is None or (c[2], len(c[0])) < (best[2], len(best[0])):
                best = c
        nodes, outs_, lev = best
        nm = lambda v: src_names[v] if v < n else "%s%d" % (prefix, v - n)
        nets = [("%s%d" % (prefix, j), [nm(v) for v in x], parity(len(x))) for j, x in enumerate(nodes)]
        return nets, [nm(o) for o in outs_], lev
    pnets, pout, plev = compiled(pred_rows, nin, ins, "p_")
    cnets, cout, clev = compiled(H, 32, outs, "c_")
    anets = []
    alarm = or_tree(list(zip(pout, cout)), "a_", anets)

    # flat BLIF of the top
    B = [".model sc", ".inputs " + " ".join(ins), ".outputs " + " ".join(outs + ["alarm"])]
    ren = lambda v: v if v in ins or v in outs else "b_" + v
    for o, src, rows in luts:
        B.append(".names " + " ".join([ren(v) for v in src] + [ren(o)]))
        B += rows
    for n, src, tt in pnets + cnets + anets:
        B.append(".names " + " ".join(src + [n]))
        B += ["".join(str((rr >> q) & 1) for q in range(len(src))) + " 1" for rr in range(1 << len(src)) if (tt >> rr) & 1]
    B += [".names %s alarm" % alarm, "1 1", ".end"]
    (a.out / "proof" / (a.name + "_sc.blif")).write_text("\n".join(B) + "\n")

    # Verilog tops
    W = 8 * 0 + (nin - 32)
    head = ("// %s with a concurrent detector: %d check bits, H rows %s (bit i = o[i]).\n"
            "// alarm = 1 when the check bits predicted from s, d differ from those computed from o.\n"
            "// The block instance is unchanged; predictor, checker and alarm share no net with it.\n" % (a.name, r, ", ".join("32'h%08x" % h for h in H)))
    vn = lambda v: v.replace("p_", "p_n").replace("c_", "c_n").replace("a_", "a_n") if v[:2] in ("p_", "c_", "a_") else v
    for form in ("", "_lut6"):
        V = [head, "module %s_sc%s (\n    input  wire [31:0] s,\n    input  wire [%d:0] d,\n    output wire [31:0] o,\n    output wire alarm\n);\n" % (a.name, form, W - 1),
             "  %s%s u_block (.s(s), .d(d), .o(o));\n" % (a.name, form)]
        for n, src, tt in pnets + cnets + anets:
            k = len(src)
            if form:
                V.append("  wire %s; LUT%d #(.INIT(%d'h%0*x)) u_%s (.O(%s), %s);\n" % (vn(n), k, 1 << k, max(1, (1 << k) // 4), tt, vn(n), vn(n),
                                                                             ", ".join(".I%d(%s)" % (q, vn(v)) for q, v in enumerate(src))))
            elif n.startswith("a_"):
                terms = []
                for rr in range(1 << k):
                    if (tt >> rr) & 1:
                        terms.append("(%s)" % " & ".join(("" if (rr >> q) & 1 else "~") + vn(v) for q, v in enumerate(src)))
                V.append("  (* keep = \"true\" *) wire %s = %d'h%0*x >> {%s};\n" % (vn(n), 1 << k, max(1, (1 << k) // 4), tt, ", ".join(vn(v) for v in reversed(src))))
            else:
                V.append("  (* keep = \"true\" *) wire %s = %s;\n" % (vn(n), " ^ ".join(vn(v) for v in src)))
        V.append("  assign alarm = %s;\nendmodule\n" % vn(alarm))
        (a.out / "block" / ("%s_sc%s.v" % (a.name, form))).write_text("".join(V))
    info = {"name": a.name, "r": r, "H": Hs["H"], "predictor_lut6": len(pnets), "predictor_levels": plev,
            "checker_lut6": len(cnets), "checker_levels": clev, "alarm_lut6": len(anets), "block_lut6": len(luts) - 32}
    (a.out / "proof" / (a.name + "_sc_build.json")).write_text(json.dumps(info, indent=1) + "\n")
    print(json.dumps(info))
