"""Independent replay of the derivation from the netlist; see verify()."""
import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
from fractions import Fraction as Fr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hyp_check import (parse_blif, lut_poly, BitPoly, ap, cone, topo, sub_blif, cec, write_blif, lit,  # noqa: E402
                       eval_cone, aval, wire, safe, mul_poly, add_into)


def word_poly(bits, shift=0, signed=False):
    p = {}
    n = len(bits)
    for i, a in enumerate(bits):
        w = -(1 << (shift + i)) if (signed and i == n - 1) else (1 << (shift + i))
        for mono, c in ap(a).items():
            p[mono] = p.get(mono, 0) + c * w
    return p


def rows_poly(rows, shift=0):
    p = {}
    for c, atoms in rows.items():
        for a in atoms:
            for mono, k in ap(a).items():
                p[mono] = p.get(mono, 0) + k * (1 << (int(c) + shift))
    return p


def row_atoms(rows):
    return [a for atoms in rows.values() for a in atoms]


def identity(tables, target, sources, expect, mod):
    """target: polynomial dict over target wires; substitute every LUT between sources and targets; compare."""
    tw = {w for mono in target for w in mono} - sources
    names = cone(tables, tw, sources)
    bp = BitPoly(mod)
    add_into(bp, target)
    for o in reversed(topo(tables, names)):
        bp.substitute(o, lut_poly(*tables[o]))
        if len(bp.terms) > 64 * (len(names) + len(target)) + 100000:
            return False                                # the polynomial does not close: reject
    ex = BitPoly(mod)
    add_into(ex, expect)
    return bp.terms == ex.terms


def wires_of(atoms):
    return {wire(a) for a in atoms if wire(a)}


def ripple_ref(path, cols, ins, ports_at):
    """ripple adder over cols (list of atom lists, LSB first); ports_at: {column index: port name} for sum bits."""
    ref, carry = [], None
    for c, atoms in enumerate(cols):
        ls = [lit(a) for a in atoms]
        vs = [l[0] for l in ls if l not in (0, 1)] + ([carry] if carry else [])
        srows, crows = [], []
        for bits in range(1 << len(vs)):
            env = {v: (bits >> t) & 1 for t, v in enumerate(vs)}
            tot = env[carry] if carry else 0
            for l in ls:
                tot += l if l in (0, 1) else (env[l[0]] if l[1] else 1 - env[l[0]])
            key = "".join(str(env[v]) for v in vs)
            if tot & 1:
                srows.append(key)
            if tot >> 1:
                crows.append(key)
        ref.append((ports_at.get(c, "rs%d" % c), vs, srows))
        carry = "rc%d" % c
        ref.append((carry, vs, crows))
    write_blif(path, [safe(v) for v in ins], list(ports_at.values()), ref)


def adder_cec(tables, abc, tmp, tag, cols, outs_at):
    """cols: list of atom lists; outs_at: {column: atom of our sum bit}.  cec of our cone against a ripple adder."""
    ins = sorted(wires_of([a for c in cols for a in c]))
    ports = {c: "P%d" % c for c in outs_at}
    names = cone(tables, wires_of(list(outs_at.values())), set(ins))
    sub_blif(tables, names, ins, list(ports.values()), os.path.join(tmp, tag + "_o.blif"),
             {ports[c]: a for c, a in outs_at.items()})
    ripple_ref(os.path.join(tmp, tag + "_r.blif"), cols, ins, ports)
    return cec(abc, os.path.join(tmp, tag + "_o.blif"), os.path.join(tmp, tag + "_r.blif"))


def par_eval(tables, names, env, S):
    """bit-parallel evaluation of the LUTs `names` on S assignments (env: wire -> S-bit integer)."""
    full = (1 << S) - 1
    env = dict(env)
    for o in topo(tables, names):
        vs, rows = tables[o]
        acc = 0
        for row in rows:
            term = full
            for ch, v in zip(row, vs):
                term &= env[v] if ch == "1" else full ^ env[v]
            acc |= term
        env[o] = acc
    return env


