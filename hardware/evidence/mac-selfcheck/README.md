# Self-checking multiply-accumulate verification evidence

An unsigned multiply-accumulate p = a × b + c in 6-input lookup tables: a and b of N bits, c of 2N bits, p of 2N + 1 bits, for N = 4, 5, 6, 8, 16, 32 and 64. The addend enters the same tree as the partial products, one more term per column.
- Beside it is the detector of [`../mul-selfcheck/`](../mul-selfcheck/), with one more residue. It compares ((a mod m)(b mod m) + c mod m) mod m with p mod m, the residues of a, b and c taken from the pins.
- It also watches the one wire the tree leaves above its top column.
- For m = 3 it is 206 tables at N = 64 as built (195 LUTs through Yosys), against 6,139 for the multiply-accumulate. A second multiply-accumulate and a comparison would cost 6,210.

The folder holds a proof of each netlist over all inputs with the independent checker that accepts it, SAT at N = 4 and 5, fault simulation at N = 4 to 32, and three negative controls. `evidence.md` is the summary in DO-254 / ISO 26262 terms.

| N | Multiply-accumulate, tables | Detector m = 3 | Detector m = 15 | Second MAC and (2N+1)-bit compare |
| --- | --- | --- | --- | --- |
| 4 | 45 | 22 (Yosys: 14 LUTs, 4 levels) | 53 (Yosys: 39 LUTs, 5 levels) | 49 |
| 5 | 67 | 22 (Yosys: 18 LUTs, 4 levels) | 53 (Yosys: 49 LUTs, 5 levels) | 72 |
| 6 | 87 | 24 (Yosys: 19 LUTs, 4 levels) | 61 (Yosys: 54 LUTs, 5 levels) | 92 |
| 8 | 137 | 34 (Yosys: 27 LUTs, 4 levels) | 89 (Yosys: 77 LUTs, 6 levels) | 146 |
| 16 | 468 | 58 (Yosys: 53 LUTs, 5 levels) | 161 (Yosys: 154 LUTs, 7 levels) | 487 |
| 32 | 1,788 | 110 (Yosys: 98 LUTs, 6 levels) | 309 (Yosys: 293 LUTs, 8 levels) | 1,825 |
| 64 | 6,139 | 206 (Yosys: 195 LUTs, 6 levels) | 597 (Yosys: 584 LUTs, 9 levels) | 6,210 |

Tables are counted as built. "Yosys" is `synth; abc -lut 6` on the detector alone; the levels run from the detector's inputs to `alarm`.

**Proved**, for every a, b below 2^N and c below 2^(2N), at every N here:
- p = a × b + c.
- Without a fault, `alarm` = 0.
- Claim A, m = 3 and m = 15: if one lookup table of the multiply-accumulate is wrong in any way and p ≠ a × b + c, then `alarm` = 1. That covers the `p[k]` buffers, the wire above the top, and the propagate LUT of the final adder on a carry chain.
- Claim B, m = 15: the same when all outputs of one cell are wrong at once. This holds for the 22 cell shapes used here, all with at most three outputs.

**Not claimed:**
- A fault on an input pin before it fans out (c included).
- A fault in the detector or one that holds `alarm` at 0 (latent; periodic test or a two-rail alarm).
- Two faults at once.
- The carry-chain elements and routing.
- Anything about the netlist a synthesis tool makes from these tables.

## Contents

