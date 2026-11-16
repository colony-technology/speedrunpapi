"""PBS counter for TFHE-rs radix scalar multiplication, CPU parallel server key.

Plain-integer simulation of the control flow of tfhe-rs commit
b07e249c925bad47b03ed2bc93a99c2b6feaaad7. No ciphertext arithmetic: every block is
(trivial, degree, noise) and every non-trivial lookup-table application adds 1 to the
PBS counter. Line references are to tfhe/src/integer/server_key/radix_parallel/.

Parameter set: PARAM_MESSAGE_2_CARRY_2 (message 4, carry 4, max noise level 5).

Strategies
  binary : what the library does (scalar_mul.rs:44-80), digits 0/1.
  naf    : non-adjacent form, digits -1/0/+1. A negative term enters the existing
           sum routine as bitnot(copy) << s (bitnot is linear, bitwise_op.rs:350-361)
           plus a clear constant 4**(s/2) folded into one trivial term. [design, inferred]
  wnaf3  : width-3 signed window, digits in {+-1, +-3}. Precomputes 3X with one
           add_parallelized and the shifted copies it needs. [design, inferred]
  wnaf4  : width-4 signed window, digits in {+-1, +-3, +-5, +-7}. [design, inferred]

Usage:  python -I tfhe_scalar_mul_count.py [threads] [samples] [seed]
"""
import math
import random
import sys

MSG = 4
CARRY = 4
BLOCK_MOD = MSG * CARRY          # 16
MAX_DEGREE = BLOCK_MOD - 1       # 15
MAX_NOISE = 5
MSG_BITS = 2
THREADS = 192
COUNT_TRIVIAL = False


class Blk:
    __slots__ = ("triv", "deg", "noise")

    def __init__(self, triv, deg, noise):
        self.triv, self.deg, self.noise = triv, deg, noise

    def copy(self):
        return Blk(self.triv, self.deg, self.noise)


def fresh(deg=MSG - 1):
    return Blk(False, deg, 1)


def tzero():
    return Blk(True, 0, 0)


class Counter:
    def __init__(self):
        self.pbs = 0

    def lut(self, b, out_deg=MSG - 1):
        """apply_lookup_table: trivial input short-circuits (shortint/server_key/mod.rs:985-994)."""
        if b.triv:
            # The library's pbs-stats counter also counts these (trivial_pbs_assign,
            # shortint/server_key/mod.rs:1300-1304); COUNT_TRIVIAL=True reproduces it.
            if COUNT_TRIVIAL:
                self.pbs += 1
            return Blk(True, out_deg, 0)
        self.pbs += 1
        return Blk(False, out_deg, 1)


def add(a, b):
    return Blk(a.triv and b.triv, a.deg + b.deg, a.noise + b.noise)


