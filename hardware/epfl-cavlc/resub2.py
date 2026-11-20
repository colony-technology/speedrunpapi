#!/usr/bin/env python3
"""Global resubstitution for circuits too wide to enumerate (i2c, priority, router).

Same moves as resub.py, but signals are compared on a sample of input patterns, so a move can be
wrong. Every move is therefore checked on the whole netlist with ABC cec against the suite
circuit before it is kept; a refused move gives back a counterexample, which joins the sample.
The netlist on disk is equal to the suite circuit after every kept move.

Usage: resub2.py NAME START.blif OUT.blif [--levels L] [--time SEC] [--seed S] [--iters N]
NAME picks the suite reference (epfl-suite/random_control/NAME.blif) and the pattern family.
"""
import os, random, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from resub import Net

HERE = os.path.dirname(os.path.abspath(__file__))
SUITE = os.environ.get("EPFL_SUITE", "random_control")
ABC = os.environ.get("ABC", "yosys-abc")


class Restart(Exception):
    pass


def patterns(name, n, seed):
    rng = np.random.default_rng(seed)
    cols = [np.zeros(n, bool), np.ones(n, bool)]
    for i in range(n):
        c = np.zeros(n, bool); c[i] = True; cols.append(c)
        c = np.ones(n, bool); c[i] = False; cols.append(c)
    for d in (0.02, 0.05, 0.1, 0.2, 0.35, 0.5, 0.65, 0.8, 0.9, 0.95, 0.98):
        cols += list((rng.random((600, n)) < d))
    if name == "router":                                   # two 30-bit numbers: equal, close, small, one zero
        def num(v, lo):
            c = np.zeros(n, bool)
            for i in range(30): c[lo + i] = (v >> i) & 1
            return c
        vals = [0, 1, 2, 3, (1 << 30) - 1, (1 << 29), (1 << 15), 15258, 15259, 15260]
        vals += [int(v) for v in rng.integers(0, 1 << 30, 40)] + [int(v) for v in rng.integers(0, 1 << 16, 40)]
        for a in vals:
            for b in vals:
                cols.append(np.logical_or(num(a, 0), num(b, 30)))
        for _ in range(3000):
            a = int(rng.integers(0, 1 << int(rng.integers(1, 31)))); b = a ^ int(rng.integers(0, 1 << int(rng.integers(1, 31)))) if rng.random() < 0.7 else a
            cols.append(np.logical_or(num(a, 0), num(b % (1 << 30), 30)))
            cols.append(np.logical_or(num(b % (1 << 30), 0), num(a, 30)))
    if name == "priority":
        for i in range(n):
            for j in range(i):
                c = np.zeros(n, bool); c[i] = True; c[j] = True; cols.append(c)
            for d in (0.03, 0.15, 0.5):
                for _ in range(32):
                    c = np.zeros(n, bool); c[i] = True
                    c[:i] = rng.random(i) < d
                    cols.append(c)
    return np.array(cols, dtype=bool).T.copy()        # (n, R)


def cec(a, b):
    """(equal?, counterexample dict or None)"""
    r = subprocess.run([ABC, "-c", f"cec {a} {b}"], capture_output=True, text=True, timeout=600)
    out = r.stdout + r.stderr
    if "Networks are equivalent" in out: return True, None
    cex = None
    for line in out.splitlines():
        if line.startswith("INPUT:"):
            cex = {}
            for m in re.finditer(r"(\S+) = (\d+)'h([0-9a-fA-F]+)", line):
                width, val = int(m.group(2)), int(m.group(3), 16)
                cex[m.group(1)] = bool(val & 1)                    # scalar name
                for i in range(width):                             # bus: name[i]
                    cex[f"{m.group(1)}[{i}]"] = bool((val >> i) & 1)
    return False, cex


