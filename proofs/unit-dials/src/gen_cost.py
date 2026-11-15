#!/usr/bin/env python3
"""What a unit set costs in lookup tables. Writes Verilog for one moduli set:

  chadd_<m>.v, chmul_<m>.v  one channel: (a + b) mod m and (a * b) mod m, as full tables (a case over every pair of
                            residues: one table per output bit); a, b of ceil(log2 m) bits
  back.v                    reading back to binary: x = (sum_i c_i r_i) mod M with c_i the reconstruction constants
                            (unit set: c_i = e_i M/m_i, e_i = +-1; otherwise c_i = (M/m_i)(inverse of M/m_i mod m_i)),
                            then the reduction: the sum s lies in a known range [L, U]; x = s - jM for the one j with
                            0 <= s - jM < M, chosen by comparing s with the multiples of M in range (all in parallel)
  binadd.v, binmul.v        the yardstick: a b-bit adder and a b x b multiplier (low b bits), b = ceil(log2 M)
and spec.json (the set, M, b, the constants, the range of s, the number of multiples compared).
Inputs to every module are taken as valid residues (r_i < m_i); outputs for other inputs are unconstrained.
usage: gen_cost.py OUTDIR m1 m2 m3 ...
"""
import json
import os
import sys
from math import gcd


def bits(n):
    return max(1, (n - 1).bit_length())


def main():
    out = sys.argv[1]
    ms = [int(a) for a in sys.argv[2:]]
    os.makedirs(out, exist_ok=True)
    M = 1
    for m in ms:
        M *= m
    assert all(gcd(a, b) == 1 for i, a in enumerate(ms) for b in ms[i + 1:])
    consts, signs = [], []
    for m in ms:
        r = (M // m) % m
        if r == 1 % m:
            consts.append(M // m); signs.append(1)
        elif r == m - 1:
            consts.append(-(M // m)); signs.append(-1)
        else:
            consts.append((M // m) * pow(M // m, -1, m) % M); signs.append(0)
    unit = all(s != 0 for s in signs)
    L = sum(min(0, c * (m - 1)) for c, m in zip(consts, ms))
    U = sum(max(0, c * (m - 1)) for c, m in zip(consts, ms))
    jlo, jhi = L // M, U // M
    b = bits(M)
    sw = max(abs(L), abs(U)).bit_length() + 2
    # channels
    for m in ms:
        k = bits(m)
        for op, f in (("add", lambda x, y: (x + y) % m), ("mul", lambda x, y: (x * y) % m)):
            L_ = ["module ch%s_%d(input [%d:0] a, input [%d:0] b, output reg [%d:0] y);" % (op, m, k - 1, k - 1, k - 1),
                  "  always @* begin", "    case ({a, b})"]
            for x in range(m):
                for y in range(m):
                    L_.append("      %d'd%d: y = %d'd%d;" % (2 * k, (x << k) | y, k, f(x, y)))
            L_ += ["      default: y = %d'bx;" % k, "    endcase", "  end", "endmodule"]
            open(os.path.join(out, "ch%s_%d.v" % (op, m)), "w").write("\n".join(L_) + "\n")
    # reading back
    ins = ", ".join("input [%d:0] r%d" % (bits(m) - 1, i) for i, m in enumerate(ms))
    L_ = ["module back(%s, output reg [%d:0] x);" % (ins, b - 1)]
    terms = " + ".join("(%s%d'sd%d * $signed({1'b0, r%d}))" % ("-" if c < 0 else "", sw, abs(c), i) for i, c in enumerate(consts))
    L_.append("  wire signed [%d:0] s = %s;" % (sw - 1, terms))
    L_.append("  always @* begin")
    L_.append("    x = %d'bx;" % b)
    for j in range(jlo, jhi + 1):
        lo, hi = j * M, (j + 1) * M
        L_.append("    if (s >= %d'sd0 + (%d) && s < %d'sd0 + (%d)) x = s - (%d);" % (sw, lo, sw, hi, j * M))
    L_ += ["  end", "endmodule"]
    open(os.path.join(out, "back.v"), "w").write("\n".join(L_) + "\n")
    # yardsticks
    open(os.path.join(out, "binadd.v"), "w").write(
        "module binadd(input [%d:0] a, input [%d:0] b, output [%d:0] y); assign y = a + b; endmodule\n" % (b - 1, b - 1, b - 1))
    open(os.path.join(out, "binmul.v"), "w").write(
        "module binmul(input [%d:0] a, input [%d:0] b, output [%d:0] y); assign y = a * b; endmodule\n" % (b - 1, b - 1, b - 1))
    spec = {"moduli": ms, "M": M, "log2M": round(__import__("math").log2(M), 3), "b": b, "unit": unit,
            "signs": signs, "constants": consts, "sum_range": [L, U], "multiples_compared": jhi - jlo + 1,
            "sum_width": sw}
    json.dump(spec, open(os.path.join(out, "spec.json"), "w"), indent=1)
    print(json.dumps(spec))


if __name__ == "__main__":
    main()
