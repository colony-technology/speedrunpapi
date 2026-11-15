# Stage 1. Exact audit of HardFloat's rounding module at small formats

Unit: Berkeley HardFloat Release 1, `HardFloat-1.zip` SHA-256 `6b3757c9fbfa2230c6a2b84605e39372cb589dd7500e979c4f0b8ecc8a03b14b`.
Module: `roundRawFNToRecFN#(expWidth = w, sigWidth = p)` (options 0), which is `roundAnyRawFNToRecFN#(w, p+2, w, p, 0)`.
Sources compiled: `source/HardFloat_primitives.v`, `source/HardFloat_rawFN.v`, includes `source/HardFloat_consts.vi` and `source/RISCV/HardFloat_specialize.vi`.
Specialization: RISCV (no NaN payload propagation; default NaN sign 0, fraction 10…0). The 8086-SSE and ARM-VFPv2 specializations define `HardFloat_propagateNaNPayloads` and are not covered.

Result: **0 mismatches** on every input of the documented domain, in all 17 documented formats with 3 ≤ w ≤ 5 and 3 ≤ p ≤ 7, and in w = 5 up to p = 11. That is 3,297,497,088 inputs, 77,893,632 of them finite nonzero.

## The valid input domain, from the documentation

From `doc/HardFloat-Verilog.html`:

- **Formats** (section 2): w ≥ 3, p ≥ 3, p ≤ 2^(w−2) + 3. "Formats not satisfying these constraints will not always operate correctly." In the grid w 3–5, p 3–7, the formats (3, 6) and (3, 7) are outside.
- **Raw value** (sections 5.3, 10.3, 10.4). `sExp` is a signed integer of w+2 bits, range −2^(w+1) to 2^(w+1) − 1, with the bias of the recoded format. `in_sig` has p+3 bits. For a finite nonzero value its two most significant bits are not 00. The value is x = (−1)^sign · in_sig · 2^(sExp − 2^w − p − 1).
- **Special inputs** (5.3, 10.3):
  - `invalidExc` = 1 gives a NaN and the invalid flag, independent of the other inputs.
  - `invalidExc` = 0 and `infiniteExc` = 1 gives an infinity of sign `in_sign` and the infinite flag.
  - `isNaN` makes every other component irrelevant (the payload is not propagated in RISCV).
  - `isInf` (with `isNaN` = 0) leaves only the sign relevant.
  - `isZero` (with `isNaN` = `isInf` = 0) leaves only the sign relevant.
- **Rounding modes** (6.2): 000, 001, 010, 011, 100, 110. The codes 101 and 111 are not modes.
- **Control** (6.1): tininess before rounding (0) and after rounding (1).

Applied: every combination of control (2), mode (6), the five bits `invalidExc infiniteExc in_isNaN in_isInf in_isZero` (32), sign (2), sExp (2^(w+2)) and in_sig (2^(p+3)). Finite nonzero inputs whose sig has top bits 00 are outside the domain; they were skipped and counted.

## The reference

`stage1/ref.py`. It works in exact rationals (`fractions.Fraction`) and is written from the definitions, not from HardFloat:

- **Format:** IEEE 754-2019 3.3 with bias 2^(w−1) − 1, emin = 1 − bias, emax = bias.
- **Rounding:** round once to the quantum 2^(max(e, emin) − p + 1), with e = ⌊log₂|x|⌋.
  - Rules: ties to even, ties away, toward zero, away from zero.
  - Round to odd as the HardFloat doc defines it: toward zero, then set the last bit if inexact.
  - Mode and sign map to these rules as doc 6.2 says.
- **Overflow** (7.4): the result rounded with unbounded exponent exceeds Ω = (2^p − 1)·2^(emax−p+1). It delivers ∞ for nearest and away, Ω for toward zero and odd, and is inexact.
- **Underflow** (7.5): tiny and inexact.
  - Tininess before rounding: |x| < 2^emin.
  - Tininess after rounding: |x| rounded with unbounded exponent at precision p is below 2^emin.
- **Output:** the standard encoding (sign, E, F), then the recoding table of doc 5.2. Bits that table marks x are not compared: the low exponent bits of zeros and infinities, and the fraction of infinities.
- **Special inputs:** the documented results. NaN is the RISCV default NaN; the flags are as in 10.3.

Checks of the reference itself:

- `stage1/refcheck.py` compares its round-to-nearest-even value, inexact and overflow with the host's IEEE conversion to binary16 (w 5, p 11) and binary32 (w 8, p 24), via Python's `struct`.
  - Coverage: 20,000 random raw inputs per format, plus every sExp with 7 boundary significands.
  - Result: 20,896 and 27,168 cases tested, **0 differences**.
- A planted fault: `replay.sh` writes a copy of `HardFloat_rawFN.v` with the ties-to-even clear of line 213 disabled. At w = 4, p = 5 the harness reports **960 mismatches**, all value mismatches.

## Simulators

