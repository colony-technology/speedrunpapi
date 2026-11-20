#!/usr/bin/env python3
"""Assemble a 2-level LUT-6 netlist for one EPFL function from tl2.py SAT results.

usage: assemble_tl2.py TT.npy REF.blif OUT.blif RESULT_DIR [--out N ...]

For every output with a SAT result in RESULT_DIR (hard_o<out>_k*.json, status SAT,
verified), emits m first-level .names nodes (deduped by support+table) and one top node.
Verifies the result against TT.npy on all rows before writing.
"""
import glob, json, os, sys

import numpy as np


def emit_names(fh, inputs, table, out):
    # BLIF .names: first listed input is the MSB of the row index; tl2 tables are LSB-first,
    # so list the inputs reversed.
    rev = list(reversed(inputs))
    fh.write(".names " + " ".join(rev) + " " + out + "\n")
    for a, v in enumerate(table):
        if v:
            bits = "".join(str((a >> (len(rev) - 1 - p)) & 1) for p in range(len(rev)))
            fh.write(bits + " 1\n")


def main():
    tt_path, ref_path, out_path, rdir = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    Y = np.load(tt_path)
    outs = sorted(int(o) for o in Y.shape[0] and range(Y.shape[0]))
    ref = open(ref_path).read().replace("\\\n", " ").splitlines()
    ref_in = [t for l in ref if l.startswith(".inputs") for t in l.split()[1:]]
    ref_out = [t for l in ref if l.startswith(".outputs") for t in l.split()[1:]]
    n = len(ref_in)
    assert Y.shape[1] == (1 << n), (Y.shape, n)

    results = {}
    for p in sorted(glob.glob(os.path.join(rdir, "*o*_*.json"))):
        d = json.load(open(p))
        if d.get("status") == "SAT" and d.get("verified"):
            results[d["out"]] = d
    missing = [o for o in outs if o not in results]
    if missing:
        print("no verified SAT result for outputs:", missing)
        sys.exit(2)

    nodes = {}  # (sup tuple, g tuple) -> node name
    order = []

    def intern(sup, g):
        key = (tuple(sup), tuple(g))
        if key not in nodes:
            name = f"g{len(nodes)}"
            nodes[key] = name
            order.append((name, sup, g))
        return nodes[key]

    top_of = {}
    for o in outs:
        d = results[o]
        names = [intern(d["supports"][i], d["g"][i]) for i in range(d["m"])]
        top_of[o] = (names, d["top"])

    with open(out_path, "w") as fh:
        fh.write(".model top\n")
        fh.write(".inputs " + " ".join(ref_in) + "\n")
        fh.write(".outputs " + " ".join(ref_out) + "\n")
        for name, sup, g in order:
            emit_names(fh, [ref_in[k] for k in sup], g, name)
        for o in outs:
            names, top = top_of[o]
            emit_names(fh, names, top, ref_out[o])
        fh.write(".end\n")

    # verify against the truth table on every row
    vals = {}
    for name, sup, g in order:
        sup = list(sup); g = list(g)
        col = np.zeros(1 << n, dtype=np.int64)
        for r in range(1 << n):
            a = 0
            for j, k in enumerate(sup):
                a |= ((r >> k) & 1) << j
            col[r] = g[a]
        vals[name] = col
    for o in outs:
        names, top = top_of[o]
        code = np.zeros(1 << n, dtype=np.int64)
        for i, nm in enumerate(names):
            code |= vals[nm] << i
        out = np.array(top, dtype=np.int64)[code]
        assert np.all(out == Y[o]), f"output {o} differs on some input"
    print(f"verified against {tt_path} on all {1 << n} inputs: every output matches")


if __name__ == "__main__":
    main()
