# Self-checking multiplier · verification evidence

Folder `hardware/evidence/mul-selfcheck`, 14 November 2026, colony.technology. Evidence offered to an applicant. It is not a certification, a statement of compliance, or a claim of credit under any standard; those are decisions of the applicant and the authority.

## Item

An unsigned N by N multiplier in 6-input lookup tables, with a detector beside it. Netlists for N = 8, 16, 32 and 64, each with the detector for m = 3 and for m = 15 (`netlists/scN_mM/selfcheck.blif`). The multiplier's tables inside `selfcheck.blif` are the multiplier as built, unchanged.

Ports: `a[N-1:0]`, `b[N-1:0]` → `p[2N-1:0]`, `t[0]`, `alarm`.

The multiplier is a tree of counting cells, then one ripple of full adders. Each cell replaces terms by wires that count them: sum of 2^k × term = sum of 2^k × output. `netlists/mulN/law.json` states each cell: its terms and its output wires, with their columns.

The detector is three parts:
- The remainders of `a` and of `b` modulo q, computed from the pins only.
- The remainder of `p` modulo q.
- One table that compares (a mod q)(b mod q) mod q with p mod q.

For m = 3, q = 3. For m = 15, q = 3 and q = 5. Since 15 = 3 × 5, a mismatch modulo 15 is a mismatch modulo 3 or modulo 5.

The multiplier leaves one wire above its top column: the carry out of the last full adder, column 2N. It is 0 when nothing is broken. It is kept, brought out as `t[0]`, and fed to the alarm. `alarm` = 1 when a mismatch table says so or that wire is 1.

| N | Multiplier, tables as built | Detector m = 3, as built | Detector m = 15, as built | Detector m = 3, Yosys | Detector m = 15, Yosys | Second multiplier and 2N-bit compare |
| --- | --- | --- | --- | --- | --- | --- |
| 16 | 449 | 36 | 103 | 36 LUTs, 4 levels (8.02 %) | 106 LUTs, 6 levels (23.61 %) | 449 + 20 = 469 |
| 32 | 1,714 | 72 | 205 | 67 LUTs, 5 levels (3.91 %) | 195 LUTs, 7 levels (11.38 %) | 1,714 + 37 = 1,751 |
| 64 | 6,299 | 136 | 395 | 133 LUTs, 6 levels (2.11 %) | 386 LUTs, 8 levels (6.13 %) | 6,299 + 85 = 6,384 |

- "Yosys" means `synth; abc -lut 6; opt_clean; stat; ltp -noff` on `detector.blif` (`tools/measure.py`, `results/measure.json`).
- The percentages are of the multiplier's own table count.
- The levels are from the detector's inputs (`a`, `b`, `p`, the wire above the top) to `alarm`. The alarm therefore comes that many levels after `p`.
- The same Yosys flow on the multiplier's own tables gives 536, 2,567 and 10,988 LUTs, because it remaps them. The table counts above are the netlist as built.

## Requirements

| Id | Requirement |
| --- | --- |
| SCM-1 | `p = a × b` for every `a`, `b` below 2^N. |
| SCM-2 | Without a fault, `alarm` = 0 for every `a`, `b`. |
| SCM-3 | Claim A, m = 3 and m = 15. For every `a` and `b`, and every single lookup table of the multiplier whose output is wrong in any way (inverted, stuck at 0, stuck at 1, any wrong function), if `p` differs from `a × b` then `alarm` = 1. This includes the output buffers to `p[k]` and the wire above the top, and also the propagate LUT of a full adder when the final adder is placed on a carry chain. |
| SCM-4 | Claim B, m = 15, for the cell shapes listed below. When all outputs of one cell are wrong at once, if `p` differs from `a × b` then `alarm` = 1. |
| SCM-5 | The residues of `a` and `b` depend on the pins only. No table of the multiplier reads a net of the detector. The residue of `p` reads `p` only. |
| SCM-6 | Table counts and levels as in the table above. |

