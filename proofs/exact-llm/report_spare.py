"""Steps and looks per token of exact-16 with and without the spare rows and the looks checked (spare_row.Checked16),
from count_spare.py's census, as markdown tables.

usage: python -I report_spare.py count-spare.json > tables.md

Rows of exact_llm's frames go by report_census.py's rules. Rows of spare_row's frames (named "S.<function>") that
copy Exact16's code go by the same rules under the function's own name; the work of the checks goes by the rules
below, in report_census's categories:
  steps  the multiply-adds of the spare rows: x . c1 and x . c2 on the input side, j T_j on the output side, and the
         same for the scores (q against the two sums of the keys) and the context (p against the sums of each v)
  apart  the plain sums of the outputs (sum T_j), the running sums of the keys, the arithmetic of the brackets
  looks  each comparison of a check: the two spare rows of each row (two per row), a bracket (one range test per
         value), a look made twice (its second evaluation is counted where the first is, and the comparison here);
         the left shifts by an amount read from the data (2^sh x16 . c, y 2^k, 2^b)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import report_census as RC  # noqa: E402

MM, ADD, CMUL, MUL = RC.MM, RC.ADD, RC.CMUL, RC.MUL
ROUND, CLAMP, CMP = RC.ROUND, RC.CLAMP, RC.CMP
MOVE, INNER = RC.MOVE, RC.INNER


def spare_rule(fn, line, parent, op):
    if fn == "vector_sum":
        return ADD                                             # an input vector's sum: made, and again at the read
    if fn == "two_sums":
        if "s1 = " in line:
            return ADD
        return MM if op == "multiply" else INNER
    if fn == "spare_product":
        return {"matmul": MM, "multiply": MM, "left_shift": ROUND, "gather": MOVE}.get(op, INNER)
    if fn == "spare_dot":
        return MM if op == "multiply" else INNER
    if fn == "in_range":
        return CMP if op == "less_equal" else INNER
    if op == "equal":
        return CMP
    if op in ("invert", "logical_or.reduce", "bitwise_and"):
        return INNER
    if "in_range(" in line:                                   # the bounds of a bracket
        return {"multiply": MUL, "add": ADD, "subtract": ADD, "left_shift": ROUND}.get(op, INNER)
    if fn == "_round":
        return INNER if "half = " in line else ROUND           # 2^k >> 1 from k; y 2^k
    if fn == "bitlen" and op == "left_shift":
        return ROUND                                           # 2^b
    if fn == "key_sums" and op == "add":
        return ADD                                             # the running sums
    if fn == "cache_entry":
        if op == "clip":
            return CLAMP                                       # v clamped again, for the split put together
        if op == "left_shift" and "B16 - 1" in line:
            return CMUL
        if op == "add" and "B16 - 1" in line:
            return ADD
    return None


CHECK_FNS = {"two_sums", "spare_product", "spare_dot", "in_range", "rows_check", "check", "twice", "key_sums",
             "_round", "bitlen", "fdiv", "isqrt", "peel_index"}


def rule(fn, line, parent, op):
    p = parent[2:] if parent.startswith("S.") else parent
    if fn.startswith("S."):
        f = fn[2:]
        r = spare_rule(f, line, p, op)
        return r if r is not None else ORIG_RULE(f, line, p, op)
    return ORIG_RULE(fn, line, p, op)


def site(fn, line, parent, pline, gp, op):
    f = fn[2:] if fn.startswith("S.") else fn
    p = parent[2:] if parent.startswith("S.") else parent
    g = gp[2:] if gp.startswith("S.") else gp
    if f == "vector_sum":
        return "input sums: %s" % ("formed again by the product that reads the vector (a row of ones)"
                                   if p == "read_input" else "made where the vector is made")
    if f == "read_input" or (f == "check" and p == "read_input"):
        return "input sums: compare"
    if f == "bitlen" and p == "rms":
        return "norm: bit length of the largest |x|"
    if f == "cache_entry" and fn.startswith("S.") and op == "equal":
        return "v split put together"
    if f == "mm16" and p == "attention" and parent.startswith("S."):
        return "16-bit products: %s" % ("scores q.k" if "scores q.k" in pline else "context p.vh, p.vl")
    looks = {"_round": "rounding", "bitlen": "bit length", "fdiv": "division", "isqrt": "square root"}
    if f == "twice" or (f == "check" and p == "twice"):
        return "made twice: compare (%s)" % (g if f == "check" else p)
    if f == "rows_check" or (f == "check" and p == "rows_check"):
        return "spare rows: compare"
    if (f == "check" and p in looks) or (f == "in_range" and p in looks):
        return "brackets: %s" % looks[p]
    if f in looks and "in_range(" in line or f in ("_round", "bitlen") and fn.startswith("S."):
        if spare_rule(f, line, p, op) is not None:
            return "brackets: %s" % looks[f]
    if fn.startswith("S.") and spare_rule(f, line, p, op) is not None:
        if f == "two_sums":
            return "spare rows: %s" % {"product": "product outputs, the two sums",
                                       "attention": "scores and context outputs, the two sums",
                                       "cache_entry": "the two sums of each v, as it enters the cache",
                                       "key_sums": "the two sums of the keys, kept beside the cache"}.get(p, p)
        if f in ("spare_product", "spare_dot"):
            return "spare rows: %s" % ("product inputs . c1, c2" if f == "spare_product"
                                       else "q . key sums, p . v sums")
        if f == "check" or op == "equal":
            return "checks: compare (%s)" % (p or f)
        if f == "key_sums":
            return "spare rows: the two sums of the keys, kept beside the cache"
        if f == "cache_entry":
            return "v split put together"
        return "checks: %s" % f
    return ORIG_SITE(f, line, p, pline, g, op)


def categorize(rows):
    """report_census.categorize with these rules; its shift_round grouping keys on the parent, so the parents of
    exact_llm's shift_round rows get their plain names."""
    fixed = []
    for fn, line, parent, pline, gp, op, n in rows:
        if fn == "shift_round":
            parent = parent[2:] if parent.startswith("S.") else parent
            gp = gp[2:] if gp.startswith("S.") else gp
        fixed.append((fn, line, parent, pline, gp, op, n))
    return RC.categorize(fixed)