| Path | What |
| --- | --- |
| `netlists/scmN_m3/`, `netlists/scmN_m15/` | `selfcheck.blif` (the multiply-accumulate's tables, the detector, outputs `p`, `t[0]`, `alarm`), `detector.blif` (the detector alone), `det.json` (one statement per detector node) |
| `netlists/macN/law.json` | the law: one statement per cell, its terms (partial products, wires, addend bits) and output wires with their columns; `netlists/mac4/mul.blif` is the N = 4 multiply-accumulate alone |
| `netlists/controls/` | the negative controls at N = 4: `scm4_m3_notop` (no wire above the top in the alarm), `mac4_c3` and `scm4_c3_m3` (a cell correct only on the rows that occur) |
| `proof/check_selfcheck_mac.py` | the independent checker: claims A and B, structure, separation, carry chain |
| `proof/lawcheck_mac.py` | checker of the law (every cell keeps its weighted sum on every row; every partial product and addend bit used once); called by the checker |
| `proof/macsim.py` | runs a multiply-accumulate netlist on every input (N = 4) or on corners and random inputs, against a × b + c |
| `proof/gen_detector_mac.py` | the detector generator, from a netlist and its law |
| `proof/shapes_mac.py` | the cell shapes, with their output weights and the bound B |
| `proof/control3_mac.py` | builds the third negative control and finds its escape |
| `tools/sat_faults_mac.py` | SAT, one query per fault, ABC `strash; sat`; `--split` ties the top pins of c |
| `tools/fsim_mac.py` | fault simulation, compiled to C, 64 inputs per word |
| `tools/measure_mac.py` | sizes through Yosys |
| `replay.sh` | runs the checks below and ends with PASSED or FAILED |
| `results/` | the output of every check, from the run recorded below |

Ports: `a[N-1:0]`, `b[N-1:0]`, `c[2N-1:0]` in; `p[2N:0]`, `t[0]` (the wire above the top), `alarm` out. All logic is combinational and unsigned. These copies of the multiplier folder's tools differ only where the addend enters: one more input word, one more residue, one more output bit.

Limit: the claims are about these netlists. The tables must be kept as they are, without merging or remapping, for the proof to describe the device.

## Rerun from a clean checkout

Needs Python 3.9 or later, standard library only. Optional:
- `cc`, for the fault simulation;
- `yosys-abc`, for SAT at N = 4 (under a minute);
- `yosys`, for the sizes.

No network, no credentials.

```sh
cd hardware/evidence/mac-selfcheck
sh replay.sh              # every check found tools for; ends with PASSED or FAILED
sh replay.sh --no-sat     # the same without SAT
# the proof alone, one netlist
python3 proof/check_selfcheck_mac.py netlists/scm64_m15 netlists/mac64/law.json --claim-b
```

`shasum -a 256 -c MANIFEST.sha256` confirms every file, `results/` included, is the one in this release.

## Recorded run

14 November 2026, Apple silicon, macOS 27.2:

| Check | Result |
| --- | --- |
| checker, m = 3 | claim A proved at N = 4, 5, 6, 8, 16, 32, 64 |
| checker, m = 15 | claims A and B proved at N = 4, 5, 6, 8, 16, 32, 64 |
| checker negative controls | claim B with m = 3 refused at every N; detector without the top wire refused; cell correct only on occurring rows refused |
| SAT, N = 4 (16 input bits) | claim A, each table a free input: m = 3 54 of 54 UNSATISFIABLE, m = 15 54 of 54; claim B, m = 15, each cell's outputs free: 22 of 22; controls: 21 of 22 and 5 of 54 SATISFIABLE |
| SAT, N = 5 (20 input bits) | claim A: m = 3 78 of 78, m = 15 78 of 78; claim B: 31 of 32 directly, the 32nd (cell 13) split on c[9..6] into 16 sub-queries, 16 of 16 UNSATISFIABLE |
| SAT, N = 6 (24 input bits) | tried: claim A, m = 3, the first 2 of 100 queries UNSATISFIABLE in 143.78 s and 159.54 s; stopped there, since at that rate one mode takes about 4 to 8 hours |
| SAT, N = 8 (32 input bits) | tried: the first 18 of 462 queries (three faults per table, m = 3) each reached the limit of 300 s with ABC `sat`; on one of them `iprove`, `dsat` and `dprove` gave no verdict in 300 s each. N = 8 and above rest on the checker and fault simulation |
| fault simulation | N = 4, 5, 6, 8, 16, 32: 0 escapes in every run of claims A and B; controls escape |
| `replay.sh`, fresh clone of this branch | PASSED: 43 checks with SAT in 84.63 s (no Yosys on the path); 41 checks with the sizes, without SAT, in 67.28 s |

Tool versions, as printed (`results/tools.txt`):

```
Python 3.9.6
Python 3.15.2
Yosys 0.70+post (git sha1 0c11ea098be065e585a90a06e7b7da49936cf231, Release, AppleClang clang++ 21.0.0.21000334)
UC Berkeley, ABC 1.01 (compiled Oct 13 2026 08:42:43)
Apple clang version 21.0.0 (clang-2100.3.34.2)
macOS-27.2-arm64-arm-64bit-Mach-O
```
