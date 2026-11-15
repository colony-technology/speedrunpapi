# Stage 3. The exponent stage and the flags

Unit: HardFloat Release 1, `roundRawFNToRecFN#(w, p)`, options 0, RISCV specialization, as in stage 1. Source lines are those of `source/HardFloat_rawFN.v`.

Results:

- **The exponent stage, the flags, the result kind and the exponent field are proved right for every format**, by z3, given the datapath facts of stage 2.
- **The whole module equals a module built from those formulas** at 135 formats, by Yosys SAT: every documented format with w = 3…8, binary64, x87 extended (15, 64) and binary128.

## 1. The exponent stage as integer formulas

Coordinates: bit 0 of `in_sig` is position 0; T = p + 3 is the word length; the top 1-bit is at m = p + 1 + d, with d = `doShiftSigDown1`. Let B = 2^(w−1).

- x = in_sig · 2^λ with λ = sExp − 2B − p − 1 (doc 5.2, 5.3).
- The position of 2^emin is E = B + p + 3 − sExp; that of 2^(emax+1) is O = 3B + p + 1 − sExp.
- The subnormal quantum is S = E − p + 1, and the precision-p quantum is R_u = m − p + 1 = 2 + d.
- IEEE 754 rounds at R* = max(R_u, S).
- t = `roundedSig >> p` ∈ {0, 1, 2} is the top two bits of the rounded significand (stage 2: letters N−3, N−4 of `roundedSig`).

Each Verilog expression and the integer formula it means, for every w and p. This is H1.

| expression (line) | integer meaning |
| --- | --- |
| `doShiftSigDown1` (149) | d, the top bit of `in_sig` |
| mark from `lowMaskLoHi` (primitives line 85, used at 179; and 188) | `roundMask_main[j]` = [u + j < B + 2] for j = 0…p, with u = `sExp[w:0]` read unsigned (sExp mod 4B). So `roundMask` has its ones below RHF = 2 + max(d, clamp(B + 2 − u, 0, p + 1)). For sExp ≥ 0 that is max(R_u, min(S, T)). |
| `roundMask[2+d]` (249) | RHF > R_u: tininess before rounding |
| `roundMask[3+d]` (253) | RHF > R_u + 1 |
| `sRoundedExp` (221) | sExp + t |
| `sRoundedExp >>> (w−1) >= 3` (228) | sExp + t ≥ 3B: overflow |
| `sRoundedExp < outMinNonzeroExp` (230) | sExp + t < B + 3 − p: total underflow |
| `sAdjustedExp >>> w <= 0` (247) | sExp < 2B |
| `roundCarry` (241) | bit m+1 of y = ρ(x, RHF) |
| `unboundedRange_roundIncr` (237) | the increment of rounding at R_u, from bit R_u − 1 and the bits below it |
| result (271–312) | overflow: infinity if ne, na or magUp, else the largest finite number. Total underflow: the smallest subnormal if magUp or odd, else zero. Otherwise exponent field `sRoundedExp` and the fraction bits of y. |

## 2. The exponent stage for every format, by z3

`stage3/expstage.py` writes SMT-LIB files to `stage3/smt/` and runs z3 (Z3 version 5.3.3). It uses linear integer arithmetic, symbolic in the format.

**Variables:**

