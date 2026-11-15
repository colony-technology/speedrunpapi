# usage: python3 check_selfcheck.py SCDIR LAW.json [--claim-b]
#
# Independent check of a self-checking multiplier (SCDIR/selfcheck.blif with SCDIR/det.json; LAW.json is the
# multiplier's law). Shares no code with the generator of the multiplier or with gen_detector.py. Trusts neither JSON file: they only say
# where to look; every statement is checked against the tables of selfcheck.blif.
#
#  1. The multiplier part. Its tables are cut out of selfcheck.blif and given to lawcheck2.py, which must print
#     PROVED: every cell keeps  sum of 2^k x term = sum of 2^k x output  on every row of its tables, every partial
#     product is used once, p[k] is the wire left in column k, and the wires left in columns 2N and up are listed.
#  2. Columns. Every multiplier table is the output of exactly one cell (its column is the one the cell gives it),
#     or the buffer from that wire to p[k] (column k). No other table belongs to the multiplier.
#  3. Detector. Every residue node's tables are checked on every row: the binary value of its outputs is
#     (sum of weight x value of each input group) mod q. The tree for a uses each a[i] once with weight 2^i mod q,
#     and the outputs of each other node once with weight 1; the same for b, and for p with p[k] at 2^k mod q.
#     So the roots hold a mod q, b mod q and p mod q exactly. The mismatch table (or product and compare tables)
#     is checked on every row. The OR tree is checked on every row and uses each of its leaves once: the leaves
#     must be every mismatch output and every wire above the top.
#  4. Separation. The nets of the a and b residues depend on pins only. No multiplier table reads a detector net.
#     The p residues read p[k] and their own nets only.
#  5. The final adder. The cells that leave the wire of p[k] in column k form a ripple: each reads at most three
#     terms of column k and writes column k and column k + 1, and its column k + 1 output is a term of the next
#     one or is above the top. With a carry chain (propagate LUT x ^ y, sum XORCY, carry MUXCY selecting the
#     carry-in when the propagate is 1 and x otherwise), every row of a wrong propagate LUT is checked: the cell's
#     value s + 2c' moves by -1, 0 or +1 only.
#  Claim A (one table wrong): the heap after the wrong table differs from a x b by e x 2^k, e in {-1, 0, 1}, k the
#     table's column, and every later cell carries it on (1). The wires above the top are in the alarm (3), so
#     alarm = 0 implies p = a x b + e x 2^k; 2^k is not 0 modulo m, so e != 0 gives a mismatch.
#  Claim B (every output of one cell wrong): the error is d x 2^k, d between -(largest value of the cell's terms)
#     and (largest value of its outputs); claim B needs no nonzero multiple of m in that range (checked per cell).
import itertools
import json
import os
import subprocess
import sys
import tempfile

scdir, lawpath = sys.argv[1], sys.argv[2]
claim_b = "--claim-b" in sys.argv
law = json.load(open(lawpath))
det = json.load(open(os.path.join(scdir, "det.json")))
n, m = law["n"], det["m"]
mods = det["mods"]
here = os.path.dirname(os.path.abspath(__file__))


def fail(msg):
    print("NOT PROVED: " + msg)
    sys.exit(1)


# ---- read selfcheck.blif
T = {}              # output -> (inputs, set of on rows)
order = []
inputs, outputs = [], []
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
        if cur in T:
            fail("%s driven twice" % cur)
        T[cur] = (t[1:-1], set())
        order.append(cur)
    elif t[0].startswith("."):
        cur = None
    elif cur is not None:
        ins = T[cur][0]
        if ins and len(t) == 2 and t[1] == "1" and len(t[0]) == len(ins) and set(t[0]) <= set("01"):
            T[cur][1].add(t[0])
        elif not ins and t == ["1"]:
            T[cur][1].add("")
        else:
            fail("row of %s is not a plain 0/1 row" % cur)
A = ["a[%d]" % i for i in range(n)]
B = ["b[%d]" % i for i in range(n)]
P = ["p[%d]" % k for k in range(2 * n)]
if inputs != A + B:
    fail("inputs are not a[0..N-1], b[0..N-1]")


def ev(name, v):
    ins, on = T[name]
    return 1 if "".join(str(v[x]) for x in ins) in on else 0


