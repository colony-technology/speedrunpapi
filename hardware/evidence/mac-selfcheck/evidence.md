# Self-checking multiply-accumulate · verification evidence

Folder `hardware/evidence/mac-selfcheck`, 14 November 2026, colony.technology. Evidence offered to an applicant. It is not a certification, a statement of compliance, or a claim of credit under any standard; those are decisions of the applicant and the authority.

## Item

An unsigned multiply-accumulate p = a × b + c in 6-input lookup tables, with a detector beside it.
- a and b have N bits, c has 2N bits, p has 2N + 1 bits.
- Netlists for N = 4, 5, 6, 8, 16, 32 and 64, each with the detector for m = 3 and for m = 15 (`netlists/scmN_mM/selfcheck.blif`).

The tables form a tree of counting cells, then one ripple of full adders, as in [`../mul-selfcheck/`](../mul-selfcheck/). Each bit c[k] enters column k as one more term. Every cell replaces its terms by wires that count them: sum of 2^k × term = sum of 2^k × output. `netlists/macN/law.json` states each cell.

The detector has five parts:
- the remainders of a, b and c modulo q, computed from the pins only;
- the remainder of p modulo q;
- x = (a mod q)(b mod q) mod q;
- s = (x + c mod q) mod q;
- one table that compares s with p mod q.

For m = 3, q = 3. For m = 15, q = 3 and q = 5. The tree leaves one wire above its top column, column 2N + 1. It is 0 when nothing is broken; it is kept, brought out as `t[0]`, and fed to the alarm. `alarm` = 1 when a mismatch table says so or that wire is 1.

The table counts and sizes are in `README.md` (the detector through Yosys `synth; abc -lut 6`, `results/measure.json`). At N = 64 the detector is 206 tables as built (195 LUTs through Yosys) for m = 3, and 597 (584) for m = 15. The multiply-accumulate is 6,139 tables; a second multiply-accumulate and a comparison would be 6,210.

## Requirements

| Id | Requirement |
| --- | --- |
| SCA-1 | p = a × b + c for every a, b below 2^N and c below 2^(2N). |
| SCA-2 | Without a fault, `alarm` = 0 for every a, b, c. |
| SCA-3 | Claim A, m = 3 and m = 15. For every a, b, c, and every single lookup table of the multiply-accumulate whose output is wrong in any way (inverted, stuck at 0, stuck at 1, any wrong function), if p differs from a × b + c then `alarm` = 1. This includes the output buffers to `p[k]` and the wire above the top, and the propagate LUT of a full adder when the final adder is placed on a carry chain. |
| SCA-4 | Claim B, m = 15, for the cell shapes in `results/shapes.md`. When all outputs of one cell are wrong at once, if p differs from a × b + c then `alarm` = 1. |
| SCA-5 | The residues of a, b and c depend on the pins only. No table of the multiply-accumulate reads a net of the detector. The residue of p reads p only. |

Outside the requirements, and not claimed:
- **A fault on the stem of an input pin, c included, before it fans out.** Both sides then see the same wrong number.
- **A fault that holds `alarm` at 0, or any fault inside the detector.** Such a fault is latent. It needs a periodic test of the alarm path, or a two-rail alarm.
- **Two faults at once.**
- **Cells with four or more outputs.** There are none here; a cell with four outputs can escape m = 15.
- **The carry-chain elements and routing.**

## Verification

**Why the claims hold.**
- `proof/lawcheck_mac.py` proves that every cell keeps its weighted sum on every row of its tables, including rows that cannot occur without a fault, and that every partial product and every addend bit is used once.
- One wrong table in column k leaves the final value at a × b + c + e × 2^k, with e = −1, 0 or +1, because every later cell carries the error on unchanged.
- If the value reaches 2^(2N+1), the wire above the top is 1.
- Otherwise p = a × b + c ± 2^k, and 2^k is not 0 modulo 3 or 15, so the remainders differ.
- For a whole cell the error is d × 2^k, with d between −T and B. The 22 shapes have at most three outputs (B ≤ 7, d in −6..7), so no nonzero multiple of 15 lies in the range.

**1. Proof by an independent checker (SCA-1..5).**
- `proof/check_selfcheck_mac.py` shares no code with the generators. It checks, against the tables of `selfcheck.blif`:
  1. the law, through `proof/lawcheck_mac.py`;
  2. the column of every table;
  3. every residue table on all its rows, and the use of each pin once with its weight;
  4. the product, sum and compare tables and the OR tree, on all their rows;
  5. that the residues of a, b and c depend on the pins only;
  6. one unbroken ripple of full adders;
  7. the carry-chain form.
- Results (`results/check/`):
  - Claim A proved at N = 4, 5, 6, 8, 16, 32 and 64 for m = 3 and m = 15.
  - Claim B proved for m = 15 at every N.
- SCA-2 follows from the same checks. The N = 4 netlist is also right on all 65,536 inputs (`proof/macsim.py`, which reads no law).

