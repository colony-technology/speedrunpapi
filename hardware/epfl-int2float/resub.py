#!/usr/bin/env python3
"""Global resubstitution on a LUT-6 netlist, exact on small circuits (all 2^n input rows).

Every signal (input or node) is held as its full truth table over the primary inputs. A node is
only ever re-expressed as a LUT over signals that determine it on every row, so every node keeps
its function and the netlist stays equal to the start netlist by construction.

Moves (count = nodes with >= 2 inputs, the table convention):
  eliminate(u): give every fanout of u a new fanin set (<= 6 signals) that does not use u; then u,
                and whatever only fed u, is dropped.
  trivialize(w): w equals another signal or its inverse -> w becomes a wire/inverter (free).
  perturb(w): give w a different fanin set of <= 6 signals (same count), to open new eliminations.
A fanin set for w is searched among ALL signals outside w's fanout cone (not a local window) by a
set-cover SAT: for every pair of rows where w differs, a chosen signal must differ.

Depth mode (--levels L): no output may sit deeper than L (levels over nodes with >= 2 inputs).

Usage: resub.py START.blif OUT.blif [--levels L] [--iters N] [--seed S] [--time SEC]
"""
import random, sys, time
import numpy as np
from pysat.solvers import Solver
from pysat.card import CardEnc, EncType


def read_blif(path):
    text = open(path).read().replace("\\\n", " ")
    inputs, outputs, nodes = [], [], {}
    cur = None
    for line in text.splitlines():
        line = line.split("#")[0].strip()
        if not line: continue
        if line.startswith(".inputs"): inputs += line.split()[1:]; cur = None
        elif line.startswith(".outputs"): outputs += line.split()[1:]; cur = None
        elif line.startswith(".names"):
            sig = line.split()[1:]; cur = sig[-1]; nodes[cur] = (sig[:-1], [])
        elif line.startswith("."): cur = None
        else:
            parts = line.split()
            nodes[cur][1].append(("", parts[0]) if len(nodes[cur][0]) == 0 else (parts[0], parts[1]))
    return inputs, outputs, nodes


def evaluate(fanins, rows, vals, size):
    if not fanins:
        return np.full(size, any(v == "1" for _, v in rows), dtype=bool)
    on = [p for p, v in rows if v == "1"]; off = [p for p, v in rows if v == "0"]
    acc = np.zeros(size, dtype=bool)
    for pat in (on or off):
        c = np.ones(size, dtype=bool)
        for ch, x in zip(pat, fanins):
            if ch == "1": c = np.logical_and(c, vals[x])
            elif ch == "0": c = np.logical_and(c, np.logical_not(vals[x]))
        acc = np.logical_or(acc, c)
    return np.logical_not(acc) if off else acc