# ---- 1. the multiplier part, through lawcheck2.py
det_nets = {x for x in T if x.startswith("d_")} | {x for x in T if x.startswith("t[")} | {"alarm"}
mul_tables = [x for x in order if x not in det_nets]
with tempfile.TemporaryDirectory() as td:
    with open(os.path.join(td, "mul.blif"), "w") as f:
        f.write(".model mul\n.inputs %s\n.outputs %s\n" % (" ".join(A + B), " ".join(P)))
        for o in mul_tables:
            ins, on = T[o]
            f.write(".names %s %s\n" % (" ".join(ins), o))
            for r in sorted(on):
                f.write(("%s 1\n" % r) if ins else "1\n")
        f.write(".end\n")
    json.dump(law, open(os.path.join(td, "law.json"), "w"))
    r = subprocess.run([sys.executable, "-I", os.path.join(here, "lawcheck2.py"), td], capture_output=True, text=True)
    first = (r.stdout.strip().splitlines() or [""])[0]
    if r.returncode != 0 or not first.startswith("PROVED"):
        fail("lawcheck2.py on the multiplier part: " + (r.stdout + r.stderr).strip()[:300])
law_line = first

# ---- 2. columns
col = {}
cell_of = {}
for ci, c in enumerate(law["cells"]):
    for k, o in c["out"]:
        if o in col:
            fail("wire %s is the output of two cells" % o)
        col[o] = k
        cell_of[o] = ci
for k in range(2 * n):
    w = law["outputs"][k]
    if P[k] not in T:
        fail("%s not driven" % P[k])
    if w is None:
        if T[P[k]] != ([], set()):
            fail("%s should be constant 0" % P[k])
    elif T[P[k]] != ([w], {"1"}):
        fail("%s is not the buffer of %s" % (P[k], w))
    col[P[k]] = k
extra = [x for x in mul_tables if x not in col]
if extra:
    fail("multiplier tables outside every cell: %s" % extra[:5])
for x in mul_tables:
    for i in T[x][0]:
        if i in det_nets:
            fail("multiplier table %s reads detector net %s" % (x, i))
top = list(law["above_the_top"])
for w in top:
    if col.get(w, -1) < 2 * n:
        fail("top wire %s is not above column 2N-1" % w)

# ---- 3. detector
used = set()


def deps(x, seen=None):
    seen = set() if seen is None else seen
    stack = [x]
    while stack:
        y = stack.pop()
        if y in seen:
            continue
        seen.add(y)
        if y in T:
            stack += T[y][0]
    return seen


def width(q):
    return (q - 1).bit_length()


def check_rows(outs, ins, fn):
    """Every row of the tables outs (all reading exactly ins) against fn(values) -> integer."""
    for o in outs:
        if T.get(o, (None,))[0] != ins:
            fail("table %s does not read %s" % (o, ins))
    for r in range(1 << len(ins)):
        v = dict(zip(ins, [(r >> i) & 1 for i in range(len(ins))]))
        got = sum(ev(o, v) << b for b, o in enumerate(outs))
        if got != fn([v[x] for x in ins]):
            fail("tables %s on row %s: %d, expected %d" % (outs, v, got, fn([v[x] for x in ins])))


nodes_by_out = {}
rows_checked = 0
for nd in det["nodes"]:
    outs = nd["out"] if isinstance(nd["out"], list) else [nd["out"]]
    for o in outs:
        if o in nodes_by_out:
            fail("detector net %s made twice" % o)
        nodes_by_out[o] = nd
    if nd["kind"] == "residue":
        q = nd["mod"]
        groups = nd["in"]
        ins = [x for g, _ in groups for x in g]
        if len(outs) != width(q):
            fail("residue node %s: %d outputs" % (outs, len(outs)))

        def fn(vals, groups=groups, q=q):
            s, pos = 0, 0
            for g, w in groups:
                s += w * sum(vals[pos + i] << i for i in range(len(g)))
                pos += len(g)
            return s % q
        check_rows(outs, ins, fn)
        rows_checked += (1 << len(ins)) * len(outs)
    elif nd["kind"] == "mismatch":
        q, k = nd["mod"], width(nd["mod"])
        ins = nd["a"] + nd["b"] + nd["p"]
        val = lambda v, off, k=k: sum(v[off + i] << i for i in range(k))
        check_rows([nd["out"]], ins, lambda v, q=q, k=k: int((val(v, 0) * val(v, k)) % q != val(v, 2 * k) % q))
        rows_checked += 1 << len(ins)
    elif nd["kind"] == "product":
        q, k = nd["mod"], width(nd["mod"])
        val = lambda v, off, k=k: sum(v[off + i] << i for i in range(k))
        check_rows(nd["out"], nd["a"] + nd["b"], lambda v, q=q, k=k: (val(v, 0) * val(v, k)) % q)
        rows_checked += (1 << (2 * k)) * k
    elif nd["kind"] == "compare":
        q, k = nd["mod"], width(nd["mod"])
        val = lambda v, off, k=k: sum(v[off + i] << i for i in range(k))
        check_rows([nd["out"]], nd["x"] + nd["p"], lambda v, q=q, k=k: int(val(v, 0) % q != val(v, k) % q))
        rows_checked += 1 << (2 * k)
    elif nd["kind"] == "or":
        check_rows([nd["out"]], nd["in"], lambda v: int(any(v)))
        rows_checked += 1 << len(nd["in"])
    else:
        fail("unknown detector node %s" % nd["kind"])
