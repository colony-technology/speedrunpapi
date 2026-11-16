"""Independent exhaustive check of LUT netlists against the EPFL sin benchmark.

usage: python -I check_depth.py BENCH.blif TABLES.json NET.blif [NET.blif ...]

BENCH.blif  arithmetic/sin.blif of the EPFL suite (commit 82d8cc6), evaluated directly.
TABLES.json tables C0, C1, K of the formula on our sin size page (second comparison only).
NET.blif    netlists to check. Each is read as generic BLIF (.names covers, any polarity); nothing about how it was
            built is assumed. Inputs and outputs are matched to the benchmark by name.

The benchmark is simulated bit-parallel, 2^18 input words per pass. Each netlist node is evaluated as a truth table
over its own support (the raw inputs it depends on structurally): the fanin tables are broadcast onto the node's
support and indexed into the node's cover. Every node therefore holds its value on all 2^|support| points, and an
output is compared with the benchmark on all 2^24 input words. A node's table is dropped after its last reader.

Prints, per netlist: nodes, maximum fanin, depth, inputs that differ from the benchmark (any output bit), and the
outputs that differ. Exit status 1 if any netlist differs. Shares no code with the generator.
"""
import json
import sys
import time

import numpy as np

NIN = 24


def parse(path):
    """-> (inputs, outputs, nodes) where nodes maps signal -> (fanin names, truth table int, k)."""
    ins, outs, nodes = [], [], {}
    cur = None
    pend = ""
    rows = []

    def close():
        if cur is None:
            return
        name, fan = cur
        k = len(fan)
        full = (1 << (1 << k)) - 1
        if k not in mask_cache:
            masks = []
            for i in range(k):
                m = 0
                for r in range(1 << k):
                    if (r >> i) & 1:
                        m |= 1 << r
                masks.append(m)
            mask_cache[k] = masks
        masks = mask_cache[k]
        on, pol = 0, None
        for cube, o in rows:
            assert pol is None or pol == o, "mixed cover polarity in " + name
            pol = o
            t = full
            assert len(cube) == k
            for i, ch in enumerate(cube):
                if ch == "1":
                    t &= masks[i]
                elif ch == "0":
                    t &= full ^ masks[i]
                else:
                    assert ch == "-"
            on |= t
        tt = on if pol in (None, "1") else full ^ on
        assert name not in nodes, "signal defined twice: " + name
        nodes[name] = (fan, tt, k)

    mask_cache = {}
    with open(path) as f:
        for line in f:
            line = line.split("#", 1)[0].rstrip("\n")
            if line.endswith("\\"):
                pend += line[:-1] + " "
                continue
            line = pend + line
            pend = ""
            t = line.split()
            if not t:
                continue
            if t[0].startswith("."):
                close()
                cur, rows = None, []
                if t[0] == ".inputs":
                    ins += t[1:]
                elif t[0] == ".outputs":
                    outs += t[1:]
                elif t[0] == ".names":
                    cur = (t[-1], t[1:-1])
                elif t[0] in (".model", ".end"):
                    pass
                else:
                    raise SystemExit("unsupported BLIF line: " + line)
            else:
                assert cur is not None
                if len(cur[1]) == 0:
                    rows.append(("", t[0]))
                else:
                    rows.append((t[0], t[1]))
        close()
    return ins, outs, nodes


def topo(ins, outs, nodes):
    """nodes reachable from the outputs, fanins first; plus the reader count of each signal."""
    order, state = [], {}
    for o in outs:
        stack = [(o, 0)]
        while stack:
            s, i = stack.pop()
            if s in ins or state.get(s) == 2:
                continue
            assert s in nodes, "undriven signal " + s
            fan = nodes[s][0]
            if i == 0:
                assert state.get(s) != 1, "combinational loop at " + s
                state[s] = 1
            if i < len(fan):
                stack.append((s, i + 1))
                stack.append((fan[i], 0))
            else:
                state[s] = 2
                order.append(s)
    readers = {}
    for s in order:
        for x in nodes[s][0]:
            readers[x] = readers.get(x, 0) + 1
    for o in outs:
        readers[o] = readers.get(o, 0) + 1
    return order, readers


def bench_table(path):
    """the benchmark's 25-bit output word on all 2^24 inputs, by bit-parallel simulation."""
    ins, outs, nodes = parse(path)
    assert len(ins) == NIN
    order, _ = topo(ins, outs, nodes)
    LOWB = 18
    words = 1 << (LOWB - 6)
    ones = np.uint64(0xFFFFFFFFFFFFFFFF)
    pat = []
    for i in range(6):
        w = 0
        for b in range(64):
            if (b >> i) & 1:
                w |= 1 << b
        pat.append(np.full(words, w, dtype=np.uint64))
    widx = np.arange(words)
    for i in range(6, LOWB):
        pat.append(np.where((widx >> (i - 6)) & 1, ones, np.uint64(0)).astype(np.uint64))
    table = np.zeros(1 << NIN, dtype=np.uint32)
    for h in range(1 << (NIN - LOWB)):
        env = {}
        for i, nm in enumerate(ins):
            if i < LOWB:
                env[nm] = pat[i]
            else:
                env[nm] = np.full(words, ones if (h >> (i - LOWB)) & 1 else 0, dtype=np.uint64)
        for s in order:
            fan, tt, k = nodes[s]
            acc = np.zeros(words, dtype=np.uint64)
            for r in range(1 << k):
                if (tt >> r) & 1:
                    term = np.full(words, ones, dtype=np.uint64)
                    for i, x in enumerate(fan):
                        term &= env[x] if (r >> i) & 1 else ~env[x]
                    acc |= term
            env[s] = acc
        block = np.zeros(1 << LOWB, dtype=np.uint32)
        for kk, o in enumerate(outs):
            bits = np.unpackbits(env[o].view(np.uint8), bitorder="little")
            block |= bits.astype(np.uint32) << np.uint32(kk)
        table[h << LOWB:(h + 1) << LOWB] = block
    return ins, outs, table