def exhaustive(tables, names, srcw):
    """all 2^len(srcw) assignments of the source wires, bit-parallel; returns a getter env(i)."""
    S = 1 << len(srcw)
    pv = {w: sum(((i >> q) & 1) << i for i in range(S)) for q, w in enumerate(srcw)}
    pv = par_eval(tables, names, pv, S)
    return S, (lambda i: {w: (x >> i) & 1 for w, x in pv.items()})


def colslist(rows, lo, hi):
    return [[a for a in rows.get(str(c), []) if a != 0] for c in range(lo, hi)]


def verify(raw, der, abc):
    if der.get("schema") != "colony.lut-prescaled-root.v1":
        return "schema"
    if der["netlist_digest"] != "sha256:" + hashlib.sha256(raw).hexdigest():
        return "digest"
    P = der["params"]
    m, k, t, FM, f, J, jd = (P[x] for x in ("m", "k", "t", "FM", "f", "J", "jd"))
    r, nd = 1 << k, k + 2
    L = FM + 2 * m
    Wv, LU = L + nd, FM + k * J
    WU, WS, WZ = LU + 2, k * J + 3, 2 * m + 5
    inputs, outputs, tables = parse_blif(raw)
    hyp = der["kind"] == "hyp"
    if hyp:
        if inputs != ["a[%d]" % i for i in range(m)] + ["b[%d]" % i for i in range(m)] or \
                outputs != ["hypotenuse[%d]" % i for i in range(m)]:
            return "interface"
    elif inputs != ["a[%d]" % i for i in range(2 * m)] or outputs != ["asqrt[%d]" % i for i in range(m)]:
        return "interface"
    tmp = tempfile.mkdtemp(prefix="psq_")
    say = lambda s: print(s, flush=True)
    # 0. radicand
    if hyp:
        mod = 1 << (2 * m)
        rws = {str(c): v for c, v in enumerate(der["rows"])}
        bp = BitPoly(mod)
        add_into(bp, rows_poly(rws))
        for name in reversed(der["heap"]):
            if name in tables:
                bp.substitute(name, lut_poly(*tables[name]))
        ex = {}
        for v in "ab":
            for i in range(m):
                for j in range(m):
                    mono = frozenset(["%s[%d]" % (v, i), "%s[%d]" % (v, j)])
                    ex[mono] = (ex.get(mono, 0) + (1 << (i + j))) % mod
        if bp.terms != {mm: c for mm, c in ex.items() if c}:
            return "radicand heap"
        X = der["radicand"]
        if not adder_cec(tables, abc, tmp, "rad", [list(a for a in col if a != 0) for col in der["rows"]],
                         {c: X[c] for c in range(2 * m)}):
            return "radicand adder"
        say("0. radicand rows = a*a + b*b (polynomial); radicand = ripple sum (cec)")
    else:
        X = ["a[%d]" % i for i in range(2 * m)]
    # 1. normalisation
    fh, Xn = der["f"], der["Xn"]
    src = wires_of(X)
    names = cone(tables, wires_of(fh + Xn), src)
    fp, xp = ["F%d" % p for p in range(m)], ["XN%d" % i for i in range(2 * m)]
    sub_blif(tables, names, sorted(src), fp + xp, os.path.join(tmp, "n_o.blif"), dict(zip(fp + xp, fh + Xn)))
    Rl = [lit(a) for a in X]
    cube = lambda pairs, vs: "".join(next((str(p) for (w, p) in pairs if w == v), "-") for v in vs)
    Ln = [".model r", ".inputs " + " ".join(safe(v) for v in sorted(src)), ".outputs " + " ".join(fp + xp)]

    def names_or(name, lits):
        lits = [l for l in lits if l != 0]
        if any(l == 1 for l in lits):
            Ln.extend([".names " + name, "1"])
            return
        vs = sorted({l[0] for l in lits})
        Ln.append(".names " + " ".join(vs + [name]))
        Ln.extend(cube([l], vs) + " 1" for l in lits)
    for p in range(m):
        names_or("z%d" % p, [Rl[2 * p], Rl[2 * p + 1]])
        names_or("ab%d" % p, Rl[2 * p + 2:])
        Ln.extend([".names z%d ab%d F%d" % (p, p, p), "10 1"])
    for i in range(2 * m):
        terms = [(p, Rl[i - 2 * (m - 1 - p)]) for p in range(m) if 0 <= i - 2 * (m - 1 - p) < 2 * m]
        terms = [(p, l) for p, l in terms if l != 0]
        vs = sorted({"F%d" % p for p, _ in terms} | {l[0] for _, l in terms if l != 1})
        Ln.append(".names " + " ".join(vs + ["XN%d" % i]))
        Ln.extend(cube([("F%d" % p, 1)] + ([] if l == 1 else [l]), vs) + " 1" for p, l in terms)
    Ln.append(".end")
    open(os.path.join(tmp, "n_r.blif"), "w").write("\n".join(Ln) + "\n")
    if not cec(abc, os.path.join(tmp, "n_o.blif"), os.path.join(tmp, "n_r.blif")):
        return "normalisation"
    say("1. normalisation = one-hot highest pair and its shift (cec)")
    # 2. table
    idx = der["idx"]
    if idx != Xn[2 * m - t:]:
        return "table index"
    Mw, S0w, U0w, C0w = der["Mw"], der["S0w"], der["U0w"], der["C0w"]
    iw = sorted(wires_of(idx))
    if len(iw) != t:
        return "table index wires"
    outs = Mw + S0w + U0w + C0w
    names = cone(tables, wires_of(outs), set(iw))
    word = lambda bits, env: sum(aval(a, env) << q for q, a in enumerate(bits))
    tab = {}
    S = 1 << t
    full = (1 << S) - 1
    pv = {}
    for q, a in enumerate(idx):
        vec = sum(((i >> q) & 1) << i for i in range(S))
        pv[a.lstrip("!")] = (full ^ vec) if a.startswith("!") else vec
    pv = par_eval(tables, names, pv, S)
    for i in range(S):
        env = {w: (x >> i) & 1 for w, x in pv.items()}
        Mv, Sv, Uv, Cv = (word(b, env) for b in (Mw, S0w, U0w, C0w))
        if Uv != 2 * Mv * Sv or Cv != Mv * Sv * Sv:
            return "table words at index %d" % i
        tab[i] = (Mv, Sv)
    say("2. table read on all %d indices; U0 = 2 M S0 and C0 = M S0^2 everywhere" % (1 << t))
    # 3. v_0, U_0
    vs_, Us = der["v"], der["U"]
    srcs = wires_of(Mw + Xn + C0w)
    ex = mul_poly(word_poly(Mw), word_poly(Xn, k), 1 << Wv)
    add_into_d = lambda p, q, s=1: [p.__setitem__(mm, p.get(mm, 0) + s * c) for mm, c in q.items()]
    add_into_d(ex, word_poly(C0w, L - FM - k), -1)
    ex[frozenset()] = ex.get(frozenset(), 0) + (1 << (L - 1))
    if not identity(tables, rows_poly(vs_[0]), srcs, ex, 1 << Wv):
        return "v_0 rows"
    if not identity(tables, rows_poly(Us[0]), wires_of(U0w), word_poly(U0w, LU - FM - k), 1 << WU):
        return "U_0 rows"
    say("3. v_0 = M Xn 2^k - C0 + 1/2 and U_0 = U0 (polynomial identities)")
    # 4. digits
    ds, dsqs = der["d"], der["dsq"]
    if len(ds) != J or len(dsqs) != J - 1:
        return "digit count"
    for j in range(J):
        v = vs_[j]
        cols = colslist(v, L - f, Wv)
        if not adder_cec(tables, abc, tmp, "dg%d" % j, cols, {f + q: ds[j][q] for q in range(nd)}):
            return "digit adder %d" % j
        if j == J - 1:
            break
        d, dsq = ds[j], dsqs[j]
        dw = sorted(wires_of(d))
        names = cone(tables, wires_of(dsq), set(dw))
        if not dsq and not (j == J - 2 and j >= jd):
            return "missing d^2 table at digit %d" % j
        S_, envf = exhaustive(tables, names, dw)
        for bits in range(S_) if dsq else ():
            env = envf(bits)
            dv = word(d, env)
            dv -= (dv >> (nd - 1)) << nd
            if word(dsq, env) != dv * dv:
                return "d^2 table at digit %d" % j
        dp = word_poly(d, 0, signed=True)
        ex = rows_poly(v, k)
        ex[frozenset()] = ex.get(frozenset(), 0) - (r - 1) * (1 << (L - 1))
        add_into_d(ex, mul_poly(dp, rows_poly(Us[j], L + k - LU), 1 << Wv), -1)
        srcs = wires_of(row_atoms(v) + d + row_atoms(Us[j]) + Mw)
        if j < jd:
            add_into_d(ex, mul_poly(word_poly(Mw), word_poly(dsq, 2 * m - k * j), 1 << Wv), -1)
            srcs |= wires_of(dsq)
        if j - 1 >= jd:
            add_into_d(ex, mul_poly(word_poly(Mw), word_poly(dsqs[j - 1], 2 * m - k * (j - 2)), 1 << Wv), -1)
            srcs |= wires_of(dsqs[j - 1])
        if not identity(tables, rows_poly(vs_[j + 1]), srcs, ex, 1 << Wv):
            return "residual recurrence at digit %d" % j
        if j == J - 2:
            continue
        ex = rows_poly(Us[j])
        add_into_d(ex, mul_poly(dp, word_poly(Mw, 1 + LU - FM - k * (j + 1)), 1 << WU))
        if not identity(tables, rows_poly(Us[j + 1]), wires_of(row_atoms(Us[j]) + d + Mw), ex, 1 << WU):
            return "U recurrence at digit %d" % j
    say("4. %d digits: digit = integer part of the cut rows (cec); d^2 tables; residual and U recurrences (polynomial)" % J)
    # 5. S
    ex = word_poly(S0w, k * (J - 1))
    for j, d in enumerate(ds, start=1):
        add_into_d(ex, word_poly(d, k * (J - j), signed=True))
    Sr = der["Srows"]
    if not identity(tables, rows_poly(Sr), wires_of(S0w + [a for d in ds for a in d]), ex, 1 << WS):
        return "S rows"
    T = der["T"]
    if len(T) != m + 1 or not adder_cec(tables, abc, tmp, "S", colslist(Sr, 0, WS), {k * J - m + q: T[q] for q in range(m + 1)}):
        return "S adder / T"
    say("5. S = S0 + sum d_j r^-j (polynomial, cec); T = floor(S 2^m)")
    # 6. corrections
    Tp_ = word_poly(T)
    sq = mul_poly(Tp_, Tp_, 1 << WZ)
    for name, extra in (("Z0rows", {}), ("Z1rows", None)):
        ex = word_poly(Xn)
        add_into_d(ex, sq, -1)
        if extra is None:
            add_into_d(ex, word_poly(T, 1), -1)
            ex[frozenset()] = ex.get(frozenset(), 0) - 1
        if not identity(tables, rows_poly(der[name]), wires_of(Xn + T), ex, 1 << WZ):
            return name
    for name, sg in (("Z0rows", der["s0"]), ("Z1rows", der["s1"])):
        if not adder_cec(tables, abc, tmp, name, colslist(der[name], 0, WZ), {WZ - 1: sg}):
            return "sign of " + name
    for name, wname, cst in (("Tprows", "Tp", 1), ("Tmrows", "Tm", -1)):
        ex = word_poly(T)
        ex[frozenset()] = ex.get(frozenset(), 0) + cst
        if not identity(tables, rows_poly(der[name]), wires_of(T), ex, 1 << (m + 1)):
            return name
        if not adder_cec(tables, abc, tmp, wname, colslist(der[name], 0, m + 1), {c: der[wname][c] for c in range(m)}):
            return wname
    Qn = der["Qn"]
    for i in range(m):
        srcq = [der["s0"], der["s1"], T[i], der["Tp"][i], der["Tm"][i]]
        sw = sorted(wires_of(srcq))
        names = cone(tables, wires_of([Qn[i]]), set(sw))
        S_, envf = exhaustive(tables, names, sw)
        for bits in range(S_):
            env = envf(bits)
            s0v, s1v, tv, tpv, tmv = (aval(a, env) for a in srcq)
            if aval(Qn[i], env) != (tmv if s0v else (tv if s1v else tpv)):
                return "Qn bit %d" % i
    say("6. signs of Xn - T^2 and Xn - (T+1)^2, T +/- 1, and the selection")
    # 7. denormalisation
    srcd = wires_of(fh + Qn)
    names = cone(tables, set(outputs), srcd)
    sub_blif(tables, names, sorted(srcd), [safe(o) for o in outputs], os.path.join(tmp, "d_o.blif"), {})
    Ld = [".model r", ".inputs " + " ".join(safe(v) for v in sorted(srcd)), ".outputs " + " ".join(safe(o) for o in outputs)]
    for i in range(m):
        terms = [(lit(fh[p]), lit(Qn[i + (m - 1 - p)])) for p in range(m) if i + (m - 1 - p) < m]
        terms = [(x, y) for x, y in terms if x != 0 and y != 0]
        vs = sorted({l[0] for tt in terms for l in tt if l != 1})
        Ld.append(".names " + " ".join(vs + [safe(outputs[i])]))
        for x, y in terms:
            Ld.append(cube([l for l in (x, y) if l != 1], vs) + " 1")
    Ld.append(".end")
    open(os.path.join(tmp, "d_r.blif"), "w").write("\n".join(Ld) + "\n")
    if not cec(abc, os.path.join(tmp, "d_o.blif"), os.path.join(tmp, "d_r.blif")):
        return "denormalisation"
    say("7. outputs = Qn shifted back by the one-hot pair (cec)")
    # 8. containment, from the table values of the netlist
    up = lambda q: Fr(math.ceil(q * (1 << 48)), 1 << 48)
    sq_lo = lambda q: Fr(math.isqrt(int(q * (1 << 120))), 1 << 60)
    lim = 1 << (nd - 1)
    worst_d, worst_fin = Fr(0), Fr(0)
    for i in range(1 << (t - 2), 1 << t):
        Mi, Si = tab[i]
        Mv, S0 = Fr(Mi, 1 << FM), Fr(Si, r)
        slo, shi = sq_lo(Fr(i, 1 << t)), sq_lo(Fr(i + 1, 1 << t)) + Fr(1, 1 << 59)
        eta = up(max(abs(2 * Mv * slo - 1), abs(2 * Mv * shi - 1)))
        B = r * max(abs(slo - S0), abs(shi - S0))
        Dp = Fr(0)
        for j in range(J):
            rho = Fr(1, 2) + Fr(2, 1 << f) + Dp
            vb = B * (1 + eta + Mv * B / r ** (j + 1))
            d = up(vb + rho)
            if d >= lim or vb + Dp + Fr(1, 2) >= lim:
                return "containment fails at index %d digit %d" % (i, j)
            worst_d = max(worst_d, d)
            Dp = Mv * d * d / r ** j if j >= jd else Fr(0)
            B = up(r * (B * (eta + Mv * B / r ** (j + 1)) + rho))
        fin = B * Fr(1 << m, r ** (J + 1))
        if fin >= 1:
            return "final error at index %d" % i
        worst_fin = max(worst_fin, fin)
    say("8. containment on all %d table cells: max |d| %.1f < %d, final error %.3f ulp" % (3 << (t - 2), worst_d, lim, worst_fin))
    lev = {v: 0 for v in inputs}
    for o in topo(tables, tables.keys()):
        lev[o] = 1 + max([lev[v] for v in tables[o][0]] + [0])
    return {"ok": True, "kind": der["kind"], "m": m, "lut_count": len(tables), "levels": max(lev.values())}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--netlist", type=Path, required=True)
    p.add_argument("--derivation", type=Path, required=True)
    p.add_argument("--abc", default="yosys-abc")
    a = p.parse_args()
    res = verify(a.netlist.read_bytes(), json.loads(a.derivation.read_text()), a.abc)
    print(json.dumps(res if isinstance(res, dict) else {"ok": False, "reason": res}))
    raise SystemExit(0 if isinstance(res, dict) else 1)