Outside the requirements, and not claimed:
- **A fault on the stem of an input pin before it fans out.** The multiplier and the residue logic then both see the same wrong number. The product is correct for that number, and its remainder agrees.
- **A fault that holds `alarm` at 0, or any fault inside the detector.** Such a fault is latent. It needs a periodic test of the alarm path, or a two-rail alarm.
- **Two faults at once.** Two wrong tables can give an error that is a multiple of m.
- **Cells with four or more outputs** (see the cell shapes below). There are none in these netlists. A cell with four outputs can escape m = 15.
- **The carry-chain elements themselves.** A fault in MUXCY, XORCY or the routing between them is not a lookup-table fault.

## Verification

**Why the claims hold.**
- `proof/lawcheck2.py` proves that every cell keeps its weighted sum on every row of its tables, including rows that cannot occur without a fault.
- Suppose one table in column k is wrong. Every later cell is correct on all rows, so it carries the error on unchanged. The final value is then a × b + e × 2^k, with e = −1, 0 or +1.
- a × b − 2^k is never negative: the wire that should have been 1 was part of the sum.
- a × b + 2^k can reach 2^(2N). Then the wire above the top is 1, and the alarm reads it.
- Otherwise p = a × b ± 2^k. Since 2^k is not 0 modulo 3 or 15, the remainders differ.
- When all outputs of one cell are wrong, the error is d × 2^k. Here d lies between −T (all terms 1, all outputs 0) and B (all terms 0, all outputs 1). B is the sum of the cell's output weights.
- No nonzero multiple of 15 lies in that range for any cell below, so the remainders differ whenever d ≠ 0.

**Cell shapes (SCM-4).**
- These are the thirteen shapes used at N = 8, 16, 32 and 64 (`proof/shapes.py`, `results/shapes.md`).
- Every output has sign +1, and its offset is its column above the cell's lowest.
- T is the largest value of the terms, and B = sum of 2^offset over the outputs.
- No shape has four outputs. The largest B is 7.
- So claim B at m = 15 covers every cell of these netlists.
- The limit, which does not arise here: outputs at offsets 0 to 3 give B = 15, and 0000 turned into 1111 gives d = 15, which is 0 modulo 15. Such a cell needs an odd m of 17 or more.

| # | Terms (offset: kind × count) | Outputs (offset, sign) | T | B | d range | Cells at N = 8 | 16 | 32 | 64 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0: pp × 1 | 0 + | 1 | 1 | −1..1 | 1 | 1 | 1 | 1 |
| 2 | 0: pp × 2 | 0 +, 1 + | 2 | 3 | −2..3 | 3 | 8 | 16 | 26 |
| 3 | 0: pp × 3 | 0 +, 1 + | 3 | 3 | −3..3 | 16 | 75 | 320 | 1,321 |
| 4 | 0: pp × 2, 0: wire × 1 | 0 +, 1 + | 3 | 3 | −3..3 | 2 | 1 | 3 | 15 |
| 5 | 0: pp × 1, 0: wire × 1 | 0 +, 1 + | 2 | 3 | −2..3 | 1 | 5 | 5 | 17 |
| 6 | 0: pp × 1, 0: wire × 2 | 0 +, 1 + | 3 | 3 | −3..3 | 3 | 2 | 17 | 22 |
| 7 | 0: wire × 2 | 0 +, 1 + | 2 | 3 | −2..3 | 11 | 19 | 77 | 164 |
| 8 | 0: wire × 3 | 0 +, 1 + | 3 | 3 | −3..3 | 17 | 66 | 165 | 366 |
| 9 | 0: pp × 2, 0: wire × 2 | 0 +, 1 +, 2 + | 4 | 7 | −4..7 | 0 | 0 | 0 | 2 |
| 10 | 0: pp × 1, 0: wire × 4 | 0 +, 1 +, 2 + | 5 | 7 | −5..7 | 1 | 5 | 3 | 7 |
| 11 | 0: wire × 4 | 0 +, 1 +, 2 + | 4 | 7 | −4..7 | 3 | 1 | 7 | 57 |
| 12 | 0: wire × 5 | 0 +, 1 +, 2 + | 5 | 7 | −5..7 | 2 | 10 | 36 | 68 |
| 13 | 0: wire × 6 | 0 +, 1 +, 2 + | 6 | 7 | −6..7 | 0 | 16 | 123 | 678 |

