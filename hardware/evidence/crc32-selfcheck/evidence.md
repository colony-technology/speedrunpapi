# CRC-32 register update with a proven fault detector · verification evidence

Package `crc32-selfcheck`, 14 November 2026, colony.technology. Evidence offered to an applicant. It is not a certification, a statement of compliance, or a claim of credit or of a diagnostic coverage figure under any standard; those are decisions of the applicant and the authority.

## Item

`colony_crc32_d64_sc`: the block `colony_crc32_d64` of [`../crc32/`](../crc32/), unchanged (byte-identical files), and a detector beside it.

| Part | What | LUT-6 | Levels |
| --- | --- | --- | --- |
| block `colony_crc32_d64` | `o = L(s, d)`, register after 64 data bits | 151 | 3 |
| predictor | `p = H L (s, d)`, 2 bits, from `s`, `d` only | 14 | 3 |
| checker | `c = H o`, 2 bits, from `o` only | 7 | 2 after `o` |
| alarm | `alarm = (p[0] ^ c[0]) \| (p[1] ^ c[1])` | 1 | 1 |
| total `colony_crc32_d64_sc` | ports `s[31:0]`, `d[63:0]` → `o[31:0]`, `alarm` | 173 | 6 |

H, bit i of each row selecting `o[i]`: row 0 `32'h9f8b6d47`, row 1 `32'he0f4bafa`. Two check bits is the smallest number that works for this netlist (see Verification).

Inside: the block, the detector, the alarm wire. Outside: what the system does on an alarm, the register and clock, and any test of the alarm path.

## Requirements

| Id | Requirement |
| --- | --- |
| SC-1 | `o` of `colony_crc32_d64_sc` is `o` of `colony_crc32_d64` (CRC-3 of [`../crc32/evidence.md`](../crc32/evidence.md)): the block is unchanged. |
| SC-2 | Fault free, `alarm = 0` for every `s`, `d`. |
| SC-3 | For every net w of the block (each of its 151 LUT outputs, the 32 that drive `o` among them), for each of these faults: w inverted, w stuck at 0, w stuck at 1, any change of the table of w's LUT (one INIT bit flipped is one case), any fault on one input pin of w's LUT; and for every `s`, `d`: if `o` differs from the fault-free `o`, then `alarm = 1`. |
| SC-4 | No net of the predictor, the checker or the alarm logic is read by the block: a single fault there cannot change `o`. It can raise a false alarm or hide the alarm; see "Outside". |
| SC-5 | Ports and module names as in the table. |

What a fault is here: one net of the block, changed in one of three ways (inverted, stuck at 0, stuck at 1), or replaced by a free value (any value on any input), which contains every INIT flip of that net's LUT and every fault on one of its input pins.

Outside the requirements:
- A fault on an input `s[i]` or `d[i]` before it fans out to the block and the predictor. Both then see the same wrong bit and agree; the CRC of a wrong input is computed and no alarm is raised. Input integrity belongs to the stage that drives the block (a parity or CRC on the bus feeding it).
- A fault that holds `alarm` at 0 (the alarm LUT or the alarm wire stuck at 0) shows nothing by itself. It is latent: a second fault in the block would then go unseen. The user tests the alarm path periodically, for example by forcing one predicted bit to its complement for one cycle and checking that `alarm` rises, or brings out the two pairs `(p[j], c[j])` and compares them in a second, independent place.
- Two or more simultaneous faults.
- Faults that change which net a LUT pin is connected to (routing faults), and faults outside this logic (register, clock, reset).

## Verification

**Fault effect (SC-3, the argument).** Every LUT of the block computes the XOR of its inputs (checked from its full table). Changing net w, for any reason, flips w; each LUT that reads w then flips, and so on, so `o` changes by a fixed vector e_w over the 32 outputs: e_w[i] is the parity of the number of paths from w to `o[i]`. It is the same vector for every input and every fault type; the fault type decides only on which inputs w changes. A fault on one input pin of a LUT, or in its table, changes only that LUT's output, so it is a change of that LUT's net. With the fault, `o' = o + e_w`, so the checker gives `c' = H o + H e_w` while the predictor, outside the block, still gives `p = H o`. The alarm rises exactly when `H e_w != 0`. This step, from "for every input and every fault" to "`H e_w != 0` for every net", is proved in Lean 4 for every XOR network: theorems `Xor.flip_fixed`, `Xor.alarm_iff` and `Xor.alarm_of_change`, GitHub Actions run 43653518934 (success, commit 5de3b70). The Lean files are not part of this folder.

