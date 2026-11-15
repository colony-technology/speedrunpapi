# SEC-DED (72, 64) and (39, 32): encoder, syndrome generator and corrector · verification evidence

Package `secded-evidence`, 14 November 2026, colony.technology. Evidence offered to an applicant. It is not a certification, a statement of compliance, or a claim of credit under any standard; those are decisions of the applicant and the authority.

## Item

Single error correction, double error detection over 64 data bits and 8 check bits. The parity-check matrix H = [P | I] is OpenTitan's `prim_secded_72_64` (lowRISC/opentitan, `hw/ip/prim/rtl/prim_secded_72_64_dec.sv`, commit 0d2b191, Apache-2.0, copied in `source/`), a Hsiao code: 56 data columns of weight 3 and 8 of weight 5, check columns the unit vectors, every row of weight 27, 216 ones in all (`results/matrix_72_64.txt`).

| Block | Ports | Function | LUT-6 | Levels |
| --- | --- | --- | --- | --- |
| `colony_secded72_enc` | `d[63:0]` → `c[7:0]` | `c = P d` | 31 | 2 |
| `colony_secded72_syn` | `r[71:0]` → `s[7:0]` | `s = H r`, `r = {c, d}` as stored | 35 | 3 |
| `colony_secded72_cor` | `r[63:0]`, `s[7:0]` → `q[63:0]`, `corrected`, `uncorrectable` | `q[j] = r[j] ^ (s == column j)`; `corrected` = weight of `s` odd; `uncorrectable` = `s != 0`, weight even | 85 | 2 |

The same for (39, 32), OpenTitan `prim_secded_39_32` (same commit): 32 data and 7 check bits; 32 data columns of weight 3, check columns the unit vectors, rows of weight 15 (six) and 13, 103 ones in all (the Hsiao minimum; the rows are near balanced, not perfectly).

| Block | Ports | LUT-6 | Levels |
| --- | --- | --- | --- |
| `colony_secded39_enc` | `d[31:0]` → `c[6:0]` | 17 | 2 |
| `colony_secded39_syn` | `r[38:0]` → `s[6:0]` | 19 | 2 |
| `colony_secded39_cor` | `r[31:0]`, `s[6:0]` → `q[31:0]`, `corrected`, `uncorrectable` | 43 | 2 |

Everything below holds for each code with its own numbers (`results/*_72_64*`, `results/*_39_32*`).

Each block as `NAME.v` and `NAME_lut6.v`. Encoder and syndrome generator are XOR networks from the linear compiler of [`../../linear/`](../../linear/); the corrector is RTL written from the column table and mapped to LUT-6 by Yosys.

Inside: the three functions. Outside: the memory, its address and write path, the check-bit storage, scrubbing, and what the system does with the flags.

## Requirements

| Id | Requirement |
| --- | --- |
| C1 | For every `d`: with `r = {enc(d), d}`, `s = syn(r)` and `cor(r, s)`: `q = d`, `corrected = 0`, `uncorrectable = 0`. |
| C2 | For every `d` and every one of the 72 positions flipped in `r`: `q = d`, `corrected = 1`, `uncorrectable = 0`. |
| C3 | For every `d` and every pair of distinct positions flipped in `r`: `uncorrectable = 1` (and `corrected = 0`). |
| C4 | LUT-6 and levels as in the table, beside the plain RTL of the same code through the same Yosys flow. |

Outside the requirements: three or more flipped bits. With an odd number of them, `s` has odd weight; if `s` is one of the 72 columns a wrong bit is flipped, otherwise no bit is flipped; in both cases `corrected = 1` and the data are wrong. This is a property of every SEC-DED code with these flags.

## Verification

**Proof 1, linear algebra and exhaustion (C1, C2, C3).** The standalone checker `proof/independent_secded_checker.py` (standard library, no code shared with the generators) establishes four facts, and each claim follows from them as stated:
- M. H, read from the source text, is [P | I]; its 72 columns are non-zero, distinct and of odd weight.
- E. Every LUT of the encoder is a parity LUT; output `c[i]` has the GF(2) form of row i of P over `d`.
- S. Every LUT of the syndrome generator is a parity LUT; `s[i]` has the form of row i of H over `r`.
- K. Corrector, by exhaustion: `q[j]` reads only `r[j]` and `s`, and on all 512 values of those 9 inputs equals `r[j] ^ (s == column j)`; `corrected` and `uncorrectable` read only `s`, and on all 256 values of `s` equal "weight odd" and "non-zero, weight even".

