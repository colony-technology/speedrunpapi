# Minimal AIGER (binary .aig and ascii .aag) reader and exhaustive simulator,
# plus a BLIF (.names only, combinational) reader and simulator.
import numpy as np

def _dec(data, pos):
    x = 0; sh = 0
    while True:
        b = data[pos]; pos += 1
        x |= (b & 0x7f) << sh
        if b & 0x80 == 0:
            return x, pos
        sh += 7

def read_aig(path):
    data = open(path, "rb").read()
    nl = data.index(b"\n")
    hdr = data[:nl].split()
    M, I, L, O, A = map(int, hdr[1:6])
    assert L == 0
    pos = nl + 1
    outs = []
    for _ in range(O):
        e = data.index(b"\n", pos); outs.append(int(data[pos:e])); pos = e + 1
    ands = []
    for k in range(A):
        lhs = 2 * (I + 1 + k)
        d0, pos = _dec(data, pos); d1, pos = _dec(data, pos)
        r0 = lhs - d0; r1 = r0 - d1
        ands.append((lhs, r0, r1))
    # symbols
    rest = data[pos:].decode(errors="replace").split("\n")
    inames = [f"i{k}" for k in range(I)]; onames = [f"o{k}" for k in range(O)]
    for line in rest:
        if not line or line[0] == "c":
            if line[:1] == "c": break
            continue
        t, name = line.split(" ", 1)
        if t[0] == "i": inames[int(t[1:])] = name
        elif t[0] == "o": onames[int(t[1:])] = name
    return dict(I=I, O=O, ands=ands, outs=outs, inames=inames, onames=onames)

def input_patterns(n):
    """matrix n x 2^n of bools; column x has bit k = input k"""
    x = np.arange(1 << n, dtype=np.int64)
    return np.array([(x >> k) & 1 for k in range(n)], dtype=bool)

def sim_aig(a, X):
    I = a["I"]; vals = {0: np.zeros(X.shape[1], bool)}
    for k in range(I):
        vals[k + 1] = X[k]
    def lit(l):
        v = vals[l >> 1]
        return ~v if l & 1 else v
    for lhs, r0, r1 in a["ands"]:
        vals[lhs >> 1] = lit(r0) & lit(r1)
    return np.array([lit(o) for o in a["outs"]])

def read_blif(path):
    lines = open(path).read().replace("\\\n", " ").split("\n")
    ins, outs, nodes = [], [], []
    cur = None
    for raw in lines:
        line = raw.split("#")[0].strip()
        if not line: continue
        tok = line.split()
        if tok[0] == ".inputs": ins += tok[1:]; cur = None
        elif tok[0] == ".outputs": outs += tok[1:]; cur = None
        elif tok[0] == ".names":
            cur = [tok[1:-1], tok[-1], []]; nodes.append(cur)
        elif tok[0].startswith("."): cur = None
        else:
            if len(tok) == 1: cur[2].append(("", tok[0]))
            else: cur[2].append((tok[0], tok[1]))
    return dict(ins=ins, outs=outs, nodes=nodes)

def sim_blif(b, X, order=None):
    """order: list of input names giving the row of X for each; default b['ins']"""
    names = order if order is not None else b["ins"]
    vals = {n: X[k] for k, n in enumerate(names)}
    W = X.shape[1]
    pending = list(b["nodes"])
    while pending:
        nxt = []
        for fi, o, cubes in pending:
            if not all(f in vals for f in fi):
                nxt.append((fi, o, cubes)); continue
            on = None; acc = np.zeros(W, bool); pol = "1"
            for c, v in cubes:
                pol = v
                t = np.ones(W, bool)
                for ch, f in zip(c, fi):
                    if ch == "1": t &= vals[f]
                    elif ch == "0": t &= ~vals[f]
                acc |= t
            vals[o] = acc if pol == "1" else ~acc
            if not cubes: vals[o] = np.zeros(W, bool)
        assert len(nxt) < len(pending), "combinational loop or missing signal"
        pending = nxt
    return np.array([vals[o] for o in b["outs"]])

def lut_stats(b):
    """table convention: count nodes with >=2 fanins; levels over such nodes only"""
    drv = {o: fi for fi, o, _ in b["nodes"]}
    lev = {}
    def L(n):
        if n in lev: return lev[n]
        if n not in drv: lev[n] = 0; return 0
        fi = drv[n]
        d = max([L(f) for f in fi], default=0)
        lev[n] = d + (1 if len(fi) >= 2 else 0)
        return lev[n]
    import sys; sys.setrecursionlimit(100000)
    count = sum(1 for fi, o, _ in b["nodes"] if len(fi) >= 2)
    depth = max([L(o) for o in b["outs"]], default=0)
    kmax = max([len(fi) for fi, _, _ in b["nodes"]], default=0)
    return count, depth, kmax
