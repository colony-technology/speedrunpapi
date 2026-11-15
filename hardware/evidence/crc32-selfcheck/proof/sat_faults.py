"""SAT proof of fault detection, one Yosys miter per fault.

    python3 proof/sat_faults.py --name NAME --yosys PATH/yosys --work BUILD_DIR [--init] [--pins] [--drop J]

Good copy: proof/NAME_sc.blif.  Faulty copy: the same netlist with one block net w changed:
    inv     w replaced by NOT w
    s0, s1  w replaced by 0, 1
    free    w replaced by a new primary input (any value, chosen by the solver, independently per input vector)
    --pins: for every LUT X and every input pin of X, that pin alone sees NOT / 0 / 1 / free
    --init: for every LUT X and every bit of its table, that bit flipped
Miter:  bad = (o_good != o_faulty) & ~alarm_faulty & ~alarm_good.   `sat -prove bad 0`: proven = for every
input, if the fault changes o then the faulty circuit raises the alarm.

The conjunct ~alarm_good is the statement that the healthy circuit gives no alarm, which holds for every input
because predictor and checker compute the same linear forms; that is proven by
proof/independent_selfcheck_checker.py (item 4), not here.  Without it the solver has to rediscover a parity
identity over 96 inputs, which resolution-based SAT does not do in reasonable time.

"free" contains all others for that net: inv, s0, s1, any change of the LUT's table, and any fault on one of
its input pins are particular choices of the free value.
--drop J removes check bit J from the alarm (negative control): faults that then escape are listed by name.
"""
import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(path):
    text = path.read_text()
    blocks, cur = [], None
    head = []
    for line in text.splitlines():
        if line.startswith(".names"):
            cur = [line, []]
            blocks.append(cur)
        elif line.startswith(".end"):
            cur = None
        elif cur is not None:
            cur[1].append(line)
        else:
            head.append(line)
    return head, blocks


def emit(head, blocks, model, extra_inputs=()):
    out = []
    for h in head:
        if h.startswith(".model"):
            out.append(".model " + model)
        elif h.startswith(".inputs") and extra_inputs:
            out.append(h + " " + " ".join(extra_inputs))
        else:
            out.append(h)
    for line, rows in blocks:
        out.append(line)
        out += rows
    out.append(".end")
    return "\n".join(out) + "\n"


def faulty(head, blocks, net, kind, pin=None, bit=None):
    """Returns (blif text, has free input)."""
    B = [[l, list(r)] for l, r in blocks]
    free = False
    idx = next(i for i, (l, _) in enumerate(B) if l.split()[-1] == net)
    if bit is not None:                                       # flip one table bit of LUT `net`
        src = B[idx][0].split()[1:-1]
        row = "".join(str((bit >> q) & 1) for q in range(len(src))) + " 1"
        B[idx][1] = [r for r in B[idx][1] if r != row] if row in B[idx][1] else B[idx][1] + [row]
        return emit(head, B, "scf"), False
    if pin is not None:                                       # pin `pin` of LUT `net` sees the fault
        t = B[idx][0].split()
        src = t[1:-1]
        if kind == "free":
            free, new = True, []
            src[pin] = "fault_y"
        else:
            new = {"inv": [[".names %s fault_pin" % src[pin], ["0 1"]]],
                   "s0": [[".names fault_pin", []]],
                   "s1": [[".names fault_pin", ["1"]]]}[kind]
            src[pin] = "fault_pin"
        B[idx][0] = " ".join([t[0]] + src + [t[-1]])
        B[idx:idx] = new
        return emit(head, B, "scf", ["fault_y"] if free else ()), free
    t = B[idx][0].split()
    if kind == "free":
        B[idx][0] = " ".join(t[:-1] + [net + "__dead"])
        for b in B:
            parts = b[0].split()
            if parts[-1] != net + "__dead":
                b[0] = " ".join([parts[0]] + ["fault_y" if p == net else p for p in parts[1:-1]] + [parts[-1]])
        return emit(head, B, "scf", ["fault_y"]), True
    B[idx][0] = " ".join(t[:-1] + [net + "__raw"])
    B.insert(idx + 1, [".names %s %s" % (net + "__raw", net), ["0 1"]] if kind == "inv" else
             [".names " + net, ["1"] if kind == "s1" else []])
    return emit(head, B, "scf"), False


def drop_bit(head, blocks, j, pnet, cnet):
    """Negative control: alarm logic sees predicted = checked for bit j (both tied to the predicted net)."""
    B = []
    for l, r in blocks:
        t = l.split()
        if t[-1].startswith("a_"):
            t = [t[0]] + [pnet if v == cnet else v for v in t[1:-1]] + [t[-1]]
        B.append([" ".join(t), r])
    return B


MITER = """module miter (input [31:0] s, input [%d:0] d%s, output bad);
  wire [31:0] og, of; wire ag, af;
  sc  g (.s(s), .d(d), .o(og), .alarm(ag));
  scf f (.s(s), .d(d), %s.o(of), .alarm(af));
  assign bad = (og != of) & ~af & ~ag;
endmodule
"""