class Net:
    def __init__(self, path, X=None):
        self.inputs, self.outputs, raw = read_blif(path)
        n = len(self.inputs)
        if X is None:
            assert n <= 16, "exact mode needs <= 16 inputs"
            self.R = 1 << n
            r = np.arange(self.R, dtype=np.int64)
            self.tt = {x: ((r >> k) % 2).astype(bool) for k, x in enumerate(self.inputs)}
        else:
            self.R = X.shape[1]
            self.tt = {x: X[k] for k, x in enumerate(self.inputs)}
        self.fan = {}
        order = []; seen = set(self.inputs)
        def visit(x):
            if x in seen: return
            for y in raw[x][0]: visit(y)
            seen.add(x); order.append(x)
        sys.setrecursionlimit(100000)
        for o in self.outputs: visit(o)
        self.orig = {}
        for x in order:
            self.tt[x] = evaluate(raw[x][0], raw[x][1], self.tt, self.R)
            self.fan[x] = list(raw[x][0])
            self.orig[x] = (list(raw[x][0]), list(raw[x][1]))
        self.po = set(self.outputs)
        self.deep = 120          # iterations allowed for a fanin set that keeps none of the old fanins
        self.pert = 400          # iterations allowed for a perturbation
        self.budget = 4000       # SAT conflicts allowed per call
        self.ref = {o: self.tt[o].copy() for o in self.outputs}

    # ---- structure
    def count(self):
        return sum(1 for x, f in self.fan.items() if len(f) >= 2)

    def fanouts(self):
        fo = {x: [] for x in list(self.tt)}
        for x, f in self.fan.items():
            for y in f: fo[y].append(x)
        return fo

    def tfo(self, w, fo):
        seen = {w}; stack = [w]
        while stack:
            x = stack.pop()
            for y in fo[x]:
                if y not in seen: seen.add(y); stack.append(y)
        return seen

    def levels(self):
        lev = {x: 0 for x in self.inputs}
        def L(x):
            if x in lev: return lev[x]
            f = self.fan[x]
            lev[x] = (max(L(y) for y in f) if f else 0) + (1 if len(f) >= 2 else 0)
            return lev[x]
        for x in self.fan: L(x)
        return lev

    def topo(self):
        done = set(self.inputs); order = []
        def visit(x):
            if x in done: return
            for y in self.fan[x]: visit(y)
            done.add(x); order.append(x)
        for x in list(self.fan): visit(x)
        return order

    def required(self, Lmax, fo, lev):
        """latest level each node may have"""
        req = {}
        for x in reversed(self.topo()):
            r = Lmax if x in self.po else 10 ** 6
            for z in fo[x]:
                r = min(r, req[z] - (1 if len(self.fan[z]) >= 2 else 0))
            req[x] = r
        return req

    def sweep(self):
        fo = self.fanouts(); dead = 0
        changed = True
        while changed:
            changed = False
            for x in list(self.fan):
                if x not in self.po and not fo[x]:
                    for y in self.fan[x]: fo[y].remove(x)
                    del self.fan[x]; del self.tt[x]; del fo[x]; dead += 1; changed = True
        return dead

    # ---- the search for a fanin set
    def cover(self, w, cands, K=6, forbid=None, rng=None, maxiter=400, must=()):
        """<= K signals among cands that determine w on every row, or None"""
        if not cands: return None
        f = self.tt[w]
        on = np.flatnonzero(f); off = np.flatnonzero(np.logical_not(f))
        if len(on) == 0 or len(off) == 0: return []
        M = np.stack([self.tt[c] for c in cands])            # (m, R)
        m = len(cands)
        s = Solver(name="glucose4")
        if m > K:
            enc = CardEnc.atmost(lits=list(range(1, m + 1)), bound=K, top_id=m, encoding=EncType.seqcounter)
            for c in enc.clauses: s.add_clause(c)
        if forbid is not None:                                # not exactly this set again
            fs = set(forbid)
            s.add_clause([(j + 1) for j, c in enumerate(cands) if c not in fs] + [-(j + 1) for j, c in enumerate(cands) if c in fs])
        for c in must:                                         # signals that have to be in the set
            if c not in cands:
                s.delete(); return None
            s.add_clause([cands.index(c) + 1])
        rng = rng or random
        def add_pair(a, b):
            d = np.flatnonzero(M[:, a] != M[:, b])
            s.add_clause([int(j) + 1 for j in d])
            return len(d) > 0
        for _ in range(64):
            if not add_pair(int(on[rng.randrange(len(on))]), int(off[rng.randrange(len(off))])):
                s.delete(); return None
        res = None
        for _ in range(maxiter):
            s.conf_budget(self.budget)
            if not s.solve_limited(): break
            model = s.get_model()
            pick = [j for j in range(m) if model[j] > 0]
            code = np.zeros(self.R, dtype=np.int64)
            for b, j in enumerate(pick): code |= M[j].astype(np.int64) << b
            size = 1 << len(pick)
            c1 = np.bincount(code[on], minlength=size); c0 = np.bincount(code[off], minlength=size)
            badcodes = np.flatnonzero(np.logical_and(c1 > 0, c0 > 0))
            if len(badcodes) == 0:
                res = [cands[j] for j in pick]; break
            ok = True
            for bc in badcodes[:32]:
                a = int(on[np.flatnonzero(code[on] == bc)[0]]); b = int(off[np.flatnonzero(code[off] == bc)[0]])
                ok = add_pair(a, b) and ok
            if not ok: break
        s.delete()
        if res is None: return None
        # drop signals that are not needed
        changed = True
        while changed and len(res) > 0:
            changed = False
            for c in list(res):
                rest = [x for x in res if x != c]
                if self.determines(rest, f): res = rest; changed = True; break
        return res

    def determines(self, D, f):
        code = np.zeros(self.R, dtype=np.int64)
        for b, c in enumerate(D): code |= self.tt[c].astype(np.int64) << b
        size = 1 << len(D)
        c1 = np.bincount(code[f], minlength=size); c0 = np.bincount(code[np.logical_not(f)], minlength=size)
        return not np.any(np.logical_and(c1 > 0, c0 > 0))

    def candidates(self, w, fo, banned=(), lev=None, maxlev=None):
        bad = self.tfo(w, fo) | set(banned)
        out = [x for x in self.tt if x not in bad]
        if maxlev is not None: out = [x for x in out if lev[x] <= maxlev]
        return out

    # ---- moves
    def eliminate(self, u, Lmax=None, rng=None):
        if u in self.po: return 0
        fo = self.fanouts()
        if not fo[u]: return 0
        lev = self.levels(); req = self.required(Lmax, fo, lev) if Lmax else None
        plan = {}
        for w in fo[u]:
            ml = None
            if Lmax: ml = req[w] - 1
            cands = self.candidates(w, fo, banned=[u], lev=lev, maxlev=ml)
            keep = [x for x in self.fan[w] if x != u]
            D = self.cover(w, cands, rng=rng, must=keep, maxiter=120)      # keep w's other fanins: quick
            if D is None and self.deep:
                D = self.cover(w, cands, rng=rng, maxiter=self.deep)        # any fanin set
            if D is None: return 0
            plan[w] = D
        before = self.count()
        saved = {w: self.fan[w] for w in plan}
        for w, D in plan.items(): self.fan[w] = D
        bad = not self.acyclic()
        if not bad and Lmax:                                   # the new fanins may have moved levels
            bad = max(self.levels()[o] for o in self.outputs) > Lmax
        if bad:
            for w, f in saved.items(): self.fan[w] = f
            return 0
        self.sweep()
        return before - self.count()

    def trivialize(self, w):
        if len(self.fan[w]) < 2: return 0
        fo = self.fanouts()
        f = self.tt[w]
        for c in self.candidates(w, fo):
            if np.array_equal(self.tt[c], f) or np.array_equal(self.tt[c], np.logical_not(f)):
                before = self.count()
                self.fan[w] = [c]; self.sweep()
                return before - self.count()
        return 0

    def perturb(self, w, Lmax=None, rng=None):
        fo = self.fanouts(); lev = self.levels()
        ml = None
        if Lmax: ml = self.required(Lmax, fo, lev)[w] - 1
        cands = self.candidates(w, fo, lev=lev, maxlev=ml)
        rng.shuffle(cands)
        D = self.cover(w, cands, forbid=self.fan[w], rng=rng, maxiter=self.pert)
        if D is None or len(D) < 2: return False
        old = self.fan[w]; self.fan[w] = D
        bad = not self.acyclic()
        if not bad and Lmax:
            bad = max(self.levels()[o] for o in self.outputs) > Lmax
        if bad:
            self.fan[w] = old; return False
        self.sweep()
        return True

    def mffc(self, w, fo):
        """w and the nodes that only w needs (they go when w stops reading them)"""
        dead = {w}; changed = True
        while changed:
            changed = False
            for x in list(dead):
                for y in self.fan.get(x, []):
                    if y in self.fan and y not in dead and y not in self.po and all(z in dead for z in fo[y]):
                        dead.add(y); changed = True
        return dead

    def resub1(self, w, Lmax=None, rng=None, maxiter=400):
        """rebuild w as LUT(z, <=5 signals) with one NEW node z = LUT(<=6 signals); pays when w owns >= 2 other nodes"""
        if len(self.fan[w]) < 2: return 0
        fo = self.fanouts()
        M = self.mffc(w, fo)
        if sum(1 for x in M if len(self.fan[x]) >= 2) < 3: return 0
        lev = self.levels(); bad = self.tfo(w, fo) | M
        cands = [x for x in self.tt if x not in bad]
        candA, candB = cands, cands
        if Lmax:
            req = self.required(Lmax, fo, lev)[w]
            candA = [x for x in cands if lev[x] <= req - 2]
            candB = [x for x in cands if lev[x] <= req - 1]
        got = self.decomp1(self.tt[w], candA, candB, rng or random, maxiter)
        if got is None: return 0
        D1, z, D2 = got
        self.fresh = getattr(self, "fresh", 0) + 1
        name = f"rs{self.fresh}"
        while name in self.tt: self.fresh += 1; name = f"rs{self.fresh}"
        before = self.count(); saved = self.fan[w]
        self.tt[name] = z; self.fan[name] = list(D1); self.fan[w] = [name] + list(D2)
        bad = not self.acyclic()
        if not bad and Lmax: bad = max(self.levels()[o] for o in self.outputs) > Lmax
        if bad:
            self.fan[w] = saved; del self.fan[name]; del self.tt[name]; return 0
        self.sweep()
        return before - self.count()

    def decomp1(self, f, candA, candB, rng, maxiter):
        """f = T(z, D2), z = g(D1): returns (D1, z values, D2) or None. Lazy pair constraints."""
        R = self.R
        if not candA or not candB: return None
        MA = np.stack([self.tt[c] for c in candA]); MB = np.stack([self.tt[c] for c in candB])
        na, nb = len(candA), len(candB)
        A0, B0, Z0 = 1, na + 1, na + nb + 1               # variable offsets
        top = na + nb + R
        s = Solver(name="glucose4")
        for lits, bound in ((list(range(A0, A0 + na)), 6), (list(range(B0, B0 + nb)), 5)):
            if len(lits) > bound:
                enc = CardEnc.atmost(lits=lits, bound=bound, top_id=top, encoding=EncType.seqcounter)
                top = max(top, enc.nv)
                for c in enc.clauses: s.add_clause(c)
        on = np.flatnonzero(f); off = np.flatnonzero(np.logical_not(f))
        if len(on) == 0 or len(off) == 0:
            s.delete(); return None
        s.add_clause([-(Z0 + int(on[0]))])                  # polarity of z
        def c1(a, b):                                       # f differs: z differs or a D2 signal differs
            d = [B0 + int(j) for j in np.flatnonzero(MB[:, a] != MB[:, b])]
            s.add_clause([Z0 + a, Z0 + b] + d); s.add_clause([-(Z0 + a), -(Z0 + b)] + d)
        def c2(a, b):                                       # z differs: a D1 signal differs
            d = [A0 + int(j) for j in np.flatnonzero(MA[:, a] != MA[:, b])]
            s.add_clause([Z0 + a, -(Z0 + b)] + d); s.add_clause([-(Z0 + a), Z0 + b] + d)
        for _ in range(200):
            c1(int(on[rng.randrange(len(on))]), int(off[rng.randrange(len(off))]))
        for _ in range(400):
            a, b = rng.randrange(R), rng.randrange(R)
            if a != b: c2(a, b)
        res = None
        for _ in range(maxiter):
            s.conf_budget(self.budget * 4)
            if not s.solve_limited(): break
            model = s.get_model()
            A = [j for j in range(na) if model[A0 + j - 1] > 0]
            B = [j for j in range(nb) if model[B0 + j - 1] > 0]
            z = np.array(model[Z0 - 1: Z0 - 1 + R]) > 0
            added = 0
            code = z.astype(np.int64)
            for b_, j in enumerate(B): code |= MB[j].astype(np.int64) << (b_ + 1)
            size = 1 << (len(B) + 1)
            k1 = np.bincount(code[on], minlength=size); k0 = np.bincount(code[off], minlength=size)
            for bc in np.flatnonzero(np.logical_and(k1 > 0, k0 > 0))[:48]:
                c1(int(on[np.flatnonzero(code[on] == bc)[0]]), int(off[np.flatnonzero(code[off] == bc)[0]])); added += 1
            code = np.zeros(R, dtype=np.int64)
            for b_, j in enumerate(A): code |= MA[j].astype(np.int64) << b_
            size = 1 << len(A)
            zi = np.flatnonzero(z); zo = np.flatnonzero(np.logical_not(z))
            k1 = np.bincount(code[zi], minlength=size); k0 = np.bincount(code[zo], minlength=size)
            for bc in np.flatnonzero(np.logical_and(k1 > 0, k0 > 0))[:48]:
                ra = zi[np.flatnonzero(code[zi] == bc)]; rb = zo[np.flatnonzero(code[zo] == bc)]
                for t in range(min(3, len(ra), len(rb))):
                    c2(int(ra[rng.randrange(len(ra))]), int(rb[rng.randrange(len(rb))])); added += 1
            if added == 0:
                res = ([candA[j] for j in A], z, [candB[j] for j in B]); break
        s.delete()
        return res

    def acyclic(self):
        state = {}
        def visit(x):
            if x not in self.fan: return True
            if state.get(x) == 1: return False
            if state.get(x) == 2: return True
            state[x] = 1
            for y in self.fan[x]:
                if not visit(y): return False
            state[x] = 2; return True
        return all(visit(x) for x in list(self.fan))

    # ---- output
    def check(self):
        return all(np.array_equal(self.tt[o], self.ref[o]) for o in self.outputs)

    def write(self, path, model="top"):
        L = [f".model {model}", ".inputs " + " ".join(self.inputs), ".outputs " + " ".join(self.outputs)]
        done = set(self.inputs); order = []
        def visit(x):
            if x in done: return
            for y in self.fan[x]: visit(y)
            done.add(x); order.append(x)
        for o in self.outputs: visit(o)
        for x in order:
            f = self.fan[x]
            L.append(".names " + " ".join(f + [x]))
            if x in self.orig and self.orig[x][0] == f:      # untouched node: keep its own table
                for pat, v in self.orig[x][1]:
                    L.append((pat + " " + v) if f else v)
                continue
            if not f:
                if self.tt[x][0]: L.append("1")
                continue
            code = np.zeros(self.R, dtype=np.int64)
            for b, c in enumerate(f): code |= self.tt[c].astype(np.int64) << b
            onc = sorted(set(int(c) for c in np.unique(code[self.tt[x]])))
            for c in onc:
                L.append("".join("1" if (c >> j) & 1 else "0" for j in range(len(f))) + " 1")
            if not onc:                                   # never 1: say so with an off-set row
                L.append("-" * len(f) + " 0")
        L.append(".end")
        open(path, "w").write("\n".join(L) + "\n")

    def snapshot(self):
        return ({x: list(f) for x, f in self.fan.items()}, {x: t for x, t in self.tt.items()})

    def restore(self, snap):
        self.fan = {x: list(f) for x, f in snap[0].items()}; self.tt = dict(snap[1])


