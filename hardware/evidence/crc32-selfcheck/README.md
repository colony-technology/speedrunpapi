# CRC-32 with a proven fault detector

The CRC-32 block `colony_crc32_d64` of [`../crc32/`](../crc32/) (IEEE 802.3 / ARINC 664 frame check sequence, 64 bits per clock), unchanged, with a detector beside it: 2 check bits predicted from the inputs, the same 2 computed from the output, and an alarm when they differ. Two proofs, by unrelated methods, that no single fault in the block's logic changes the output without the alarm, on any input. `evidence.md` is the summary in DO-254 / ISO 26262 terms.

| Design | LUT-6 | Levels | Function |
| --- | --- | --- | --- |
| block | 151 | 3 | no detection |
| block + detector | 173 | 6 | detects every single fault of the listed set |
| duplicate and compare | 323 | 7 | detects a fault in one copy |
| triple modular redundancy | 507 | 7 | corrects a fault in one copy |

## Contents

| Path | What |
| --- | --- |
| `block/NAME.v`, `block/NAME_lut6.v` | the block, byte-identical to `../crc32/block/` |
| `block/NAME_sc.v`, `block/NAME_sc_lut6.v` | block + predictor + checker + alarm; ports `s`, `d`, `o`, `alarm` |
| `proof/NAME.blif`, `proof/NAME_sc.blif` | the block netlist; the flat netlist of block and detector |
| `proof/NAME_faults.json` | the effect vector e_w of every block net, and the search for the smallest number of check bits |
| `proof/NAME_H.json` | the check matrix H (rows over `o`) and the predictor rows (over `s`, `d`) |
| `proof/independent_selfcheck_checker.py` | proof 1: linear algebra, standard library only |
| `proof/sat_faults.py` | proof 2: one Yosys SAT miter per fault |
| `sim/sim_faults.py` | fault injection by bit-parallel simulation on random inputs |
| `tools/fault_vectors.py`, `tools/choose_h.py`, `tools/build_selfcheck.py` | e_w and the smallest r; the choice of H; the detector, built with [`../../linear/`](../../linear/) |
| `tools/cost.py` | the cost table, one Yosys flow |
| `tools/run_all.py` | runs every check, writes `results/` and `MANIFEST.sha256` |
| `results/` | the output of every check as printed |

Ports: `s[31:0]` register in, `d[63:0]` data (`d[0]` first), `o[31:0]` register out, `alarm`. `alarm = 1` means `o` is not to be used.

Limits: a fault that holds `alarm` at 0 is latent, so test the alarm path periodically (force one predicted bit to its complement for a cycle; `alarm` must rise). A fault on an input before it fans out reaches block and predictor alike and is not detected. Two faults at once are outside the claim. Synthesis must keep the detector apart from the block; the LUT6 form instantiates the network as built.

## Rerun from a clean checkout

Needs Python 3.9 or later (standard library only), Yosys and z3 (both in the YosysHQ OSS CAD Suite). No network, no credentials. `BIN` is the directory that holds `yosys` and `z3`.

```sh
cd hardware/evidence/crc32-selfcheck
# proof 1, under a second, Python only
python3 proof/independent_selfcheck_checker.py --netlist proof/colony_crc32_d64_sc.blif --block proof/colony_crc32_d64.blif --H proof/colony_crc32_d64_H.json
# negative control: one check bit removed, the uncovered nets by name
python3 proof/independent_selfcheck_checker.py --netlist proof/colony_crc32_d64_sc.blif --block proof/colony_crc32_d64.blif --H proof/colony_crc32_d64_H.json --drop 0
# every check except the SAT run (minutes)
python3 tools/run_all.py --bin "$BIN" --work ../../../../work-selfcheck
# with the SAT run: about 10,000 small proofs, about an hour on one core
python3 tools/run_all.py --bin "$BIN" --work ../../../../work-selfcheck --sat
```

`shasum -a 256 -c MANIFEST.sha256` confirms every file, `results/` included, is the one in this release.

## Recorded run

14 November 2026, Apple M1, macOS 27.2, `tools/run_all.py --sat`:

| Check | Result |
| --- | --- |
| e_w and smallest r | 151 nets, 90 distinct e_w, none zero; r = 1 has no solution, r = 2 found |
| proof 1, linear checker | accepted: block unchanged, detector outside the cone of `o`, H e_w != 0 for all 151 nets |
| proof 2, SAT per fault | 10,583 of 10,583 proven: 604 net faults, 2,451 pin faults, 7,528 INIT flips |
| fault injection, 4,096 inputs | 7,981 faults, each changes `o`; 0 escapes; 0 false alarms |
| check bit removed | 58 nets escape for each bit; checker, simulation and SAT list the same nets |
| cost | 151, 173, 323, 507 LUT-6 (table above) |

Tool versions, as printed (`results/tools.txt`):

```
Yosys 0.70+385 (git sha1 098e46a36, Release, Clang /usr/local/osxcross/target/bin/aarch64-apple-darwin25.5-clang++ 21.1.8)
Z3 version 4.15.5 - 64 bit
Python 3.15.2
macOS-27.2-arm64-arm-64bit-Mach-O
```