**2. SAT (SCA-3, SCA-4).**
- Each query holds the fault-free multiply-accumulate beside the self-checking circuit with the fault, and one output: some `p[k]` differs from the fault-free p, and `alarm` = 0. The engine is ABC `strash; sat`, with a limit of 300 s per query (`tools/sat_faults_mac.py`).
- Claim A replaces each table by a free input, which is any wrong function. Claim B replaces all outputs of each cell by free inputs.
- Results (`results/sat/`):
  - **N = 4 (16 input bits):**
    - claim A, m = 3: 54 of 54 UNSATISFIABLE, slowest 0.75 s;
    - claim A, m = 15: 54 of 54, slowest 1.00 s;
    - claim B: 22 of 22, slowest 7.72 s.
  - **N = 5 (20 input bits):**
    - claim A, m = 3: 78 of 78, slowest 12.83 s;
    - claim A, m = 15: 78 of 78, slowest 17.32 s;
    - claim B: 31 of 32 directly. The 32nd (cell 13) reached the limit, was split on c[9..6] into 16 sub-queries with those pins tied, and gave 16 of 16 UNSATISFIABLE, slowest 15.67 s.
  - **N = 6 (24 input bits):** tried. The first 2 of 100 claim-A queries (m = 3) were UNSATISFIABLE in 143.78 s and 159.54 s; the campaign was stopped, since at that rate one mode takes about 4 to 8 hours.
  - **N = 8 (32 input bits):** tried. The first 18 of 462 queries (three faults per table, m = 3) each reached 300 s with ABC `sat`, and on one of them `iprove`, `dsat` and `dprove` gave no verdict in 300 s each (`results/sat/engines_w1_stuck0.txt`).
  - From N = 6 on, the evidence is the checker and fault simulation.

**3. Fault simulation (SCA-3, SCA-4).**
- `tools/fsim_mac.py`: every fault on every input.
- Inputs: the multiplier's corner pairs, each with c = 0 and c = 2^(2N) − 1, plus 1,024 random triples (`results/fsim/`).

| N | m | Faults | Wrong (fault, input) cases | Alarmed | Escapes |
| --- | --- | --- | --- | --- | --- |
| 4 | 3 | 162: every table, stuck at 0, stuck at 1, inverted | 122,112 | 122,112 | 0 |
| 4 | 15 | 162: every cell, every set of outputs inverted, outputs held at every value | 158,976 | 158,976 | 0 |
| 5 | 3 | 234: every table × 3 | 177,408 | 177,408 | 0 |
| 5 | 15 | 248: every cell | 246,528 | 246,528 | 0 |
| 6 | 3 | 300: every table × 3 | 228,096 | 228,096 | 0 |
| 6 | 15 | 318: every cell | 315,648 | 315,648 | 0 |
| 8 | 3 | 462: every table × 3 | 391,680 | 391,680 | 0 |
| 8 | 15 | 520: every cell | 581,120 | 581,120 | 0 |
| 16 | 3 | 1,503: every table × 3 | 1,728,000 | 1,728,000 | 0 |
| 16 | 15 | 1,818: every cell | 2,768,256 | 2,768,256 | 0 |
| 32 | 3 | 5,559: every table × 3 | 12,563,968 | 12,563,968 | 0 |
| 32 | 15 | 7,131: every cell | 21,478,144 | 21,478,144 | 0 |

The claim-A runs with m = 15 give the same counts as those with m = 3, also with 0 escapes.

**Negative controls, each shown by a named escape.**
- **The detector without the wire above the top** (`netlists/controls/scm4_m3_notop`).
  - The checker refuses it.
  - SAT: 5 of 54 queries are SATISFIABLE.
  - Fault simulation: 84 escapes. The first is w18 stuck at 1 at a = b = 15, c = 255.
- **Claim B with m = 3.**
  - The checker refuses it at every N, since every cell admits d = ±3.
  - SAT at N = 4: 21 of 22 whole-cell queries are SATISFIABLE.
  - Fault simulation: 22,248 escapes at N = 4. The first is cell 0 with both outputs inverted at a = b = c = 0.
- **A cell made correct only on the rows that occur** (`netlists/controls/mac4_c3`, `proof/control3_mac.py`, `results/control3.json`).
  - Cell 10 (column 6) gives 3 instead of 1 on one row, which no input reaches without a fault.
  - Without a fault, all 65,536 inputs are right. `proof/lawcheck_mac.py` and the checker refuse it.
  - With w10 inverted, a = b = c = 0 gives p = 192, both remainders 0 and the wire above the top 0: an escape.
  - Fault simulation on it: 382 escapes.

## What the applicant can and cannot claim from this folder

As in [`../mul-selfcheck/evidence.md`](../mul-selfcheck/evidence.md), with the addend among the inputs.

Can use, as provider data:
- A proof at netlist level, for every input, that the block computes a × b + c.
- A proof that one wrong lookup table, or for m = 15 one wrong cell, cannot give a wrong result without `alarm`.
- The independent checker.
- SAT at N = 4 and 5.
- Fault simulation from N = 4 to 32.

Remains the applicant's:
- Diagnostic coverage figures and the FMEDA.
- Whether the fault model fits their device.
- The latent faults: input stems, the detector and the alarm path, two faults, carry-chain elements and routing.
- Verification after synthesis and place and route.
- Timing.
- Tool assessment, requirements trace and configuration control.
- For the regulatory frame, see [`../crc32/evidence.md`](../crc32/evidence.md).