# ---------------------------------------------------------------- add.rs:44-100
def should_parallel_propagation_be_faster(full_modulus, num_blocks, num_threads):
    penalty_threshold = num_threads // 2

    def layer(n, t):
        lat = -(-n // t)
        return lat * 1 if n >= penalty_threshold else lat

    par = 3 * layer(num_blocks, num_threads)
    g = int(math.log2(full_modulus))
    groups = -(-num_blocks // g)
    ntr = max(groups - 1, 0)
    seq_depth = max(ntr - 1, 0) // (g - 1)
    hs_depth = 0 if ntr == 0 else math.ceil(math.log2(ntr))
    if seq_depth <= hs_depth:
        par += seq_depth * layer(g, num_threads)
    else:
        space = 1
        for _ in range(math.ceil(math.log2(num_blocks))):
            par += layer(num_blocks - space, num_threads)
            space *= 2
    return par < num_blocks


# ---------------------------------------------------------------- add.rs:497-638
def add_sequential(c, lhs, rhs):
    n = len(lhs)
    out = []
    carry = tzero()
    for i in range(n):
        s = add(add(lhs[i], rhs[i]), carry)
        out.append(c.lut(s))            # message_extract
        carry = c.lut(s, 1)             # carry_extract (also done on last block, add.rs:588-601)
    return out


# ---------------------------------------------------------------- add.rs:710-1331
def add_parallel(c, lhs, rhs):
    """advanced_add_assign_with_carry_at_least_4_bits, OutputFlag::None."""
    n = len(lhs)
    blocks = [add(lhs[i], rhs[i]) if rhs else lhs[i] for i in range(n)]
    g = int(math.log2(BLOCK_MOD))       # grouping_size = 4
    # step 1: many-LUT, 1 PBS per block -> (state, shifted)  add.rs:1302-1320
    states, shifted = [], []
    for b in blocks:
        r = c.lut(b)
        states.append(r.copy())
        shifted.append(r.copy())
    states.pop()                         # add.rs:779
    m = len(states)
    if m == 0:
        sims, resolved = [Blk(True, 1, 0)], [tzero()]
    else:
        groups = -(-m // g)
        ntr = groups - 1
        seq_depth = max(ntr - 1, 0) // (g - 1)
        hs_depth = 0 if ntr == 0 else math.ceil(math.log2(ntr))
        use_seq = seq_depth <= hs_depth
        cums = []
        for start in range(0, m, g):     # add.rs:1038-1047
            acc = None
            for s in states[start:start + g]:
                acc = s.copy() if acc is None else add(s, acc)
                cums.append(acc)
        cums = [c.lut(x) for x in cums]  # add.rs:1052-1091
        pgns, sims = [], [Blk(True, 1, 0)]
        for b in cums:                   # add.rs:1097-1108
            if len(sims) % g == 0:
                pgns.append(b)
                sims.append(Blk(True, 1, 0))
            else:
                sims.append(b)
        if not pgns:
            resolved = [tzero()]
        elif use_seq:                    # add.rs:1178-1219
            first = pgns[0]
            rest = pgns[1:]
            resolved = [tzero(), first]
            for k in range(0, len(rest), g - 1):
                chunk = [x.copy() for x in rest[k:k + g - 1]]
                chunk[0] = add(chunk[0], resolved[-1])
                acc = chunk[0]
                for j in range(1, len(chunk)):
                    acc = add(acc, chunk[j])
                    chunk[j] = acc
                resolved += [c.lut(x, 1) for x in chunk]
        else:                            # add.rs:1130-1161, 1334-1369
            blocks_hs = [x.copy() for x in pgns]
            P = len(blocks_hs)
            space = 1
            for _ in range(math.ceil(math.log2(P)) if P > 1 else 0):
                new = [x.copy() for x in blocks_hs]
                for i in range(space, P):
                    new[i] = c.lut(add(blocks_hs[i], blocks_hs[i - space]), 1)
                blocks_hs = new
                space *= 2
            resolved = [tzero()] + blocks_hs
    out = []
    for i in range(n):                   # add.rs:849-865
        b = add(add(shifted[i], sims[i] if i < len(sims) else tzero()),
                resolved[min(i // g, len(resolved) - 1)])
        out.append(c.lut(b))
    return out


def advanced_add(c, lhs, rhs):
    """add.rs:380-424, CarryPropagationAlgorithm::Automatic."""
    if should_parallel_propagation_be_faster(BLOCK_MOD, len(lhs), THREADS):
        return add_parallel(c, lhs, rhs)
    return add_sequential(c, lhs, rhs)


# ---------------------------------------------------------------- mod.rs:121-319
def partial_propagate(c, blocks):
    L = len(blocks)

    def extract(bl):
        msgs = [c.lut(b) for b in bl]
        cars = [c.lut(b) for b in bl[:-1]]
        return msgs, cars

    if should_parallel_propagation_be_faster(BLOCK_MOD, L, THREADS):   # mod.rs:147, add.rs:303-321
        if max(b.deg for b in blocks) >= (MSG - 1) * 2:                # mod.rs:154
            msgs, cars = extract(blocks)
            return [msgs[0]] + advanced_add(c, msgs[1:], cars)          # mod.rs:157-163
        return add_parallel(c, blocks, [])                             # mod.rs:165
    hi = max((b.deg for b in blocks[1:]), default=None)
    start = 0
    blocks = [b.copy() for b in blocks]
    if (hi is not None and hi > MAX_DEGREE - (CARRY - 1)) or \
            any(b.noise >= MAX_NOISE - 1 for b in blocks[1:]):         # mod.rs:184-199
        msgs, cars = extract(blocks)
        blocks = [msgs[0]] + [add(msgs[i + 1], cars[i]) for i in range(L - 1)]
        start = 1
    for i in range(start, L):                                           # mod.rs:203-215
        carry = c.lut(blocks[i], 1)
        blocks[i] = c.lut(blocks[i])
        if i < L - 1:
            blocks[i + 1] = add(blocks[i + 1], carry)
    return blocks


def full_propagate(c, blocks):
    n = len(blocks)
    start = next((i for i, b in enumerate(blocks) if b.deg >= MSG), None)
    if start is None:
        return [c.lut(b) if b.noise > 1 else b for b in blocks]
    end = min(max(i for i, b in enumerate(blocks) if b.deg != 0) + 2, n - 1)
    head = [c.lut(b) if b.noise > 1 else b for b in blocks[:start]]
    mid = partial_propagate(c, blocks[start:end + 1])
    tail = [c.lut(b) if b.noise > 1 else b for b in blocks[end + 1:]]
    return head + mid + tail


# ---------------------------------------------------------------- sum.rs:14-167
def max_sum_size(deg):
    return min(MAX_DEGREE // deg, MAX_NOISE)          # server_key/mod.rs:243-249


def sum_terms(c, terms):
    if not terms:
        return None
    if len(terms) == 1:
        return full_propagate(c, terms[0])
    n = len(terms[0])
    if len(terms) == 2:                                # sum.rs:36-38 -> add_parallelized
        return full_propagate(c, advanced_add(c, terms[0], terms[1]))
    fill = max_sum_size(MSG - 1)                       # sum.rs:48-49  -> 5
    cols = [[b for b in (t[i] for t in terms) if b.deg != 0] for i in range(n)]
    while any(len(col) > fill for col in cols):        # sum.rs:75
        outs = [[] for _ in range(n)]
        new_cols = []
        for ci, col in enumerate(cols):
            if len(col) < fill:
                new_cols.append(col)
                continue
            nchunks = len(col) // fill
            for k in range(nchunks):
                ch = col[k * fill:(k + 1) * fill]
                acc = ch[0]
                for x in ch[1:]:
                    acc = add(acc, x)
                msg = c.lut(acc)                       # sum.rs:94
                car = c.lut(acc) if ci < n - 1 else None   # sum.rs:95, 98
                outs[ci].append((msg, car))
            rest = len(col) % fill
            new_cols.append(col[len(col) - rest:] if rest else [])
        cols = new_cols
        for ci in range(n):                            # sum.rs:113-125
            for msg, car in outs[ci]:
                cols[ci].append(msg)
                if car is not None and ci + 1 < n:
                    cols[ci + 1].append(car)
    res = []
    for col in cols:                                   # sum.rs:129-142
        if not col:
            res.append(tzero())
        else:
            acc = col[0]
            for x in col[1:]:
                acc = add(acc, x)
            res.append(acc)
    return full_propagate(c, res)                      # sum.rs:163


# ---------------------------------------------------------------- building blocks
def blockshift(x, k):
    n = len(x)
    k = min(k, n)
    return [tzero() for _ in range(k)] + [b.copy() for b in x[:n - k]]


def shift1(c, x):
    """unchecked_scalar_left_shift by 1 bit: N-1 bivariate PBS + 1 univariate (scalar_shift.rs:672-705)."""
    out = [c.lut(x[0], 2)]
    for i in range(1, len(x)):
        out.append(c.lut(add(x[i - 1], x[i])))
    return out


def bitnot(x):
    return [Blk(b.triv, MSG - 1, b.noise) for b in x]


def const_term(value, n):
    out = []
    for _ in range(n):
        d = value % MSG
        out.append(Blk(True, d, 0))
        value //= MSG
    return out


# ---------------------------------------------------------------- digit recodings
def binary_digits(k):
    return [(i, 1) for i in range(k.bit_length()) if (k >> i) & 1]


def wnaf_digits(k, w):
    """Width-w NAF; w=2 is the ordinary NAF."""
    out, i = [], 0
    while k:
        if k & 1:
            d = k % (1 << w)
            if d >= (1 << (w - 1)):
                d -= 1 << w
            k -= d
            out.append((i, d))
        k >>= 1
        i += 1
    return out


# ---------------------------------------------------------------- strategies
def library_scalar_mul(k, n):
    """scalar_mul.rs:18-85 exactly."""
    c = Counter()
    nbits = MSG_BITS * n
    if k == 0 or k == 1:
        return 0, 0
    if k & (k - 1) == 0:                               # scalar_mul.rs:34-39
        s = k.bit_length() - 1
        rot = s // MSG_BITS
        if s % MSG_BITS == 0 or rot >= n:
            return 0, 1
        return n - rot, 1
    x = [fresh() for _ in range(n)]
    digits = binary_digits(k)
    pre = {0: x}
    if any(i % MSG_BITS == 1 for i, _ in digits):      # scalar_mul.rs:50-69
        pre[1] = shift1(c, x)
    terms = [blockshift(pre[i % MSG_BITS], i // MSG_BITS)
             for i, _ in digits if i < nbits]          # scalar_mul.rs:71-78
    sum_terms(c, terms)
    return c.pbs, len(terms)


def signed_scalar_mul(k, n, w):
    """Signed-digit design fed into the same sum routine. [inferred design]"""
    c = Counter()
    nbits = MSG_BITS * n
    mod = 1 << nbits
    if k in (0, 1):
        return 0, 0
    if k & (k - 1) == 0:
        return library_scalar_mul(k, n)
    digits = [(i, d) for i, d in wnaf_digits(k, w) if i < nbits]
    x = [fresh() for _ in range(n)]
    odd = {1: x}
    need = sorted({abs(d) for _, d in digits})
    # precompute odd multiples with add_parallelized + clean (counted)
    x1 = None
    for m in need:
        if m == 1:
            continue
        if m == 3:
            x1 = x1 or shift1(c, x)
            odd[3] = full_propagate(c, advanced_add(c, x, x1))
        elif m == 5:
            odd[5] = full_propagate(c, advanced_add(c, x, blockshift(x, 1)))
        elif m == 7:
            if 3 not in odd:
                x1 = x1 or shift1(c, x)
                odd[3] = full_propagate(c, advanced_add(c, x, x1))
            odd[7] = full_propagate(c, advanced_add(c, odd[3], blockshift(x, 1)))
    pre = {}

    def get(m, parity):
        key = (m, parity)
        if key not in pre:
            if parity == 0:
                pre[key] = odd[m]
            elif m == 1 and x1 is not None:
                pre[key] = x1
            else:
                pre[key] = shift1(c, odd[m])
        return pre[key]

    terms, const = [], 0
    for i, d in digits:
        base = get(abs(d), i % MSG_BITS)
        s = i // MSG_BITS
        if d > 0:
            terms.append(blockshift(base, s))
        else:
            terms.append(blockshift(bitnot(base), s))
            const = (const + (MSG ** s)) % mod
    if const:
        terms.append(const_term(const, n))
    sum_terms(c, terms)
    return c.pbs, len(digits)


def patched_scalar_mul(k, n):
    """Mirror of tfhe-naf/scalar_mul_naf.patch: NAF only when it has fewer terms
    (the folded constant counted) than binary; otherwise the library path."""
    nbits = MSG_BITS * n
    if k in (0, 1) or k & (k - 1) == 0:
        return library_scalar_mul(k, n)
    binary_terms = sum(1 for i, _ in binary_digits(k) if i < nbits)
    naf = [(i, d) for i, d in wnaf_digits(k, 2) if i < nbits]
    naf_terms = len(naf) + (1 if any(d < 0 for _, d in naf) else 0)
    if naf_terms < binary_terms:
        return signed_scalar_mul(k, n, 2)
    return library_scalar_mul(k, n)


def main():
    global THREADS, COUNT_TRIVIAL
    THREADS = int(sys.argv[1]) if len(sys.argv) > 1 else 192
    samples = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 20261115
    COUNT_TRIVIAL = len(sys.argv) > 4 and sys.argv[4] == "count-trivial"
    rng = random.Random(seed)
    print(f"threads={THREADS} samples={samples} seed={seed} count_trivial={COUNT_TRIVIAL} "
          f"params=2_2 (msg 4, carry 4, noise 5)")
    print("width blocks | strategy | mean terms | mean PBS | min PBS | max PBS | PBS vs binary")
    for width in (16, 32, 64):
        n = width // MSG_BITS
        ks = [rng.getrandbits(width) for _ in range(samples)]
        rows = {}
        for name, fn in (("binary", lambda k: library_scalar_mul(k, n)),
                         ("naf", lambda k: signed_scalar_mul(k, n, 2)),
                         ("patch", lambda k: patched_scalar_mul(k, n)),
                         ("wnaf3", lambda k: signed_scalar_mul(k, n, 3)),
                         ("wnaf4", lambda k: signed_scalar_mul(k, n, 4))):
            res = [fn(k) for k in ks]
            pbs = [r[0] for r in res]
            terms = [r[1] for r in res]
            rows[name] = (sum(terms) / samples, sum(pbs) / samples, min(pbs), max(pbs))
        base = rows["binary"][1]
        for name, (t, p, lo, hi) in rows.items():
            print(f"{width:5d} {n:6d} | {name:6s} | {t:10.2f} | {p:8.1f} | {lo:7d} | {hi:7d} | {100 * (p / base - 1):+6.1f}%")


if __name__ == "__main__":
    main()
