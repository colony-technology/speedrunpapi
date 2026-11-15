"""Fault injection by simulation on random inputs.  Python, bit-parallel: each net carries N samples as one integer.

    python3 sim/sim_faults.py --name NAME [--n 4096] [--seed 1] [--init] [--drop J]

For every block net w and each fault (inverted, stuck at 0, stuck at 1; with --init also every table bit of
w's LUT flipped) the faulty netlist proof/NAME_sc.blif is simulated on the same N random inputs as the good one.
Counted per fault: samples where o changed, and among those, samples where alarm stayed 0 (escapes).
The healthy netlist must give alarm 0 on every sample.  --drop J removes check bit J from the alarm.
Independent of Yosys and Verilator; it reads only the BLIF.
"""
import argparse
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(path):
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
            cur = [t[-1], t[1:-1], []]
            luts.append(cur)
        elif t[0] in (".model", ".end"):
            cur = None
        else:
            cur[2].append(t[0] if len(t) == 2 else "")
    return ins, outs, luts


def evaluate(luts, val, mask, fault=None):
    """fault: (net, kind, bit) kind in inv, s0, s1, init."""
    v = dict(val)
    for name, src, rows in luts:
        if not src:
            x = mask if rows else 0
        else:
            rows_ = set(rows)
            if fault and fault[0] == name and fault[1] == "init":
                pat = "".join(str((fault[2] >> q) & 1) for q in range(len(src)))
                rows_ ^= {pat}
            x = 0
            for row in rows_:                                  # sum of minterms
                term = mask
                for q, c in enumerate(row):
                    term &= v[src[q]] if c == "1" else ~v[src[q]] & mask
                    if not term:
                        break
                x |= term
        if fault and fault[0] == name:
            x = {"inv": ~x & mask, "s0": 0, "s1": mask}.get(fault[1], x)
        v[name] = x
    return v


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--n", type=int, default=4096)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--drop", type=int)
    a = ap.parse_args()
    ins, outs, luts = load(ROOT / "proof" / (a.name + "_sc.blif"))
    if a.drop is not None:
        al = [l for l in luts if l[0].startswith("a_")]
        leaves = [v for l in al for v in l[1] if not v.startswith("a_")]
        p, c = leaves[2 * a.drop], leaves[2 * a.drop + 1]
        for l in al:
            l[1] = [p if v == c else v for v in l[1]]
    rng = random.Random(a.seed)
    mask = (1 << a.n) - 1
    val = {v: rng.getrandbits(a.n) for v in ins}
    good = evaluate(luts, val, mask)
    o = [good[x] for x in outs[:32]]
    if good["alarm"]:
        raise SystemExit("healthy circuit raises the alarm on %d samples" % bin(good["alarm"]).count("1"))
    nets = [n for n, _, _ in luts if n.startswith("b_")]
    faults = []
    for n in nets:
        faults += [(n, k, None) for k in ("inv", "s0", "s1")]
        if a.init:
            k = len(next(s for m, s, _ in luts if m == n))
            faults += [(n, "init", b) for b in range(1 << k)]
    tally, escapes, never = {}, [], []
    for f in faults:
        v = evaluate(luts, val, mask, f)
        changed = 0
        for i, x in enumerate(outs[:32]):
            changed |= v[x] ^ o[i]
        esc = changed & ~v["alarm"] & mask
        kind = f[1]
        t = tally.setdefault(kind, [0, 0, 0, 0])               # faults, faults that changed o, samples changed, escapes
        t[0] += 1
        t[1] += bool(changed)
        t[2] += bin(changed).count("1")
        t[3] += bin(esc).count("1")
        if esc:
            escapes.append("%s %s%s" % (f[0], kind, "" if f[2] is None else f[2]))
        if not changed:
            never.append("%s %s%s" % (f[0], kind, "" if f[2] is None else f[2]))
    print("samples %d, seed %d, healthy alarms 0%s" % (a.n, a.seed, "" if a.drop is None else ", check bit %d dropped" % a.drop))
    for kind, (nf, nc, sc, se) in tally.items():
        print("%-5s faults %5d  changed o %5d  samples with o changed %9d  of those with alarm 0: %d" % (kind, nf, nc, sc, se))
    print("faults that never changed o on these samples: %d" % len(never))
    if escapes:
        print("ESCAPES %d: %s" % (len(escapes), " ".join(escapes)))
    raise SystemExit(0 if (a.drop is not None or not escapes) else 1)