undeclared = [x for x in T if x.startswith("d_") and x not in nodes_by_out]
if undeclared:
    fail("detector tables without a statement: %s" % undeclared[:4])


def tree(root, leaves_w, q):
    """The residue tree under root uses each leaf bit once with its weight and every inner node once (weight 1)."""
    seen_leaf, seen_node = {}, set()

    def walk(group):
        nd = nodes_by_out[group[0]]
        if nd["kind"] != "residue" or nd["mod"] != q or nd["out"] != group:
            fail("residue tree: %s is not a residue node modulo %d" % (group, q))
        key = tuple(group)
        if key in seen_node:
            fail("residue node %s used twice" % group)
        seen_node.add(key)
        for g, w in nd["in"]:
            if len(g) == 1 and g[0] in leaves_w:
                if g[0] in seen_leaf:
                    fail("leaf %s used twice" % g[0])
                if w % q != leaves_w[g[0]]:
                    fail("leaf %s has weight %d, not %d" % (g[0], w, leaves_w[g[0]]))
                seen_leaf[g[0]] = w
            else:
                if w != 1:
                    fail("inner group %s has weight %d" % (g, w))
                walk(g)
    walk(root)
    if set(seen_leaf) != set(leaves_w):
        fail("residue tree modulo %d misses leaves %s" % (q, sorted(set(leaves_w) - set(seen_leaf))[:4]))


roots = det["roots"]
for q in mods:
    r = roots[str(q)]
    tree(r["a"], {x: pow(2, i, q) for i, x in enumerate(A)}, q)
    tree(r["b"], {x: pow(2, i, q) for i, x in enumerate(B)}, q)
    tree(r["p"], {x: pow(2, k, q) for k, x in enumerate(P)}, q)
    mis = [nd for nd in det["nodes"] if nd["kind"] in ("mismatch", "compare") and nd["mod"] == q]
    if len(mis) != 1:
        fail("modulo %d: %d mismatch tables" % (q, len(mis)))
    nd = mis[0]
    if nd["kind"] == "mismatch":
        if nd["a"] != r["a"] or nd["b"] != r["b"] or nd["p"] != r["p"]:
            fail("mismatch modulo %d does not read the roots" % q)
    else:
        pr = [x for x in det["nodes"] if x["kind"] == "product" and x["mod"] == q]
        if len(pr) != 1 or pr[0]["a"] != r["a"] or pr[0]["b"] != r["b"] or nd["x"] != pr[0]["out"] or nd["p"] != r["p"]:
            fail("product / compare modulo %d do not read the roots" % q)
mis_outs = [nd["out"] for nd in det["nodes"] if nd["kind"] in ("mismatch", "compare")]
# OR tree: leaves exactly the mismatch outputs and the top wires
want = set(mis_outs) | set(top)
seen = []


def walk_or(x):
    nd = nodes_by_out.get(x)
    if nd is not None and nd["kind"] == "or":
        for y in nd["in"]:
            walk_or(y)
    else:
        seen.append(x)


if T.get("alarm") != ([det["alarm"]], {"1"}):
    fail("alarm is not the buffer of the OR tree's root")
walk_or(det["alarm"])
if len(seen) != len(set(seen)):
    fail("an alarm leaf is used twice")
missing = want - set(seen)
if missing:
    fail("alarm does not read %s" % sorted(missing))
if set(seen) - want:
    fail("alarm reads other nets: %s" % sorted(set(seen) - want))
for i, w in enumerate(top):
    if T.get("t[%d]" % i) != ([w], {"1"}) or "t[%d]" % i not in outputs:
        fail("top wire %s is not brought out as t[%d]" % (w, i))

# ---- 4. separation
pins = set(A + B)
for q in mods:
    r = roots[str(q)]
    for g in (r["a"], r["b"]):
        for x in g:
            bad = [y for y in deps(x) if y not in pins and not y.startswith("d_")]
            if bad:
                fail("residue net %s depends on %s" % (x, bad[:3]))
    for x in r["p"]:
        for y in deps(x):
            if y.startswith("d_"):
                for z in T[y][0]:
                    if not z.startswith("d_") and z not in P:
                        fail("p residue net %s reads %s" % (y, z))

