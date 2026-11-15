# Unit dials

Pairwise coprime moduli m_1 … m_k, M = m_1 ⋯ m_k. The set is a **unit set** when every Chinese-remainder reading-back constant is ±M/m_i, that is M/m_i ≡ ±1 (mod m_i) for every i. A unit set reads back to binary with no constant multiplication.

The criterion is Mordell's. L. J. Mordell, "Systems of congruences", Canad. Math. Bull. 16 (1973) 457–462, solves x_r | x_1 ⋯ x_n / x_r ± 1 in integers of either sign. With the signs allowed, his solutions are exactly the unit sets: the one congruence below, its unit-fraction form, the automatic coprimality, the three-dial equation with all its solutions, and the factoring by which he solves four and five dials are on his pages 457 to 462. No residue-arithmetic paper found cites him.

## The law, oldest form: a signed sum of unit fractions

  Σ ε_i / m_i ≡ 1/M (mod 1), ε_i = ±1. With every modulus at least 6 and up to five moduli, this is an equality: Σ ε_i / m_i = 1/M.

| set | source | signed sum, exact | reading-back constants |
| --- | --- | --- | --- |
| (n, n + 1) | Nunes 1542, Vernier 1631 (30 against 31) | 1/n − 1/(n+1) = 1/(n(n+1)), n = 2..60; 1/30 − 1/31 = 1/930 | |
| (3, 5, 7) | Sunzi, 卷下 26; Liber Abaci ch. 12 | −1/3 + 1/5 + 1/7 = 1/105 | 70, 21, 15 ≡ −35, +21, +15 (mod 105) |
| (5, 8, 13) | three Fibonacci numbers; Babb 1989 | −1/5 + 1/8 + 1/13 = 1/520 | −104, 65, 40 |
| (7, 9, 32) | (2^k − 1, 2^k + 1, 2^(2k−1)), k = 3 | +1/7 − 1/9 − 1/32 = 1/2016 | 288, −224, −63 |
| (15, 17, 128) | the same, k = 4 | +1/15 − 1/17 − 1/128 = 1/32640 | 2176, −1920, −255 |
| (3, 7, 10, 11) | four dials, cheap moduli | −1/3 + 1/7 + 1/10 + 1/11 = 1/2310 | −770, 330, 231, 210 |
| (8, 9, 11, 13) | four dials, cheap moduli, ratio 1.625 | −1/8 + 1/9 + 1/11 − 1/13 = 1/10296 | −1287, 1144, 936, −792 |
| (7, 8, 9) | textbook | not a unit set | 288, −63, 280 (mod 504) |
| (15, 16, 17) | textbook | not a unit set | 2176, −255, 2160 (mod 4080) |

`record/oldest.txt`

## Statements

| | statement | checked | result | Lean |
| --- | --- | --- | --- | --- |
| 1 | any k: unit with signs ε ⇔ Σ ε_i M/m_i ≡ 1 (mod M) | every pairwise coprime triple ≤ 300 (1,264,341) with 8 sign vectors each; every quadruple ≤ 60 (50,257) | 0 disagreements | `unit_iff_sum`, proved |
| 2 | two dials: unit ⇔ m_2 = m_1 + 1 | every coprime pair ≤ 1000 (303,192) | 0 failures | `two_dials`, proved, no coprimality assumed |
| 3 | three dials: unit ⇔ z(x + y) = xy ± 1 for some labelling | every triple ≤ 300 | 620 unit triples, 0 failures, no exceptions | |
| 3 | the equation forces pairwise coprimality | every triple ≤ 300 satisfying it | 0 not coprime | |
| 3 | all unit triples: s ≥ 2 and x² ≡ ±1 (mod s) give (x, s − x, (x(s − x) ± 1)/s) | every triple ≤ 300 | 620 generated, equal to the 620 unit triples | |
| 4 | four dials, signs (+, +, −, −) on (w, x, y, z): yz(w + x) − wx(y + z) = ±1 ⇔ (Ay − p)(Az − p) = p² ± A, A = w + x, p = wx | every quadruple ≤ 60; the 512 such sets of the search below | 0 failures; 512 of 512 | the identity, `four_factor`, proved |
| 5 | five dials: fix v, w, x; Q = vwx, P/Q = ε_v/v + ε_w/w + ε_x/x: (Py + Qε_y)(Pz + Qε_z) = σP + Q²ε_yε_z | the identity (Py + Qε_y)(Pz + Qε_z) − (σP + Q²ε_yε_z) = P(Pyz + Qε_y z + Qε_z y − σ) | | `five_factor`, proved |

(2, 3, 5) is not an exception to 3: 2·(3 + 5) = 3·5 + 1. Its all-plus sign vector, 1/2 + 1/3 + 1/5 = 1 + 1/30, exists only because +1 ≡ −1 (mod 2). It is the only unit triple ≤ 300 with one.

