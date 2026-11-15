# Stage 2. The significand datapath, proved at every width

Unit: HardFloat Release 1, `source/HardFloat_rawFN.v`, module `roundAnyRawFNToRecFN`, lines 174–218. This is the code that `roundRawFNToRecFN#(w, p)` instantiates with options 0 and the RISCV specialization:

- `neverUnderflows` = 0, so `roundMask` comes from `lowMaskLoHi`;
- `propagateNaNPayload` = 0, so the split ORs of lines 193–202 are one OR.

**Result: for every word length N ≥ 6 (every p ≥ 2, with N = p + 4), all six rounding modes and both signs, HardFloat's `roundedSig`, `roundPosBit`, `anyRoundExtra` and `anyRound` equal the definition of rounding at the marked position.**

- "The definition" means: ρ(x, R)/4, bit R−1 of x, [x mod 2^(R−1) ≠ 0], [x mod 2^R ≠ 0].
- The proof covers every rounding mask that is a run of at least two ones from bit 0, which includes every mask the exponent stage can produce.
- The rounding carries `roundedSig[p+1]` and `roundedSig[p]`, which the exponent stage adds to `sExp`, are letters N−3 and N−4 of `roundedSig`. They are covered by the same equality.

## The tool

`stage2/bvfsm.py`, with `live.py` and `guard.py`, in Python 3 with no other dependency.

**Descriptions** (`.bv` files):

- A word length parameter N ≥ Lmin.
- Vector inputs of width N − c, read least significant bit first; scalar inputs.
- Assumptions: `ones_below(v)`, `onehot(v)`, or any scalar expression.
- Operations: `~ & | ^` (bitwise), `+ -` (modulo the width), shifts by constants, `?:` with a scalar condition, constants 0 and 1.
- Functions:
  - `orr` (OR-reduction);
  - `preor` (OR of the bits below each letter);
  - `bit(v,k)`, `top(v,k)`;
  - `eq`, `lt` (unsigned);
  - `cout` (carry out of a sum);
  - truncation `let v : N-c = …`, and zero-extension of a name.
- Semantics are Verilog's unsigned rules. A scalar in a vector operation is zero-extended, not broadcast.
- Widening is allowed only for a name, `let v : N = name`, as a zero-extension. Widening an expression is refused, because Verilog would evaluate the whole expression at the wider width and keep its carry.

**Method.** Each description compiles to a letter-to-letter automaton:

- Scalars that feed vector operations are guessed at the start and checked when known. Scalars that only reach outputs are computed at the end.
- A right shift by k guesses its output bit and checks it k letters later. Truncation relative to the end uses one guess of the end, shared by both sides.
- Each automaton's live states are kept: reachable, and able to reach an accepting end.
- A breadth-first search of the product of live states looks for an accepted word with different outputs. If there is none, the two descriptions are equal on every length. If there is one, the first found is a shortest counterexample, and its outputs are recomputed by direct integer evaluation.
- The search stops at 3,000,000 stored states or 2,000 MB and then reports the result as undecided (`guard.py`).

**Second semantics.** `bvfsm.py selftest` compares the automaton with direct integer evaluation of the same description on random words. That does not test the language itself, so each description is also checked against the arithmetic definition (`check_ref.py`, `check_lemma.py`) and against the Verilog (below).

## The descriptions

**`stage2/hf_datapath.bv`: lines 174–218, one `let` per Verilog wire, names kept.**

- `sig` is `adjustedSig` = `in_sig` (p + 3 bits) and `mask` is `roundMask`.
- Widths follow the Verilog. The expression of `roundedSig` has context width max(p + 3, 32) because of the unsized `0` on line 215. The ones that `~(… ? roundMask>>1 : 0)` puts above bit p+2 meet zero bits of `((adjustedSig|roundMask)>>2)+1`, which is below 2^(p+2). Modelling that `~` at p + 3 bits therefore gives the same p + 2 bits of `roundedSig`.

**`stage2/ref_round.bv`: the definition, written from the arithmetic, not from HardFloat.**

