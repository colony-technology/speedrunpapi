#!/usr/bin/env python3
"""bvfsm: equality of width-generic bit-vector descriptions on words of every length.

A description (.bv file) defines, for every word length N >= Lmin, a function from input vectors (bit i of
every vector is letter i, read least significant bit first) and scalar inputs to output vectors and scalars.

    length N >= 6                     word length parameter and its least value
    input sig, mask : N-1             vectors of width N-1 (bits at positions >= width are 0)
    input m2, m1, m0, sign : bit      scalar inputs (one bit for the whole word)
    assume ones_below(mask)           mask = 2^R - 1 for some R (a run of ones from bit 0, then zeros)
    assume bit(mask,0) & bit(mask,1)  any scalar expression: it must be 1
    let name = expr                   width: the largest operand width
    let name : N-2 = expr             truncated to width N-2
    output name                       or  output name = expr
Expressions follow Verilog's unsigned semantics: ~ & | ^ (bitwise), + - (modulo the width), >> k, << k
(constant k), c ? a : b (c a scalar), 0 and 1 (scalars). A scalar used as a vector operand is
zero-extended (it is bit 0), as Verilog does. Functions giving scalars: orr(v) (OR-reduction), bit(v,k)
(bit k), top(v,k) (bit N-1-k), eq(a,b), lt(a,b) (unsigned), cout(a,b) (carry out of the N-bit sum a+b).

Method. Each description compiles to a finite automaton over letters (the input bits at one position).
Scalars computed from vectors are guessed at the start and checked when their value is known; a right
shift by k guesses its output bit and checks it k letters later; truncation to width N-c uses one guess,
shared by both descriptions, of the position c letters before the end. Bitwise operations are stateless,
shifts hold k bits, add and subtract hold one carry. Two descriptions are equal on every length exactly
when no word is accepted by both with different outputs: a breadth-first search of the product decides
it and returns a shortest counterexample.

usage:
    bvfsm.py equiv A.bv B.bv            decide equality for every N >= max(Lmin); print a shortest counterexample
    bvfsm.py selftest A.bv NMAX COUNT   compare the automaton with direct integer evaluation on random words
    bvfsm.py eval A.bv N name=value ... direct integer evaluation at one length
    bvfsm.py states A.bv PHASEVEC [MARKBIT]  phase-state counts of a machine for A's outputs (see count_states)
"""
import itertools
import random
import re
import sys
from collections import deque

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))

# ----------------------------------------------------------------------------------------------- parsing


class Node:
    __slots__ = ("id", "kind", "args", "k", "woff", "name")

    def __init__(self, kind, args, k, woff, name=None):
        self.kind, self.args, self.k, self.woff, self.name = kind, args, k, woff, name

    @property
    def scalar(self):
        return self.woff is None


TOKEN = re.compile(r"\s*(?:(\d+)|([A-Za-z_][A-Za-z_0-9]*)|(>>|<<|[~&|^+\-?:(),]))")


def tokenize(s):
    pos, out = 0, []
    s = s.strip()
    while pos < len(s):
        m = TOKEN.match(s, pos)
        if not m or m.end() == pos:
            raise SyntaxError("cannot read %r" % s[pos:])
        out.append(m.group(1) or m.group(2) or m.group(3))
        pos = m.end()
    return out


def parse_width(s):
    s = s.replace(" ", "")
    if s == "bit":
        return None
    m = re.fullmatch(r"N([+-]\d+)?", s)
    if not m:
        raise SyntaxError("width must be N, N-c or bit: %r" % s)
    c = int(m.group(1) or 0)
    if c > 0:
        raise SyntaxError("widths above N are not supported: %r" % s)
    return c


