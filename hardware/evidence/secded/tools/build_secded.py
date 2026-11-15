"""Builds the SEC-DED blocks of one code from proof/H_N_K.json (n code bits, k data bits, r = n - k check bits).

    python3 tools/build_secded.py --H proof/H_72_64.json --linear PATH/speedrunpapi/hardware/linear --yosys PATH/yosys --out . --work DIR

H = [P | I] (r x n): rows over the n code bits, bits 0..k-1 data, k..n-1 check.  For (72, 64), N = 72:
  colony_secdedN_enc   d[k-1:0] -> c[r-1:0],  c = P d                    linear compiler, LUT-6 network
  colony_secdedN_syn   r[n-1:0] -> s[r-1:0],  s = H r                    linear compiler, LUT-6 network
  colony_secdedN_cor   r[k-1:0], s[r-1:0] -> q[k-1:0], corrected, uncorrectable
        q[j] = r[j] ^ (s == column j);  corrected = s has odd weight;  uncorrectable = s != 0 and of even weight
        (the Hsiao flags: every column has odd weight, every sum of two columns even weight)
        RTL written here from the column table, mapped to LUT-6 by Yosys (synth -lut 6)
Each block: block/NAME.v (plain), block/NAME_lut6.v (LUT primitives), proof/NAME.blif, proof/NAME.json.
Baselines for C4: the same three functions as plain RTL (^(x & mask), ==), through Yosys synth_xilinx.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


def parity(n):
    return sum(1 << r for r in range(1 << n) if bin(r).count("1") & 1)


def linear_block(L, name, rows, nin, inp, outp, out, code):
    best = None
    for depth in (None, 3, 2):
        try:
            c = L.compile_linear(rows, nin, 6, depth)
        except ValueError:
            continue
        if best is None or (c[2], len(c[0])) < (best[2], len(best[0])):
            best = c
    nodes, outs, lev = best
    ins = ["%s[%d]" % (inp, i) for i in range(nin)]
    ons = ["%s[%d]" % (outp, i) for i in range(len(rows))]
    data = L.blif(nodes, outs, ["x[%d]" % i for i in range(nin)], ["y[%d]" % i for i in range(len(rows))], name)   # checker names
    (out / "proof" / (name + ".blif")).write_bytes(data)
    cert = {"schema": "colony.lut-linear.v1", "kind": "matrix", "inputs": nin, "rows": ["%x" % m for m in rows], "k": 6,
            "lut_count": len(nodes), "levels": lev, "netlist_digest": "sha256:" + hashlib.sha256(data).hexdigest()}
    (out / "proof" / (name + ".json")).write_text(json.dumps(cert, sort_keys=True) + "\n")
    nm = lambda v: ins[v] if v < nin else "n%d" % (v - nin)
    port = "module %s (input wire [%d:0] %s, output wire [%d:0] %s);\n" % ("%s", nin - 1, inp, len(rows) - 1, outp)
    head = "// %s: %s = rows of H over %s.  %d LUT-6, %d levels.  Matrix: OpenTitan prim_secded_%s (Hsiao).\n" % (name, outp, inp, len(nodes), lev, code)
    plain, prim = [head + port % name], [head + port % (name + "_lut6")]
    for j, x in enumerate(nodes):
        plain.append("  (* keep = \"true\" *) wire n%d = %s;\n" % (j, " ^ ".join(nm(v) for v in x)))
        k = len(x)
        prim.append("  wire n%d; LUT%d #(.INIT(%d'h%x)) u%d (.O(n%d), %s);\n" % (j, k, 1 << k, parity(k), j, j, ", ".join(".I%d(%s)" % (q, nm(v)) for q, v in enumerate(x))))
    for i, o in enumerate(outs):
        line = "  assign %s[%d] = %s;\n" % (outp, i, "1'b0" if o is None else nm(o))
        plain.append(line)
        prim.append(line)
    (out / "block" / (name + ".v")).write_text("".join(plain) + "endmodule\n")
    (out / "block" / (name + "_lut6.v")).write_text("".join(prim) + "endmodule\n")
    return {"name": name, "lut6": len(nodes), "levels": lev}


def corrector_rtl(cols, name, k, r, code):
    V = ["// %s: q[j] = r[j] ^ (s == column j); corrected = odd weight of s; uncorrectable = s != 0, even weight.\n" % name,
         "// Columns of H (OpenTitan prim_secded_%s, Hsiao): data %s; check bits are the unit vectors.\n" % (code, " ".join("%02x" % c for c in cols[:k])),
         "module %s (input wire [%d:0] r, input wire [%d:0] s, output wire [%d:0] q, output wire corrected, output wire uncorrectable);\n" % (name, k - 1, r - 1, k - 1)]
    for j in range(k):
        V.append("  assign q[%d] = r[%d] ^ (s == %d'h%02x);\n" % (j, j, r, cols[j]))
    V.append("  assign corrected = ^s;\n")
    V.append("  assign uncorrectable = (s != %d'h0) & ~(^s);\nendmodule\n" % r)
    return "".join(V)


def parse_blif(text):
    ins, outs, luts, cur = [], [], [], None
    for line in text.replace("\\\n", " ").splitlines():
        t = line.split()
        if not t or t[0].startswith("#"):
            continue
        if t[0] == ".inputs":
            ins += t[1:]
        elif t[0] == ".outputs":
            outs += t[1:]
        elif t[0] == ".names":
            cur = (t[-1], t[1:-1], [])
            luts.append(cur)
        elif t[0] in (".model", ".end"):
            cur = None
        else:
            cur[2].append(t[0] if len(cur[1]) else "")
    return ins, outs, luts


def truth(cubes, n):
    tt = 0
    for r in range(1 << n):
        if any(all(c == "-" or int(c) == ((r >> q) & 1) for q, c in enumerate(cube)) for cube in cubes):
            tt |= 1 << r
    return tt


def canonical(ins, outs, luts):
    drv = {o: (src, truth(c, len(src)) if src else (1 if c else 0)) for o, src, c in luts}
    const = {o: tt & 1 for o, (src, tt) in drv.items() if not src}
    order, seen = [], set(ins)

    def visit(v):
        if v in seen or v in const:
            return
        for u in drv[v][0]:
            visit(u)
        seen.add(v)
        order.append(v)
    for o in outs:
        visit(o)
    name, net = {}, []
    for v in order:
        src, tt = drv[v]
        live = [q for q, u in enumerate(src) if u not in const]
        t2 = 0
        for r in range(1 << len(live)):
            full = sum(((r >> t) & 1) << q for t, q in enumerate(live)) | sum(const[u] << q for q, u in enumerate(src) if u in const)
            t2 |= ((tt >> full) & 1) << r
        srcs = [name.get(src[q], src[q]) for q in live]
        if v in outs and len(srcs) == 1 and t2 == 2:
            net.append((v, srcs, 2, True))
            continue
        name[v] = "n%d" % len(name)
        net.append((name[v], srcs, t2, False))
        if v in outs:
            net.append((v, [name[v]], 2, True))
    for o in outs:
        if o in const:
            net.append((o, [], const[o], True))
    return [x for x in net if not x[3]] + [x for x in net if x[3]]


def mapped_block(yosys, name, rtl, out, work, k, r):
    (out / "block" / (name + ".v")).write_text(rtl)
    raw = work / (name + "_yosys.blif")
    run = subprocess.run([yosys, "-q", "-p", "read_verilog %s; synth -top %s -lut 6; opt_clean -purge; rename %s %s; write_blif %s" % (
        out / "block" / (name + ".v"), name, name, name, raw)], capture_output=True, text=True)
    if run.returncode:
        raise SystemExit(run.stderr[-1500:])
    ins, outs, luts = parse_blif(raw.read_text())
    net = canonical(ins, outs, luts)
    B = [".model " + name, ".inputs " + " ".join(ins), ".outputs " + " ".join(outs)]
    for n, src, tt, buf in net:
        B.append(".names " + " ".join(src + [n]))
        B += [("".join(str((rr >> q) & 1) for q in range(len(src))) + " 1").strip() for rr in range(1 << len(src)) if (tt >> rr) & 1]
    text = "\n".join(B) + "\n.end\n"
    (out / "proof" / (name + ".blif")).write_text(text)
    lev = {v: 0 for v in ins}
    V = ["// %s, LUT-6 network mapped by Yosys from block/%s.v.\n" % (name, name),
         "module %s_lut6 (input wire [%d:0] r, input wire [%d:0] s, output wire [%d:0] q, output wire corrected, output wire uncorrectable);\n" % (name, k - 1, r - 1, k - 1)]
    count = 0
    for n, src, tt, buf in net:
        if buf:
            V.append("  assign %s = %s;\n" % (n, src[0] if src else "1'b%d" % tt))
            lev[n] = lev[src[0]] if src else 0
            continue
        k = len(src)
        V.append("  wire %s; LUT%d #(.INIT(%d'h%0*x)) u_%s (.O(%s), %s);\n" % (n, k, 1 << k, max(1, (1 << k) // 4), tt, n, n, ", ".join(".I%d(%s)" % (q, v) for q, v in enumerate(src))))
        lev[n] = 1 + max(lev[v] for v in src)
        count += 1
    (out / "block" / (name + "_lut6.v")).write_text("".join(V) + "endmodule\n")
    levels = max(lev[o] for o in outs)
    cert = {"schema": "colony.secded-corrector.v1", "lut_count": count, "levels": levels,
            "netlist_digest": "sha256:" + hashlib.sha256(text.encode()).hexdigest()}
    (out / "proof" / (name + ".json")).write_text(json.dumps(cert, sort_keys=True) + "\n")
    return {"name": name, "lut6": count, "levels": levels}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--H", type=Path, required=True)
    ap.add_argument("--linear", type=Path, required=True)
    ap.add_argument("--yosys", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--work", type=Path, required=True)
    a = ap.parse_args()
    sys.path.insert(0, str(a.linear.resolve()))
    import linear_compiler as L
    out, work = a.out.resolve(), a.work.resolve()
    for sub in ("block", "proof"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    Hj = json.loads(a.H.read_text())
    rows = [int(x, 16) for x in Hj["rows"]]
    cols = [int(x, 16) for x in Hj["columns"]]
    n, k, r = Hj["n"], Hj["k"], Hj["r"]
    code, base = "%d_%d" % (n, k), "colony_secded%d" % n
    P = [m & ((1 << k) - 1) for m in rows]
    res = [linear_block(L, base + "_enc", P, k, "d", "c", out, code),
           linear_block(L, base + "_syn", rows, n, "r", "s", out, code),
           mapped_block(a.yosys, base + "_cor", corrector_rtl(cols, base + "_cor", k, r, code), out, work, k, r)]
    (out / "proof" / ("blocks_%s.json" % code)).write_text(json.dumps(res, indent=1) + "\n")
    for x in res:
        print(json.dumps(x))
