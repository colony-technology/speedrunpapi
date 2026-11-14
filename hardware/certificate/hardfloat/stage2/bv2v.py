#!/usr/bin/env python3
"""bv2v: a bvfsm description at a fixed word length N, emitted as a Verilog module.

The module has the description's inputs (vectors at their widths, scalars as 1-bit ports), one output port
per description output, and an output `valid`, the conjunction of the description's assumptions.
Every node becomes one wire of exactly its bvfsm width, assigned from wires of its operands, so the
semantics are bvfsm's (bitwise operations on zero-extended operands, + and - modulo the width, shifts
within the width, scalars zero-extended), with no Verilog context-width effect crossing nodes:
each operand is first zero-extended or truncated to the node's width by an explicit concatenation.
usage: bv2v.py DESC.bv N MODULE OUT.v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bvfsm  # noqa: E402


def emit(d, N, mod):
    W = {}
    for n in d.nodes:
        W[n.id] = 1 if n.scalar else N + n.woff
    name = {n.id: "n%d" % n.id for n in d.nodes}

    def ext(x, w):
        """operand node x as a w-bit expression (zero-extended or truncated)."""
        wx = W[x.id]
        if wx == w:
            return name[x.id]
        if wx < w:
            return "{%d'd0, %s}" % (w - wx, name[x.id])
        return "%s[%d:0]" % (name[x.id], w - 1)

    ports, body = [], []
    for nm, n in d.inputs_vec:
        ports.append("input [%d:0] %s" % (W[n.id] - 1, nm))
    for nm, n in d.inputs_sc:
        ports.append("input %s" % nm)
    for nm, n in d.outputs:
        ports.append("output [%d:0] %s" % (W[n.id] - 1, nm) if not n.scalar else "output %s" % nm)
    ports.append("output valid")
    for n in d.nodes:
        w = W[n.id]
        k = n.kind
        a = n.args
        decl = "wire [%d:0] %s" % (w - 1, name[n.id]) if w > 1 or not n.scalar else "wire %s" % name[n.id]
        if not n.scalar and w == 1:
            decl = "wire [0:0] %s" % name[n.id]
        if k == "in":
            e = n.name
        elif k == "insc":
            e = n.name
        elif k == "const":
            e = "1'b%d" % n.k
        elif k == "not":
            e = "~%s" % ext(a[0], w)
        elif k in ("and", "or", "xor"):
            op = {"and": "&", "or": "|", "xor": "^"}[k]
            e = "%s %s %s" % (ext(a[0], w), op, ext(a[1], w))
        elif k in ("add", "sub"):
            e = "%s %s %s" % (ext(a[0], w), "+" if k == "add" else "-", ext(a[1], w))
        elif k == "shr":
            e = "%s >> %d" % (ext(a[0], w), n.k)
        elif k == "shl":
            e = "%s << %d" % (ext(a[0], w), n.k)
        elif k == "sel":
            e = "%s ? %s : %s" % (name[a[0].id], ext(a[1], w), ext(a[2], w))
        elif k in ("trunc", "ext"):
            e = ext(a[0], w)
        elif k == "preor":
            bits = ["1'b0"] + ["|%s[%d:0]" % (name[a[0].id], j - 1) for j in range(1, w)]
            e = "{" + ", ".join(reversed(bits)) + "}"
        elif k == "orr":
            e = "|%s" % name[a[0].id]
        elif k == "bit":
            e = "%s[%d]" % (name[a[0].id], n.k) if n.k < W[a[0].id] else "1'b0"
        elif k == "top":
            j = N - 1 - n.k
            e = "%s[%d]" % (name[a[0].id], j) if 0 <= j < W[a[0].id] else "1'b0"
        elif k == "eq":
            e = "%s == %s" % (ext(a[0], N), ext(a[1], N))
        elif k == "lt":
            e = "%s < %s" % (ext(a[0], N), ext(a[1], N))
        elif k == "cout":
            e = "(%s + %s) >> %d" % (ext(a[0], N + 1), ext(a[1], N + 1), N)
            body.append("  wire [%d:0] c%d = %s;" % (N, n.id, e))
            e = "c%d[%d]" % (n.id, N)
        else:
            raise ValueError(k)
        body.append("  %s = %s;" % (decl, e))
    conds = ["%s" % name[n.id] for n in d.assumes_sc]
    for n in d.thermo:
        w = W[n.id]
        conds.append("((%s & (%s + %d'd1)) == %d'd0)" % (ext(n, w + 1), ext(n, w + 1), w + 1, w + 1))
    for n in d.onehot:
        w = W[n.id]
        conds.append("((%s != 0) && ((%s & (%s - %d'd1)) == %d'd0))" % (name[n.id], name[n.id], name[n.id], w, w))
    body.append("  assign valid = %s;" % (" && ".join(conds) if conds else "1'b1"))
    for nm, n in d.outputs:
        body.append("  assign %s = %s;" % (nm, name[n.id]))
    return "// emitted by bv2v.py from %s at N = %d\nmodule %s (\n  %s\n);\n%s\nendmodule\n" % (
        os.path.basename(d.path), N, mod, ",\n  ".join(ports), "\n".join(body))


def main():
    d = bvfsm.Desc(sys.argv[1])
    N = int(sys.argv[2])
    open(sys.argv[4], "w").write(emit(d, N, sys.argv[3]))


if __name__ == "__main__":
    main()
