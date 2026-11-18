#!/usr/bin/env python3
"""Two-level LUT-K decomposition of one Boolean function, self-contained (numpy + python-sat).

f(x) = TOP(g_1(S_1), ..., g_m(S_m)),  |S_i| <= K,  m <= K.   A g_i may be a bare input.

Encoding ("support invariance"): o[i][r] is the value of g_i on row r, sel[i][k] says
input k is in S_i, and o[i][r] == o[i][r ^ (1<<k)] unless sel[i][k]. TOP is a 2^m table.
Symmetry breaking: g_i(row 0) = 0, support masks in lexicographic order, every support
padded to exactly K inputs (when n >= K), every relevant input used at least once.
An UNSAT answer is a proof that no such two-level network exists for this m and K.

Usage: tl2.py TT.npy OUT_INDEX [--m 6] [--K 6] [--solver cadical153] [--seed 0]
               [--budget SEC] [--save PATH.json] [--weights w0,w1,...]
TT.npy: uint8 array (outputs, 2^n), column r = input assignment r (input k = bit k of r).
--weights: per-input weight (an input standing for a bundle of w raw inputs); the sum of
           selected weights per g_i must stay <= K.
"""
import json, os, random, sys, threading, time
import numpy as np
from pysat.solvers import Solver
from pysat.card import CardEnc, EncType


def build(tt, n, m=6, K=6, weights=None, exact=True):
    R = 1 << n
    nv = [0]
    def new():
        nv[0] += 1; return nv[0]
    sel = [[new() for _ in range(n)] for _ in range(m)]
    o = [[new() for _ in range(R)] for _ in range(m)]
    T = [new() for _ in range(1 << m)]
    cl = []
    w = list(weights) if weights is not None else [1] * n
    # functional support
    relevant = []
    for k in range(n):
        b = 1 << k
        idx = np.arange(R)
        lo = idx[(idx & b) == 0]
        if np.any(tt[lo] != tt[lo | b]):
            relevant.append(k)
    for i in range(m):
        lits = []
        for k in range(n):
            lits += [sel[i][k]] * w[k]
        if sum(w) > K:
            enc = CardEnc.atmost(lits=lits, bound=K, top_id=nv[0], encoding=EncType.seqcounter)
            nv[0] = max(nv[0], enc.nv); cl += enc.clauses
            if exact and all(x == 1 for x in w):
                enc = CardEnc.atleast(lits=lits, bound=K, top_id=nv[0], encoding=EncType.seqcounter)
                nv[0] = max(nv[0], enc.nv); cl += enc.clauses
        for k in range(n):
            b = 1 << k
            for r in range(R):
                if r & b: continue
                cl.append([sel[i][k], -o[i][r], o[i][r | b]])
                cl.append([sel[i][k], o[i][r], -o[i][r | b]])
        cl.append([-o[i][0]])
    for k in relevant:
        cl.append([sel[i][k] for i in range(m)])
    # lexicographic order of support masks: sel[i] <= sel[i+1]
    for i in range(m - 1):
        a, b = sel[i], sel[i + 1]
        e = [new() for _ in range(n + 1)]
        cl.append([e[0]])
        for k in range(n):
            cl.append([-e[k], -a[k], b[k]])
            cl.append([e[k + 1], -e[k], a[k], b[k]])
            cl.append([e[k + 1], -e[k], -a[k], -b[k]])
            cl.append([-e[k + 1], e[k]])
            cl.append([-e[k + 1], -a[k], b[k]])
            cl.append([-e[k + 1], a[k], -b[k]])
    for r in range(R):
        fr = int(tt[r])
        for a in range(1 << m):
            c = [(-o[i][r] if (a >> i) & 1 else o[i][r]) for i in range(m)]
            c.append(T[a] if fr else -T[a])
            cl.append(c)
    return cl, nv[0], sel, o, T


def shuffle(cl, nvars, seed):
    if not seed:
        return cl, None
    rng = random.Random(seed)
    perm = list(range(1, nvars + 1)); rng.shuffle(perm)
    mp = [0] + perm
    out = [[(mp[l] if l > 0 else -mp[-l]) for l in c] for c in cl]
    for c in out: rng.shuffle(c)
    rng.shuffle(out)
    return out, mp


def solve(tt, n, m=6, K=6, solver="cadical153", seed=0, budget=None, weights=None, exact=True):
    cl, nvars, sel, o, T = build(tt, n, m, K, weights, exact)
    cl2, mp = shuffle(cl, nvars, seed)
    s = Solver(name=solver, bootstrap_with=cl2)
    timer = None
    if budget:
        timer = threading.Timer(budget, s.interrupt); timer.start()
    t0 = time.time()
    try:
        try:
            r = s.solve_limited(expect_interrupt=True)
        except NotImplementedError:
            r = s.solve()
    finally:
        if timer: timer.cancel()
    dt = time.time() - t0
    if r is None:
        s.delete(); return dict(status="UNKNOWN", time=dt)
    if r is False:
        s.delete(); return dict(status="UNSAT", time=dt)
    model = s.get_model(); s.delete()
    pos = set(l for l in model if l > 0)
    def val(v):
        return (mp[v] if mp else v) in pos
    R = 1 << n
    sup = [[k for k in range(n) if val(sel[i][k])] for i in range(m)]
    ov = np.array([[1 if val(o[i][r]) else 0 for r in range(R)] for i in range(m)], dtype=np.uint8)
    Tt = [1 if val(T[a]) else 0 for a in range(1 << m)]
    # verify and compress each g_i to a table over its own support
    code = np.zeros(R, dtype=np.int64)
    for i in range(m): code |= ov[i].astype(np.int64) << i
    used = np.zeros(1 << m, bool); used[np.unique(code)] = True
    ok = bool(np.all(np.array(Tt)[code] == tt))
    gt = []
    for i in range(m):
        mask = sum(1 << k for k in sup[i])
        idx = np.arange(R)
        ok = ok and bool(np.all(ov[i] == ov[i][idx & mask]))
        tab = []
        for a in range(1 << len(sup[i])):
            r = sum(((a >> j) & 1) << k for j, k in enumerate(sup[i]))
            tab.append(int(ov[i][r]))
        gt.append(tab)
    return dict(status="SAT", time=dt, verified=ok, supports=sup, g=gt, top=Tt, m=m, K=K, n=n)


