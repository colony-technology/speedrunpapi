"""Builds the four CRC-32 blocks of this package from the public speedrunpapi generator.

    python3 tools/build_blocks.py --linear PATH/speedrunpapi/hardware/linear --out .

Writes, for each block NAME:
    block/NAME.v        XOR assigns, one kept wire per LUT
    block/NAME_lut6.v   Xilinx LUT1..LUT6 primitives, same network
    proof/NAME.blif     the netlist the independent checker reads
    proof/NAME.json     the derivation (claim, declared LUT count and levels, netlist digest)

Blocks (polynomial 0x04C11DB7, register update, no initial value, no final complement):
    colony_crc32_d8     8 data bits per call
    colony_crc32_d32    32 data bits
    colony_crc32_d64    64 data bits
    colony_crc32_be64   64 data bits, e = number of empty bytes at the top of the word (0..7)
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

POLY = 0x04C11DB7
FIXED = [("colony_crc32_d8", 8), ("colony_crc32_d32", 32), ("colony_crc32_d64", 64)]
HEAD = ("// CRC-32, polynomial 0x04C11DB7 (IEEE 802.3 frame check sequence), register update.\n"
        "// Recurrence, applied to d[0] first:  fb = s[31] ^ d[t];  s = (s << 1) ^ (fb ? 32'h04C11DB7 : 0).\n"
        "// s[i] holds the coefficient of x^i.  Initial value and final complement are outside this block.\n")


def parity(n):
    return sum(1 << r for r in range(1 << n) if bin(r).count("1") & 1)


def pick_fixed(L, W):
    """Smallest number of LUT levels, then fewest LUTs (same rule as the taxi delivery)."""
    rows = L.crc_rows(POLY, 32, W)
    nin = 32 + W
    free = L.compile_linear(rows, nin, 6, None)
    cands = [free]
    for d in range(1, free[2]):
        try:
            cands.append(L.compile_linear(rows, nin, 6, d))
            break
        except ValueError:
            pass
    mind = min(c[2] for c in cands)
    if mind + 1 < free[2]:
        cands.append(L.compile_linear(rows, nin, 6, mind + 1))
    nodes, outs, lev = min((c for c in cands if c[2] == mind), key=lambda c: len(c[0]))
    return rows, nodes, outs, lev


def fixed_block(L, name, W, out):
    rows, nodes, outs, lev = pick_fixed(L, W)
    ins = ["s[%d]" % i for i in range(32)] + ["d[%d]" % i for i in range(W)]
    ons = ["o[%d]" % i for i in range(32)]
    nm = lambda v: ins[v] if v < len(ins) else "n%d" % (v - len(ins))
    data = L.blif(nodes, outs, ins, ons, "crc")
    cert = {"schema": "colony.lut-linear.v1", "kind": "crc", "poly": POLY, "width": 32, "data": W, "k": 6,
            "lut_count": len(nodes), "levels": lev, "netlist_digest": "sha256:" + hashlib.sha256(data).hexdigest()}
    (out / "proof" / (name + ".blif")).write_bytes(data)
    (out / "proof" / (name + ".json")).write_text(json.dumps(cert, sort_keys=True) + "\n")
    port = "module %s (\n    input  wire [31:0] s,\n    input  wire [%d:0] d,\n    output wire [31:0] o\n);\n" % ("%s", W - 1)
    info = "// %d data bits per call, d[0] first.  o = register after d[0] .. d[%d] from s.  %d LUT-6, %d levels.\n" % (W, W - 1, len(nodes), lev)
    plain, prim = [HEAD + info + port % name], [HEAD + info + port % (name + "_lut6")]
    for j, x in enumerate(nodes):
        plain.append("  (* keep = \"true\" *) wire n%d = %s;\n" % (j, " ^ ".join(nm(v) for v in x)))
        k = len(x)
        prim.append("  wire n%d; LUT%d #(.INIT(%d'h%x)) u%d (.O(n%d), %s);\n" % (
            j, k, 1 << k, parity(k), j, j, ", ".join(".I%d(%s)" % (q, nm(v)) for q, v in enumerate(x))))
    for i, o in enumerate(outs):
        line = "  assign o[%d] = %s;\n" % (i, "1'b0" if o is None else nm(o))
        plain.append(line)
        prim.append(line)
    (out / "block" / (name + ".v")).write_text("".join(plain) + "endmodule\n")
    (out / "block" / (name + "_lut6.v")).write_text("".join(prim) + "endmodule\n")
    return {"name": name, "data_bits": W, "inputs": 32 + W, "lut6": len(nodes), "levels": lev}


def be_block(L, G, out):
    name, nbytes = "colony_crc32_be64", 8
    luts, lev, ebits = G.generate(POLY, 32, nbytes, 6, None)
    data = G.blif(luts, 32, nbytes, ebits)
    count = sum(1 for n, _, _ in luts if not n.startswith("o["))
    cert = {"schema": "colony.lut-crc.v1", "poly": POLY, "width": 32, "bytes": nbytes, "k": 6,
            "lut_count": count, "levels": lev, "netlist_digest": "sha256:" + hashlib.sha256(data).hexdigest()}
    (out / "proof" / (name + ".blif")).write_bytes(data)
    (out / "proof" / (name + ".json")).write_text(json.dumps(cert, sort_keys=True) + "\n")
    info = ("// 64 data bits per call, byte b = d[8b+7:8b], d[0] first.  e = number of empty bytes at the top of the word, 0..7.\n"
            "// o = register after the first 8 * (8 - e) bits of d from s.  Bytes 8-e .. 7 of d must be zero.  %d LUT-6, %d levels.\n" % (count, lev))
    port = "module %s (\n    input  wire [31:0] s,\n    input  wire [63:0] d,\n    input  wire [2:0]  e,\n    output wire [31:0] o\n);\n"
    plain, prim = [HEAD + info + port % name], [HEAD + info + port % (name + "_lut6")]
    for nm_, src, tt in luts:
        n = len(src)
        if nm_.startswith("o["):
            line = "  assign %s = %s;\n" % (nm_, src[0])
            plain.append(line)
            prim.append(line)
            continue
        w = nm_
        ref = lambda v: v
        if nm_.startswith("f") or nm_.startswith("u"):
            assert tt == parity(n)
            expr = " ^ ".join(ref(v) for v in src)
        else:                                               # x<j>_<i>: own ^ (e[j] & parity(fan))
            ej = next(q for q, v in enumerate(src) if v.startswith("e["))
            fan2 = src[:ej]                                 # the parity inputs; the own bit follows e[j] or is among them
            # the own bit is the one input that alone sets the output while e[j] = 0
            e0 = [q for q in range(n) if q != ej and (tt >> (1 << q)) & 1]
            assert len(e0) == 1
            own = src[e0[0]]
            expr = "%s ^ (%s & (%s))" % (ref(own), src[ej], " ^ ".join(ref(v) for v in fan2))
            for r in range(1 << n):                          # the expression equals the table
                b = {v: (r >> q) & 1 for q, v in enumerate(src)}
                val = b[own] ^ (b[src[ej]] & (sum(b[v] for v in fan2) & 1))
                assert val == (tt >> r) & 1, nm_
        plain.append("  (* keep = \"true\" *) wire %s = %s;\n" % (w, expr))
        prim.append("  wire %s; LUT%d #(.INIT(%d'h%x)) u_%s (.O(%s), %s);\n" % (
            w, n, 1 << n, tt, w, w, ", ".join(".I%d(%s)" % (q, ref(v)) for q, v in enumerate(src))))
    (out / "block" / (name + ".v")).write_text("".join(plain) + "endmodule\n")
    (out / "block" / (name + "_lut6.v")).write_text("".join(prim) + "endmodule\n")
    return {"name": name, "data_bits": 64, "inputs": 32 + 64 + ebits, "lut6": count, "levels": lev}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--linear", type=Path, required=True, help="speedrunpapi/hardware/linear")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    sys.path.insert(0, str(a.linear.resolve()))
    import linear_compiler as L
    import crc_gen as G
    for sub in ("block", "proof"):
        (a.out / sub).mkdir(parents=True, exist_ok=True)
    table = [fixed_block(L, n, W, a.out) for n, W in FIXED] + [be_block(L, G, a.out)]
    (a.out / "proof" / "blocks.json").write_text(json.dumps(table, indent=1) + "\n")
    for t in table:
        print(json.dumps(t))