- Verilator 5.055 devel rev v5.054-183-g9040f8666, compiled exhaustive harness `stage1/harness.cpp`, one build per format.
- Icarus Verilog version 14.0 (devel) (s20260301-978-g70cee475f-dirty). `stage1/tb_icarus.v` writes the outputs for every valid finite nonzero input of formats (3, 5), (4, 7) and (5, 5): 147,456, 1,179,648 and 589,824 lines. Each file is **identical** to the Verilator dump (`stage1/cross.sh`, `record/stage1/cross.txt`).
- Python 3.15.2 for the reference.

## Counts (`record/stage1/table.md`)

| w | p | documented | inputs applied | finite nonzero | special | mismatches (value, flags) |
| --- | --- | --- | --- | --- | --- | --- |
| 3 | 3 | yes | 1,560,576 | 36,864 | 1,523,712 | 0 (0, 0) |
| 3 | 4 | yes | 3,121,152 | 73,728 | 3,047,424 | 0 (0, 0) |
| 3 | 5 | yes | 6,242,304 | 147,456 | 6,094,848 | 0 (0, 0) |
| 3 | 6 | no | 12,484,608 | 294,912 | 12,189,696 | 2,072 (2,012, 60) |
| 3 | 7 | no | 24,969,216 | 589,824 | 24,379,392 | 113,700 (100,552, 107,612) |
| 4 | 3 | yes | 3,121,152 | 73,728 | 3,047,424 | 0 (0, 0) |
| 4 | 4 | yes | 6,242,304 | 147,456 | 6,094,848 | 0 (0, 0) |
| 4 | 5 | yes | 12,484,608 | 294,912 | 12,189,696 | 0 (0, 0) |
| 4 | 6 | yes | 24,969,216 | 589,824 | 24,379,392 | 0 (0, 0) |
| 4 | 7 | yes | 49,938,432 | 1,179,648 | 48,758,784 | 0 (0, 0) |
| 5 | 3 | yes | 6,242,304 | 147,456 | 6,094,848 | 0 (0, 0) |
| 5 | 4 | yes | 12,484,608 | 294,912 | 12,189,696 | 0 (0, 0) |
| 5 | 5 | yes | 24,969,216 | 589,824 | 24,379,392 | 0 (0, 0) |
| 5 | 6 | yes | 49,938,432 | 1,179,648 | 48,758,784 | 0 (0, 0) |
| 5 | 7 | yes | 99,876,864 | 2,359,296 | 97,517,568 | 0 (0, 0) |
| 5 | 8 | yes | 199,753,728 | 4,718,592 | 195,035,136 | 0 (0, 0) |
| 5 | 9 | yes | 399,507,456 | 9,437,184 | 390,070,272 | 0 (0, 0) |
| 5 | 10 | yes | 799,014,912 | 18,874,368 | 780,140,544 | 0 (0, 0) |
| 5 | 11 | yes | 1,598,029,824 | 37,748,736 | 1,560,281,088 | 0 (0, 0) |

- Documented formats: 3,297,497,088 inputs, 77,893,632 finite nonzero, 3,219,603,456 special, **0 mismatches**.
- Undocumented formats (3, 6) and (3, 7): 37,453,824 inputs, 115,772 mismatches.

## Findings

1. **No mismatch in the documented domain.**
2. **Formats outside the documented constraint fail, as the documentation says they may.**
   - At (3, 6) the smallest subnormal has recoded exponent 2^(w−1) + 3 − p = 1. Its top three bits are 000, the code of zero, so it cannot be encoded.
     - Reproducer: sExp −1, sig 0x101, near_even. HardFloat returns 0x0; the reference wants that subnormal.
   - At (3, 7) the two lowest binades are lost the same way.
   - The constraint p ≤ 2^(w−2) + 3 exists for this reason.
3. **`invalidExc` = `infiniteExc` = 1** (840,302,592 inputs over all formats).
   - The output is the default NaN in every case. The flags are 11000: both bits pass through from line 316.
   - The documentation describes only `invalidExc` = 1, and `invalidExc` = 0 with `infiniteExc` = 1. The source comment says `invalidExc` "overrides `infiniteExc`".
   - No HardFloat module drives both. `divSqrtRecFN_small.v` makes them exclusive (lines 262–263: `majorExc && isNaN` and `majorExc && !isNaN`). The other callers tie `infiniteExc` to 0: `addRecFN` line 241, `mulRecFN` 224, `mulAddRecFN` 465, `recFNToRecFN` 97, `iNToRecFN` 111.
   - This combination is counted as outside the domain. A client that sets both sees two flags.

## Files

| file | role |
| --- | --- |
| `stage1/ref.py` | reference |
| `stage1/harness.cpp` | exhaustive comparison |
| `stage1/tb.v` | wrapper |
| `stage1/one.sh` | one format |
| `stage1/run_all.sh` | the grid |
| `stage1/table.py` | the table |
| `stage1/refcheck.py` | reference against the host |
| `stage1/tb_icarus.v`, `stage1/cross.sh` | second simulator |
| `record/stage1/` | `summary.txt`, `table.md`, `cross.txt` |