def run_batch(yosys, work, tag, jobs, W):
    """jobs: [(label, scf blif text, free)].  One Yosys process, design reset between proofs."""
    lines = []
    for q, (label, text, free) in enumerate(jobs):
        bf = work / ("%s_%d.blif" % (tag, q))
        bf.write_text(text)
        mv = work / ("%s_%d_m.v" % (tag, q))
        mv.write_text(MITER % (W - 1, ", input fault_y" if free else "", ".fault_y(fault_y), " if free else ""))
        lines += ["design -reset", "read_blif -wideports %s" % (work / "good.blif"), "read_blif -wideports %s" % bf,
                  "read_verilog %s" % mv, "hierarchy -top miter", "flatten", "opt_clean",
                  "log MARK %d" % q, "sat -prove bad 0"]
    ys = work / (tag + ".ys")
    ys.write_text("\n".join(lines) + "\n")
    log = work / (tag + ".log")
    subprocess.run([yosys, "-q", "-l", str(log), "-s", str(ys)], capture_output=True, text=True, timeout=3600)
    res, cur = {}, None
    for line in log.read_text().splitlines():
        m = re.match(r"MARK (\d+)", line.strip())
        if m:
            cur = int(m.group(1))
        elif "SAT proof finished - no model found: SUCCESS!" in line and cur is not None:
            res[cur] = "PROVED"
        elif "SAT proof finished - model found: FAIL!" in line and cur is not None:
            res[cur] = "ESCAPES"
    return [(label, res.get(q, "ERROR")) for q, (label, _, _) in enumerate(jobs)]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--yosys", default="yosys")
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--pins", action="store_true")
    ap.add_argument("--drop", type=int)
    ap.add_argument("--batch", type=int, default=40)
    ap.add_argument("--limit", type=int, help="first N faults only (timing)")
    a = ap.parse_args()
    a.work.mkdir(parents=True, exist_ok=True)
    head, blocks = load(ROOT / "proof" / (a.name + "_sc.blif"))
    ins = [h for h in head if h.startswith(".inputs")][0].split()[1:]
    W = sum(1 for v in ins if v.startswith("d["))
    nets = [l.split()[-1] for l, _ in blocks if l.split()[-1].startswith("b_")]
    if a.drop is not None:
        alarm_srcs = [l.split()[1:-1] for l, _ in blocks if l.split()[-1].startswith("a_")]
        leaves = [v for s in alarm_srcs for v in s if not v.startswith("a_")]
        pnet, cnet = leaves[2 * a.drop], leaves[2 * a.drop + 1]
        blocks = drop_bit(head, blocks, a.drop, pnet, cnet)
        kinds = ["inv"]
    else:
        kinds = ["inv", "s0", "s1", "free"]
    (a.work / "good.blif").write_text(emit(head, blocks, "sc"))
    jobs = []
    for n in nets:
        for k in kinds:
            text, free = faulty(head, blocks, n, k)
            jobs.append(("%s %s" % (n, k), text, free))
        src = [l for l, _ in blocks if l.split()[-1] == n][0].split()[1:-1]
        if a.pins and a.drop is None:
            for p in range(len(src)):
                for k in ("inv", "s0", "s1"):
                    text, free = faulty(head, blocks, n, k, pin=p)
                    jobs.append(("%s pin%d %s" % (n, p, k), text, free))
        if a.init and a.drop is None:
            for b in range(1 << len(src)):
                text, free = faulty(head, blocks, n, None, bit=b)
                jobs.append(("%s init%d" % (n, b), text, free))
    if a.limit:
        jobs = jobs[:a.limit]
    out = []
    for i in range(0, len(jobs), a.batch):
        out += run_batch(a.yosys, a.work, "b%d" % (i // a.batch), jobs[i:i + a.batch], W)
        done = len(out)
        print("progress %d / %d" % (done, len(jobs)), flush=True)
    tally = {}
    for label, res in out:
        kind = label.split()[-1] if "init" not in label else "init"
        kind = ("pin " + kind) if " pin" in label else kind
        tally.setdefault(kind, {}).setdefault(res, 0)
        tally[kind][res] += 1
    (a.work / "results.txt").write_text("\n".join("%s %s" % x for x in out) + "\n")
    for kind in sorted(tally):
        print("%-8s %s" % (kind, "  ".join("%s %d" % kv for kv in sorted(tally[kind].items()))))
    esc = [label for label, res in out if res != "PROVED"]
    if a.drop is not None:
        print("check bit %d dropped: %d of %d inverted-net faults escape: %s" % (a.drop, len(esc), len(out), " ".join(l.split()[0] for l in esc)))
        raise SystemExit(0)
    print("FAULTS %d  PROVED %d  NOT PROVED %d" % (len(out), len(out) - len(esc), len(esc)))
    raise SystemExit(1 if esc else 0)