**1. Proof by an independent checker (SCM-1..5).**
- `proof/check_selfcheck.py` shares no code with the multiplier's generator or with `proof/gen_detector.py`. It trusts neither JSON file; every statement is checked against the tables of `selfcheck.blif`. It checks, in order:
  1. It cuts the multiplier's tables out of the netlist and requires `proof/lawcheck2.py` to print PROVED on them.
  2. It gives every multiplier table its column: as a cell output, as a `p[k]` buffer, or as the wire above the top. It accepts no other tables.
  3. It checks every residue table on all its rows. It checks that each residue tree uses each pin, or each `p[k]`, once with weight 2^i mod q. So the roots hold a mod q, b mod q and p mod q exactly.
  4. It checks the compare tables, and the OR tree to `alarm`, on all their rows. The OR tree's leaves must be exactly the mismatch outputs and the wire above the top.
  5. It checks that the residues of `a` and `b` depend on the pins only, and that no multiplier table reads a detector net.
  6. It checks that the cells that leave each `p[k]` form one unbroken ripple of full adders: columns 1..2N−1, each read by the next or above the top.
  7. For the carry-chain form, it checks every row of a wrong propagate LUT (sum by XORCY, carry by MUXCY selecting the carry-in when the propagate is 1). The cell's value moves by −1, 0 or +1 only.
- Results (`results/check/`):
  - Claim A proved at N = 8, 16, 32 and 64, for m = 3 and for m = 15.
  - Claim B proved for m = 15 at every N: d lies in −6..7 (−5..7 at N = 8) over all cells.
  - Each run takes under a second.
- SCM-2 follows from the same checks: p = a × b, the wire above the top is 0, and the residues are exact.

**2. SAT at N = 8 (SCM-3, SCM-4).**
- Each query is one netlist for ABC. It holds the fault-free multiplier beside the self-checking circuit with the fault, and one output: some `p[k]` differs from the fault-free `p`, and `alarm` = 0. The engine is ABC `strash; sat` (MiniSat inside `yosys-abc`), with a limit of 300 s per query (`tools/sat_faults.py`). UNSATISFIABLE means no input pair gives such an escape.
- Results (`results/sat/`; no query timed out or ended undecided):
  - m = 3, every multiplier table stuck at 0, stuck at 1 and inverted: 423 queries, 423 UNSATISFIABLE, slowest 11.72 s.
  - m = 3, every table replaced by a free input, which is any wrong function at once: 141 queries, 141 UNSATISFIABLE, slowest 9.85 s.
  - m = 15, three faults per table: 423 queries, 423 UNSATISFIABLE, slowest 19.86 s.
  - m = 15, all outputs of one cell replaced by free inputs: 60 queries, 60 UNSATISFIABLE, slowest 35.16 s.
- At N = 12 (289 tables, 867 queries) one query ran for about 600 s, so this method stops at N = 8. The checker covers every N.

**3. Fault simulation (SCM-3, SCM-4).**
- `tools/fsim.py` compiles `selfcheck.blif` to C, 64 input pairs per machine word, and re-evaluates the netlist from the wrong table on. It applies every fault to every pair and counts wrong products, alarms and escapes (wrong and no alarm). The fault-free run comes first: p = a × b and `alarm` = 0 on every pair.
- Pairs: the corners and 1,024 random pairs (seed 2026), filled up to a whole word with (0, 0).
  - Corners: C = {0, 1, 2^N − 1, 2^i for every i}. At N ≤ 32, every pair of C × C. At N = 64, every x in C against each of 0, 1 and 2^N − 1 in both orders, and every (2^i, 2^i), which makes 450 corners.
- Results (`results/fsim/`):