def run(start, out, Lmax=None, iters=2000, seed=1, tlimit=600, log=print, newnode=True):
    rng = random.Random(seed)
    net = Net(start)
    lev0 = max(net.levels()[o] for o in net.outputs)
    log(f"start {start}: count {net.count()} levels {lev0} inputs {len(net.inputs)} rows {net.R}")
    if Lmax is None: Lmax_eff = None
    else: Lmax_eff = Lmax
    best = net.count(); bestsnap = net.snapshot()
    t0 = time.time()
    def greedy():
        gain = 0; again = True
        while again:
            again = False
            for w in list(net.fan):
                if w in net.fan:
                    g = net.trivialize(w)
                    if g: gain += g; again = True
            for u in sorted(list(net.fan), key=lambda x: rng.random()):
                if u in net.fan and len(net.fan[u]) >= 2:
                    g = net.eliminate(u, Lmax_eff, rng)
                    if g > 0: gain += g; again = True
            if not again and newnode:
                for w in sorted(list(net.fan), key=lambda x: rng.random()):
                    if w in net.fan and len(net.fan[w]) >= 2:
                        g = net.resub1(w, Lmax_eff, rng)
                        if g > 0:
                            gain += g; again = True
                            log(f"  new-node move at {w}: -{g} -> {net.count()}")
        return gain
    g = greedy()
    log(f"greedy: -{g} -> {net.count()}  [{time.time()-t0:.0f}s]")
    if net.count() < best:
        best = net.count(); bestsnap = net.snapshot()
        net.write(out); log(f"  wrote {out} at {best}")
    it = 0
    while it < iters and time.time() - t0 < tlimit:
        it += 1
        nodes = [x for x in net.fan if len(net.fan[x]) >= 2]
        for w in rng.sample(nodes, min(len(nodes), rng.choice([1, 2, 3]))):
            if w in net.fan: net.perturb(w, Lmax_eff, rng)
        g = greedy()
        c = net.count()
        if c < best:
            assert net.check()
            best = c; bestsnap = net.snapshot(); net.write(out)
            log(f"iter {it}: count {c} levels {max(net.levels()[o] for o in net.outputs)}  wrote {out}  [{time.time()-t0:.0f}s]")
        elif c > best:
            net.restore(bestsnap)
    net.restore(bestsnap)
    assert net.check()
    net.write(out)
    log(f"done: best count {best} levels {max(net.levels()[o] for o in net.outputs)} after {it} iterations [{time.time()-t0:.0f}s]")
    return best


if __name__ == "__main__":
    a = sys.argv[1:]
    start, out = a[0], a[1]
    opt = dict(levels=None, iters=2000, seed=1, time=600)
    i = 2
    while i < len(a):
        opt[a[i].lstrip("-")] = a[i + 1]; i += 2
    run(start, out, int(opt["levels"]) if opt["levels"] else None, int(opt["iters"]), int(opt["seed"]), float(opt["time"]))
