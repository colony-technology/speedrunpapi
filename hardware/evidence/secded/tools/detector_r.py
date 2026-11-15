"""Smallest number of check bits for a detector beside a small linear block (outputs <= 12), by exhaustive search.

    python3 tools/detector_r.py --blif proof/NAME.blif --out proof/NAME_detector_r.json

e_w for every net of the parity network (parity of the number of paths from w to each output, computed backward).
For r = 1, 2, ...: every r x n matrix H over GF(2) is tried (2^(r n) of them); H covers the block when H e_w != 0
for every net.  The first r with a covering H is the minimum, proven by exhaustion of all smaller r.  Among the
covering H of that r, the one with the fewest ones in H plus H M (M the block's matrix over its inputs) is kept.
Beyond --rmax, with --solver, z3 decides r = rmax + 1 and rmax + 2 (an H, not the cheapest one).
"""
import argparse
import json
from pathlib import Path


def parse(path):
    ins, outs, luts, cur = [], [], [], None
    for line in path.read_text().splitlines():
        t = line.split()
        if not t:
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
        else:
            cur[2].add(t[0])
    return ins, outs, luts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--blif", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--rmax", type=int, default=2, help="largest r searched exhaustively")
    ap.add_argument("--solver", help="z3, for r beyond --rmax")
    a = ap.parse_args()
    ins, outs, luts = parse(a.blif)
    n = len(outs)
    bufs, nets, form = {}, [], {v: 1 << i for i, v in enumerate(ins)}
    for name, src, rows in luts:
        k = len(src)
        if name in outs:
            assert k == 1 and rows == {"1"}
            bufs.setdefault(src[0], []).append(outs.index(name))
            form[name] = form[src[0]]
            continue
        assert rows == {format(r, "0%db" % k) for r in range(1 << k) if bin(r).count("1") & 1}, name
        nets.append((name, src))
        v = 0
        for u in src:
            v ^= form[u]
        form[name] = v
    M = [form[o] for o in outs]
    readers = {}
    for name, src in nets:
        for u in src:
            readers.setdefault(u, []).append(name)
    e = {}
    for name, src in reversed(nets):
        x = 0
        for c in readers.get(name, []):
            x ^= e[c]
        for i in bufs.get(name, []):
            x ^= 1 << i
        e[name] = x
    vecs = sorted(set(e.values()))
    pc = lambda x: bin(x).count("1")
    res = {"nets": len(nets), "outputs": n, "distinct_vectors": len(vecs), "zero_vectors": sum(1 for v in e.values() if v == 0),
           "vectors": {k: "%x" % v for k, v in e.items()}}
    trail = []
    for r in range(1, a.rmax + 1):
        best = None
        for code in range(1 << (r * n)):
            H = [(code >> (j * n)) & ((1 << n) - 1) for j in range(r)]
            if all(any(pc(h & v) & 1 for h in H) for v in vecs if v):
                cost = 0
                for h in H:
                    m = 0
                    for i in range(n):
                        if (h >> i) & 1:
                            m ^= M[i]
                    cost += pc(m) + pc(h)
                if best is None or cost < best[0]:
                    best = (cost, H)
        trail.append("r=%d: %s" % (r, "no H among all %d" % (1 << (r * n)) if best is None else "H found, fewest ones %d" % best[0]))
        if best:
            res["r_min"], res["H"], res["ones"] = r, ["%x" % h for h in best[1]], best[0]
            break
    if "r_min" not in res and a.solver:                    # beyond the exhaustive range: z3
        import re
        import subprocess
        for r in range(a.rmax + 1, a.rmax + 3):
            L = ["(declare-const h_%d_%d Bool)" % (j, i) for j in range(r) for i in range(n)]
            for v in vecs:
                if v:
                    t = lambda j: ["h_%d_%d" % (j, i) for i in range(n) if (v >> i) & 1]
                    L.append("(assert (or %s))" % " ".join(t(j)[0] if len(t(j)) == 1 else "(xor %s)" % " ".join(t(j)) for j in range(r)))
            L += ["(check-sat)", "(get-model)"]
            p2 = a.out.with_suffix(".r%d.smt2" % r)
            p2.write_text("\n".join(L) + "\n")
            o = subprocess.run([a.solver, "-T:300", str(p2)], capture_output=True, text=True).stdout
            p2.unlink()
            if o.startswith("sat"):
                H = [0] * r
                for m in re.finditer(r"define-fun h_(\d+)_(\d+) \(\) Bool\s+(true|false)", o):
                    if m.group(3) == "true":
                        H[int(m.group(1))] |= 1 << int(m.group(2))
                assert all(any(pc(h & v) & 1 for h in H) for v in vecs if v)
                trail.append("r=%d: H found by z3 (%s)" % (r, ",".join("%x" % h for h in H)))
                res["r_min"], res["H"] = r, ["%x" % h for h in H]
                break
            trail.append("r=%d: z3 %s" % (r, o.split()[0] if o else "no answer"))
    res["trail"] = trail
    a.out.write_text(json.dumps(res, indent=1) + "\n")
    print("; ".join(trail), "| nets %d, distinct e_w %d, zero e_w %d" % (len(nets), len(vecs), res["zero_vectors"]))