- ulp = 2^R, half = ulp/2, rem = x mod ulp, t = x − rem.
- The rule decides from rem > half, rem = half, rem ≠ 0 and the parity of t/ulp. Odd is toward zero, then set the last bit if inexact (HardFloat doc 6.2).
- `stage2/check_ref.py` checks it against `rounded()` of `common/rounding.py`: every sig, every mask with 2 ≤ R ≤ N−1, six modes, both signs, N = 6…11. **195,840 cases, 0 differences.** The same check on `hf_datapath.bv`: 195,840 cases, 0 differences.

## The transcription against HardFloat's own netlist, at 111 widths

`stage2/formal/one.sh`, `stage2/formal/all.sh`, `record/stage2/formal.txt`.

The widths: every p = 3…113, each at the smallest exponent width the documentation allows for it (w = 3 for p ≤ 5, 4 for p ≤ 7, 5 for p ≤ 11, 6 for p ≤ 19, 7 for p ≤ 35, 8 for p ≤ 67, 9 for p = 68…113). For each:

1. Yosys 0.70+385 reads `HardFloat_primitives.v` and `HardFloat_rawFN.v` unchanged, sets `roundRawFNToRecFN#(w, p)`, flattens, and runs `opt_clean`.
2. It cuts HardFloat's own wire `roundAnyRawFNToRecFN.genblk2.roundMask` from its driver into a free input (`expose -input`), and brings out the wires `roundedSig`, `roundPosBit`, `anyRoundExtra`, `anyRound`.
3. `stage2/bv2v.py` emits `hf_datapath.bv` at N = p + 4 as a Verilog module.
4. A miter asserts that, whenever the description's assumptions hold (mask a run of at least two ones from bit 0; a valid mode), the four signals are equal. sExp, control and the sign are free.
5. `sat -verify -prove bad 0`.

Results:

- **EQUIVALENT at all 111 widths**, at most 1 s each.
- The two broken descriptions give **DIFFERENT** at p = 3, 11, 24, 53, 113: 10 of 10.
- Without `opt_clean`, some readers of the mask stay attached to an alias of the cut wire, the cut is incomplete, and the miter reports a difference. That is why the step is there.

**The emitter against the language's semantics** (`stage2/emitcheck.py`). The emitted module is simulated by Icarus and compared with `bvfsm.evaluate`:

- every input at N = 6 (16,384 inputs) and N = 7 (65,536);
- random inputs at N = 8 and 9 (20,000 each) and at N = 12, 28, 57, 117 (5,000 each);
- 0 differences.

**Proved, and not proved.**

- **Proved:** formal equivalence of the transcription with HardFloat's own netlist at 111 widths, binary16 (p 11), binary32 (24), binary64 (53) and binary128 (113) among them.
- **Not proved:** the link at other widths. It rests on the text: one description line per Verilog line, with the same names.

| Verilog (HardFloat_rawFN.v) | hf_datapath.bv |
| --- | --- |
| 121–126 `roundingMode_* = (roundingMode == ...)` | 22–27, the same six decodes of m2 m1 m0 |
| 127–128 `roundMagUp = (min && in_sign) \|\| (max && !in_sign)` | 28 |
| 174–189 `roundMask = {roundMask_main \| doShiftSigDown1, 2'b11}` | input `mask`, assumed a run of ones from bit 0 with bits 0 and 1 set (18–19); its value is stage 3's |
| 190 `shiftedRoundMask = roundMask>>1` | 30 |
| 191–192 `roundPosMask = ~shiftedRoundMask & roundMask` | 31 |
| 193–197 `roundPosBit = (\|(adjustedSig[p+2:3] & roundPosMask[p+2:3])) \|\| ((\|(adjustedSig[2:0] & roundPosMask[2:0])) && !propagateNaNPayload)` | 32, `orr(sig & roundPosMask)`; `propagateNaNPayload` is 0 (RISCV) |
| 198–202 `anyRoundExtra`, the same with `shiftedRoundMask` | 33 |
| 203 `anyRound = roundPosBit \|\| anyRoundExtra` | 34 |
| 206–209 `roundIncr` | 35 |
| 210–215 the increment branch, with the ties-to-even clear | 36 `incd` |
| 216–218 the truncation branch, with the odd jam | 37 `trnc` |
| 210 `roundedSig = roundIncr ? ... : ...`, p+2 bits | 38, width N−2 = p+2 |

