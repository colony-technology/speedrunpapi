# SEC-DED (72, 64) and (39, 32) verification evidence

Encoder, syndrome generator and corrector for the Hsiao codes of OpenTitan's `prim_secded_72_64` (64 data bits, 8 check bits) and `prim_secded_39_32` (32 and 7): single errors corrected, double errors flagged. A proof over every data word, every single and every pair of flipped bits, by linear algebra with exhaustion of the corrector and again by SAT on the whole chain. `evidence.md` is the summary in DO-254 / ISO 26262 terms.

| Block | LUT-6 | Levels | OpenTitan RTL, same Yosys flow |
| --- | --- | --- | --- |
| encoder `colony_secded72_enc` | 31 | 2 | 59, 3 |
| syndrome `colony_secded72_syn` | 35 | 3 | |
| corrector `colony_secded72_cor` | 85 | 2 | |
| decoder (syndrome + corrector) | 120 | 5 | 151, 5 |
| encoder `colony_secded39_enc` | 17 | 2 | 26, 3 |
| syndrome `colony_secded39_syn` | 19 | 2 | |
| corrector `colony_secded39_cor` | 43 | 2 | |
| (39, 32) decoder | 62 | 4 | 77, 5 |

## Contents

| Path | What |
| --- | --- |
| `source/` | the OpenTitan encoder and decoder RTL the matrix is read from, with its licence |
| `block/NAME.v`, `block/NAME_lut6.v` | the three blocks, plain and LUT primitives |
| `proof/H_72_64.json`, `proof/H_39_32.json` | the matrices, their columns and the Hsiao weights |
| `proof/NAME.blif`, `proof/NAME.json` | the netlists and derivations |
| `proof/independent_secded_checker.py` | proof 1: matrix conditions, linear forms, corrector by exhaustion |
| `proof/independent_linear_checker.py` | the CRC package's matrix checker, for the two XOR networks |
| `proof/mutate_secded.py` | negative controls for proof 1 |
| `proof/sat_secded.py`, `proof/lut_to_dollar_lut.v` | proof 2: SAT on encoder → error → syndrome → corrector |
| `tools/matrix.py`, `tools/build_secded.py` | matrix from the source; the blocks, built with the linear compiler and Yosys |
| `tools/cost.py` | the cost table |
| `tools/detector_r.py` | the smallest number of check bits for a detector beside each XOR block |
| `tools/run_all.py` | runs every check, writes `results/` and `MANIFEST.sha256` |

Ports: encoder `d[63:0]` → `c[7:0]`. Syndrome `r[71:0]` (`r[63:0]` data, `r[71:64]` check bits, as stored) → `s[7:0]`. Corrector `r[63:0]`, `s[7:0]` → `q[63:0]`, `corrected`, `uncorrectable`.

Limit: three or more flipped bits are outside the claim; an odd number of them gives `corrected = 1` with wrong data, as in every SEC-DED code with these flags.

## Rerun

Needs Python 3.9 or later (standard library only), Yosys and z3 (YosysHQ OSS CAD Suite). `BIN` holds `yosys` and `z3`.

```sh
cd hardware/evidence/secded
# proof 1 for (72, 64), seconds, Python only; the same with 39_32 / secded39 for (39, 32)
python3 proof/independent_secded_checker.py --source source/prim_secded_72_64_dec.sv \
    --enc proof/colony_secded72_enc.blif --syn proof/colony_secded72_syn.blif --cor proof/colony_secded72_cor.blif
# every check, both codes, SAT included
python3 tools/run_all.py --bin "$BIN" --work ../../../../work-secded
```

## Recorded run

14 November 2026, Apple M1, macOS 27.2, `tools/run_all.py`: ALL PASS.

| Check | Result |
| --- | --- |
| matrix | (72, 64): 72 columns non-zero, distinct, odd; 56 of weight 3, 8 of weight 5; rows 27 each. (39, 32): 32 data columns of weight 3; rows 15 (six) and 13. Both: decoder table equals the columns |
| proof 1 | M, E, S, K accepted for both codes; C1, C2, C3 derived from them |
| negative controls | 151 and 79 LUT mutants rejected; 3 bad matrices rejected for each code |
| proof 2, SAT, LUT6 and plain forms | C1, C2 proved; C3 proved in 71 and 38 miters; the false-claim control gives a counterexample |
| cost | (72, 64) encoder 31 against 59, decoder 120 against 151; (39, 32) encoder 17 against 26, decoder 62 against 77 |
| detector, smallest r | (72, 64) encoder 2, syndrome generator 3; (39, 32) 2 and 2 (no smaller r exists) |

Tool versions, as printed (`results/tools.txt`):

```
Yosys 0.70+385 (git sha1 098e46a36, Release, Clang /usr/local/osxcross/target/bin/aarch64-apple-darwin25.5-clang++ 21.1.8)
Z3 version 4.15.5 - 64 bit
Python 3.15.2
macOS-27.2-arm64-arm-64bit-Mach-O
```