def run(name, start, out, Lmax=None, tlimit=600, seed=1, iters=10 ** 9, log=print, deep=0, pert=60, newnode=True):
    rng = random.Random(seed)
    ref = os.path.join(SUITE, name + ".blif")
    eq, _ = cec(start, ref)
    assert eq, "start netlist is not equal to the suite circuit"
    net0 = Net(start, X=np.zeros((1, 1), bool)) if False else None
    from resub import read_blif
    ins = read_blif(start)[0]
    n = len(ins)
    X = [patterns(name, n, seed)]
    tmp = out + ".try.blif"; good = out + ".good.blif"
    net = Net(start, X[0]); net.deep = deep; net.pert = pert; net.write(good, model=name)
    eq, _ = cec(good, ref)
    assert eq, "rewrite of the start netlist is not equal (sample too thin for the LUT tables)"
    state = dict(best=net.count(), kept=0, refused=0)
    lev0 = max(net.levels()[o] for o in net.outputs)
    log(f"start: count {net.count()} levels {lev0} inputs {n} patterns {X[0].shape[1]}")
    t0 = time.time()

    def rebuild(extra=None):
        nonlocal net
        if extra is not None:
            X[0] = np.concatenate([X[0], extra], axis=1)
        net = Net(good, X[0]); net.deep = deep; net.pert = pert

    def commit():
        """the net was changed by a move: keep it only if the whole netlist is still equal"""
        net.write(tmp, model=name)
        eq, cex = cec(tmp, ref)
        if eq:
            if Lmax and max(net.levels()[o] for o in net.outputs) > Lmax:
                rebuild(); raise Restart()
            os.replace(tmp, good); state["kept"] += 1
            if state["kept"] % 20 == 1:
                log(f"  ... kept={state['kept']} refused={state['refused']} count={net.count()} [{time.time()-t0:.0f}s]")
            c = net.count()
            if c < state["best"]:
                state["best"] = c
                net.write(out, model=name)
                log(f"  count {c} levels {max(net.levels()[o] for o in net.outputs)} kept={state['kept']} refused={state['refused']} patterns={X[0].shape[1]} [{time.time()-t0:.0f}s]")
            return
        state["refused"] += 1
        if state["refused"] % 20 == 1:
            log(f"  ... refused={state['refused']} kept={state['kept']} patterns={X[0].shape[1]} count={state['best']} [{time.time()-t0:.0f}s]")
        extra = None
        if cex:
            base = np.array([cex.get(x, False) for x in net.inputs], dtype=bool)
            g = np.random.default_rng(state["refused"])
            cols = [base]
            for _ in range(48):
                c = base.copy(); flip = g.random(n) < (g.choice([1, 2, 4, 8]) / n); c[flip] = np.logical_not(c[flip]); cols.append(c)
            extra = np.array(cols, dtype=bool).T
        rebuild(extra)
        raise Restart()

    def greedy():
        again = True
        while again:
            again = False
            for w in list(net.fan):
                if w in net.fan and len(net.fan[w]) >= 2:
                    before = dict(net.fan)
                    g = net.trivialize(w)
                    if net.fan != before:
                        commit(); again = again or g > 0
            for u in sorted(list(net.fan), key=lambda x: rng.random()):
                if time.time() - t0 > tlimit: return
                if u in net.fan and len(net.fan[u]) >= 2:
                    before = dict(net.fan)
                    g = net.eliminate(u, Lmax, rng)
                    if net.fan != before:
                        commit(); again = again or g > 0
            if not again and newnode:
                for w in sorted(list(net.fan), key=lambda x: rng.random()):
                    if time.time() - t0 > tlimit: return
                    if w in net.fan and len(net.fan[w]) >= 2:
                        before = dict(net.fan)
                        g = net.resub1(w, Lmax, rng, maxiter=150)
                        if net.fan != before:
                            commit(); again = again or g > 0

    it = 0
    while time.time() - t0 < tlimit and it < iters:
        it += 1
        try:
            greedy()
            nodes = [x for x in net.fan if len(net.fan[x]) >= 2]
            for w in rng.sample(nodes, min(len(nodes), rng.choice([1, 2, 3]))):
                if w in net.fan:
                    before = dict(net.fan)
                    net.perturb(w, Lmax, rng)
                    if net.fan != before: commit()
        except Restart:
            continue
        if it % 25 == 0:
            log(f"  ... iteration {it} count={net.count()} best={state['best']} kept={state['kept']} refused={state['refused']} patterns={X[0].shape[1]} [{time.time()-t0:.0f}s]")
    final = Net(good, X[0])
    final.write(out, model=name)
    eq, _ = cec(out, ref)
    log(f"done: count {final.count()} levels {max(final.levels()[o] for o in final.outputs)} equal={eq} kept={state['kept']} refused={state['refused']} iterations={it} [{time.time()-t0:.0f}s]")
    for f in (tmp, good):
        if os.path.exists(f): os.unlink(f)
    return final.count()


if __name__ == "__main__":
    a = sys.argv[1:]
    name, start, out = a[0], a[1], a[2]
    opt = dict(levels=None, time=600, seed=1, iters=10 ** 9, deep=0, pert=60, newnode=0)
    i = 3
    while i < len(a):
        opt[a[i].lstrip("-")] = a[i + 1]; i += 2
    run(name, start, out, int(opt["levels"]) if opt["levels"] else None, float(opt["time"]), int(opt["seed"]), int(opt["iters"]), deep=int(opt["deep"]), pert=int(opt["pert"]), newnode=bool(int(opt["newnode"])))
