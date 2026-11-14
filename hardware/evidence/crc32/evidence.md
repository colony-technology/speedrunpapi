# CRC-32 register update · verification evidence

Package `crc32-evidence`, 14 November 2026, colony.technology. Evidence offered to an applicant. It is not a certification, a statement of compliance, or a claim of credit under any standard; those are decisions of the applicant and the authority.

## Item

Four soft-IP blocks, Verilog, combinational. Each comes as `NAME.v` (XOR assigns, one kept wire per LUT) and `NAME_lut6.v` (Xilinx LUT1..LUT6 primitives, same network).

| Block | Ports | Function | LUT-6 | Levels |
| --- | --- | --- | --- | --- |
| `colony_crc32_d8` | `s[31:0]`, `d[7:0]` → `o[31:0]` | register after 8 bits | 41 | 2 |
| `colony_crc32_d32` | `s[31:0]`, `d[31:0]` → `o[31:0]` | register after 32 bits | 100 | 3 |
| `colony_crc32_d64` | `s[31:0]`, `d[63:0]` → `o[31:0]` | register after 64 bits | 151 | 3 |
| `colony_crc32_be64` | `s[31:0]`, `d[63:0]`, `e[2:0]` → `o[31:0]` | register after the first 64 − 8e bits | 348 | 13 |

Definition R(s; b0, b1, …): starting from `s`, for each bit b in order, `fb = s[31] ^ b; s = (s << 1) ^ (fb ? 32'h04C11DB7 : 0)`. `s[i]` is the coefficient of x^i. Data bit `d[0]` enters first; byte k of a frame is `d[8k+7:8k]`, least significant bit first.

Inside the block: the update only. Outside: the register, its initial value `32'hFFFFFFFF`, the final complement and bit reversal that form the FCS, the FCS compare, zeroing of bytes past the end of the frame, clocking and reset.

## Requirements

| Id | Requirement |
| --- | --- |
| CRC-1 | `colony_crc32_d8`: for every `s` and `d`, `o = R(s; d[0..7])`. |
| CRC-2 | `colony_crc32_d32`: for every `s` and `d`, `o = R(s; d[0..31])`. |
| CRC-3 | `colony_crc32_d64`: for every `s` and `d`, `o = R(s; d[0..63])`. |
| CRC-4 | `colony_crc32_be64`: for every `s`, every `e` in 0..7 and every `d` whose bits `d[63 : 64−8e]` are zero, `o = R(s; d[0 .. 63−8e])`. |
| CRC-5 | In each block, `NAME.v` and `NAME_lut6.v` compute the function of the netlist that CRC-1..4 are proven on. |
| CRC-6 | Chained from `32'hFFFFFFFF` over a message, `~bitreverse(o)` is the CRC-32 of the message as computed by zlib `crc32`; for "123456789" it is `CBF43926`. Over a message followed by its FCS (least significant byte first) `o` is `C704DD7B`. |
| CRC-7 | No flip-flop, latch, memory, process or clock in any file. |
| CRC-8 | Ports, widths and module names as in the table above. |
| CRC-9 | LUT count and logic levels as in the table above. |

Outside the requirements: the output of `colony_crc32_be64` when the bytes past the valid ones are not zero. `o` is then a fixed function of the inputs but not the CRC, neither specified nor proven. The integrator zeroes those bytes.

## Verification

**Proof (CRC-1..4).** Each block is a linear map over GF(2) from its inputs to its 32 outputs (for `be64`, one map for each value of `e`). `proof/independent_linear_checker.py` and `proof/independent_crc_checker.py` read the netlist `proof/NAME.blif` and share no code with the generator. Each LUT is read in full (all 2^k rows of its table) and accepted only if it is the XOR of a subset of its inputs and 0 at the all-zero input; a network of such LUTs is linear. The checker carries, for every wire, its values on the n unit input vectors as an n-bit mask, and runs the bit-serial recurrence on the same n unit vectors. A linear map is fixed by its values on a basis: every input is a sum of unit vectors, so two linear maps that agree on the n unit vectors agree on all 2^n inputs. Basis vectors compared, each on 32 outputs: d8 40, d32 64, d64 96, be64 544 (for e = 0..7, 32 + 8(8 − e) each, the dead bytes fixed at zero). All four accepted (`results/checker_*.txt`). Negative control: every LUT of every netlist with one row of its table removed, 640 mutants, 640 rejected (`results/checker_mutants.txt`).

