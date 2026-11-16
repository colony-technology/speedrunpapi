"""Steps and looks per token from the census of count_ops.py, as markdown tables.

usage: python -I report_census.py census.json > tables.md

Each census row (function, line, parent, parent's line, grandparent, operation, count) goes to one category by the
rules below; a row no rule matches stops the script. One count per value per operation:
  step   a product that enters a sum (a multiply-add); the adds that join those products are not counted again
  look   a value read for its magnitude: rounding, rescale or split (right shifts; left shifts by an amount read from
         the data; low-bit masks), clamp (clip, min or max against a bound), comparison (each value entering a max,
         argmax, range test or selection), bit length, division, square root, table read
  apart  adds, constant multiplies and other multiplies: steps, listed separately
  not counted: selects by a mask, data movement, run-time checks (asserts), instrumentation (clamp counters, peaks),
         and the operations inside another count (the add of the half in a rounding, an absolute value read by the
         max that follows it, the integer correction steps inside a square root)
"""
import json
import sys

CENSUS_OLD = False                                             # set by main() from the census

MM, OTHER = "multiply-adds in the matrix products", "multiply-adds elsewhere"
ADD, CMUL, MUL = "adds and subtractions", "multiplies by a constant (shifts left by a fixed amount, negation)", \
    "other multiplies (norm weight, SiLU(gate) times up)"
ROUND, CLAMP, CMP = "roundings, rescales and splits", "clamps", "comparisons"
BITS, DIV, SQRT, TABLE = "bit lengths", "divisions", "square roots", "table reads"
SEL, MOVE, CHECK, INSTR, INNER = ("selects by a mask", "data movement (concatenate, gather and scatter)",
                                  "run-time checks (asserts)", "instrumentation (clamp counters, peaks, held p)",
                                  "inside another count")
STEPS, APART, LOOKS, NOT = [MM, OTHER], [ADD, CMUL, MUL], [ROUND, CLAMP, CMP, BITS, DIV, SQRT, TABLE], \
    [SEL, MOVE, CHECK, INSTR, INNER]


def rule(fn, line, parent, op):
    if line.startswith("assert") or "assert " in line:
        return CHECK
    if op in ("concatenate", "take_along_axis", "put_along_axis"):
        return MOVE
    if op == "where":
        return SEL
    if op == "matmul":
        return MM
    if fn == "harness" and op == "argmax":
        return CMP
    if fn == "clamp":
        return CLAMP if op == "clip" else INSTR
    if "p_held" in line or "int(over.sum())" in line:
        return INSTR
    if fn == "rshift_round":
        return ROUND if op == "right_shift" else INNER
    if fn == "fdiv" and op == "floor_divide":
        return DIV
    if fn == "isqrt":
        return SQRT if op == "sqrt" else INNER
    if fn == "bitlen" or op == "frexp":
        return BITS
    if fn in ("exp", "silu"):
        if op == "gather":
            return TABLE
        if op == "multiply":
            return OTHER                                        # E[k] (256 - r) + E[k + 1] r
        if op == "add" and "SILU_LO" in line:
            return ADD                                          # u = x + 16
        if op == "add":
            return [(ADD, 0.5), (INNER, 0.5)]                   # k + 1, and the add joining the two products
        if op == "subtract":
            return ADD                                          # 256 - r
        if op in ("minimum", "clip"):
            return CLAMP
        if op in ("right_shift", "bitwise_and") and ("k = " in line or "r = " in line or "k, r" in line):
            return ROUND                                        # the index t >> 8 and the fraction t & 255
        if op == "right_shift":
            return ROUND                                        # the interpolation >> 8
        if op in ("greater_equal", "less"):
            return CMP                                          # SiLU's range tests
        if op == "bitwise_and":
            return INNER                                        # joining two range tests
    if fn == "rope_tables" and op == "gather":
        return TABLE                                            # cos and sin, once per forward pass
    if fn == "cache_entry" and op in ("right_shift", "bitwise_and"):
        return ROUND                                            # v >> 15, v & (2^15 - 1), once per position
    if fn == "rope":
        if op == "gather":
            return TABLE
        if op == "multiply":
            return OTHER
        if op in ("add", "subtract"):
            return INNER
    if fn == "rms":
        if op == "gather":
            return TABLE                                        # eps by the shift
        if op == "maximum.reduce":
            return CMP
        if op == "absolute":
            return INNER
        if op == "maximum":
            return CLAMP
        if op == "multiply" and "xs * xs" in line:
            return OTHER
        if op == "add.reduce":
            return INNER                                        # the sum of the squares
        if op == "multiply":
            return MUL
        if op in ("add", "subtract"):
            return ADD
        if op in ("right_shift", "left_shift"):
            return ROUND                                        # x >> sh; x << (16 - sh), by an amount read
    if fn == "attention":
        if op == "maximum.reduce":
            return CMP
        if op == "add.reduce":
            return ADD
        if op == "left_shift" and ("e << A" in line or "B16 - 1" in line):
            return CMUL
        if op == "left_shift":
            return ROUND                                        # 2^(sh_q + sh_k)
        if op in ("maximum", "minimum"):
            return CLAMP
        if op in ("right_shift", "bitwise_and"):
            return ROUND                                        # (m - s) >> 19; v >> 15, v & (2^15 - 1)
        if op in ("subtract", "add"):
            return ADD
    if fn == "forward":
        if op == "gather":
            return TABLE                                        # the embedding row
        if op == "multiply":
            return MUL
        if op == "add":
            return ADD
    if fn == "linear" and op == "add":
        return ADD                                              # sum(): 0 + the first chunk, then the chunks
    if fn == "block16":
        if op in ("maximum.reduce", "greater"):
            return CMP                                          # max |x| per vector; the over-check
        if op in ("absolute", "logical_or.reduce"):
            return INNER
        if op == "maximum":
            return CLAMP
        if op in ("subtract", "add"):
            return ADD
    if fn == "peel_index":
        if op == "argpartition":
            return CMP
        if op in ("absolute", "add"):
            return INNER
        if op in ("left_shift", "negative"):
            return CMUL
    if fn == "product":
        if op == "multiply":
            return MM                                           # the peeled terms x w16
        if op == "add":
            return INNER
        if op == "left_shift":
            return ROUND                                        # 2^sh
    return None