class Desc:
    def __init__(self, path):
        self.path = path
        self.nodes = []
        self.memo = {}
        self.names = {}
        self.inputs_vec = []      # (name, node)
        self.inputs_sc = []
        self.assumes_sc = []      # scalar nodes that must be 1
        self.thermo = []          # vector nodes that must be ones_below
        self.onehot = []          # vector nodes that must have exactly one bit set
        self.outputs = []         # (name, node)
        self.lmin = 1
        for lineno, raw in enumerate(open(path), 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            try:
                self.statement(line)
            except SyntaxError as e:
                raise SystemExit("%s:%d: %s" % (path, lineno, e))
        self.finish()

    # node construction with sharing of equal subexpressions
    def mk(self, kind, args=(), k=None, woff=None, name=None):
        key = (kind, tuple(a.id for a in args), k, woff, name if kind in ("in", "insc") else None)
        if key in self.memo:
            return self.memo[key]
        n = Node(kind, tuple(args), k, woff, name)
        n.id = len(self.nodes)
        self.nodes.append(n)
        self.memo[key] = n
        return n

    def statement(self, line):
        m = re.fullmatch(r"length\s+N\s*>=\s*(\d+)", line)
        if m:
            self.lmin = int(m.group(1))
            return
        m = re.fullmatch(r"input\s+(.+?)\s*:\s*(\S.*)", line)
        if m:
            w = parse_width(m.group(2))
            for nm in [x.strip() for x in m.group(1).split(",")]:
                if w is None:
                    n = self.mk("insc", name=nm)
                    self.inputs_sc.append((nm, n))
                else:
                    n = self.mk("in", woff=w, name=nm)
                    self.inputs_vec.append((nm, n))
                self.names[nm] = n
            return
        m = re.fullmatch(r"assume\s+ones_below\(\s*([A-Za-z_]\w*)\s*\)", line)
        if m:
            n = self.names[m.group(1)]
            if n.scalar:
                raise SyntaxError("ones_below needs a vector")
            self.thermo.append(n)
            return
        m = re.fullmatch(r"assume\s+onehot\(\s*([A-Za-z_]\w*)\s*\)", line)
        if m:
            n = self.names[m.group(1)]
            if n.scalar:
                raise SyntaxError("onehot needs a vector")
            self.onehot.append(n)
            return
        m = re.fullmatch(r"assume\s+(.+)", line)
        if m:
            n = self.expr(m.group(1))
            if not n.scalar:
                raise SyntaxError("assume needs a scalar expression")
            self.assumes_sc.append(n)
            return
        m = re.fullmatch(r"let\s+([A-Za-z_]\w*)\s*(?::\s*([^=]+?))?\s*=\s*(.+)", line)
        if m:
            n = self.expr(m.group(3))
            if m.group(2):
                w = parse_width(m.group(2))
                if (w is None) != n.scalar:
                    raise SyntaxError("width does not match the expression's kind")
                if w is not None and w < n.woff:
                    n = self.mk("trunc", (n,), woff=w)
                elif w is not None and w > n.woff:
                    # Widening is a zero-extension of a named value. Verilog would instead evaluate the
                    # whole expression at the wider width, so widening an expression is refused: widen
                    # its operands first.
                    if not re.fullmatch(r"[A-Za-z_]\w*", m.group(3).strip()):
                        raise SyntaxError("widen a name, not an expression (Verilog would widen the operation)")
                    n = self.mk("ext", (n,), woff=w)
            self.names[m.group(1)] = n
            return
        m = re.fullmatch(r"output\s+([A-Za-z_]\w*)(?:\s*=\s*(.+))?", line)
        if m:
            n = self.expr(m.group(2)) if m.group(2) else self.names[m.group(1)]
            self.outputs.append((m.group(1), n))
            return
        raise SyntaxError("cannot read statement %r" % line)

    # expression parser: ?:  |  ^  &  << >>  + -  ~
    def expr(self, s):
        self.toks = tokenize(s)
        self.tp = 0
        n = self.p_cond()
        if self.tp != len(self.toks):
            raise SyntaxError("trailing text in %r" % s)
        return n

    def peek(self):
        return self.toks[self.tp] if self.tp < len(self.toks) else None

    def take(self, t=None):
        x = self.peek()
        if t is not None and x != t:
            raise SyntaxError("expected %r, found %r" % (t, x))
        self.tp += 1
        return x

    def p_cond(self):
        c = self.p_bin(0)
        if self.peek() == "?":
            self.take()
            a = self.p_cond()
            self.take(":")
            b = self.p_cond()
            if not c.scalar:
                raise SyntaxError("the condition of ?: must be a scalar")
            return self.mk("sel", (c, a, b), woff=wmax(a, b))
        return c

    LEVELS = [("|",), ("^",), ("&",), (">>", "<<"), ("+", "-")]

    def p_bin(self, lv):
        if lv == len(self.LEVELS):
            return self.p_unary()
        a = self.p_bin(lv + 1)
        while self.peek() in self.LEVELS[lv]:
            op = self.take()
            if op in (">>", "<<"):
                k = int(self.take())
                if a.scalar:
                    raise SyntaxError("shift of a scalar")
                a = self.mk("shr" if op == ">>" else "shl", (a,), k=k, woff=a.woff)
                continue
            b = self.p_bin(lv + 1)
            kind = {"|": "or", "^": "xor", "&": "and", "+": "add", "-": "sub"}[op]
            if kind in ("add", "sub") and a.scalar and b.scalar:
                raise SyntaxError("add of two scalars")
            a = self.mk(kind, (a, b), woff=wmax(a, b))
        return a

    def p_unary(self):
        if self.peek() == "~":
            self.take()
            a = self.p_unary()
            return self.mk("not", (a,), woff=a.woff)
        return self.p_prim()

    def p_prim(self):
        t = self.take()
        if t == "(":
            n = self.p_cond()
            self.take(")")
            return n
        if t is None:
            raise SyntaxError("unexpected end")
        if t.isdigit():
            if t not in ("0", "1"):
                raise SyntaxError("constants are 0 and 1")
            return self.mk("const", k=int(t))
        if self.peek() == "(":
            self.take()
            args = [self.p_cond()]
            while self.peek() == ",":
                self.take()
                if self.peek() and self.peek().isdigit() and t in ("bit", "top"):
                    args.append(int(self.take()))
                else:
                    args.append(self.p_cond())
            self.take(")")
            return self.func(t, args)
        if t not in self.names:
            raise SyntaxError("unknown name %r" % t)
        return self.names[t]

    def func(self, f, args):
        if f == "preor" and len(args) == 1 and not args[0].scalar:
            return self.mk("preor", (args[0],), woff=args[0].woff)
        if f == "orr" and len(args) == 1 and not args[0].scalar:
            return self.mk("orr", (args[0],))
        if f in ("bit", "top") and len(args) == 2 and isinstance(args[1], int) and not args[0].scalar:
            return self.mk(f, (args[0],), k=args[1])
        if f in ("eq", "lt", "cout") and len(args) == 2 and not (args[0].scalar and args[1].scalar):
            return self.mk(f, (args[0], args[1]))
        raise SyntaxError("bad call %s(...)" % f)

    def finish(self):
        self.ks = [n.k for n in self.nodes if n.kind == "bit"]
        self.trunc_depth = max([-n.woff for n in self.nodes if not n.scalar] + [0])
        # A scalar whose value reaches only outputs (through scalar operations) is "late": it is computed
        # from the state at the end of the word, so it needs no guess. Assumed scalars are checked at the
        # start, so they and what feeds them are guessed.
        cons = {n.id: [] for n in self.nodes}
        for n in self.nodes:
            for a in n.args:
                cons[a.id].append(n)
        early = set(x.id for x in self.assumes_sc)
        self.late = set()
        for n in reversed(self.nodes):
            if (n.scalar and n.kind not in ("insc", "const") and n.id not in early
                    and all(c.id in self.late for c in cons[n.id])):
                self.late.add(n.id)
        self.guessed = [n for n in self.nodes if n.kind in GUESS_KINDS and n.id not in self.late]
        self.shr = [n for n in self.nodes if n.kind == "shr"]
        names = [nm for nm, _ in self.outputs]
        if len(set(names)) != len(names):
            raise SystemExit("%s: repeated output name" % self.path)


GUESS_KINDS = ("orr", "bit", "top", "eq", "lt", "cout")


def wmax(a, b):
    if a.scalar and b.scalar:
        return None
    if a.scalar:
        return b.woff
    if b.scalar:
        return a.woff
    return max(a.woff, b.woff)


# ------------------------------------------------------------------------------------- direct evaluation


def evaluate(d, N, vin, sin):
    """Integer semantics at length N. vin: name -> int, sin: name -> 0/1. Returns dict name -> value of
    every node id, and the outputs; raises nothing on violated assumptions (returns ok flag)."""
    val = {}
    for n in d.nodes:
        width = None if n.scalar else N + n.woff
        mask = None if width is None else (1 << width) - 1
        a = [val[x.id] for x in n.args]
        k = n.kind
        if k == "in":
            v = vin[n.name] & mask
        elif k == "insc":
            v = sin[n.name] & 1
        elif k == "const":
            v = n.k
        elif k == "not":
            v = (~a[0]) & (mask if mask is not None else 1)
        elif k == "and":
            v = a[0] & a[1]
        elif k == "or":
            v = a[0] | a[1]
        elif k == "xor":
            v = a[0] ^ a[1]
        elif k == "add":
            v = (a[0] + a[1]) & mask
        elif k == "sub":
            v = (a[0] - a[1]) & mask
        elif k == "shr":
            v = (a[0] >> n.k) & mask
        elif k == "shl":
            v = (a[0] << n.k) & mask
        elif k == "sel":
            v = a[1] if a[0] else a[2]
        elif k in ("trunc", "ext"):
            v = a[0] & mask
        elif k == "preor":
            v = 0
            for j in range(1, width + 1):
                if a[0] & ((1 << (j - 1)) * 2 - 1) and j < width:
                    v |= 1 << j
        elif k == "orr":
            v = int(a[0] != 0)
        elif k == "bit":
            v = (a[0] >> n.k) & 1
        elif k == "top":
            v = (a[0] >> (N - 1 - n.k)) & 1
        elif k == "eq":
            v = int(a[0] == a[1])
        elif k == "lt":
            v = int(a[0] < a[1])
        elif k == "cout":
            v = ((a[0] + a[1]) >> N) & 1
        else:
            raise ValueError(k)
        if mask is not None:
            v &= mask
        val[n.id] = v
    ok = (all(val[n.id] == 1 for n in d.assumes_sc) and all((val[n.id] & (val[n.id] + 1)) == 0 for n in d.thermo)
          and all(bin(val[n.id]).count("1") == 1 for n in d.onehot))
    return ok, {nm: val[n.id] for nm, n in d.outputs}


# --------------------------------------------------------------------------------------------- automaton
#
# A description state is a tuple: one entry per node that has state, in node order, plus the guessed
# scalars (fixed for the run). Shared context per letter: pc (letters read so far, capped), rem (letters
# left including this one, or None while the end is more than trunc_depth letters away).


class Auto:
    def __init__(self, d, depth, cap):
        self.d = d
        self.depth = depth          # shared truncation depth
        self.cap = cap              # pc cap
        self.slot = {}
        idx = 0
        for n in d.nodes:
            if n.kind in ("shl", "shr", "add", "sub", "preor", "orr", "bit", "top", "eq", "lt", "cout"):
                self.slot[n.id] = idx
                idx += 1
        self.nthermo = len(d.thermo) + len(d.onehot)
        self.nslots = idx
        self.gidx = {n.id: i for i, n in enumerate(d.guessed)}
        self.memo = {}

    def initial(self):
        """All start states: one per assignment of the guessed scalars."""
        out = []
        for g in itertools.product((0, 1), repeat=len(self.d.guessed)):
            st = []
            for n in self.d.nodes:
                if n.id not in self.slot:
                    continue
                if n.kind == "shl":
                    st.append((0,) * n.k)
                elif n.kind == "shr":
                    st.append(())
                elif n.kind == "top":
                    st.append((0,) * (n.k + 1))
                else:
                    st.append(0)
            st += [0] * self.nthermo
            out.append((tuple(st), g))
        return out

    def trim(self, limit=200000):
        """Empty the step cache when it grows past limit entries (it is only a cache)."""
        if len(self.memo) > limit:
            self.memo.clear()

    def step(self, state, letter, sin, pc, rem):
        """letter: tuple of input-vector bits in d.inputs_vec order. Returns list of (state', outputs)
        where outputs is a tuple of output bits at this position (scalars give their constant)."""
        key = (state, letter, sin, pc, rem)
        r = self.memo.get(key)
        if r is not None:
            return r
        st, g = state
        d = self.d
        res = []
        for sg in itertools.product((0, 1), repeat=len(d.shr)):
            r1 = self._step1(st, g, letter, sin, pc, rem, sg)
            if r1 is not None:
                res.append(r1)
        res = tuple(res)
        self.memo[key] = res
        return res

    def _step1(self, st, g, letter, sin, pc, rem, sg):
        d = self.d
        val = {}
        new = list(st)
        shr_i = 0
        vin = dict(zip((nm for nm, _ in d.inputs_vec), letter))
        sin = dict(sin)
        for n in d.nodes:
            k = n.kind
            a = [val[x.id] for x in n.args]
            if not n.scalar or k in ("orr", "bit", "top", "eq", "lt", "cout"):
                # zero-extension of scalar operands in a vector context: a scalar is bit 0 only
                # (the condition of ?: stays a scalar)
                first = 1 if k == "sel" else 0
                a = a[:first] + [x if (not y.scalar or pc == 0) else 0
                                 for x, y in zip(a[first:], n.args[first:])]
            if k == "in":
                v = vin[n.name]
            elif k == "insc":
                v = sin[n.name]
            elif k == "const":
                v = n.k
            elif k == "not":
                v = 1 - a[0]
            elif k == "and":
                v = a[0] & a[1]
            elif k == "or":
                v = a[0] | a[1]
            elif k == "xor":
                v = a[0] ^ a[1]
            elif k == "add":
                s = self.slot[n.id]
                c = st[s]
                v = a[0] ^ a[1] ^ c
                new[s] = (a[0] & a[1]) | (c & (a[0] ^ a[1]))
            elif k == "sub":
                s = self.slot[n.id]
                b = st[s]
                v = a[0] ^ a[1] ^ b
                new[s] = ((1 - a[0]) & a[1]) | (b & (1 - (a[0] ^ a[1])))
            elif k == "shl":
                s = self.slot[n.id]
                fifo = st[s]
                v = fifo[0] if n.k else a[0]
                new[s] = (fifo[1:] + (a[0],)) if n.k else ()
            elif k == "shr":
                s = self.slot[n.id]
                fifo = st[s]
                v = sg[shr_i]
                shr_i += 1
                fifo = fifo + (v,)
                if len(fifo) > n.k:
                    if fifo[0] != a[0]:
                        return None
                    fifo = fifo[1:]
                new[s] = fifo
            elif k == "sel":
                v = a[1] if a[0] else a[2]
            elif k == "preor":
                s = self.slot[n.id]
                v = st[s]
                new[s] = st[s] | a[0]
            elif k in ("trunc", "ext"):
                v = a[0]
            elif k in GUESS_KINDS:
                late = n.id not in self.gidx
                v = 0 if late else g[self.gidx[n.id]]      # a late value is never read during the word
                if k == "orr":
                    s = self.slot[n.id]
                    if a[0] and not v and not late:
                        return None
                    new[s] = st[s] | a[0]
                elif k == "bit":
                    s = self.slot[n.id]
                    if pc == n.k:
                        if not late and a[0] != v:
                            return None
                        new[s] = a[0]
                elif k == "top":
                    s = self.slot[n.id]
                    new[s] = st[s][1:] + (a[0],)
                elif k == "eq":
                    s = self.slot[n.id]
                    new[s] = st[s] | (a[0] ^ a[1])
                elif k == "lt":
                    s = self.slot[n.id]
                    if a[0] != a[1]:
                        new[s] = a[1]          # a < b decided by the most significant differing bit
                elif k == "cout":
                    s = self.slot[n.id]
                    c = st[s]
                    new[s] = (a[0] & a[1]) | (c & (a[0] ^ a[1]))
            else:
                raise ValueError(k)
            if not n.scalar and rem is not None and rem <= -n.woff:
                if k == "in" and v:
                    return None
                v = 0
            val[n.id] = v
        for i, n in enumerate(d.thermo):
            s = self.nslots + i
            if val[n.id] and st[s]:
                return None
            new[s] = st[s] | (1 - val[n.id])
        for i, n in enumerate(d.onehot):
            s = self.nslots + len(d.thermo) + i
            if val[n.id] and st[s]:
                return None
            new[s] = st[s] | val[n.id]
        out = tuple(0 if n.scalar else val[n.id] for _, n in d.outputs)
        return ((tuple(new), g), out)

    def final(self, state, sin):
        """Values of the scalar outputs at the end of the word (vector outputs give 0 here)."""
        st, g = state
        sin = dict(sin)
        val = {}
        for n in self.d.nodes:
            if not n.scalar:
                continue
            k = n.kind
            a = [val.get(x.id) for x in n.args]
            if k == "insc":
                v = sin[n.name]
            elif k == "const":
                v = n.k
            elif k in GUESS_KINDS:
                if n.id in self.gidx:
                    v = g[self.gidx[n.id]]
                else:
                    s = st[self.slot[n.id]]
                    v = s[0] if k == "top" else (1 - s if k == "eq" else s)
            elif k == "not":
                v = 1 - a[0]
            elif k == "and":
                v = a[0] & a[1]
            elif k == "or":
                v = a[0] | a[1]
            elif k == "xor":
                v = a[0] ^ a[1]
            elif k == "sel":
                v = a[1] if a[0] else a[2]
            else:
                raise ValueError(k)
            val[n.id] = v
        return tuple(val[n.id] if n.scalar else 0 for _, n in self.d.outputs)

    def end_ok(self, state):
        st, g = state
        d = self.d
        for i in range(len(d.onehot)):
            if not st[self.nslots + len(d.thermo) + i]:
                return False
        for n in d.nodes:
            k = n.kind
            if k in GUESS_KINDS and n.id not in self.gidx:
                continue
            if k == "shr" and any(st[self.slot[n.id]]):
                return False
            if k == "orr" and g[self.gidx[n.id]] != st[self.slot[n.id]]:
                return False
            if k == "top" and g[self.gidx[n.id]] != st[self.slot[n.id]][0]:
                return False
            if k == "eq" and g[self.gidx[n.id]] != 1 - st[self.slot[n.id]]:
                return False
            if k in ("lt", "cout") and g[self.gidx[n.id]] != st[self.slot[n.id]]:
                return False
        return True

    def start_ok(self, state, sin):
        """Assumed scalars must be 1; checked on the final values, which for guessed scalars are the
        guesses, for scalar inputs the inputs. Evaluated symbolically on scalar nodes only."""
        st, g = state
        d = self.d
        val = {}
        for n in d.nodes:
            if not n.scalar or n.id in d.late:
                continue
            a = [val.get(x.id) for x in n.args]
            k = n.kind
            if k == "insc":
                v = sin[n.name]
            elif k == "const":
                v = n.k
            elif k in self.gidx_kinds():
                v = g[self.gidx[n.id]]
            elif k == "not":
                v = 1 - a[0]
            elif k == "and":
                v = a[0] & a[1]
            elif k == "or":
                v = a[0] | a[1]
            elif k == "xor":
                v = a[0] ^ a[1]
            elif k == "sel":
                v = a[1] if a[0] else a[2]
            else:
                raise ValueError(k)
            val[n.id] = v
        return all(val[n.id] == 1 for n in d.assumes_sc)

    @staticmethod
    def gidx_kinds():
        return ("orr", "bit", "top", "eq", "lt", "cout")


# ----------------------------------------------------------------------------------------------- product


def product_search(A, B, maxlen=None, report=None):
    """Breadth-first search of the product. Returns (None, nstates) if the descriptions agree on every
    length >= Lmin, else (counterexample, nstates). Raises guard.Stop at the state cap or memory limit.
    Compact storage: each automaton's states are interned to integers, a product state is one packed
    integer (A id, B id, letters read capped, end countdown, differs-so-far bit, scalar inputs), and the
    parent of a state is one integer (parent key and letter index)."""
    sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
    import guard
    import live as livemod
    da, db = A.d, B.d
    vnames = [nm for nm, _ in da.inputs_vec]
    if sorted(vnames) != sorted(nm for nm, _ in db.inputs_vec):
        raise SystemExit("the two descriptions must have the same vector inputs")
    snames = sorted(set(nm for nm, _ in da.inputs_sc) | set(nm for nm, _ in db.inputs_sc))
    bperm = [vnames.index(nm) for nm, _ in db.inputs_vec]
    outs_a = [nm for nm, _ in da.outputs]
    outs_b = [nm for nm, _ in db.outputs]
    common = [nm for nm in outs_a if nm in outs_b]
    ia = [outs_a.index(nm) for nm in common]
    ib = [outs_b.index(nm) for nm in common]
    lmin = max(da.lmin, db.lmin)
    depth = A.depth
    cap = A.cap
    if cap >= 16 or depth >= 15 or len(snames) > 8 or len(vnames) > 8:
        raise SystemExit("product_search: description too large for the packed state encoding")
    # Only live states (reachable, and able to reach an accepting end) of each automaton are expanded:
    # a dead state accepts no word, so no counterexample is lost.
    live_a, ra_n = livemod.live_states(A, None, depth, cap, lmin, guard.Guard("live A " + da.path))
    live_b, rb_n = livemod.live_states(B, None, depth, cap, lmin, guard.Guard("live B " + db.path))
    sys.stderr.write("  live states: A %d of %d reachable, B %d of %d reachable\n" % (len(live_a), ra_n, len(live_b), rb_n))
    if report is not None:
        report.update(live_a=len(live_a), reach_a=ra_n, live_b=len(live_b), reach_b=rb_n)
    g = guard.Guard("product")
    aid, alist, bid, blist = {}, [], {}, []

    def intern(table, lst, s):
        i = table.get(s)
        if i is None:
            i = len(lst)
            table[s] = i
            lst.append(s)
        return i

    def pack(pc, rem, a, b, diff, svi):
        return ((((a << 24 | b) << 4 | pc) << 4 | (15 if rem is None else rem)) << 1 | diff) << 8 | svi

    def unpack(key):
        svi = key & 255
        key >>= 8
        diff = key & 1
        key >>= 1
        rem = key & 15
        key >>= 4
        pc = key & 15
        key >>= 4
        b = key & ((1 << 24) - 1)
        a = key >> 24
        return pc, (None if rem == 15 else rem), a, b, diff, svi

    svals = list(itertools.product((0, 1), repeat=len(snames)))
    sin_a = [tuple(sorted((k, dict(zip(snames, sv))[k]) for k, _ in da.inputs_sc)) for sv in svals]
    sin_b = [tuple(sorted((k, dict(zip(snames, sv))[k]) for k, _ in db.inputs_sc)) for sv in svals]
    parent = {}
    q = deque()
    for svi in range(len(svals)):
        sina, sinb = sin_a[svi], sin_b[svi]
        for sa in A.initial():
            if not A.start_ok(sa, dict(sina)) or (0, None, sa, sina) not in live_a:
                continue
            for sb in B.initial():
                if not B.start_ok(sb, dict(sinb)) or (0, None, sb, sinb) not in live_b:
                    continue
                key = pack(0, None, intern(aid, alist, sa), intern(bid, blist, sb), 0, svi)
                if key not in parent:
                    parent[key] = -1
                    q.append(key)
    letters = list(itertools.product((0, 1), repeat=len(vnames)))
    expanded = 0
    while q:
        key = q.popleft()
        expanded += 1
        g.tick(expanded, len(parent))
        pc, rem, ai, bi, diff, svi = unpack(key)
        sa, sb = alist[ai], blist[bi]
        sina, sinb = sin_a[svi], sin_b[svi]
        rems = [rem] if rem is not None else ([None, depth] if depth > 0 else [None])
        for r in rems:
            for li, let in enumerate(letters):
                letb = tuple(let[i] for i in bperm)
                ra = A.step(sa, let, sina, pc, r)
                if not ra:
                    continue
                rb = B.step(sb, letb, sinb, pc, r)
                npc = min(pc + 1, cap)
                nrem = None if r is None else r - 1
                ra = [x for x in ra if (npc, nrem, x[0], sina) in live_a]
                rb = [x for x in rb if (npc, nrem, x[0], sinb) in live_b]
                for na, oa in ra:
                    for nb, ob in rb:
                        d2 = diff | int(any(oa[i] != ob[j] for i, j in zip(ia, ib)))
                        nkey = pack(npc, nrem, intern(aid, alist, na), intern(bid, blist, nb), d2, svi)
                        if nkey in parent:
                            continue
                        parent[nkey] = key << 8 | li
                        at_end = (nrem == 0 or depth == 0) and npc >= lmin
                        if at_end and A.end_ok(na) and B.end_ok(nb):
                            fa, fb = A.final(na, sina), B.final(nb, sinb)
                            if d2 or any(fa[i] != fb[j] for i, j in zip(ia, ib)):
                                return trace(parent, nkey, unpack, letters, snames, svals, vnames, common,
                                             outs_a, outs_b), len(parent)
                        if nrem == 0:
                            continue          # the word must end here
                        q.append(nkey)
        A.trim()
        B.trim()
    return None, len(parent)


def trace(parent, key, unpack, letters, snames, svals, vnames, common, outs_a, outs_b):
    steps = []
    while parent[key] != -1:
        v = parent[key]
        steps.append((letters[v & 255],))
        key = v >> 8
    steps.reverse()
    svi = unpack(key)[5]
    return {"scalars": dict(zip(snames, svals[svi])), "letters": steps, "vnames": vnames,
            "common": common, "outs_a": outs_a, "outs_b": outs_b}


def show_cex(cex, A, B):
    N = len(cex["letters"])
    lines = ["COUNTEREXAMPLE, word length N = %d (least significant bit first)" % N,
             "  scalars: " + " ".join("%s=%d" % kv for kv in sorted(cex["scalars"].items()))]
    for i, nm in enumerate(cex["vnames"]):
        lines.append("  %-10s %s" % (nm, "".join(str(l[0][i]) for l in cex["letters"])))
    # outputs recomputed exactly by direct evaluation at length N
    vin = {nm: sum(l[0][i] << j for j, l in enumerate(cex["letters"])) for i, nm in enumerate(cex["vnames"])}
    oka, oa = evaluate(A.d, N, vin, cex["scalars"])
    okb, ob = evaluate(B.d, N, vin, cex["scalars"])
    lines.append("  assumptions hold (direct evaluation): %s, %s" % (oka, okb))
    for nm in cex["common"]:
        na = dict(A.d.outputs)[nm]
        if na.scalar:
            fa, fb = str(oa[nm]), str(ob[nm])
        else:
            fa = "".join(str((oa[nm] >> j) & 1) for j in range(N))
            fb = "".join(str((ob[nm] >> j) & 1) for j in range(N))
        mark = "   <- differs" if fa != fb else ""
        lines.append("  %-10s A %s   B %s%s" % (nm, fa, fb, mark))
    return "\n".join(lines)


def make_pair(a_path, b_path):
    da, db = Desc(a_path), Desc(b_path)
    depth = max(da.trunc_depth, db.trunc_depth)
    lmin = max(da.lmin, db.lmin)
    if lmin <= depth:
        raise SystemExit("length bound must exceed the truncation depth %d" % depth)
    ks = da.ks + db.ks + [n.k for n in da.nodes + db.nodes if n.kind == "top"]
    if ks and lmin <= max(ks):
        raise SystemExit("length bound must exceed every constant bit position (%d)" % max(ks))
    cap = max([lmin] + [k + 1 for k in da.ks + db.ks] + [1])
    return Auto(da, depth, cap), Auto(db, depth, cap)


# ------------------------------------------------------------------------------------------ self-test


def run_word(A, N, vin, sin):
    """Run the automaton on one word: returns the list of surviving runs' outputs."""
    d = A.d
    vnames = [nm for nm, _ in d.inputs_vec]
    sint = tuple(sorted((k, sin[k]) for k, _ in d.inputs_sc))
    runs = [(s, []) for s in A.initial() if A.start_ok(s, dict(sint))]
    for j in range(N):
        let = tuple((vin[nm] >> j) & 1 for nm in vnames)
        rem = N - j if N - j <= A.depth else None
        pc = min(j, A.cap)
        nxt = []
        for s, outs in runs:
            for s2, o in A.step(s, let, sint, pc, rem):
                nxt.append((s2, outs + [o]))
        runs = nxt
    return [(outs, A.final(s, sint)) for s, outs in runs if A.end_ok(s)]


def selftest(path, nmax, count, seed=1):
    A, _ = make_pair(path, path)
    d = A.d
    rng = random.Random(seed)
    bad = tested = 0
    for _ in range(count):
        N = rng.randrange(max(d.lmin, A.depth + 1), nmax + 1)
        vin = {}
        for nm, n in d.inputs_vec:
            wid = N + n.woff
            if n in d.thermo and rng.random() < 0.8:
                vin[nm] = (1 << rng.randrange(0, wid + 1)) - 1
            else:
                vin[nm] = rng.getrandbits(wid)
        sin = {nm: rng.randrange(2) for nm, _ in d.inputs_sc}
        ok, ref = evaluate(d, N, vin, sin)
        runs = run_word(A, N, vin, sin)
        tested += 1
        if not ok:
            if runs:
                bad += 1
                print("accepted a word that violates an assumption: N=%d %s %s" % (N, vin, sin))
            continue
        if len(runs) != 1:
            bad += 1
            print("%d runs survive (expected 1): N=%d %s %s" % (len(runs), N, vin, sin))
            continue
        outs, fin = runs[0]
        for i, (nm, n) in enumerate(d.outputs):
            if n.scalar:
                got = fin[i]
            else:
                got = sum(outs[j][i] << j for j in range(N))
            if got != ref[nm]:
                bad += 1
                print("output %s differs: automaton %s direct %s at N=%d %s %s" % (nm, got, ref[nm], N, vin, sin))
                break
    print("selftest %s: %d words, %d disagreements between automaton and direct evaluation" % (path, tested, bad))
    return bad


# -------------------------------------------------------------------------------------------------- main


def main(argv):
    if len(argv) >= 3 and argv[0] == "equiv":
        A, B = make_pair(argv[1], argv[2])
        print("equiv %s %s" % (argv[1], argv[2]))
        import guard
        try:
            cex, n = product_search(A, B)
        except guard.Stop as e:
            print(e)
            return 3
        print("  outputs compared: %s" % ", ".join(nm for nm, _ in A.d.outputs if nm in dict(B.d.outputs)))
        print("  product states reached: %d" % n)
        if cex is None:
            print("EQUAL on every word length N >= %d" % max(A.d.lmin, B.d.lmin))
            return 0
        print(show_cex(cex, A, B))
        return 1
    if len(argv) == 4 and argv[0] == "selftest":
        return 1 if selftest(argv[1], int(argv[2]), int(argv[3])) else 0
    if len(argv) >= 3 and argv[0] == "eval":
        d = Desc(argv[1])
        N = int(argv[2])
        kv = dict(a.split("=") for a in argv[3:])
        vin = {nm: int(kv.get(nm, "0"), 0) for nm, _ in d.inputs_vec}
        sin = {nm: int(kv.get(nm, "0"), 0) for nm, _ in d.inputs_sc}
        ok, o = evaluate(d, N, vin, sin)
        print("assumptions hold: %s" % ok)
        for nm, v in o.items():
            print("  %s = %s" % (nm, bin(v)))
        return 0
    if len(argv) >= 3 and argv[0] == "states":
        sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
        import states
        return states.main(argv[1:])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