**Second proof, unrelated method (CRC-1..5).** Yosys `equiv_make` / `equiv_simple` pairs every named net of each Verilog file with the same net of the BLIF and proves each pair by SAT: d8 73, d32 132, d64 183, be64 380 pairs, all proven, both forms; in the LUT6 forms the primitives enter as Yosys `$lut` cells through `proof/lut_to_dollar_lut.v`. One flipped LUT INIT bit leaves pairs unproven in every block (2, 1, 1, 1). For d8 each form is also proven against the reference model `proof/reference.v` (the recurrence as a Verilog loop) by one SAT miter over all 40 inputs, with Yosys's Xilinx LUT models: all three proven, the flipped-bit mutant gives a counterexample. The same miter for d32 did not finish within 600 s; for d32, d64 and be64 the link to the recurrence is the checker. `proof/lut6_vs_blif.py` checks every LUT instance's pins and INIT against the BLIF table: 41, 100, 151, 348 instances, all match. `results/yosys_equiv.txt`, `results/lut6_vs_blif.txt`.

**Simulation (CRC-1..5).** `sim/tb_rand.sv` in Verilator runs both forms of all four blocks, with Yosys's Xilinx LUT models, against `proof/reference.v`: per block 776 directed vectors (zero and every unit vector of `s` and `d`, for each `e`) and 1,000,000 random vectors, seed 1; 0 mismatches in 1,000,776 per block. It adds a run of the delivered files in a simulator, independent of the BLIF and of both checkers. It does not cover every input, and it shares the definition with the proof: an error in the definition itself is caught only by the known-answer vectors.

**Known answers (CRC-6).** `vectors/vectors.txt`: 53 messages, 15,452 bytes, including "123456789" (`CBF43926`), the empty message, and Ethernet frames of 60 to 67 bytes (every length mod 8), 64, 100, 1514 and 9014 bytes. `vectors/replay.py` recomputes each with a bit-serial loop without zlib, then runs each through 9 paths in Verilator (reference model; d8; d32, d64 and be64 chained with a d8 tail; both forms of each) from `32'hFFFFFFFF`: 0 CRC mismatches, 0 residue mismatches (`results/vectors.txt`). Expected values come from zlib, not from this package.

**Structure (CRC-7..9).** `proof/structure.py`: after Yosys `proc` no flip-flop, latch, memory or process remains in any `NAME.v`; every cell of every `NAME_lut6.v` is LUT1..LUT6; kept wires and LUT cells 41, 100, 151, 348, equal to the netlists; Verilator 5.055 `--lint-only -Wall`: 0 warnings in all 8 files. The independent checkers recompute the LUT count and levels from the netlist and reject a declared value that differs (`results/structure.txt`, `results/checker_*.txt`). Ports and names (CRC-8): the checkers fix the netlist interface; Yosys and Verilator elaborate each module by the name in the table.

## What the applicant can and cannot claim from this package

Can use, as provider data under FAA AC 20-152A / EASA AMC 20-152A §5.11 (COTS IP) or as the IP supplier's verification input under ISO 26262: a functional proof of each block over all inputs at the RTL / netlist level, replayable in seconds; a second proof by an unrelated tool; simulation and standard test vectors. AC/AMC IP-4 Note 1 allows "reliable and trustworthy test data, test cases or procedures from the COTS IP provider" in the verification strategy, and Note 2 "proven standardized test vectors verifying compliance with the standard".

Remains the applicant's:
- Whether the block qualifies as COTS IP at all (AC/AMC §5.11.1: "used by a number of different users"); with no service history, IP-3 complementary assurance.
- Simple / complex classification of the device (CD-1). AMC Appendix B, B.2.1.2: classification is "based on the design content of the device, regardless of the proposed verification method".
- Verification after synthesis and place and route, and in the integrated device (IP-4 items 2 and 3); timing across process, voltage and temperature (CD-7).
- Tool assessment of their synthesis and implementation tools (§5.8, CD-10), and the decision whether the independent checker serves as the independent assessment of our generator's output.
- Requirements capture and trace in their system (IP-6), configuration control (HCI, §5.10), and DAL A / B Appendix B methods (IP-7).
- For ISO 26262: the safety manual, FMEDA and work products of ISO 26262-11 clause 4.5.4, none of which this package contains.

## Sources opened

FAA AC 20-152A, 10/7/22 (faa.gov). EASA AMC 20-152A in "AMC-20 Amendment 19, Change Information", ED Decision 2020/010/R, pp. 71–104 (easa.europa.eu). ISO 26262-11:2018 and -8:2018, public previews on iso.org (headings and informative text only). DO-254 / ED-80 and the normative text of ISO 26262 were not opened; no section of them is quoted here except as cited by the FAA and EASA documents.