def site(fn, line, parent, pline, gp, op):
    """A short name for where a row's work is done."""
    if fn == "harness":
        return "greedy argmax over the vocabulary"
    if fn == "mm16":
        if parent == "product":
            return "16-bit products: %s" % ("logits" if gp == "logits" else "q, k, v, o, gate, up, down")
        return "16-bit products: %s" % ("scores q.k" if "S = mm16" in pline else "context p.vh, p.vl")
    if fn == "linear" and op == "matmul":
        return "products: q, k, v, o, gate, up, down"
    if fn == "logits" and op == "matmul":
        return "products: logits"
    if fn == "attention" and op == "matmul":
        return "products: %s" % ("scores q.k" if "qc @" in line else "context p.v")
    where = {"rshift_round": {"linear": "linear outputs", "logits": "logits", "rms": "norm output", "rope": "rotary",
                              "attention": "context", "forward": "SiLU(gate) times up"},
             "clamp": {"linear": "product inputs", "forward": "residual, gate, up", "logits": "logits input",
                       "attention": "q, and k and v over the whole cache" if CENSUS_OLD else "q",
                       "cache_entry": "k, v as they enter the cache"},
             "fdiv": {"rms": "norm: mean square, x / r", "attention": "softmax p"},
             "shift_round": {"block16": "16-bit inputs (x16, and again where the over-check needs it)",
                             "product": "product outputs, 2^-g", "attention": "p at 2^-15"}}
    if fn in where:
        return "%s: %s" % (fn, where[fn].get(parent, parent))
    if fn in ("block16", "bitlen"):
        if parent == "product" or gp == "product":
            return "block16: product inputs"
        if parent == "cache_entry" or gp == "cache_entry":
            return "block16: k as it enters the cache"
        return "block16: %s" % ("q, and k over the whole cache" if CENSUS_OLD else "q")
    if fn == "rope_tables":
        return "rotary"
    if fn == "cache_entry":
        return "cache: v split as it enters the cache"
    if fn == "peel_index":
        return "peel: the two largest |x|"
    if fn == "exp":
        return "exp table"
    if fn == "silu":
        return "SiLU table"
    if fn == "isqrt":
        return "norm: integer square root"
    if fn == "rope":
        return "rotary"
    if fn == "rms":
        return "norm"
    if fn == "product":
        return "product: peeled terms, 2^sh"
    if fn == "forward":
        return {"gather": "embedding row", "multiply": "SiLU(gate) times up", "add": "residual adds"}.get(op, fn)
    if fn == "attention":
        if "vh, vl" in line:
            return "attention: v split over the whole cache"
        return "attention: softmax"
    if fn == "linear":
        return "linear: chunk sums (from 0)"
    return fn