C1: by E and S, `s = H {P d, d} = P d + P d = 0`; by K at `s = 0`, `q = r = d` and both flags are 0.
C2: flipping position j adds the unit vector e_j to `r`; by S, `s = 0 + H e_j` = column j; by M that column has odd weight and is equal to no other column, so by K exactly `q[j]` flips back (none if j is a check bit), `corrected = 1`, `uncorrectable = 0`.
C3: flipping i and j gives `s` = column i + column j; by M it is non-zero (the columns differ) and of even weight (two odd weights), so by K `uncorrectable = 1`, `corrected = 0`, and since it is not a column, no `q` bit flips.
Accepted for both codes (`results/checker_72_64.txt`, `results/checker_39_32.txt`); for (39, 32) the exhaustion of K runs over 256 values per data bit and 128 syndromes. The encoder and syndrome networks are accepted again by the CRC package's matrix checker (`results/linear_*.txt`).

Negative controls (`results/checker_mutants_*.txt`): every LUT of the three netlists with one table row removed, 31 + 35 + 85 = 151 mutants for (72, 64) and 17 + 19 + 43 = 79 for (39, 32), all rejected; H with one data column replaced by an even-weight value, by a copy of another column, or by zero: each rejected by condition M.

**Proof 2, SAT on the whole chain (C1, C2, C3).** `proof/sat_secded.py` connects encoder, error, syndrome generator and corrector in one Yosys design, with `d` and the error positions as free inputs, and asks the solver for an input that breaks the claim: one miter for C1, one for C2 (position `p < 72` free), one for C3 (positions `p1 < p2 < 72` free), for the LUT6 files and for the plain files. Recorded run, both forms of both codes: C1 proved, C2 proved; C3 proved as 71 miters for (72, 64) and 38 for (39, 32), one for each first position p1 with p2 free above it, which together cover every pair once (for (72, 64) a single miter with both positions free did not finish in 300 s) (`results/sat_*.txt`). Control: the false claim "two flipped bits give `corrected = 1`" must give a counterexample, and does.

**Cost (C4)**, one Yosys flow (`synth_xilinx -flatten -noiopad`, `results/cost_*.txt`), LUT-6 and levels:

| Block | (72, 64) this package | (72, 64) OpenTitan RTL | (39, 32) this package | (39, 32) OpenTitan RTL |
| --- | --- | --- | --- | --- |
| encoder | 31, 2 | 59, 3 | 17, 2 | 26, 3 |
| decoder (syndrome + corrector) | 120, 5 | 151, 5 | 62, 4 | 77, 5 |

The OpenTitan decoder has the same syndrome, correction and flags (its `err_o[0]` is the odd-weight flag, `err_o[1]` the even non-zero flag).

**Detector, the question of the CRC package.** For the two XOR blocks the smallest number of check bits with `H e_w != 0` for every net (`results/detector_r_*.txt`): (72, 64) encoder 2 (no single check bit among all 256 works), syndrome generator 3 (no pair among all 65,536 works; z3 finds three); (39, 32) encoder 2 and syndrome generator 2 (no single check bit among all 128). Not built here. For the syndrome generator, with 72 inputs and 8 outputs, three predicted parities over the inputs are likely to cost about as much as the block, so duplicate and compare may be cheaper there; that is to be measured, not assumed. The corrector is not linear: a fault's effect depends on the input, so the argument of the CRC package does not apply. A detector for it would need its own proof: for example a second, independent decode of the flags, or a check that `q` re-encodes to the stored check bits after correction. No claim is made for it.

## What the applicant can and cannot claim from this package

Can use: a proof over every data word, every single and every double error, by two unrelated methods, that the delivered encoder, syndrome generator and corrector correct single and flag double errors with the matrix named above; the cost beside the plain RTL of the same code.

Remains the applicant's:
- That the memory, its addressing and its write path are protected as their analysis needs (address errors are not bit errors and this code does not see them unless the address is folded into the check bits).
- Behaviour for three or more errors (see "Outside").
- Faults in these blocks themselves (no detector is claimed here), scrubbing, error logging and the reaction to the flags.
- Verification after synthesis and place and route, timing, tool assessment, configuration control, as listed in [`../crc32/evidence.md`](../crc32/evidence.md).