# ---- 5. final adder and carry chain: the cell that leaves the wire of p[k], for each column k
by_col, kinds = {}, {"adder": 0, "and": 0, "tree": 0}
for k in range(2 * n):
    w = law["outputs"][k]
    if w is None:
        continue
    ci = cell_of[w]
    c = law["cells"][ci]
    if c["out"][0] != [k, w]:
        fail("the wire of p[%d] is not the lowest output of its cell" % k)
    cols_out = [kk for kk, _ in c["out"]]
    if cols_out == [k, k + 1] and 2 <= len(c["in"]) <= 3 and all(t[0] == k for t in c["in"]):
        by_col[k] = ci
        kinds["adder"] += 1
    elif cols_out == [k] and len(c["in"]) == 1:
        kinds["and"] += 1
    else:
        kinds["tree"] += 1
for k, ci in by_col.items():
    c = law["cells"][ci]
    carry = c["out"][1][1]
    nxt = by_col.get(k + 1)
    reads = nxt is not None and any(t[1] == "w" and t[2] == carry for t in law["cells"][nxt]["in"])
    if not reads and carry not in top:
        fail("carry of column %d goes neither to the adder of column %d nor above the top" % (k, k + 1))
ripple_cols = sorted(by_col)
if ripple_cols != list(range(ripple_cols[0], ripple_cols[-1] + 1)):
    fail("the adder cells do not form one unbroken ripple: columns %s" % ripple_cols)
chain = set()
for x, y, c in itertools.product((0, 1), repeat=3):
    pr = x ^ y
    for wrong in (0, 1):
        pp = pr ^ wrong
        s = pp ^ c
        co = c if pp else x
        if not wrong and s + 2 * co != x + y + c:
            fail("carry-chain model is not a full adder")
        chain.add(s + 2 * co - (x + y + c))
if not chain <= {-1, 0, 1}:
    fail("carry chain: a wrong propagate LUT moves the value by %s" % sorted(chain))

# ---- claims
colset = sorted(set(col.values()))
for k in colset:
    if pow(2, k, m) == 0:
        fail("2^%d is 0 modulo %d" % (k, m))
print(law_line)
print("  multiplier tables %d (%d cells, %d p buffers), columns %d..%d; detector tables %d, %d rows checked; "
      "alarm leaves %d (%d mismatch, %d above the top); p wires from %d adder cells in one ripple over "
      "columns %d..%d, %d single AND cells, %d tree cells"
      % (len(mul_tables), len(law["cells"]), 2 * n, colset[0], colset[-1], len([x for x in T if x.startswith("d_")]),
         rows_checked, len(seen), len(mis_outs), len(top), kinds["adder"], ripple_cols[0], ripple_cols[-1], kinds["and"], kinds["tree"]))
print("PROVED claim A: N = %d, m = %d. For every a, b below 2^%d and every one lookup table of the multiplier with a "
      "wrong output (any wrong function), p != a x b implies alarm = 1. Also with the final adder on a carry chain, "
      "for a wrong propagate LUT." % (n, m, n))
if claim_b:
    worst = []
    for ci, c in enumerate(law["cells"]):
        base = min(t[0] for t in c["in"])
        tmax = sum(1 << (t[0] - base) for t in c["in"])
        omax = sum(1 << (k - base) for k, _ in c["out"])
        bad = [d for d in range(-tmax, omax + 1) if d != 0 and d % m == 0]
        if bad:
            worst.append((ci, base, tmax, omax, bad[:3]))
    if worst:
        ci, base, tmax, omax, bad = worst[0]
        print("NOT PROVED claim B: N = %d, m = %d. %d of %d cells admit a nonzero multiple of %d; first: cell %d (column %d), "
              "d from -%d to %d includes %s." % (n, m, len(worst), len(law["cells"]), m, ci, base, tmax, omax, bad))
        sys.exit(2)
    rng = max(sum(1 << (k - min(t[0] for t in c["in"])) for k, _ in c["out"]) for c in law["cells"])
    tr = max(sum(1 << (t[0] - min(tt[0] for tt in c["in"])) for t in c["in"]) for c in law["cells"])
    print("PROVED claim B: N = %d, m = %d. All outputs of one cell wrong at once: d lies in -%d..%d over all %d cells "
          "(p buffers: -1..1), no nonzero multiple of %d, and p != a x b implies alarm = 1." % (n, m, tr, rng, len(law["cells"]), m))