def formula_table(tables):
    """README formula of our size page, written out again here."""
    C0 = np.array(tables["C0"], dtype=np.int64)
    C1 = np.array(tables["C1"], dtype=np.int64)
    K = np.array(tables["K"], dtype=np.int64)
    a = np.arange(1 << NIN, dtype=np.int64)
    q = a >> 22
    b = a & ((1 << 22) - 1)
    y = np.where((q & 1) == 1, b, (-b) & ((1 << 22) - 1))
    A = y >> 15
    Z = y & ((1 << 15) - 1)
    core = (C0[A] * (1 << 14) + (C1[A] - ((K[A] * (Z >> 3)) >> 12)) * Z + (1 << 16)) >> 17
    core = np.where(((q & 1) == 0) & (b == 0), 1 << 23, core)
    out = np.where((q == 0) | (q == 3), core, -core)
    return (out & ((1 << 25) - 1)).astype(np.uint32)


def check_net(path, ref_ins, ref_outs, ref, form):
    t0 = time.time()
    ins, outs, nodes = parse(path)
    assert ins == ref_ins, "inputs differ from the benchmark's names or order"
    assert outs == ref_outs, "outputs differ from the benchmark's names or order"
    pos = {nm: i for i, nm in enumerate(ins)}
    order, readers = topo(ins, outs, nodes)
    val = {}                                      # signal -> (sorted support list, uint8 array shape (2,)*n)
    for nm in ins:
        val[nm] = ([pos[nm]], np.array([0, 1], dtype=np.uint8))
    depth = {nm: 0 for nm in ins}
    outset = {}
    for kk, o in enumerate(outs):
        outset.setdefault(o, []).append(kk)
    diff = np.zeros(1 << NIN, dtype=bool)
    diff_f = np.zeros(1 << NIN, dtype=bool)
    bad_outputs = []
    maxk = 0

    def expand(sup_f, arr, sup_n):
        sf = set(sup_f)
        shape = tuple(2 if v in sf else 1 for v in reversed(sup_n))
        return arr.reshape(shape)

    def finish(o, sup, arr):
        full = np.broadcast_to(expand(sup, arr, list(range(NIN))), (2,) * NIN).reshape(-1)
        for kk in outset[o]:
            want = ((ref >> np.uint32(kk)) & 1).astype(np.uint8)
            d = full != want
            if d.any():
                bad_outputs.append(kk)
            np.logical_or(diff, d, out=diff)
            want = ((form >> np.uint32(kk)) & 1).astype(np.uint8)
            np.logical_or(diff_f, full != want, out=diff_f)

    for nm in ins:
        if nm in outset:
            finish(nm, *val[nm])
    for s in order:
        fan, tt, k = nodes[s]
        maxk = max(maxk, k)
        depth[s] = 1 + max([depth[x] for x in fan], default=0)
        sup = sorted(set(v for x in fan for v in val[x][0]))
        n = len(sup)
        if k == 0:
            arr = np.array(tt & 1, dtype=np.uint8)
        else:
            dt = np.uint8 if k <= 8 else np.uint32
            idx = np.zeros((1,) * n, dtype=dt)
            for i, x in enumerate(fan):
                sf, af = val[x]
                idx = idx + (expand(sf, af, sup).astype(dt) << dt(i))
            idx = np.broadcast_to(idx, (2,) * n)
            ttarr = np.array([(tt >> r) & 1 for r in range(1 << k)], dtype=np.uint8)
            arr = ttarr[idx]
        val[s] = (sup, np.ascontiguousarray(arr))
        for x in fan:
            readers[x] -= 1
            if readers[x] == 0 and x not in ins:
                del val[x]
        if s in outset:
            finish(s, *val[s])
            readers[s] -= len(outset[s])
            if readers[s] == 0:
                del val[s]
    nd = int(diff.sum())
    lev = max(depth[o] for o in outs)
    print("%s: %d nodes, at most %d inputs each, depth %d; %d of %d inputs differ from the benchmark "
          "(%d from the formula); outputs differing: %s  (%.0f s)"
          % (path, len(order), maxk, lev, nd, 1 << NIN, int(diff_f.sum()),
             sorted(set(bad_outputs)) or "none", time.time() - t0), flush=True)
    return nd


def main():
    bench, tables, nets = sys.argv[1], sys.argv[2], sys.argv[3:]
    t0 = time.time()
    ref_ins, ref_outs, ref = bench_table(bench)
    print("benchmark %s simulated on %d inputs (%.0f s)" % (bench, 1 << NIN, time.time() - t0), flush=True)
    f = formula_table(json.load(open(tables)))
    print("formula: %d of %d inputs differ from the benchmark" % (int((f != ref).sum()), 1 << NIN), flush=True)
    bad = 0
    for p in nets:
        bad += check_net(p, ref_ins, ref_outs, ref, f) != 0
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
