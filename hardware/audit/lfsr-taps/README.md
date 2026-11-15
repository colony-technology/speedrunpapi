# LFSR feedback-tap tables: maximal period of every entry

Hardware libraries ship tables of feedback taps that are meant to give a linear-feedback shift register its longest period, 2^n − 1. We tested every entry of four such tables, under every update rule that reads it, for that period. One entry is not maximal: the 16-bit register of PULP common_cells. The tables of Chisel and OpenTitan are maximal in all 2,568 entries.

| Library, commit | Table | Entries tested | Maximal | Not maximal |
| --- | --- | --- | --- | --- |
| [chipsalliance/chisel](https://github.com/chipsalliance/chisel) `2a75ff9` | `LFSR.tapsMaxPeriod`: 788 widths (2 to 786, 1024, 2048, 4096), 1,118 tap sets, each under `FibonacciLFSR` and `GaloisLFSR` | 2,236 | 2,236 | 0 |
| [lowRISC/opentitan](https://github.com/lowRISC/opentitan) `0d2b191` | `prim_lfsr` `LFSR_COEFFS`: widths 3 to 168, each under `GAL_XOR` and `FIB_XNOR` (one table serves both) | 332 | 332 | 0 |
| [pulp-platform/common_cells](https://github.com/pulp-platform/common_cells) `e73baae` | `cc_lfsr` `Masks`, Galois, widths 4 to 64 | 61 | 61 | 0 |
| pulp-platform/common_cells `e73baae` | the fixed registers `cc_lfsr_8bit`, `cc_lfsr_16bit` | 2 | 1 | **`cc_lfsr_16bit`** |
| control | ten Chisel entries with one tap moved by one place (widths 5, 9, 12, 16, 19, 31, 64, 100, 168, 255) | 10 | 0 | 10 |

## The finding: `cc_lfsr_16bit`

`src/cc_lfsr_16bit.sv`, line 44 (also used through `src/deprecated/lfsr_16bit.sv`, which wraps it):

    shift_in = !(shift_q[15] ^ shift_q[12] ^ shift_q[5] ^ shift_q[1]);
    ...
    shift_d = {shift_q[14:0], shift_in};

| Taps | Cycles over all 65,536 states | Period from the default seed 0 |
| --- | --- | --- |
| 15, 12, 5, 1 (as shipped) | 64,897; 511; 127; 1 | 64,897 |
| 15, 14, 12, 3 (x^16 + x^15 + x^13 + x^4 + 1) | 65,535; 1 | 65,535 |

- 64,897 = 127 × 511.
- Seeds on the two short cycles repeat after 511 or 127 steps.
- The 8-bit register of the same library is maximal.
- `finding-cc_lfsr_16bit/` holds the shipped file with the headers it includes and its licence, a test bench of a few lines (`tb_period.sv`), the full cycle count (`cycles.py`) and the one-line fix (`fix.diff`).

## Method

For a table entry and an update rule, the rule is a map s ↦ A s + b on the state s ∈ GF(2)^n. Here b = 0 for XOR feedback, and b is one bit for XNOR feedback.

1. **The characteristic polynomial.**
   - The rule as the library writes it is run from a random state for 2n + 64 steps. Berlekamp–Massey finds the shortest recurrence of the output bit, of length L, with connection polynomial C(z).
   - L = n held for every entry, and P(z) = z^n C(1/z) is the characteristic polynomial of A.
   - P was also read off the rule by hand for each Fibonacci rule and for the right-shift Galois rule, as 1 + Σ_{i ∈ taps} z^i up to reciprocal. It agreed in every such entry.
2. **Brute force, n ≤ 20.** Every state is run through the map itself, b included, and its cycles are counted. Maximal means one cycle of 2^n − 1 states and one fixed state. This agreed with step 3 on all 113 entries with n ≤ 20 and on the 5 control entries there.
3. **Primitivity.** A is maximal exactly when P is primitive.
   - **Rabin's test:** P is irreducible when x^(2^n) ≡ x (mod P) and gcd(x^(2^(n/q)) − x, P) = 1 for every prime q dividing n.
   - **Order:** an irreducible P is primitive when x^((2^n − 1)/r) ≢ 1 (mod P) for every prime r dividing 2^n − 1.
4. **The factorisations of 2^n − 1** (`data/factors.json`) come from J. Arndt's extract of the Cunningham tables (n ≤ 1200) and from factordb (the Fermat numbers F10 and F11, which complete 2^2048 − 1 and 2^4096 − 1).
   - They are not trusted. On every run the product of the listed factors must equal 2^n − 1 exactly, and every factor must pass Miller–Rabin to the 24 prime bases up to 89 and a strong Lucas test (Baillie–PSW).
   - All 788 widths pass.
5. **Control.** Ten entries with one tap moved by one place must be found non-maximal. All ten are: nine reducible, one irreducible of order dividing (2^12 − 1)/5.

## Rerun from a clean checkout

Needs Python 3.9 or later (standard library only) and, for the last step, Verilator. No network, no credentials.

```sh
cd hardware/audit/lfsr-taps
sh replay.sh                        # every check; ends with PASSED or FAILED (about 6 to 9 minutes)
python3 audit_taps.py data out cc   # one table
```

`data/tables.json` holds every entry as extracted from the files at the commits above. Each file is named there with its git blob id, so the extraction can be checked against the upstream file. `shasum -a 256 -c MANIFEST.sha256` confirms every file of this folder.

## Contents

| Path | What |
| --- | --- |
| `audit_taps.py` | the audit: update rules, Berlekamp–Massey, brute force, Rabin's test, order test, factor verification, control |
| `selftest.py` | the arithmetic on known answers: 12 primes and 13 composites (strong base-2 pseudoprimes among them), five GF(2) polynomials of known type, six factorisations |
| `data/tables.json`, `data/factors.json` | the entries and the factorisations, as described above |
| `results/` | per table, the counts (`*.txt`) and every entry with its polynomial and verdict (`*.json`), from the run recorded below |
| `finding-cc_lfsr_16bit/` | the finding: test bench, cycle count, fix, the shipped file with its headers and licence (Solderpad 0.51) |
| `replay.sh` | runs the checks above |

## Recorded run

14 November 2026, Apple silicon, macOS 27.2: the counts in the first table (`results/`). `replay.sh` from a fresh clone of this branch: PASSED, 10 checks in 537.71 s, under Python 3.9.6 and Verilator 5.055.
