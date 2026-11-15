# usage: python3 sat_faults_mac.py SCDIR LAW.json MODE [--limit SECONDS] [--out FILE]
# Copy of sat_faults.py that takes the pins and the p outputs from the netlist (for the multiply-accumulate: a, b, c in,
# p[0..2N] out); otherwise unchanged.
#
# SAT over all inputs a, b: for each fault, is there an input where p differs from the fault-free p and alarm = 0?
# Each query is one netlist for ABC: the fault-free multiplier (tables of SCDIR/selfcheck.blif, renamed) beside the
# self-checking circuit with the fault, and the single output  bad = (some p[k] differs) and not alarm.
# ABC: strash; sat (MiniSat inside ABC). UNSATISFIABLE = no such input exists.
# MODE:
#   table3   every multiplier table, each of stuck at 0, stuck at 1, inverted (3 queries per table)
#   tablefree every multiplier table replaced by a free input: any wrong function at once (1 query per table)
#   cellfree all outputs of one cell replaced by free inputs: any wrong values at once (1 query per cell)
# Prints one line per satisfiable query (an escape, with the input that shows it) and a summary.
import json
import os
import re
import subprocess
import sys
import tempfile
import time

scdir, lawpath, mode = sys.argv[1], sys.argv[2], sys.argv[3]
limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 600
outf = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
law = json.load(open(lawpath))
n = law["n"]

T, order, outputs, inputs = {}, [], [], []
cur = None
for line in open(os.path.join(scdir, "selfcheck.blif")):
    t = line.split()
    if not t:
        continue
    if t[0] == ".inputs":
        inputs = t[1:]
    elif t[0] == ".outputs":
        outputs = t[1:]
    elif t[0] == ".names":
        cur = t[-1]
        T[cur] = (t[1:-1], [])
        order.append(cur)
    elif t[0].startswith("."):
        cur = None
    elif cur is not None:
        T[cur][1].append(" ".join(t))
PINS = list(inputs)
P = [o for o in outputs if o.startswith("p[")]
mul = [x for x in order if not (x.startswith("d_") or x.startswith("t[") or x == "alarm")]


def table_text(o, ins, rows):
    # ABC refuses a table with inputs and no rows ("SOP has a mismatch between its cover size (0) and its fanin
    # number"); a constant-0 table is written without inputs
    if not rows:
        return ".names %s\n" % o
    return ".names %s %s\n%s" % (" ".join(ins), o, "".join(r + "\n" for r in rows))


def gold_text():
    ren = lambda x: x if x in PINS else "G_" + x
    return "".join(table_text(ren(o), [ren(i) for i in T[o][0]], T[o][1]) for o in mul)


GOLD = gold_text()


def query(faulty, free):
    """faulty: {table: replacement rows or None (free input)}; free: list of free input names."""
    body = []
    for o in order:
        ins, rows = T[o]
        if o in faulty:
            if faulty[o] is None:
                continue
            rows = faulty[o]
        body.append(table_text(o, ins, rows))
    diff = []
    for k in range(len(P)):
        body.append(".names %s G_%s x_%d\n10 1\n01 1\n" % (P[k], P[k], k))
        diff.append("x_%d" % k)
    # bad = OR(diff) and not alarm, as a chain of 2-input tables
    acc = diff[0]
    for i, d in enumerate(diff[1:]):
        body.append(".names %s %s o_%d\n1- 1\n-1 1\n" % (acc, d, i))
        acc = "o_%d" % i
    body.append(".names %s alarm bad\n10 1\n" % acc)
    txt = ".model q\n.inputs %s\n.outputs bad\n%s%s.end\n" % (" ".join(PINS + free), GOLD, "".join(body))
    with tempfile.NamedTemporaryFile("w", suffix=".blif", delete=False) as f:
        f.write(txt)
        path = f.name
    t0 = time.time()
    try:
        r = subprocess.run(["yosys-abc", "-c", "read_blif %s; strash; sat -v" % path], capture_output=True, text=True, timeout=limit)
        out = r.stdout + r.stderr
        if "Reading network from file has failed" in out or "Io_Read" in out:
            sys.exit("ABC could not read the query for %s: %s" % (list(faulty), out.strip()[-400:]))
        verdict = "UNSATISFIABLE" if "UNSATISFIABLE" in out else "SATISFIABLE" if "SATISFIABLE" in out else "UNDECIDED"
        cex = None
        if verdict == "SATISFIABLE":
            r2 = subprocess.run(["yosys-abc", "-c", "read_blif %s; strash; sat; write_cex -n %s.cex" % (path, path)],
                                capture_output=True, text=True, timeout=limit)
            if os.path.exists(path + ".cex"):
                cex = " ".join(open(path + ".cex").read().split())
                os.unlink(path + ".cex")
    except subprocess.TimeoutExpired:
        verdict, cex = "TIMEOUT", None
    os.unlink(path)
    return verdict, round(time.time() - t0, 2), cex


def inverted(o):
    ins, rows = T[o]
    on = {r.split()[0] if ins else "" for r in rows}
    allr = ["".join(str((v >> i) & 1) for i in range(len(ins))) for v in range(1 << len(ins))]
    return [("%s 1" % r) if ins else "1" for r in allr if r not in on]


jobs = []
if mode == "table3":
    for o in mul:
        jobs += [(o, "stuck0", {o: []}, []), (o, "stuck1", {o: ["%s 1" % ("-" * len(T[o][0]))] if T[o][0] else ["1"]}, []),
                 (o, "inverted", {o: inverted(o)}, [])]
elif mode == "tablefree":
    for o in mul:
        jobs.append((o, "free", {o: None}, [o]))
elif mode == "cellfree":
    for ci, c in enumerate(law["cells"]):
        outs = [w for _, w in c["out"]]
        jobs.append(("cell%d:%s" % (ci, "+".join(outs)), "free", {w: None for w in outs}, outs))
counts = {}
t_all = time.time()
worst = 0
# results go to OUT as they come: one line per query (verdict, seconds, fault); a rerun skips the queries already
# written there, so stopping loses nothing
done = {}
if outf and os.path.exists(outf):
    for l in open(outf):
        t = l.split("\t")
        if len(t) >= 4 and t[0] in ("UNSATISFIABLE", "SATISFIABLE", "TIMEOUT", "UNDECIDED"):
            done[(t[2], t[3].strip())] = (t[0], float(t[1]))
log = open(outf, "a") if outf else None
for name, kind, faulty, free in jobs:
    if (name, kind) in done:
        v, dt = done[(name, kind)]
    else:
        v, dt, cex = query(faulty, free)
        if log:
            log.write("%s\t%.2f\t%s\t%s%s\n" % (v, dt, name, kind, ("\tcex " + cex[:300]) if cex else ""))
            log.flush()
        if v != "UNSATISFIABLE":
            print("%s %s %s %s" % (v, name, kind, ("cex " + cex[:200]) if cex else ""), flush=True)
    worst = max(worst, dt)
    counts[v] = counts.get(v, 0) + 1
summary = ("SUMMARY %s N = %d m = %s mode %s: %d queries, %s; slowest %.2f s, this run %.1f s, limit %d s per query"
           % (os.path.basename(scdir), n, json.load(open(os.path.join(scdir, "det.json")))["m"], mode, len(jobs),
              ", ".join("%s %d" % kv for kv in sorted(counts.items())), worst, time.time() - t_all, limit))
print(summary)
if log:
    log.write(summary + "\n")
    log.close()
