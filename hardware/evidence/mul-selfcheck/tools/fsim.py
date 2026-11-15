# usage: python3 fsim.py SCDIR LAW.json FAULTSET OUTDIR [--random R] [--seed S]
#
# Fault simulation of a self-checking multiplier. selfcheck.blif is compiled to C, 64 input pairs per machine word;
# for each fault the netlist is re-evaluated from the first wrong table on, and over all pairs it counts
#   wrong  = pairs where p != a x b,   alarm  = pairs where alarm = 1,   escape = pairs where p != a x b and alarm = 0.
# The fault-free run is checked first: p = a x b and alarm = 0 on every pair.
# FAULTSET:
#   table3   every multiplier table (cells, p buffers, the wires above the top), stuck at 0, stuck at 1, inverted
#   cell     every cell: every nonempty set of its outputs inverted, and its outputs held at every constant value
# Pairs: the corners and R random pairs (default 1024). Corners, with C = {0, 1, 2^N - 1, 2^i for every i}:
#   N <= 32: every pair of C x C;  N = 64: (x, y) and (y, x) for x in C and y in {0, 1, 2^N - 1}, and (2^i, 2^i).
# Writes OUTDIR/fsim_FAULTSET.txt (summary and every escape) and OUTDIR/fsim_FAULTSET.tsv (one line per fault).
import itertools
import json
import os
import random
import subprocess
import sys
import time

scdir, lawpath, fset, outdir = sys.argv[1:5]
R = int(sys.argv[sys.argv.index("--random") + 1]) if "--random" in sys.argv else 1024
seed = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 2026
law = json.load(open(lawpath))
n = law["n"]
os.makedirs(outdir, exist_ok=True)

T, order = {}, []
cur = None
for line in open(os.path.join(scdir, "selfcheck.blif")):
    t = line.split()
    if not t:
        continue
    if t[0] == ".names":
        cur = t[-1]
        T[cur] = (t[1:-1], set())
        order.append(cur)
    elif t[0].startswith("."):
        cur = None
    elif cur is not None:
        T[cur][1].add(t[0] if T[cur][0] else "")
A = ["a[%d]" % i for i in range(n)]
B = ["b[%d]" % i for i in range(n)]
P = ["p[%d]" % k for k in range(2 * n)]
idx = {x: i for i, x in enumerate(A + B + order)}
NP = 2 * n
mul = [x for x in order if not (x.startswith("d_") or x.startswith("t[") or x == "alarm")]
for x in order:
    for i in T[x][0]:
        if idx[i] >= idx[x]:
            sys.exit("not in topological order: %s reads %s" % (x, i))


def cexpr(ins, on):
    """C expression of the table on 64-bit words; rows: ins[0] is the first character."""
    k = len(ins)
    tt = [1 if "".join(str((r >> i) & 1) for i in range(k)) in on else 0 for r in range(1 << k)]
    memo = {}

    def rec(tt, j):          # tt over variables 0..j-1
        key = (tuple(tt), j)
        if key in memo:
            return memo[key]
        if all(x == 0 for x in tt):
            e = "0ULL"
        elif all(x == 1 for x in tt):
            e = "~0ULL"
        else:
            v = "v[%d]" % idx[ins[j - 1]]
            h = len(tt) // 2
            f0, f1 = tt[:h], tt[h:]
            if f0 == f1:
                e = rec(f0, j - 1)
            elif f1 == [1 - x for x in f0]:
                e = "(%s ^ %s)" % (v, rec(f0, j - 1))
            elif all(x == 0 for x in f0):
                e = "(%s & %s)" % (v, rec(f1, j - 1))
            elif all(x == 0 for x in f1):
                e = "(~%s & %s)" % (v, rec(f0, j - 1))
            elif all(x == 1 for x in f0):
                e = "(~%s | %s)" % (v, rec(f1, j - 1))
            elif all(x == 1 for x in f1):
                e = "(%s | %s)" % (v, rec(f0, j - 1))
            else:
                a0, a1 = rec(f0, j - 1), rec(f1, j - 1)
                e = "(%s ^ (%s & (%s ^ %s)))" % (a0, v, a0, a1)
        memo[key] = e
        return e
    # row index r has bit i = value of ins[i]; split on the highest variable first
    return rec(tt, k)


# ---- input pairs
full = (1 << n) - 1
C = [0, 1, full] + [1 << i for i in range(n)]
C = list(dict.fromkeys(C))
if n <= 32:
    pairs = list(itertools.product(C, C))
else:
    pairs = []
    for x in C:
        for y in (0, 1, full):
            pairs += [(x, y), (y, x)]
    pairs += [(1 << i, 1 << i) for i in range(n)]
    pairs = list(dict.fromkeys(pairs))
ncorner = len(pairs)
rng = random.Random(seed)
pairs += [(rng.getrandbits(n), rng.getrandbits(n)) for _ in range(R)]
W = (len(pairs) + 63) // 64
pairs += [(0, 0)] * (64 * W - len(pairs))