## Three lines of unit triples

| line | checked | result |
| --- | --- | --- |
| (F_n, F_n+1, F_n+2), F_1 = F_2 = 1: F_n F_n+3 − F_n+1 F_n+2 = (−1)^(n+1) | n = 3..55 | unit 53 of 53 |
| δ = 2t + 1: (t² + t − 1, 2t² + t − 2, 2t² + 3t − 1) and (t² + t + 1, 2t² + t + 2, 2t² + 3t + 3) | odd δ = 3..199 | the identities proved in Lean (`delta_line1`, `delta_line2`); 197 triples with every modulus ≥ 2, unit 197: (3, 5, 8), (5, 8, 13), (7, 12, 17), (11, 19, 26), (13, 23, 30), (19, 34, 43), (21, 38, 47), (29, 53, 64), (31, 57, 68), … |
| (2^k − 1, 2^k + 1, 2^(2k−1)), constants (+1, −1, −1) | k = 2..128 | unit 127 of 127 |
| the textbook (2^n − 1, 2^n, 2^n + 1) | n = 2..128 | not unit, 127 of 127; inverses 2^(n−1), −1, −2^(n−1) |

`record/claims.txt`

## Searches: balanced sets

| search | bound | candidates | unit sets | sign multisets |
| --- | --- | --- | --- | --- |
| four dials, largest / smallest ≤ 4 | every modulus < 2,000 | 3,140 | **549** | (−, +, +, +) 24; (−, −, +, +) 512; (−, −, −, +) 13 |
| five dials, largest / smallest ≤ 4 | every modulus < 600 | 397 | **52** | (−, −, −, +, +) 13; (−, −, +, +, +) 39 |

| most balanced | signs | ratio | range, bits |
| --- | --- | --- | --- |
| (1828, 1857, 1859, 1889) | −, +, +, − | 1.0334 | 43.4 |
| (1709, 1737, 1739, 1768) | −, +, +, − | 1.0345 | 43.1 |
| (1594, 1621, 1623, 1651) | −, +, +, − | 1.0358 | 42.7 |
| (59, 69, 82, 101, 107) | −, −, +, +, + | 1.8136 | 31.7 |
| (121, 133, 172, 181, 225) | −, −, +, +, + | 1.8595 | 36.7 |
| (67, 95, 109, 119, 127) | −, −, +, +, + | 1.8955 | 33.3 |

Cheap moduli are 2..16 and 2^k, 2^k ± 1 for k ≤ 40 (124 moduli); every pairwise coprime set of them with ratio ≤ 4:

| size | candidate sets | unit sets |
| --- | --- | --- |
| 3 | 869 | 50: (2, 3, 7), (3, 4, 11), (3, 5, 7), (3, 5, 8), (5, 7, 17), (5, 8, 13), (5, 9, 11), (6, 11, 13), (7, 12, 17), (7, 13, 15), (11, 17, 31), and (2^k, 2^(k+1) − 1, 2^(k+1) + 1) for k = 1..39 |
| 4 | 578 | **2: (3, 7, 10, 11) and (8, 9, 11, 13)** |
| 5 | 169 | 0 |

The line (2^k − 1, 2^k + 1, 2^(2k−1)) is never balanced: (7, 9, 32) already has ratio 4.57.

The searches fix the smallest three (four) moduli and the signs, and solve the equality for the last one. Every candidate is then checked against the definition. Sets containing a modulus below 6 are searched by brute force. Both programs equal brute force below 91 (four dials, 59 sets) and below 61 (five dials, 12 sets).

`record/four.txt`, `five.txt`, `analyse4.txt`, `analyse5.txt`, `cheap.txt`, `search.txt`

## Cost in 6-input lookup tables

Channels: (a + b) mod m and (a · b) mod m, each written as a full table over every residue pair. Reading back: Σ c_i r_i, then one parallel compare against the multiples of M in range. Yardsticks: a b-bit adder and a b × b multiplier (low b bits), b = ⌈log2 M⌉. Each is mapped by Yosys 0.70+385, `synth -flatten; abc -lut 6; opt_clean`, with levels from `ltp -noff`.

| set | unit | range, bits | multiples of M compared | reading back LUT / levels | channel add LUT / levels | channel mul LUT / levels | binary add LUT / levels | binary mul LUT / levels |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| (5, 8, 13) | yes | 9.022 | 3 | **45 / 5** | 27 / 3 | 30 / 3 | 14 / 4 | 74 / 5 |
| (7, 8, 9) | no | 8.977 | 9 | **94 / 8** | 18 / 3 | 26 / 2 | 12 / 4 | 55 / 5 |
| (7, 9, 32) | yes | 10.977 | 3 | **53 / 5** | 22 / 3 | 47 / 4 | 17 / 4 | 87 / 5 |
| (15, 16, 17) | no | 11.994 | 17 | **203 / 12** | 91 / 4 | 103 / 4 | 17 / 5 | 115 / 6 |
| (15, 17, 128) | yes | 14.994 | 3 | **89 / 7** | 105 / 4 | 335 / 5 | 26 / 6 | 190 / 7 |

