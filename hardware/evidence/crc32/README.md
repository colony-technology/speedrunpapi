# CRC-32 verification evidence

CRC-32 (polynomial `0x04C11DB7`, the IEEE 802.3 and ARINC 664 part 7 frame check sequence), register update for one bus word: 8, 32 and 64 bits per call, and 64 bits with a count of empty bytes. Verilog in two forms, a proof of each block over all inputs with the independent checker that accepts it, a second proof in Yosys, simulation against the bit-serial recurrence, and known-answer vectors. `evidence.md` is the one-page summary in DO-254 / ISO 26262 terms.

## Contents

| Path | What |
| --- | --- |
| `block/NAME.v`, `block/NAME_lut6.v` | the four blocks, XOR assigns and Xilinx LUT1..LUT6 primitives |
| `proof/NAME.blif`, `proof/NAME.json` | the netlist and the derivation (claim, LUT count, levels, SHA-256 of the netlist) |
| `proof/independent_linear_checker.py` | checker for d8, d32, d64 (schema `colony.lut-linear.v1`) |
| `proof/independent_crc_checker.py` | checker for be64, every number of valid bytes (schema `colony.lut-crc.v1`) |
| `proof/mutate_checkers.py` | negative controls: one mutant per LUT, all must be rejected |
| `proof/lut6_vs_blif.py` | every LUT instance of `NAME_lut6.v` against the BLIF |
| `proof/sat_equiv.py`, `proof/reference.v`, `proof/lut_to_dollar_lut.v` | Yosys proofs: each Verilog file against the BLIF, per net; d8 against the reference recurrence |
| `proof/structure.py` | no state, LUT-only, counts, Verilator `-Wall` lint |
| `sim/tb_rand.sv`, `sim/run_sim.py` | both forms of all blocks against the reference recurrence, directed and random |
| `vectors/vectors.txt`, `vectors/make_vectors.py`, `vectors/replay.py`, `sim/tb_kat.sv` | known answers: "123456789", Ethernet frames 60 to 9014 bytes, random messages |
| `tools/build_blocks.py` | rebuilds `block/` and `proof/` from the generator in [`../../linear/`](../../linear/) |
| `tools/run_all.py` | runs every check, writes `results/` and `MANIFEST.sha256` |
| `results/` | the output of every check as printed, from the run recorded below |

Port convention, all blocks: `s` register in, `d` data (`d[0]` first on the wire; byte k is `d[8k+7:8k]`), `o` register out. be64 adds `e`, the number of empty bytes at the top of the word, 0 to 7.

Limit of be64: the bytes past the valid ones, `d[63 : 64−8e]`, must be zero. If they are not, `o` is a fixed function of the inputs but not the CRC, and that case is neither specified nor proven; zero them before the block.

FCS of a frame, from these blocks: register `32'hFFFFFFFF`, feed every byte, FCS = `~bitreverse(o)`, sent least significant byte first. Receiver: feed the frame with its FCS, the register ends at `32'hC704DD7B`.

## Rerun from a clean checkout

Needs Python 3.9 or later (standard library only), Yosys and Verilator (both from the YosysHQ OSS CAD Suite). No network, no credentials. `BIN` is the directory that holds `yosys` and `verilator`.

```sh
cd hardware/evidence/crc32
# the proof alone, seconds, Python only
python3 proof/independent_linear_checker.py --netlist proof/colony_crc32_d64.blif --derivation proof/colony_crc32_d64.json
python3 proof/independent_crc_checker.py   --netlist proof/colony_crc32_be64.blif --derivation proof/colony_crc32_be64.json
# every check
python3 tools/run_all.py --bin "$BIN" --work ../../../../work-crc32
# known answers only
python3 vectors/replay.py --verilator "$BIN/verilator" --cells "$BIN/../share/yosys/xilinx/cells_sim.v" --work ../../../../work-kat
# rebuild the blocks from the generator and compare
python3 tools/build_blocks.py --linear ../../linear --out ../../../../work-rebuild
for f in block/* proof/*.blif proof/*.json; do cmp "$f" "../../../../work-rebuild/$f"; done   # silent = identical
```

`shasum -a 256 -c MANIFEST.sha256` confirms every file, `results/` included, is the one in this release.

## Recorded run

14 November 2026, Apple M1, macOS 27.2, `tools/run_all.py --n 1000000`:

| Check | Result |
| --- | --- |
| independent checkers | d8, d32, d64, be64 accepted: 41 / 2, 100 / 3, 151 / 3, 348 / 13 LUT-6 / levels |
| checker negative controls | 640 one-row mutants, 640 rejected |
| LUT6 file vs BLIF | 41, 100, 151, 348 instances, all match |
| Yosys per-net equivalence | 73, 132, 183, 380 net pairs proven, both forms; mutants unproven |
| Yosys miter, d8 vs reference | 3 forms proven; mutant gives a counterexample |
| structure, lint | no state; LUT-only; 0 Verilator `-Wall` warnings |
| simulation | 1,000,776 vectors per block, 0 mismatches |
| known answers | 53 messages, 15,452 bytes, 9 paths, 0 mismatches |

Tool versions, as printed (`results/tools.txt`):

```
Yosys 0.70+385 (git sha1 098e46a36, Release, Clang /usr/local/osxcross/target/bin/aarch64-apple-darwin25.5-clang++ 21.1.8)
Verilator 5.055 devel rev v5.054-183-g9040f8666 (mod)
Python 3.15.2
zlib 1.2.12
macOS-27.2-arm64-arm-64bit-Mach-O
```

Generator: [`../../linear/linear_compiler.py`](../../linear/) and `crc_gen.py`, unchanged since commit `65651dbcba49dcf7ac4e3b357c4b46e058021340`. The checkers in `proof/` are copies of the ones in that directory.