# ---- faults: list of (label, [(table, code)]); code 1 stuck 0, 2 stuck 1, 3 inverted
faults = []
if fset == "table3":
    for x in mul:
        for code, nm in ((1, "stuck0"), (2, "stuck1"), (3, "inverted")):
            faults.append(("%s %s" % (x, nm), [(x, code)]))
elif fset == "cell":
    for ci, c in enumerate(law["cells"]):
        outs = [w for _, w in c["out"]]
        for r in range(1, len(outs) + 1):
            for sub in itertools.combinations(outs, r):
                faults.append(("cell%d invert %s" % (ci, "+".join(sub)), [(w, 3) for w in sub]))
        for val in range(1 << len(outs)):
            faults.append(("cell%d hold %d" % (ci, val), [(w, 2 if (val >> b) & 1 else 1) for b, w in enumerate(outs)]))
else:
    sys.exit("unknown fault set")

# ---- C source
src = os.path.join(outdir, "fsim_%s.c" % fset)
NV = len(idx)
# the tables go into chunks of CH, one C file each, compiled one at a time (small compiler memory)
CH = 400
chunks = [order[i:i + CH] for i in range(0, len(order), CH)]
srcs = []
for ci, part in enumerate(chunks):
    cp = os.path.join(outdir, "fsim_%s_c%03d.c" % (fset, ci))
    with open(cp, "w") as f:
        f.write("#include <stdint.h>\nextern uint64_t v[]; extern unsigned char ft[];\n")
        f.write("static inline uint64_t F(uint64_t x, int c) { return c == 1 ? 0ULL : c == 2 ? ~0ULL : c == 3 ? ~x : x; }\n")
        f.write("void eval%d(int from) {\n  switch (from) {\n  default:\n" % ci)
        for x in part:
            i = idx[x]
            f.write("  case %d: v[%d] = %s; if (ft[%d]) v[%d] = F(v[%d], ft[%d]);\n" % (i, i, cexpr(*T[x]), i, i, i, i))
        f.write("  }\n}\n")
    srcs.append(cp)
starts = [idx[p[0]] for p in chunks]
with open(src, "w") as f:
    f.write("#include <stdio.h>\n#include <stdint.h>\n#include <string.h>\n#include <stdlib.h>\n")
    f.write("uint64_t v[%d]; unsigned char ft[%d];\n" % (NV, NV))
    for ci in range(len(chunks)):
        f.write("void eval%d(int from);\n" % ci)
    f.write("typedef void (*evf)(int);\nstatic const evf evs[%d] = {%s};\n" % (len(chunks), ",".join("eval%d" % ci for ci in range(len(chunks)))))
    f.write("static const int cstart[%d] = {%s};\n" % (len(chunks), ",".join(map(str, starts))))
    f.write("static void eval(int from) {\n  int k = 0;\n  while (k + 1 < %d && cstart[k + 1] <= from) k++;\n"
            "  evs[k](from);\n  for (k = k + 1; k < %d; k++) evs[k](-1);\n}\n" % (len(chunks), len(chunks)))
    f.write("int main(void) {\n")
    f.write("  static const uint64_t pin[%d][%d] = {\n" % (W, NP))
    for w in range(W):
        rowv = []
        for i in range(n):
            rowv.append(sum(((pairs[64 * w + j][0] >> i) & 1) << j for j in range(64)))
        for i in range(n):
            rowv.append(sum(((pairs[64 * w + j][1] >> i) & 1) << j for j in range(64)))
        f.write("    {%s},\n" % ",".join("0x%xULL" % x for x in rowv))
    f.write("  };\n")
    f.write("  static const uint64_t exp_[%d][%d] = {\n" % (W, 2 * n))
    for w in range(W):
        prods = [pairs[64 * w + j][0] * pairs[64 * w + j][1] for j in range(64)]
        f.write("    {%s},\n" % ",".join("0x%xULL" % sum(((prods[j] >> k) & 1) << j for j in range(64)) for k in range(2 * n)))
    f.write("  };\n")
    f.write("  static const int pidx[%d] = {%s};\n" % (2 * n, ",".join(str(idx[x]) for x in P)))
    f.write("  const int alarm = %d;\n" % idx["alarm"])
    nf = len(faults)
    flat = [(fi, idx[t], c) for fi, (_, lst) in enumerate(faults) for t, c in lst]
    f.write("  static const int fstart[%d] = {%s};\n" % (nf + 1, ",".join(str(x) for x in
            [0] + list(itertools.accumulate(len(l) for _, l in faults)))))
    f.write("  static const int ftab[%d] = {%s};\n  static const unsigned char fcode[%d] = {%s};\n" % (
        len(flat), ",".join(str(t) for _, t, _ in flat), len(flat), ",".join(str(c) for _, _, c in flat)))
    f.write("""  static uint64_t base[%d];
  static long wrong[%d], alarmed[%d], esc[%d]; static int escw[%d]; static uint64_t escm[%d];
  long basebad = 0, basealarm = 0;
  for (int i = 0; i < %d; i++) escw[i] = -1;
  for (int w = 0; w < %d; w++) {
    memset(ft, 0, sizeof ft);
    for (int i = 0; i < %d; i++) v[i] = pin[w][i];
    eval(%d);
    for (int k = 0; k < %d; k++) basebad += __builtin_popcountll(v[pidx[k]] ^ exp_[w][k]);
    basealarm += __builtin_popcountll(v[alarm]);
    memcpy(base, v, sizeof v);
    for (int fi = 0; fi < %d; fi++) {
      int first = %d;
      for (int j = fstart[fi]; j < fstart[fi + 1]; j++) { ft[ftab[j]] = fcode[j]; if (ftab[j] < first) first = ftab[j]; }
      eval(first);
      uint64_t bad = 0;
      for (int k = 0; k < %d; k++) bad |= v[pidx[k]] ^ exp_[w][k];
      uint64_t e = bad & ~v[alarm];
      wrong[fi] += __builtin_popcountll(bad); alarmed[fi] += __builtin_popcountll(v[alarm]); esc[fi] += __builtin_popcountll(e);
      if (e && escw[fi] < 0) { escw[fi] = w; escm[fi] = e; }
      for (int j = fstart[fi]; j < fstart[fi + 1]; j++) ft[ftab[j]] = 0;
      memcpy(v + first, base + first, sizeof(uint64_t) * (%d - first));
    }
  }
  printf("BASE %%ld %%ld\\n", basebad, basealarm);
  for (int fi = 0; fi < %d; fi++) printf("F %%d %%ld %%ld %%ld %%d %%llu\\n", fi, wrong[fi], alarmed[fi], esc[fi], escw[fi], (unsigned long long)escm[fi]);
  return 0;
}
""" % (NV, nf, nf, nf, nf, nf, nf, W, NP, NP, 2 * n, nf, NV, 2 * n, NV, nf))
exe = src[:-2]
t0 = time.time()
objs = []
for s in srcs + [src]:
    r = subprocess.run(["cc", "-O1", "-c", "-o", s[:-2] + ".o", s], capture_output=True, text=True)
    if r.returncode:
        sys.exit("cc failed on %s: %s" % (s, r.stderr[-1500:]))
    objs.append(s[:-2] + ".o")