ORIG_RULE, ORIG_SITE = RC.rule, RC.site
RC.rule, RC.site = rule, site                        # report_census.categorize looks them up by name
d = json.load(open(sys.argv[1]))
W = [("exact16", "last", 1), ("checked16", "last", 1), ("exact16", "prefill", 64), ("checked16", "prefill", 64)]
R = {}
for kind, w, div in W + [("exact16", "last32", 1), ("checked16", "last32", 1)]:
    tot, sites = categorize(d["%s %s" % (kind, w)])
    R[(kind, w)] = ({k: v / div for k, v in tot.items()}, {k: v / div for k, v in sites.items()})

f = lambda v: ("{:,.0f}".format(v) if abs(v - round(v)) < 1e-9 else "{:,.2f}".format(v)) if v else ""
pct = lambda a, b: "%+.2f%%" % (100.0 * (b - a) / a) if a else ""
out = ["## By type, per token (SmolLM2-135M, route f64)", "",
       "| per token | exact-16, last position (context 64) | with the checks | added | exact-16, prefill average | "
       "with the checks | added |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
tl = {}
for group, cats in (("steps", RC.STEPS), ("apart", RC.APART), ("looks", RC.LOOKS), ("not counted", RC.NOT)):
    for c in cats:
        v = [R[(k, w)][0].get(c, 0) for k, w, _ in W]
        out.append("| %s: %s | %s | %s | %s | %s | %s | %s |" % (group, c, f(v[0]), f(v[1]), f(v[1] - v[0]),
                                                                 f(v[2]), f(v[3]), f(v[3] - v[2])))
    if group in ("steps", "apart", "looks"):
        v = [sum(R[(k, w)][0].get(c, 0) for c in cats) for k, w, _ in W]
        tl[group] = v
        out.append("| **%s, total** | **%s** | **%s** | **%s (%s)** | **%s** | **%s** | **%s (%s)** |" % (
            group, f(v[0]), f(v[1]), f(v[1] - v[0]), pct(v[0], v[1]), f(v[2]), f(v[3]), f(v[3] - v[2]),
            pct(v[2], v[3])))
spl = [tl["steps"][i] / tl["looks"][i] for i in range(4)]
out.append("| **steps per look** | **%.1f** | **%.1f** | | **%.1f** | **%.1f** | |" % tuple(spl))
out += ["", "## What the checks add, by site (last position, context 64)", "",
        "| category: site | added per token |", "| --- | ---: |"]
a, b = R[("exact16", "last")][1], R[("checked16", "last")][1]
for key in sorted(set(a) | set(b), key=lambda k: (k[0], -(b.get(k, 0) - a.get(k, 0)))):
    dv = b.get(key, 0) - a.get(key, 0)
    if abs(dv) > 1e-9:
        out.append("| %s: %s | %s |" % (key[0], key[1], f(dv)))
out += ["", "## Decode step: fixed and per key read", "",
        "| per token, decode step | exact-16, fixed | per key read | with the checks, fixed | per key read |",
        "| --- | ---: | ---: | ---: | ---: |"]
for group, cats in (("steps", RC.STEPS), ("apart", RC.APART), ("looks", RC.LOOKS)):
    cells = []
    for kind in ("exact16", "checked16"):
        x = sum(R[(kind, "last32")][0].get(c, 0) for c in cats)
        y = sum(R[(kind, "last")][0].get(c, 0) for c in cats)
        cells += [f(y - 64 * (y - x) / 32), f((y - x) / 32)]
    out.append("| %s | %s |" % (group, " | ".join(cells)))
print("\n".join(out))
