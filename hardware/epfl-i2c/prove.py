"""Prove a LUT netlist equal to the suite's circuit, one output at a time, without ABC.

usage: python3 prove.py REF.blif OURS.blif

For every output, U is the set of inputs that either netlist can reach from that output.
Neither side can depend on an input outside U, so comparing the two on all 2^|U| settings of U
decides that output completely. In the i2c netlists an output reaches at most 25 inputs.

It also prints the shape of OURS read straight from the file: nodes by number of inputs, and the
number of levels both when every node counts and when only nodes with two or more inputs count.

Needs Python 3 and numpy.
"""
import sys
import numpy as np


def read_blif(path):
    text = open(path).read().replace("\\\n", " ")
    inputs, outputs, nodes = [], [], {}
    cur = None
    for line in text.splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        if line.startswith(".inputs"):
            inputs += line.split()[1:]
            cur = None
        elif line.startswith(".outputs"):
            outputs += line.split()[1:]
            cur = None
        elif line.startswith(".names"):
            sig = line.split()[1:]
            cur = sig[-1]
            assert cur not in nodes, "node defined twice: " + cur
            nodes[cur] = (sig[:-1], [])
        elif line.startswith("."):
            cur = None
        else:
            parts = line.split()
            if len(nodes[cur][0]) == 0:
                nodes[cur][1].append(("", parts[0]))
            else:
                nodes[cur][1].append((parts[0], parts[1]))
    return inputs, outputs, nodes


def cone(nodes, inputs, root):
    """inputs reached from root, and the nodes of the cone in evaluation order"""
    iset = set(inputs)
    seen, pis, order = set(), set(), []
    stack = [(root, False)]
    while stack:
        x, done = stack.pop()
        if done:
            order.append(x)
            continue
        if x in seen:
            continue
        seen.add(x)
        if x in iset:
            pis.add(x)
            continue
        assert x in nodes, "undriven signal: " + x
        stack.append((x, True))
        for y in nodes[x][0]:
            stack.append((y, False))
    return pis, order


def evaluate(fanins, rows, vals, size):
    if not fanins:
        return np.full(size, any(v == "1" for _, v in rows), dtype=bool)
    on = [p for p, v in rows if v == "1"]
    off = [p for p, v in rows if v == "0"]
    assert not (on and off), "cover mixes 0 and 1 rows"
    acc = np.zeros(size, dtype=bool)
    for pat in (on or off):
        c = np.ones(size, dtype=bool)
        for ch, x in zip(pat, fanins):
            if ch == "1":
                c = np.logical_and(c, vals[x])
            elif ch == "0":
                c = np.logical_and(c, np.logical_not(vals[x]))
        acc = np.logical_or(acc, c)
    return np.logical_not(acc) if off else acc


def levels(nodes, inputs, outputs, least):
    lev = {x: 0 for x in inputs}
    for o in outputs:
        for x in cone(nodes, inputs, o)[1]:
            fi = nodes[x][0]
            lev[x] = (max(lev[y] for y in fi) if fi else 0) + (1 if len(fi) >= least else 0)
    return max(lev[o] for o in outputs)


def main():
    ref_in, ref_out, ref = read_blif(sys.argv[1])
    our_in, our_out, our = read_blif(sys.argv[2])
    assert sorted(ref_in) == sorted(our_in), "input names differ"
    assert sorted(ref_out) == sorted(our_out), "output names differ"
    by = {}
    for x, (fi, _) in our.items():
        assert len(fi) <= 6, "more than 6 inputs: " + x
        by[len(fi)] = by.get(len(fi), 0) + 1
    print("nodes by number of inputs:", dict(sorted(by.items())))
    print("LUTs with 2 or more inputs:", sum(v for k, v in by.items() if k >= 2))
    print("levels, every node counted:", levels(our, our_in, our_out, 1))
    print("levels, nodes with 2 or more inputs counted:", levels(our, our_in, our_out, 2))
    bad, widest, total = 0, 0, 0
    for o in ref_out:
        pr, order_r = cone(ref, ref_in, o)
        po, order_o = cone(our, our_in, o)
        U = sorted(pr | po)
        assert len(U) <= 26, (o, len(U))
        widest = max(widest, len(U))
        size = 1 << len(U)
        total += size
        r = np.arange(size, dtype=np.int64)
        base = {x: ((r >> k) % 2).astype(bool) for k, x in enumerate(U)}
        vr = dict(base)
        for x in order_r:
            vr[x] = evaluate(ref[x][0], ref[x][1], vr, size)
        vo = dict(base)
        for x in order_o:
            vo[x] = evaluate(our[x][0], our[x][1], vo, size)
        d = int(np.sum(vr[o] != vo[o]))
        if d:
            bad += 1
            print("MISMATCH", o, d, "of", size)
    print(f"{len(ref_out)} outputs, each compared on every setting of the inputs it can reach "
          f"(at most {widest} inputs, {total} settings in all): {bad} outputs differ")
    print("PROVED EQUAL" if bad == 0 else "NOT EQUAL")
    sys.exit(0 if bad == 0 else 1)


if __name__ == "__main__":
    main()