r = subprocess.run(["cc", "-o", exe] + objs, capture_output=True, text=True)
if r.returncode:
    sys.exit("link failed: " + r.stderr[-1500:])
tc = time.time() - t0
t0 = time.time()
r = subprocess.run([exe], capture_output=True, text=True)
ts = time.time() - t0
lines = r.stdout.splitlines()
basebad, basealarm = map(int, lines[0].split()[1:])
rows, escapes = [], []
tot = dict(faults=len(faults), wrong_faults=0, wrong_pairs=0, alarms_on_wrong=0, escapes=0, false_alarm_pairs=0)
for l in lines[1:]:
    _, fi, wr, al, es, ew, em = l.split()
    fi, wr, al, es, ew, em = int(fi), int(wr), int(al), int(es), int(ew), int(em)
    label = faults[fi][0]
    rows.append("%s\t%d\t%d\t%d" % (label, wr, al, es))
    tot["wrong_faults"] += wr > 0
    tot["wrong_pairs"] += wr
    tot["escapes"] += es
    tot["alarms_on_wrong"] += wr - es
    tot["false_alarm_pairs"] += al - (wr - es)
    if es:
        j = (em & -em).bit_length() - 1
        a, b = pairs[64 * ew + j]
        escapes.append("ESCAPE %s: a = %d, b = %d, a x b = %d" % (label, a, b, a * b))
with open(os.path.join(outdir, "fsim_%s.tsv" % fset), "w") as f:
    f.write("fault\twrong pairs\talarm pairs\tescapes\n" + "\n".join(rows) + "\n")
summary = ("%s, N = %d, m = %d, faults %s: %d faults over %d pairs (%d corner, %d random, seed %d). Fault-free: %d wrong "
           "product bits, %d alarms. Faults that make some product wrong: %d. Wrong (fault, pair) cases: %d; with alarm: %d; "
           "escapes: %d. Alarms with a right product: %d. Compile %.1f s, run %.1f s."
           % (os.path.basename(scdir), n, json.load(open(os.path.join(scdir, "det.json")))["m"], fset, len(faults),
              ncorner + R, ncorner, R, seed, basebad, basealarm, tot["wrong_faults"], tot["wrong_pairs"], tot["alarms_on_wrong"],
              tot["escapes"], tot["false_alarm_pairs"], tc, ts))
with open(os.path.join(outdir, "fsim_%s.txt" % fset), "w") as f:
    f.write(summary + "\n" + "\n".join(escapes[:50]) + ("\n... %d escaping faults in all\n" % len(escapes) if len(escapes) > 50 else "\n"))
print(summary)
for e in escapes[:5]:
    print(e)
