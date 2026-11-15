# Certificate: Berkeley HardFloat `roundRawFNToRecFN`

Unit: HardFloat Release 1 (Verilog) by John R. Hauser, `HardFloat-1.zip` SHA-256 `6b3757c9fbfa2230c6a2b84605e39372cb589dd7500e979c4f0b8ecc8a03b14b`. Module `roundRawFNToRecFN#(expWidth, sigWidth)` with options 0, which is `roundAnyRawFNToRecFN#(w, p+2, w, p, 0)`, compiled with the RISCV specialization.

## What is certified

For every format HardFloat documents (w ≥ 3, 3 ≤ p ≤ 2^(w−2) + 3), up to w = 29 where the source's 32-bit integer constants stay exact, the module returns the IEEE 754-2019 result for every valid finite nonzero raw input, every rounding mode and both tininess settings:

- the correctly rounded value, in the recoded format as HardFloat's documentation states it;
- the overflow, underflow and inexact flags.

The certificate rests on three things:

- an exhaustive check, at the 17 documented formats with w ≤ 5, of every documented input, special inputs included;
- a formal equivalence of the whole module (every output) with a module built from the proved formulas, at 135 formats: every documented format with w = 3…8 (binary16 and binary32 among them), plus binary64, x87 extended (15, 64) and binary128;
- for every format, a proof of the datapath for every width (stage 2) and of the exponent stage for every format (stage 3).

At formats outside those 135, the proof is **conditional on** two things:

- the hand steps H1, H2 and H3 named below, which are formally checked at those 135 formats;
- for p > 113, the line-by-line identity of the datapath transcription.

No counterexample was found in the documented domain.

## How each part was discharged

| part | how discharged | evidence |
| --- | --- | --- |
| Rounded significand, round bit, sticky, inexact (lines 174–218), every width | **proved for all widths** by the automata tool `stage2/bvfsm.py` | `record/stage2/hf_ref.txt`: EQUAL on every N ≥ 6; broken copies refuted (`record/stage2/broken_ref.txt`, `broken2_ref.txt`) |
| The transcription `stage2/hf_datapath.bv` of those lines | **formally equivalent** to HardFloat's own netlist at every p = 3…113, binary16 to binary128 included (Yosys SAT, `roundMask` cut to a free input; the emitter checked against the semantics). **At other widths: by text**, one description line per Verilog line (stage2.md). Also simulated at p = 3…9 and checked against the definition at N = 6…11. | `record/stage2/formal.txt`: 111 of 111 EQUIVALENT, broken copies 10 of 10 DIFFERENT; `record/stage2/anchor.txt`; `stage2/check_ref.py`: 195,840 cases, 0 differences |
| Lemma L1 (the tininess-after term = the carry of rounding one place lower), every width | **proved for all widths** by the tool | `record/stage2/lemma_cu.txt`: EQUAL on every N ≥ 2; a broken right-hand side is refuted (`lemma_cu_broken.txt`); `stage2/check_lemma.py`: 92,170 cases, 0 differences, N = 2…11 |
| Exponent stage, flags, result kind, exponent field, every format | **proved by z3** (linear integer arithmetic, symbolic in w and p) given H1 and the facts about ρ; planted faults give counter-models | `record/stage3/expstage.txt`: 9 claims proved; `record/stage3/smt/` |
| Facts about ρ used by the z3 model | true by the definition of rounding; **checked** on 1,916,928 inputs, 0 false | `record/stage3/factcheck.txt` |
| **H1:** each Verilog expression of the exponent stage means the integer formula in `stage3/expstage.py` | **by hand, and formally equal to the source at 135 formats**: every documented format with w = 3…8, binary64, x87 15/64, binary128 | `record/stage3/whole.txt`: the whole module equivalent to `stage3/whole/spec_gen.py`'s module at 135 of 135 formats (Yosys SAT, at most 88 s each). The spec is built from the integer formulas, the definition's datapath (`ref_round.bv`), H2 and H3 as stated. Planted faults in HardFloat and in the spec: DIFFERENT. Also 1,916,928 inputs against HardFloat's outputs, 0 wrong predictions. |
| **H2:** the fraction field is the bits of ρ below its top (lines 225–226, 305–312) | **by hand, and formally equal to the source at the same 135 formats** | the same run; exhaustive at 17 formats (stage 1) |
| **H3:** special inputs (NaN, ∞, zero, `invalidExc`, `infiniteExc`; lines 264–312) give their documented outputs | **by hand, and formally equal to the source at the same 135 formats** | the same run; exhaustive at 17 formats, 3,219,603,456 inputs |
| Exhaustive audit, 17 documented formats with w ≤ 5 | **checked**, every documented input, against an exact-rational reference | stage1.md; `record/stage1/summary.txt`: 3,297,497,088 inputs, 0 mismatches |
| Verilog semantics | **assumed** (the simulators and Yosys read the source as the standard says). Verilator 5.055 and Icarus 14.0 agree on 1,916,928 outputs. | `record/stage1/cross.txt` |

## Scope and exclusions

Not covered:

- formats with p > 2^(w−2) + 3, which fail, as the documentation says they may (stage1.md);
- w ≥ 30;
- the 8086-SSE and ARM-VFPv2 specializations (NaN payload propagation);
- options other than 0;
- `roundAnyRawFNToRecFN` with unequal input and output formats;
- the input combination `invalidExc` = `infiniteExc` = 1. The output there is the NaN with flags 11000, and no HardFloat module drives it.

The certificate is about the recoded output; `recFNToFN` is not covered. The other HardFloat units (addition, multiplication, fused multiply-add, division, conversions) are not covered. Of them, `mulRecFN`, `mulAddRecFN` and `divSqrtRecFN_small` round through this module in the certified configuration. `addRecFN`, `recFNToRecFN` and `iNToRecFN` use other branches of `roundAnyRawFNToRecFN`.

## Replay

```
EDA_BIN=/path/to/oss-cad-suite/bin zsh replay.sh /path/to/HardFloat-1.zip
```

It prints each check and ends with `replay PASSED` or `replay FAILED`. The logs of record are in `record/`.