- H ≥ 2, with B = 2H = 2^(w−1); the claims are proved for every integer H ≥ 2, not only powers of two;
- 3 ≤ p ≤ H + 3 (the documentation's constraint);
- −4B ≤ sExp ≤ 4B − 1;
- d ∈ {0, 1};
- the rule (one of five);
- the tininess control.

**HardFloat:** the integer formulas of section 1.

**The datapath, abstracted by facts about ρ at the three positions RHF, R*, R_u** (true by the definition of rounding):

- for r ≤ m: inexactness, and the top bit of y is m + c_r;
- for r > m: y is 0 or 2^r, with which one fixed by the rule when r ≥ m + 2, and for toward zero, away and odd when r = m + 1;
- toward zero and odd never carry;
- equal positions give equal facts;
- inexactness is monotone in r;
- lemma L1 (stage 2, every width).

**Reference:** IEEE overflow, inexact, tininess before and after, underflow, result kind and exponent field, as `stage1/ref.py` defines them, in the same coordinates.

Each claim is proved by z3 answering "unsat" to its negation (`record/stage3/expstage.txt`):

| claim | result |
| --- | --- |
| domain and facts satisfiable (the claims are not vacuous) | sat |
| overflow flag = IEEE overflow | proved |
| inexact flag = IEEE inexact | proved |
| underflow flag = IEEE underflow, both tininess modes | proved |
| result kind (zero, finite, ∞, largest finite) = IEEE | proved |
| finite result: exponent field, and the same rounding position or both powers of two | proved |
| exponent field never takes the zero, ∞ or NaN codes for a finite nonzero result | proved |
| `sRoundedExp` fits its w + 3 signed bits | proved |
| `lowMaskLoHi` reads inside its (2^(w+1)+1)-bit constant | proved |
| the `sExp < 2^w` term of the underflow flag is redundant | proved |

**Sensitivity** (planted faults in the model):

- Total underflow with ≤ for <: counter-models for inexact, underflow, kind and value.
- Overflow at 3B − 1: counter-models for overflow, inexact and kind.
- Tininess-after exception removed: counter-models for underflow, and for the redundancy claim, which restates HardFloat's underflow formula with that exception.

**The model against HardFloat's real outputs** (`stage3/factcheck.py`, `record/stage3/factcheck.txt`). Data: every valid finite nonzero input of formats (3, 5), (4, 7) and (5, 5), from stage 1's Verilator dumps.

- Every fact asserted about ρ is false on 0 of 1,916,928 inputs.
- The model's prediction of HardFloat (kind, exponent field, overflow, underflow, inexact) is wrong on 0 of 1,916,928.

## 3. The whole module against the formulas, formally, at 135 formats

`stage3/whole/spec_gen.py`, `one.sh`, `all.sh`; `record/stage3/whole.txt`.

**The spec module.** For each format, `spec_gen.py` writes a Verilog module that computes the whole output of `roundRawFNToRecFN`: the recoded result, a care mask of the bits the documentation fixes, and the five flags. It is built from:

- the integer formulas of section 1 as integer comparisons on 40-bit signed values (H1);
- the rounding datapath of the **definition**: `ref_round.bv` emitted by `stage2/bv2v.py`, not the HardFloat transcription;
- the fraction field as "the p − 1 bits of the rounded significand below its top bit", `(roundedSig >> t)[p−2:0]` (H2);
- the special inputs as the documentation states them (H3);
- the recoding table of doc 5.2.

**The check.** A miter with the real `roundRawFNToRecFN#(w, p)`, read unchanged from the source, asserts that wherever the documented domain holds, the outputs agree on every care bit and on all five flags. The domain: a valid mode; not both exception inputs; sig top bits not 00 for a finite nonzero input. Then `sat -verify -prove bad 0`, with a 900 s limit per format.

| formats | result |
| --- | --- |
| every documented format with w = 3…8: p = 3…2^(w−2)+3, 132 formats, binary16 (5, 11) and binary32 (8, 24) among them | 132 of 132 EQUIVALENT |
| binary64 (11, 53) | EQUIVALENT, 1 s |
| x87 extended (15, 64) | EQUIVALENT, 42 s |
| binary128 (15, 113) | EQUIVALENT, 88 s |
| planted fault in HardFloat (the ties-to-even clear removed), (4, 5) | DIFFERENT |
| planted fault in the spec (total underflow ≤ instead of <, `spec_gen_mut.py`), (4, 5) | DIFFERENT |

Total 179 s for the 135. Yosys 0.70+385.

**What it gives.** At these 135 formats H1, H2 and H3 are not hand steps: the source equals a module whose correctness follows from section 2 and stage 2.

**Outside the documented domain.** At the undocumented format (3, 6) the spec and HardFloat agree bit for bit, including the smallest subnormal whose exponent code collides with zero. The spec reproduces HardFloat's encoding, and the proof that this encoding is IEEE-correct (the claim `exponent_field_code`) needs p ≤ 2^(w−2) + 3. Outside the domain the two agree with each other and both differ from IEEE, as stage 1 found.

## 4. Scope

- **Exponent width.** HardFloat's localparams are 32-bit Verilog integers. `lowMaskLoHi` computes `1<<inWidth` with inWidth = w + 1, which is negative from w = 30 on. The integer model is therefore the source's meaning for 3 ≤ w ≤ 29.
- **Outside the documented domain.** The formats with p > 2^(w−2) + 3, and inputs with `invalidExc` = `infiniteExc` = 1 (see stage 1), are not covered.
- **Special inputs** are covered by section 3 at the 135 formats and by stage 1 at 17. The z3 model of section 2 does not cover them.

## Files

| file | role |
| --- | --- |
| `stage3/expstage.py` | model and claims |
| `record/stage3/smt/` | the SMT-LIB files, one per claim and variant |
| `record/stage3/expstage.txt` | z3 results |
| `stage3/factcheck.py`, `record/stage3/factcheck.txt` | model against HardFloat's outputs |
| `stage3/whole/` | the whole-module check |
| `record/stage3/whole.txt` | its results |