| channel m | add LUT / levels | mul LUT / levels |
| --- | --- | --- |
| 5, 7, 8 | 3 / 1 | 3 / 1 |
| 9 | 12 / 3 | 20 / 2 |
| 13 | 21 / 3 | 24 / 3 |
| 15 | 24 / 3 | 27 / 3 |
| 16 | 5 / 2 | 6 / 2 |
| 17 | 62 / 4 | 70 / 4 |
| 32 | 7 / 3 | 24 / 4 |
| 128 | 19 / 4 | 238 / 5 |

| per bit of range (LUT-6 / log2 M) | channel add | binary add | channel mul | binary mul | reading back |
| --- | --- | --- | --- | --- | --- |
| (5, 8, 13) | 2.99 | 1.55 | 3.33 | 8.20 | 4.99 |
| (7, 8, 9) | 2.01 | 1.34 | 2.90 | 6.13 | 10.47 |
| (7, 9, 32) | 2.00 | 1.55 | 4.28 | 7.93 | 4.83 |
| (15, 16, 17) | 7.59 | 1.42 | 8.59 | 9.59 | 16.93 |
| (15, 17, 128) | 7.00 | 1.73 | 22.34 | 12.67 | 5.94 |

ABC's result follows the order of the cells, which Yosys names after the source path. The same modules, read by an absolute path with the same Yosys, gave these reading-back counts in LUT / levels: (5, 8, 13) 44 / 5; (7, 9, 32) 51 / 6; (15, 17, 128) 89 / 7; (7, 8, 9) 89 / 8; (15, 16, 17) 239 / 10. Every other column was unchanged. The unit sets stay at about half the textbook sets, or less.

`record/cost.txt`, `record/cost_table.md`; mapped netlists in `netlists/`

## Netlist checks

Each mapped netlist is simulated with Icarus Verilog 14.0 on every valid input, with Yosys's `simlib.v` for the `$lut` cells. It is compared against a definition written in the bench, independent of the generated Verilog:
- channels: (a + b) mod m and (a · b) mod m;
- reading back: x → (x mod m_i) → x, with no constants;
- binary units: (a ∘ b) mod 2^b.

| set | channels (add, mul per channel) | reading back | binary add | binary mul |
| --- | --- | --- | --- | --- |
| (5, 8, 13) | 0 mismatches; 25, 25, 64, 64, 169, 169 vectors | 0 of 520 | 0 of 1,048,576 | 0 of 1,048,576 |
| (7, 9, 32) | 0; 49, 49, 81, 81, 1,024, 1,024 | 0 of 2,016 | 0 of 4,194,304 | 0 of 4,194,304 |
| (15, 17, 128) | 0; 225, 225, 289, 289, 16,384, 16,384 | 0 of 32,640 | ABC `cec` against a + b: equivalent | ABC `cec` against a · b: equivalent |
| (7, 8, 9) | 0; 49, 49, 64, 64, 81, 81 | 0 of 504 | 0 of 262,144 | 0 of 262,144 |
| (15, 16, 17) | 0; 225, 225, 256, 256, 289, 289 | 0 of 4,080 | 0 of 16,777,216 | 0 of 16,777,216 |
| control: the (5, 8, 13) reading back with 65 changed to 66 | | **455 of 520 mismatch** | | |
| control: (a · b) ⊕ 1 against the 15 × 15 netlist | | | | **not equivalent** |

`record/proof.txt`

## Lean

| theorem | statement | axioms |
| --- | --- | --- |
| `unit_iff_sum` | 1. Moduli m_i ≥ 2, pairwise coprime, ε_i² = 1: (M/m_i ≡ ε_i (mod m_i) for every i) ⇔ Σ ε_i M/m_i ≡ 1 (mod M) | propext, Classical.choice, Quot.sound |
| `two_dials` | 2. 2 ≤ a < b: (b ≡ ±1 (mod a) and a ≡ ±1 (mod b)) ⇔ b = a + 1 | propext, Classical.choice, Quot.sound |
| `delta_line1` | the first δ line: a(b + c) − bc = 1 | propext, Quot.sound |
| `delta_line2` | the second δ line: a(b + c) − bc = −1 | propext |
| `four_factor` | 4. (Ay − p)(Az − p) − (p² + sA) = A(yz(w + x) − wx(y + z) − s) | propext, Quot.sound |
| `five_factor` | 5. (Py + Qε_y)(Pz + Qε_z) − (σP + Q²ε_yε_z) = P(Pyz + Qε_y z + Qε_z y − σ) | propext, Quot.sound |

