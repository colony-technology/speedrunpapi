"""Independent check of the self-checking CRC block.  Shares no code with the generators.  Standard library only.

    python3 proof/independent_selfcheck_checker.py --netlist proof/NAME_sc.blif --block proof/NAME.blif --H proof/NAME_H.json

Reads the flat netlist of block + detector, the block's own netlist and H.  Accepts only if all of these hold:

1. Block unchanged: the nets in the cone of o (the transitive fan-in of the 32 outputs) are exactly the block
   netlist, renamed b_*, table for table.
2. Separation: no net outside that cone is read by a net inside it.  The predictor, checker and alarm nets
   are therefore outside the cone of o: a fault there cannot change o.
3. Every LUT in the cone is the parity of its inputs.  Every net w then has an effect vector e_w in GF(2)^32:
   flipping w flips exactly the outputs o[i] with e_w[i] = 1, for every input.  e_w is computed backward from the
   outputs (the parity of the number of paths from w to o[i]).
4. Detector function: the nets named by H as predicted bits p[j] and checked bits c[j] are parity networks;
   p[j] has the GF(2) form (row j of H) . L over (s, d), with L the forms of o; c[j] reads only o[0..31] and has
   the form row j of H over o.  The alarm net is a function of the p[j], c[j] only, and equals 1 exactly when
   some p[j] != c[j] (its table is checked on all 2^(2r) patterns of those nets).
5. Coverage: H e_w != 0 for every net w of the block.

From 3, a fault on w (inverted, stuck at 0 or 1, or any change of its LUT's table) changes o, when it changes
w at all, by exactly e_w; a fault on one input pin of a LUT changes only that LUT's output, so it is a change
of that LUT's net.  From 4, the faulty o' = o + e_w gives c' = c + H e_w while p is unchanged, so the alarm is 1
exactly when H e_w != 0; from 5 that holds for every w.
"""
import argparse
import json
from pathlib import Path


def parse(path):
    ins, outs, luts, cur = [], [], [], None
    for line in path.read_text().replace("\\\n", " ").splitlines():
        t = line.split()
        if not t or t[0].startswith("#"):
            continue
        if t[0] == ".inputs":
            ins += t[1:]
        elif t[0] == ".outputs":
            outs += t[1:]
        elif t[0] == ".names":
            cur = [t[-1], t[1:-1], set()]
            luts.append(cur)
        elif t[0] in (".model", ".end"):
            cur = None
        elif t[0].startswith("."):
            raise ValueError("unsupported construct " + t[0])
        else:
            if cur is None or len(t) != 2 or t[1] != "1" or len(t[0]) != len(cur[1]) or set(t[0]) - {"0", "1"}:
                raise ValueError("row format")
            cur[2].add(t[0])
    return ins, outs, luts


def is_parity(src, rows):
    n = len(src)
    return n > 0 and rows == {format(r, "0%db" % n)[::-1] for r in range(1 << n) if bin(r).count("1") & 1}


