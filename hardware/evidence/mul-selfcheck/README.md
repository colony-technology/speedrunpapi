# Self-checking multiplier verification evidence

An unsigned N by N multiplier in 6-input lookup tables, for N = 8, 16, 32 and 64. Beside it is a detector that raises `alarm` when one table of the multiplier is wrong and the product is wrong with it.
- The detector compares (a mod m)(b mod m) mod m with p mod m, the remainders of `a` and `b` taken from the pins.
- It also watches the one wire the multiplier leaves above its top column.
- For m = 3 it is 136 lookup tables at N = 64, against 6,299 for the multiplier. A second multiplier and a comparison would cost 6,384.

The folder holds a proof of each netlist over all inputs with the independent checker that accepts it, SAT at N = 8, fault simulation at every N, and three negative controls. `evidence.md` is the summary in DO-254 / ISO 26262 terms.

| N | Multiplier, tables | Detector m = 3 | Detector m = 15 | Second multiplier and 2N-bit compare |
| --- | --- | --- | --- | --- |
| 8 | 125 | 22 | 59 | |
| 16 | 449 | 36 (Yosys: 36 LUTs, 4 levels) | 103 (Yosys: 106 LUTs, 6 levels) | 469 |
| 32 | 1,714 | 72 (Yosys: 67 LUTs, 5 levels) | 205 (Yosys: 195 LUTs, 7 levels) | 1,751 |
| 64 | 6,299 | 136 (Yosys: 133 LUTs, 6 levels) | 395 (Yosys: 386 LUTs, 8 levels) | 6,384 |

Tables are counted as built. "Yosys" is `synth; abc -lut 6` on the detector alone; the levels run from the detector's inputs to `alarm`.

**Proved**, for every `a` and `b`, at every N here:
- `p = a × b`.
- Without a fault, `alarm` = 0.
- Claim A, m = 3 and m = 15: if one lookup table of the multiplier is wrong in any way and `p` ≠ `a × b`, then `alarm` = 1. That covers the `p[k]` buffers, the wire above the top, and the propagate LUT of the final adder on a carry chain.
- Claim B, m = 15: the same when all outputs of one cell are wrong at once. This holds for the thirteen cell shapes used here, all with at most three outputs. A cell with four outputs could escape m = 15.

**Not claimed:**
- A fault on an input pin before it fans out.
- A fault in the detector or one that holds `alarm` at 0 (latent; periodic test or a two-rail alarm).
- Two faults at once.
- The carry-chain elements and routing.
- Anything about the netlist a synthesis tool makes from these tables.

## Contents

| Path | What |
| --- | --- |
| `netlists/scN_m3/`, `netlists/scN_m15/` | `selfcheck.blif` (multiplier tables, detector, outputs `p`, `t[0]`, `alarm`), `detector.blif` (the detector alone), `det.json` (one statement per detector node) |
| `netlists/mulN/law.json` | the multiplier's law: one statement per cell, its terms and output wires with their columns; `netlists/mul8/mul.blif` is the N = 8 multiplier alone |
| `netlists/controls/` | the negative controls: `sc8_m3_notop` (no wire above the top in the alarm), `mul8_c3` and `sc8_c3_m3` (a cell correct only on the rows that occur) |
| `proof/check_selfcheck.py` | the independent checker: claims A and B, structure, separation, carry chain |
| `proof/lawcheck2.py` | checker of the multiplier's law (every cell keeps its weighted sum on every row); called by the checker |
| `proof/lawsim2.py` | runs a multiplier netlist on every pair (N = 8) or on random pairs, against `a × b` |
| `proof/gen_detector.py` | the detector generator, from a multiplier netlist and its law |
| `proof/shapes.py` | the cell shapes, with their output weights and the bound B |
| `proof/control3.py` | builds the third negative control and finds its escape |
| `tools/sat_faults.py` | SAT, one query per fault, ABC `strash; sat` |
| `tools/fsim.py` | fault simulation, compiled to C, 64 pairs per word |
| `tools/measure.py` | sizes through Yosys |
| `replay.sh` | runs the checks below and ends with PASSED or FAILED |
| `results/` | the output of every check, from the run recorded below |

Ports: `a[N-1:0]`, `b[N-1:0]` in; `p[2N-1:0]`, `t[0]` (the wire above the top), `alarm` out. All logic is combinational and unsigned.

Limit: the claims are about these netlists. The multiplier's tables must be kept as they are, without merging or remapping, for the proof to describe the device.

## Rerun from a clean checkout

Needs Python 3.9 or later, standard library only. Optional:
- `cc`, for the fault simulation;
- `yosys-abc`, for SAT at N = 8 (about 35 minutes);
- `yosys`, for the sizes.

No network, no credentials.

```sh
cd hardware/evidence/mul-selfcheck
sh replay.sh              # every check found tools for; ends with PASSED or FAILED
sh replay.sh --no-sat     # the same without SAT: under a minute, about 3 more with Yosys for the sizes
# the proof alone, one netlist
python3 proof/check_selfcheck.py netlists/sc64_m15 netlists/mul64/law.json --claim-b
```

`shasum -a 256 -c MANIFEST.sha256` confirms every file, `results/` included, is the one in this release.

## Recorded run

14 November 2026, Apple silicon, macOS 27.2:

| Check | Result |
| --- | --- |
| checker, m = 3 | claim A proved at N = 8, 16, 32, 64 |
| checker, m = 15 | claims A and B proved at N = 8, 16, 32, 64 |
| checker negative controls | claim B with m = 3 refused at every N; detector without the top wire refused; cell correct only on occurring rows refused |
| SAT, N = 8 | m = 3: 423 + 141 queries UNSATISFIABLE; m = 15: 423 + 60 UNSATISFIABLE; controls: 17 and 58 SATISFIABLE |
| fault simulation | N = 8 to 64, 0 escapes in every run of claims A and B; controls 282, 12, and 431,266 to 7,968,692 escapes |
| `replay.sh`, fresh clone of this branch | PASSED: 33 checks with SAT in 1,990 s (no Yosys on the path); 31 checks with the sizes, without SAT, in 200 s |

Tool versions, as printed (`results/tools.txt`):

```
Python 3.15.2
Yosys 0.70+post (git sha1 0c11ea098be065e585a90a06e7b7da49936cf231, Release, AppleClang clang++ 21.0.0.21000334)
UC Berkeley, ABC 1.01 (compiled Oct 13 2026 08:42:43)
Apple clang version 21.0.0 (clang-2100.3.34.2)
macOS-27.2-arm64-arm-64bit-Mach-O
```