Rebuilt on a clean runner: GitHub Actions run 43701616486, 15 November 2026, 09:56Z to 10:20Z, success. Lean 4.35.0, Mathlib v4.35.0, `lake build` 9,101 jobs for the project that holds this file, 179 theorems in its axiom report, no `sorryAx`. The axioms above are as `lean/P7DialsCheck.lean` prints them. No `sorry`, `admit` or `native_decide` appears.

`two_dials` needs no coprimality. Also, a ≡ ±1 (mod b) alone forces b = a + 1: a ≡ 1 (mod b) is impossible because 0 < a − 1 < b, and a ≡ −1 (mod b) with 0 < a + 1 ≤ b gives b = a + 1.

`lean/RoundingLean/P7Dials.lean` holds the statements and proofs as built; only its module comment is reworded. `lean/` also carries the toolchain, lakefile and manifest of that build. Its root file imports this module alone. The folder's own Lean project was not built separately.

## Sources

| statement | in print, in the sources opened |
| --- | --- |
| a fraction as a sum of unit fractions | Rhind papyrus (MacTutor) |
| dials n and n + 1 | Vernier 1631, Nunes 1542 |
| 3, 5, 7 with 70, 21, 15 | Sunzi; Liber Abaci ch. 12 |
| 70, 21, 15 ≡ −35, +21, +15 (mod 105) | not found; searched in the Sunzi and Liber Abaci passages and course notes; Libbrecht, Needham and Martzloff not opened |
| every constant of three consecutive Fibonacci moduli is ±1 | Babb 1989, p. 5; Murakami 2003, Theorem 2.1; as arccot F_2n = arccot F_2n+1 + arccot F_2n+2, Lehmer 1936 |
| one congruence for any k, its unit-fraction form, coprimality automatic | Mordell 1973, p. 457, eqs. (1) to (4) |
| unit triples are exactly z(x + y) = xy ± 1, and every one of them | Mordell 1973, p. 457; the + case is the arccot relation of Wallace 1839 and Dodgson 1884 |
| the four- and five-dial factor forms | the method is Mordell's, pp. 459 to 462, used there for y = ±1; the y = 0 forms on this page not found stated |
| four dials with the equality, Σ ε_i / m_i = ±1/M | Mordell's research problem, Canad. Math. Bull. 17 (1974): 1/x + 1/y + 1/z + 1/w + 1/(xyzw) = 0; infinitely many solutions, Zhang 1985 (Acta Math. Sinica 1, 221–224); solutions of each sign pattern, including (+, +, −, −), Cao 1987 (J. Math. Wuhan 7, 239–244; review read); families, Choudhry 2009. The sets in the searches below are solutions of it |
| (2^(n−1), 2^n − 1, 2^n + 1), constants (−1, +1, +1) | Hiasat and Sweidan 2003, J. Systems Architecture 49, 53–58; abstract and snippets read, full text not |
| (2^k − 1, 2^k + 1, 2^(2k−1)), constants (+1, −1, −1) | the member k = n − 1 of the family {2^n + 1, 2^(n+k), 2^n − 1} of Chaves and Sousa 2004 (metadata), whose inverses Mohan 2016 eq. (5.10) gives (snippet); that they are ±1 at this member not found stated |

Quotations, pages and links: `sources.md`.

## Replay

```sh
bash replay.sh      # python3, cc, Yosys with yosys-abc, Icarus Verilog; exit 0 when every check holds
```

| step | what | expected |
| --- | --- | --- |
| 1 | `src/check_claims.py 1000 300 60`, `src/oldest.py`, `src/search4.c 2000 4`, `src/search5.c 600 4`, `src/analyse.py`, `src/cheap4.py 40 4` | equal to `record/`, line for line |
| 2 | `src/prove_sim.sh` on every netlist in `netlists/`; ABC `cec` for the 15-bit adder and multiplier | 0 mismatches; equivalent; both controls fail |
| 3 | `src/gen_cost.py`, `src/map.sh`, `src/cost_table.py` with the local Yosys | equal to `record/cost_table.md` with Yosys 0.70+385, mapped from the recorded relative paths (ABC's result follows the source path); counts can differ with another Yosys |
| Lean, apart from `replay.sh` | `cd lean; lake exe cache get; lake build; lake env lean P7DialsCheck.lean` | builds; the axioms in the Lean table |

Recorded run: 15 November 2026, Apple M1, macOS 27.2, `replay.sh` from a fresh clone of this branch: 17 ok, 0 failed, 677 s. `shasum -a 256 -c MANIFEST.sha256` confirms every file of this folder.