| N | m | Faults | Evaluated pairs | Wrong (fault, pair) cases | Alarmed | Escapes |
| --- | --- | --- | --- | --- | --- | --- |
| 8 | 3 | 423: every table, stuck at 0, stuck at 1, inverted | 1,152 | 322,560 | 322,560 | 0 |
| 16 | 3 | 1,443: the same | 1,408 | 1,351,680 | 1,351,680 | 0 |
| 16 | 15 | 1,443: the same | 1,408 | 1,351,680 | 1,351,680 | 0 |
| 16 | 15 | 1,715: every cell, every set of outputs inverted, outputs held at every value | 1,408 | 2,117,632 | 2,117,632 | 0 |
| 32 | 3 | 5,334: every table, three faults | 2,240 | 7,960,960 | 7,960,960 | 0 |
| 32 | 15 | 5,334: the same | 2,240 | 7,960,960 | 7,960,960 | 0 |
| 32 | 15 | 6,759: every cell, as at N = 16 | 2,240 | 13,404,160 | 13,404,160 | 0 |
| 64 | 3 | 19,281: every table, three faults | 1,536 | 19,740,672 | 19,740,672 | 0 |
| 64 | 15 | 19,281: the same | 1,536 | 19,740,672 | 19,740,672 | 0 |
| 64 | 15 | 25,700: every cell, as at N = 16 | 1,536 | 35,257,344 | 35,257,344 | 0 |

- Alarms with a right product, at N = 16, m = 3, three faults per table: 2,816 cases. All of them come from the wire above the top itself, stuck at 1 or inverted, on all 1,408 pairs each.

**Negative controls, each shown by a named escape.**
- **The detector without the wire above the top** (`netlists/controls/sc8_m3_notop`).
  - The checker refuses it: "alarm does not read ['w125']".
  - SAT: 17 of 141 free-table queries are SATISFIABLE. The first is w27 = 1 at a = b = 254.
  - Fault simulation: 282 escapes. The first is w27 stuck at 1 at a = b = 255.
- **Claim B with m = 3.**
  - The checker refuses it at every N. At N = 64, 2,743 of 2,744 cells admit d = ±3.
  - SAT at N = 8: 58 of 60 whole-cell queries are SATISFIABLE. The first is cell 0, with three partial products all 1 and both outputs 0 (d = −3), at a = 95, b = 127.
  - Fault simulation: 431,266 escapes at N = 16, 3,325,768 at N = 32 and 7,968,692 at N = 64.
- **A cell made correct only on the rows that occur** (`netlists/controls/mul8_c3`, built by `proof/control3.py`; `results/control3.json`).
  - Cell 53 (column 9) gives 2 instead of 3 on one row, w82 = w83 = w111 = 1, which no input reaches without a fault.
  - Without a fault, all 65,536 pairs are multiplied correctly (`proof/lawsim2.py`). `proof/lawcheck2.py` and the checker refuse it.
  - With w4 inverted, a = 255 and b = 191 give p = 48129 against a × b = 48705. Both remainders are 0 and the wire above the top is 0: an escape.
  - Fault simulation on it: 12 escapes. The first is w65 stuck at 1 at a = 223, b = 135.

## What the applicant can and cannot claim from this folder

Can use, as provider data:
- A proof, at netlist level and for every input, that the multiplier multiplies.
- A proof that one wrong lookup table cannot give a wrong product without `alarm`. For m = 15, the same for one wrong cell.
- The independent checker, which replays in under a second.
- SAT at N = 8, and fault simulation at the sizes listed.
- The detector's size against duplication. At N = 64 it is 136 tables (m = 3) or 395 (m = 15), against 6,384 for a second multiplier and a compare.

Remains the applicant's:
- Diagnostic coverage figures and the FMEDA. This folder gives a fault model and a proof inside it, not a coverage percentage of a device.
- Whether the fault model fits their device: single lookup-table faults, or single cells for m = 15. Faults outside it are listed above: input stems, the detector and the alarm path, two faults, carry-chain elements and routing.
- How the latent faults are handled: a periodic test of the alarm path, or a two-rail alarm.
- Verification after synthesis and place and route. A synthesis tool may merge or remap the tables, and then the proof is about the netlist given here, not the one they build. The Yosys row above shows such a remapping.
- Timing, and the extra levels of the alarm after `p`.
- Tool assessment of their tools, requirements trace and configuration control.
- For the regulatory frame (AC 20-152A / AMC 20-152A COTS IP, ISO 26262), see [`../crc32/evidence.md`](../crc32/evidence.md). No further source was opened for this folder.