def categorize(rows):
    tot, sites, sr = {}, {}, {}
    for fn, line, parent, pline, gp, op, n in rows:
        if fn == "shift_round" and not line.startswith("assert"):
            sr.setdefault((parent, pline, gp), {})[op] = sr.setdefault((parent, pline, gp), {}).get(op, 0) + n
            continue
        c = rule(fn, line, parent, op)
        if c is None:
            raise SystemExit("unmapped: %r" % ((fn, parent, op, n, line),))
        for cc, f in (c if isinstance(c, list) else [(c, 1.0)]):
            tot[cc] = tot.get(cc, 0) + n * f
            s = site(fn, line, parent, pline, gp, op)
            sites[(cc, s)] = sites.get((cc, s), 0) + n * f
    for (parent, pline, gp), d in sr.items():                # (v + (2^k >> 1)) >> k: one rounding per value
        k = d.get("left_shift", 0)                           # the constants 2^k >> 1, one per shift value
        s = site("shift_round", "", parent, pline, gp, "right_shift")
        tot[ROUND] = tot.get(ROUND, 0) + d["right_shift"] - k
        sites[(ROUND, s)] = sites.get((ROUND, s), 0) + d["right_shift"] - k
        tot[INNER] = tot.get(INNER, 0) + d.get("add", 0) + 2 * k
    return tot, sites


def main():
    global CENSUS_OLD
    d = json.load(open(sys.argv[1]))
    CENSUS_OLD = not any(r[0] == "cache_entry" for r in d["exact last"])     # the code before cache_entry
    W = [("exact", "last", 1), ("exact", "prefill", 64), ("exact16", "last", 1), ("exact16", "prefill", 64)]
    R = {}
    for kind, w, div in W + [("exact", "last32", 1), ("exact16", "last32", 1)]:
        tot, sites = categorize(d["%s %s" % (kind, w)])
        R[(kind, w)] = ({k: v / div for k, v in tot.items()}, {k: v / div for k, v in sites.items()})
    
    f = lambda v: ("{:,.0f}".format(v) if abs(v - round(v)) < 1e-9 else "{:,.2f}".format(v)) if v else ""
    head = "| per token | exact, last position | exact, prefill average | exact-16, last position | " \
           "exact-16, prefill average |\n| --- | ---: | ---: | ---: | ---: |"
    out = ["## By type", "", head]
    tl = {}
    for group, cats in (("steps", STEPS), ("apart", APART), ("looks", LOOKS), ("not counted", NOT)):
        for c in cats:
            out.append("| %s: %s | %s |" % (group, c, " | ".join(f(R[(k, w)][0].get(c, 0)) for k, w, _ in W)))
        if group in ("steps", "looks"):
            vals = [sum(R[(k, w)][0].get(c, 0) for c in cats) for k, w, _ in W]
            tl[group] = vals
            out.append("| **%s, total** | %s |" % (group, " | ".join("**%s**" % f(v) for v in vals)))
    out.append("| **steps per look** | %s |" % " | ".join("**%.1f**" % (s / l) for s, l in zip(tl["steps"], tl["looks"])))
    out += ["", "## Looks and steps by site", "", head]
    for c in STEPS + LOOKS:
        names = sorted({s for k, w, _ in W for (cc, s) in R[(k, w)][1] if cc == c},
                       key=lambda s: -max(R[(k, w)][1].get((c, s), 0) for k, w, _ in W))
        for s in names:
            out.append("| %s: %s | %s |" % (c, s, " | ".join(f(R[(k, w)][1].get((c, s), 0)) for k, w, _ in W)))
    out += ["", "## Context length: decode step at context 32 and 64", "",
            "| per token, decode step | exact, fixed | exact, per key read | exact-16, fixed | exact-16, per key read |",
            "| --- | ---: | ---: | ---: | ---: |"]
    for c in STEPS + APART + LOOKS:
        cells = []
        for kind in ("exact", "exact16"):
            a, b = R[(kind, "last32")][0].get(c, 0), R[(kind, "last")][0].get(c, 0)
            slope = (b - a) / 32
            cells += [f(b - 64 * slope), f(slope)]
        out.append("| %s | %s |" % (c, " | ".join(cells)))
    for group, cats in (("steps", STEPS), ("looks", LOOKS)):
        cells = []
        for kind in ("exact", "exact16"):
            a = sum(R[(kind, "last32")][0].get(c, 0) for c in cats)
            b = sum(R[(kind, "last")][0].get(c, 0) for c in cats)
            cells += ["**%s**" % f(b - 64 * (b - a) / 32), "**%s**" % f((b - a) / 32)]
        out.append("| **%s, total** | %s |" % (group, " | ".join(cells)))
    print("\n".join(out))


if __name__ == "__main__":
    main()