**Smallest number of check bits.** The 151 vectors e_w were computed from the netlist (`tools/fault_vectors.py`): 90 distinct, none zero, weights 1 to 13. One check bit would need h · e_w = 1 for all of them; Gaussian elimination over GF(2) shows that system has no solution. Two check bits: the z3 solver finds an H (`results/fault_vectors_d64.txt`). The H used was then chosen among the two-bit solutions by a local search for the fewest ones in predictor and checker (`tools/choose_h.py`; 2,000 restarts, 2 distinct results; a search, not a proven minimum), and compiled with the linear compiler of [`../../linear/`](../../linear/).

**Proof 1, linear algebra (SC-1..4).** `proof/independent_selfcheck_checker.py` reads the flat netlist `proof/colony_crc32_d64_sc.blif`, the block netlist and H, and shares no code with the generators. It accepts only if: the cone of `o` is the block netlist table for table (SC-1); no net in that cone reads a detector net (SC-4); every block LUT is a parity LUT; the predictor bits have the forms `H L` over `s`, `d` and the checker bits the forms `H` over `o` (SC-2: then `p = c` on every input); the alarm table is OR of `p[j] ^ c[j]` on all 16 patterns; and `H e_w != 0` for all 151 nets (SC-3). Accepted (`results/checker_d64.txt`).

**Proof 2, SAT, one miter per fault (SC-3).** `proof/sat_faults.py`: the netlist and a faulty copy side by side in Yosys, `bad = (o != o_faulty) & ~alarm_faulty & ~alarm`, `sat -prove bad 0`. Faults: per net inverted, stuck at 0, stuck at 1, and "free" (w replaced by an input the solver chooses, which contains every other fault of that net); per LUT input pin inverted, stuck at 0, stuck at 1; per LUT every INIT bit flipped. Recorded run: 10,583 faults, all proven. Per net 151 inverted, 151 stuck at 0, 151 stuck at 1, 151 free; per pin 817 inverted, 817 stuck at 0, 817 stuck at 1; 7,528 INIT bits flipped one at a time (`results/sat_faults_d64.txt`). The conjunct `~alarm` (fault-free alarm 0) is SC-2, proven by proof 1; without it the solver has to rediscover a 96-input parity identity, which resolution-based SAT does not do in reasonable time.

**Simulation, fault injection (SC-2, SC-3).** `sim/sim_faults.py` simulates the netlist bit-parallel on random inputs, injects each fault in turn and counts samples where `o` changed and `alarm` stayed 0. 4,096 random inputs: all 453 net faults and all 7,528 INIT flips change `o` on some input; 618,496, 309,035 and 309,461 samples with `o` changed for the inverted, stuck-at-0 and stuck-at-1 faults; 0 of them with `alarm` 0. Fault free, `alarm` was 0 on every sample (`results/sim_faults_d64.txt`). It samples inputs; the proofs cover all 2^96.

**Negative controls.** With check bit 0 removed from the alarm, 58 nets are uncovered; with check bit 1 removed, another 58. The linear checker (`--drop`), the simulation and SAT each list them by name, and the three lists are equal (`results/drops_d64.txt`).

**Cost**, one Yosys flow (`synth_xilinx -flatten -noiopad` on the LUT6 forms; `results/cost_d64.txt`):

| Design | LUT-6 | × block | Levels | Function |
| --- | --- | --- | --- | --- |
| block | 151 | 1.00 | 3 | no detection |
| block + detector | 173 | 1.15 | 6 | detects every listed single fault (this package) |
| duplicate and compare | 323 | 2.14 | 7 | detects a fault in one copy |
| triple modular redundancy | 507 | 3.36 | 7 | corrects a fault in one copy |

## What the applicant can and cannot claim from this package

Can use: for the fault set of SC-3 in this block, a proof over all inputs that every fault that changes `o` raises the alarm, by two unrelated methods, with the faults and the escapes of the negative controls listed by name; and the cost against duplicate and compare in one flow. A safety analysis that counts diagnostic coverage per fault model can use this as the analysis of the block's safety mechanism instead of a sampled fault-injection campaign.

Remains the applicant's:
- The fault model of their analysis, and whether SC-3's set covers it (routing faults and multiple faults are outside it).
- The latent fault of the alarm path and its periodic test.
- That synthesis and place and route keep the block and the detector apart. A tool that merges logic of the predictor with the block breaks SC-4. The LUT6 form keeps the network as built; the applicant checks the implemented netlist.
- The reaction to an alarm, its timing, and everything listed for the applicant in [`../crc32/evidence.md`](../crc32/evidence.md).