def verify(net_path, block_path, H_path, drop=None):
    try:
        ins, outs, luts = parse(net_path)
        bins, bouts, bluts = parse(block_path)
        Hj = json.loads(H_path.read_text())
        H = [int(h, 16) for h in Hj["H"]]
        r = len(H)
        if ins != bins or outs[:32] != bouts or outs[32:] != ["alarm"] or len(bouts) != 32:
            return {"ok": False, "reason": "interface"}
        drv = {}
        for name, src, rows in luts:
            if name in drv or name in ins:
                return {"ok": False, "reason": "net driven twice: " + name}
            drv[name] = (src, rows)
        order, seen = [], set(ins)
        for name, src, rows in luts:                        # netlist must be in topological order
            if any(v not in seen for v in src):
                return {"ok": False, "reason": "netlist order at " + name}
            seen.add(name)
            order.append(name)
        cone, stack = set(), list(bouts)
        while stack:
            v = stack.pop()
            if v in cone or v in ins:
                continue
            cone.add(v)
            stack += drv[v][0]
        # 1. block unchanged
        ren = lambda v: v if v in bins or v in bouts else "b_" + v
        want = {ren(o): ([ren(u) for u in s], rows) for o, s, rows in bluts}
        got = {v: drv[v] for v in cone}
        if want != got:
            return {"ok": False, "reason": "cone of o differs from the block netlist"}
        # 2. separation
        for v in cone:
            if any(u not in cone and u not in ins for u in drv[v][0]):
                return {"ok": False, "reason": "net in the cone of o reads a detector net: " + v}
        # 3. effect vectors
        bufs = {}
        for v in cone:
            src, rows = drv[v]
            if v in bouts:
                if not (len(src) == 1 and rows == {"1"}):
                    return {"ok": False, "reason": "output %s is not a buffer" % v}
                bufs.setdefault(src[0], []).append(bouts.index(v))
            elif not is_parity(src, rows):
                return {"ok": False, "reason": "not a parity LUT in the block: " + v}
        nets = [v for v in order if v in cone and v not in bouts]
        readers = {}
        for v in nets:
            for u in drv[v][0]:
                readers.setdefault(u, []).append(v)
        e = {}
        for v in reversed(nets):
            x = 0
            for c in readers.get(v, []):
                x ^= e[c]
            for i in bufs.get(v, []):
                x ^= 1 << i
            e[v] = x
        # 4. detector function: forms over inputs and over o
        form = {v: 1 << i for i, v in enumerate(ins)}
        for v in nets:
            x = 0
            for u in drv[v][0]:
                x ^= form[u]
            form[v] = x
        L = [form[drv[o][0][0]] for o in bouts]
        ofrm = {o: 1 << i for i, o in enumerate(bouts)}      # forms over o for the checker side
        alarm_src = drv["alarm"][0]
        if not (len(alarm_src) == 1 and drv["alarm"][1] == {"1"}):
            return {"ok": False, "reason": "alarm is not a buffer of the alarm net"}
        top = alarm_src[0]
        # find the p/c nets: the leaves of the alarm logic are the nets read by non-parity detector LUTs
        det = [v for v in order if v not in cone and v != "alarm"]
        pform, cform, kind = {}, {}, {}
        for v in det:
            src, rows = drv[v]
            if all(u in ins or kind.get(u) == "p" for u in src) and is_parity(src, rows):
                x = 0
                for u in src:
                    x ^= form[u] if u in ins else pform[u]
                pform[v], kind[v] = x, "p"
            elif all(u in bouts or kind.get(u) == "c" for u in src) and is_parity(src, rows):
                x = 0
                for u in src:
                    x ^= ofrm[u] if u in bouts else cform[u]
                cform[v], kind[v] = x, "c"
            else:
                kind[v] = "a"
        leaves, stack, alogic = [], [top], set()
        while stack:
            v = stack.pop()
            if kind.get(v) == "a":
                if v in alogic:
                    continue
                alogic.add(v)
                stack += drv[v][0]
            elif v in pform or v in cform:
                if v not in leaves:
                    leaves.append(v)
            else:
                return {"ok": False, "reason": "alarm logic reads %s, neither a predicted nor a checked bit" % v}
        predicted = {}
        for j, h in enumerate(H):
            want_p = 0
            for i in range(32):
                if (h >> i) & 1:
                    want_p ^= L[i]
            ps = [v for v in leaves if v in pform and pform[v] == want_p]
            cs = [v for v in leaves if v in cform and cform[v] == h]
            if not ps or not cs:
                return {"ok": False, "reason": "no predicted / checked pair for H row %d" % j}
            predicted[j] = (ps[0], cs[0])
        if len(leaves) != 2 * r:
            return {"ok": False, "reason": "alarm reads %d nets, expected %d" % (len(leaves), 2 * r)}
        # alarm table on all patterns of the 2r leaves
        alist = [v for v in order if v in alogic]
        for pat in range(1 << (2 * r)):
            val = {}
            for j in range(r):
                val[predicted[j][0]] = (pat >> (2 * j)) & 1
                val[predicted[j][1]] = (pat >> (2 * j + 1)) & 1
            for v in alist:
                src, rows = drv[v]
                val[v] = 1 if "".join(str(val[u]) for u in src) in rows else 0
            want_a = int(any(((pat >> (2 * j)) & 1) != ((pat >> (2 * j + 1)) & 1) for j in range(r)))
            if val[top] != want_a:
                return {"ok": False, "reason": "alarm table wrong at pattern %d" % pat}
        # 5. coverage
        Hc = [h for j, h in enumerate(H) if j != drop]       # --drop: coverage with one check bit removed
        miss = [v for v in nets if not any(bin(h & e[v]).count("1") & 1 for h in Hc)]
        zero = [v for v in nets if e[v] == 0]
        if miss:
            return {"ok": False, "reason": "uncovered nets: " + " ".join(miss[:20]), "uncovered": miss}
        return {"ok": True, "check_bits": r, "block_nets": len(nets), "distinct_effect_vectors": len(set(e.values())),
                "zero_effect_vectors": len(zero), "detector_luts": len(det), "alarm_luts": len(alogic),
                "proof": "block unchanged; detector outside the cone of o; parity block; H e_w != 0 for every block net"}
    except Exception as exc:
        return {"ok": False, "reason": "replay exception: " + type(exc).__name__ + ": " + str(exc)[:160]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--netlist", type=Path, required=True)
    ap.add_argument("--block", type=Path, required=True)
    ap.add_argument("--H", type=Path, required=True)
    ap.add_argument("--drop", type=int, help="negative control: judge coverage without check bit J")
    a = ap.parse_args()
    res = verify(a.netlist, a.block, a.H, a.drop)
    if a.drop is not None:
        print("check bit %d dropped: %d uncovered nets: %s" % (a.drop, len(res.get("uncovered", [])), " ".join(res.get("uncovered", []))))
        raise SystemExit(0 if res.get("uncovered") else 1)
    print(json.dumps(res, sort_keys=True))
    raise SystemExit(0 if res["ok"] else 1)