**The description in simulation** (`stage2/anchor/`, `record/stage2/anchor.txt`). The internal signals of the real module were read through Verilator's public signals at w = 5, p = 3…9, on every valid finite nonzero input, one line per distinct (mask, sig, mode, sign). Against direct evaluation of the description:

| p | distinct inputs | distinct masks | differences |
| --- | --- | --- | --- |
| 3 | 2,496 | 5 | 0 |
| 4 | 6,144 | 6 | 0 |
| 5 | 14,592 | 7 | 0 |
| 6 | 33,792 | 8 | 0 |
| 7 | 76,800 | 9 | 0 |
| 8 | 172,032 | 10 | 0 |
| 9 | 380,928 | 11 | 0 |

## The run (`record/stage2/hf_ref.txt`)

```
equiv hf_datapath.bv ref_round.bv
  live states: A 3216 of 152112 reachable, B 4348 of 204960 reachable
  outputs compared: roundedSig, roundPosBit, anyRoundExtra, anyRound
  product states reached: 33556
EQUAL on every word length N >= 6
```

Peak memory 327 MB.

## The broken copies (the tool must find them)

**`stage2/hf_datapath_broken.bv`: the tie condition of line 214 without `& ~anyRoundExtra`.**

```
COUNTEREXAMPLE, word length N = 6 (least significant bit first)
  scalars: m0=0 m1=0 m2=0 sign=0                 (near_even)
  sig        000110          (x = 24)
  mask       111110          (R = 5)
  roundedSig A 000000   B 000100   <- differs
```

x = 24 is above half of 2^5 and rounds up to 32. The broken copy treats it as a tie and clears the result to 0.

**`stage2/hf_datapath_broken2.bv`: round to odd jams on `roundPosBit` instead of `anyRound` (line 217).**

```
COUNTEREXAMPLE, word length N = 6
  scalars: m0=0 m1=1 m2=1 sign=0                 (odd)
  sig        000100          (x = 4, R = 5: inexact, round bit 0)
  roundedSig A 000000   B 000100   <- differs
```

## Lemma L1 (used by stage 3)

The tininess-after test of lines 233–256 relies on this lemma.

- **Setting:** x with its top bit set, U ≥ 1, R = U + 1 ≤ N.
- **Claim:** ρ(x, U) carries out of the top ⟺ (bit R−1 of x) ∧ (bit m+1 of ρ(x, R)) ∧ `unboundedRange_roundIncr`.

The descriptions: `stage2/lemma_cu_c.bv`, with its two sides `lemma_cu_c_lhs.bv` and `lemma_cu_c_rhs.bv`. Each rounding is decided at its letter, from the shifted bits and a running OR.

- `stage2/check_lemma.py` checks both sides against the definition at N = 2…11: 92,170 cases, 0 differences; the lemma holds on all 92,170.
- **For every width: proved.** `bvfsm.py equiv lemma_cu_c_lhs.bv lemma_cu_c_rhs.bv`: 126 of 126 states live on each side, 126 product states, **EQUAL on every word length N ≥ 2** (`record/stage2/lemma_cu.txt`).
- With `roundPosBit` dropped from the right-hand side (`lemma_cu_c_rhs_broken.bv`) the tool gives a counterexample at N = 3: x = 5, U = 1, away. ρ(5, 1) = 6 does not carry, while the broken right-hand side says it does (`record/stage2/lemma_cu_broken.txt`).

## Files

| file | role |
| --- | --- |
| `stage2/bvfsm.py`, `live.py`, `guard.py` | the tool |
| `stage2/hf_datapath.bv`, `ref_round.bv` | the two sides |
| `stage2/hf_datapath_broken.bv`, `hf_datapath_broken2.bv` | broken copies |
| `stage2/lemma_cu_c*.bv` | lemma L1 |
| `stage2/check_ref.py`, `check_lemma.py` | checks against the definition |
| `stage2/bv2v.py`, `emitcheck.py`, `formal/` | the transcription against the netlist |
| `stage2/anchor/` | the transcription in simulation |
| `stage2/run_equiv.sh` | the equivalence runs |
| `record/stage2/` | results |