def decode(pos, sel, o, T, tt, n, m, K, dt=0.0):
    """pos: set of true variable ids -> solution dict (verified against tt)"""
    R = 1 << n
    sup = [[k for k in range(n) if sel[i][k] in pos] for i in range(m)]
    ov = np.array([[1 if o[i][r] in pos else 0 for r in range(R)] for i in range(m)], dtype=np.uint8)
    Tt = [1 if T[a] in pos else 0 for a in range(1 << m)]
    code = np.zeros(R, dtype=np.int64)
    for i in range(m): code |= ov[i].astype(np.int64) << i
    ok = bool(np.all(np.array(Tt)[code] == tt))
    gt = []
    for i in range(m):
        mask = sum(1 << k for k in sup[i])
        idx = np.arange(R)
        ok = ok and bool(np.all(ov[i] == ov[i][idx & mask]))
        gt.append([int(ov[i][sum(((a >> j) & 1) << k for j, k in enumerate(sup[i]))]) for a in range(1 << len(sup[i]))])
    return dict(status="SAT", time=dt, verified=ok, supports=sup, g=gt, top=Tt, m=m, K=K, n=n)


def run_kissat(tt, n, m=6, K=6, weights=None, kissat="kissat", seed=0, budget=None, workdir=".", tag="x", extra=()):
    """solve with an external kissat binary; killable; returns solution dict"""
    import subprocess
    cl, nvars, sel, o, T = build(tt, n, m, K, weights)
    cnf = os.path.join(workdir, f"{tag}_s{seed}.cnf")
    with open(cnf, "w") as f:
        f.write(f"p cnf {nvars} {len(cl)}\n")
        f.write("\n".join(" ".join(map(str, c)) + " 0" for c in cl)); f.write("\n")
    cmd = [kissat, "-q", f"--seed={seed}"] + list(extra) + [cnf]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=budget)
        outp = r.stdout
    except subprocess.TimeoutExpired:
        os.unlink(cnf); return dict(status="UNKNOWN", time=time.time() - t0)
    os.unlink(cnf)
    dt = time.time() - t0
    if "s UNSATISFIABLE" in outp: return dict(status="UNSAT", time=dt)
    if "s SATISFIABLE" not in outp: return dict(status="UNKNOWN", time=dt, note=outp[-200:])
    pos = set()
    for line in outp.splitlines():
        if line.startswith("v "):
            for tok in line.split()[1:]:
                v = int(tok)
                if v > 0: pos.add(v)
    return decode(pos, sel, o, T, tt, n, m, K, dt)


if __name__ == "__main__":
    a = sys.argv[1:]
    path, out = a[0], int(a[1])
    opt = dict(m=6, K=6, solver="cadical153", seed=0, budget=None, save=None, weights=None)
    i = 2
    while i < len(a):
        k = a[i].lstrip("-"); v = a[i + 1]; i += 2
        opt[k] = v
    Y = np.load(path)
    tt = Y[out].astype(np.uint8)
    n = int(round(np.log2(tt.shape[0])))
    wts = [int(x) for x in opt["weights"].split(",")] if opt["weights"] else None
    if opt.get("kissat"):
        ex = tuple(x for x in (opt.get("kopts") or "").split(",") if x)
        res = run_kissat(tt, n, int(opt["m"]), int(opt["K"]), wts, opt["kissat"], int(opt["seed"]),
                         float(opt["budget"]) if opt["budget"] else None,
                         os.path.dirname(os.path.abspath(opt["save"])) if opt["save"] else ".",
                         f"k_{os.path.basename(path)}_{out}", ex)
        opt["solver"] = "kissat" + ("/" + opt["kopts"] if opt.get("kopts") else "")
    else:
        res = solve(tt, n, int(opt["m"]), int(opt["K"]), opt["solver"], int(opt["seed"]),
                    float(opt["budget"]) if opt["budget"] else None, wts)
    res.update(out=out, solver=opt["solver"], seed=int(opt["seed"]), file=os.path.basename(path))
    if opt["save"] and res["status"] != "UNKNOWN":
        tmp = opt["save"] + f".tmp{os.getpid()}"
        json.dump(res, open(tmp, "w")); os.replace(tmp, opt["save"])
    brief = {k: v for k, v in res.items() if k not in ("g", "top")}
    print(json.dumps(brief), flush=True)
