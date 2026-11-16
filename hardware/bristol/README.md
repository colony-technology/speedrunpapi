# Bristol Fashion arithmetic circuits

Garbled circuits, multi-party computation and zero-knowledge proofs over Boolean circuits pay for every AND gate. XOR and NOT are free.
The circuits most of those systems load are the [Bristol Fashion](https://nigelsmart.github.io/MPC-Circuits/) set, which has 64-bit integer arithmetic and IEEE double-precision floating point.

This folder holds sixteen of those functions with fewer AND gates.
Each file has the inputs, the outputs and the format of the published one, and returns the same value.

| Function | File | Published, AND gates | Here, AND gates | Published, AND depth | Here, AND depth |
| --- | --- | --- | --- | --- | --- |
| double add | [`FP-add.txt`](FP-add.txt) | 5,385 | 1,447 | 235 | 240 |
| double multiply | [`FP-mul.txt`](FP-mul.txt) | 19,626 | 5,218 | 129 | 227 |
| double divide | [`FP-div.txt`](FP-div.txt) | 82,269 | 4,559 | 3,619 | 3,020 |
| double square root | [`FP-sqrt.txt`](FP-sqrt.txt) | 91,504 | 2,013 | 6,507 | 1,433 |
| double equal | [`FP-eq.txt`](FP-eq.txt) | 315 | 138 | 9 | 10 |
| double less than | [`FP-lt.txt`](FP-lt.txt) | 381 | 214 | 67 | 65 |
| double to integer | [`FP-f2i.txt`](FP-f2i.txt) | 1,467 | 656 | 94 | 92 |
| integer to double | [`FP-i2f.txt`](FP-i2f.txt) | 2,416 | 593 | 206 | 153 |
| double floor | [`FP-floor.txt`](FP-floor.txt) | 651 | 433 | 71 | 90 |
| double ceil | [`FP-ceil.txt`](FP-ceil.txt) | 650 | 433 | 71 | 90 |
| 64 x 64 multiply, low half | [`mult64.txt`](mult64.txt) | 4,033 | 3,623 | 63 | 63 |
| 64 x 64 multiply, 128 bits | [`mult2_64.txt`](mult2_64.txt) | 8,128 | 5,272 | 127 | 127 |
| 64-bit unsigned divide | [`udivide64.txt`](udivide64.txt) | 4,285 | 3,197 | 2,204 | 2,700 |
| 64-bit signed divide | [`divide64.txt`](divide64.txt) | 4,664 | 3,388 | 4,158 | 2,826 |
| 512-bit addition modulo p | [`ModAdd512.txt`](ModAdd512.txt) | 3,583 | 1,537 | 1,027 | 514 |
| shares to a 64-bit integer | [`LSSS_to_GC.txt`](LSSS_to_GC.txt) | 2,817 | 1,730 | 1,028 | 579 |

The ten float circuits take 15,704 AND gates together. The published ten take 204,664.
The counts are taken from the files by `check.py`: the AND gates, and the longest chain of AND gates between an input and an output.
The first fourteen are on the Bristol Fashion page. The last two are in SCALE-MAMBA (`Circuits/Bristol`) and in the circuit set of MP-SPDZ.

## What the functions compute

The published float circuits were compiled from Berkeley SoftFloat 2 and keep its conventions.
A double is 64 wires, bit 0 first: 52 fraction bits, 11 exponent bits and the sign.

```
rounding            to nearest, ties to even
subnormals          as operands and as results
invalid result      7fffffffffffffff      inf - inf, 0 * inf, 0 / 0, inf / inf, the square root of a negative number
NaN operand         comes back with its quiet bit set
two NaN operands    the second one, unless only the first is signalling
FP-div              first operand / second operand
FP-eq, FP-lt        the answer is bit 0 of the output word; a NaN operand gives 0; +0 equals -0
FP-f2i              to a signed 64-bit integer, to nearest even
                    a NaN and anything too large give 7fffffffffffffff, anything too negative 8000000000000000
FP-i2f              from a signed 64-bit integer, to nearest even
FP-floor, FP-ceil   the result is a double; floor(-0.5) is -1, ceil(-0.5) is -0
```

```
mult2_64            the first output word is the high half of the product
udivide64           a zero divisor gives all ones
divide64            truncates toward zero; -2^63 / -1 is -2^63
                    a zero divisor gives -1 for a dividend that is not negative, 1 for a negative one, 2 for -2^63
ModAdd512           inputs a, b, p: a + b, less p once when the sum is at least p
LSSS_to_GC          inputs a, b, p; s = a + b, h = p >> 1: s less p once when s >= h and once more when s >= p + h;
                    the low 64 bits. For a, b below p that is the sum modulo p as a signed number around zero.
```

[`rules.py`](rules.py) has the sixteen functions as Python.

## The circuits

Each circuit is the datapath of its function, built for this cost. With XOR free, a full adder is one AND gate, and so is a selection between two wires.

- Square root and divide are digit recurrences that never restore. A row is one addition or one subtraction, so it costs one AND gate per bit. The rows of the square root grow with the root.
- The square root has no sticky bit. The square root of a double is never halfway between two doubles, so the bit after the last place decides the rounding.
- The divider's sticky bit is one comparison: the division is exact when the last remainder is the negative of the divisor.
- Multiply is a Karatsuba recursion two levels deep over the 53-bit significands: 3,925 AND gates where the array of partial products takes 5,565. `mult2_64` is the same recursion at 64 bits.
- A subnormal operand goes through a normalising shifter. Divide has two of them. Multiply has one, which takes whichever operand has an exponent field of zero. With two such operands the product is below the smallest double.
- A zero, an infinity or a NaN result is the fraction of one of the operands, inverted or not, under an exponent of all ones or all zeros. All special cases share one selection per output bit.
- Add puts the larger operand first with one comparison and a swap that costs one AND gate per bit. It aligns the smaller operand, adds, and shifts the sum left by its leading zeros or by what the exponent allows, whichever is less. A sum that stops at the smallest exponent is exact, so there is no second right shift.
- The integer dividers compare only the low bits of the divisor in the first 31 rows, where the partial remainder is short, and then switch to full rows that do not restore.
- `LSSS_to_GC` needs two comparisons, s against h and s - h against p. Only the low 64 bits of the answer are subtracted.

## Check

[`check.py`](check.py) loads a published circuit and the one here, runs both on the same operands, and counts the operands where they differ and where the circuit here differs from `rules.py`. It needs Python only.

```
python3 check.py <folder with the published files> [operands per function]
```

```
FP-sqrt    published  91504 AND, depth 6507   here  2013 AND, depth 1433   100000 operands: 0 differ from the published circuit, 0 from the rule
```

The operands are fifty special values in every combination, random patterns, and operands aimed at rounding ties, alignment, cancellation, overflow, underflow and subnormal results.
At 3,000,000 operands per function, and 300,000 for the two 512-bit circuits, nothing differs.

Nine of the circuits are also proved equal to the published ones on every input, with ABC:

```
python3 check.py bench <folder with the published files> out
abc -c "cec out/FP-add.published.bench out/FP-add.here.bench"
```

`FP-add`, `FP-eq`, `FP-lt`, `FP-f2i`, `FP-i2f`, `FP-floor`, `FP-ceil`, `ModAdd512` and `LSSS_to_GC` come back equivalent, the adder in about two minutes and the others in under 40 seconds.

Add, multiply, divide and square root also run against the arithmetic of the processor, which is IEEE 754 itself:

```
python3 bf2c.py build && cc -O1 -ffp-contract=off -I build -o build/native native.c -lm
build/native sqrt 1000000000 1
```

```
sqrt: 1000000000 operands, 0 differ from the processor's arithmetic
```

`bf2c.py` turns the four circuits into C that carries 64 operands per machine word. A billion aimed operands take a few minutes per circuit on one core of an Apple M1, and none of the four differs on any of them.

The same constructions were also built at smaller sizes and compared with exact arithmetic on every input: add, multiply and divide on all 16,777,216 operand pairs of a 12-bit format, the square root on all 65,536 inputs of half precision.

The checks run on each change to this folder, against the published files at pinned commits of [NigelSmart/nigelsmart.github.io](https://github.com/NigelSmart/nigelsmart.github.io) and [KULeuven-COSIC/SCALE-MAMBA](https://github.com/KULeuven-COSIC/SCALE-MAMBA) ([workflow](../../.github/workflows/bristol.yml), checksums in [`published.sha256`](published.sha256)).

## AND depth

In secret sharing each level of AND gates is a round of communication, so the AND depth matters as well as the count.
Five of the circuits above have more AND depth than the published ones.
Each of the five now comes in two more files: `.fewand.txt`, the fewest AND gates found under the published depth, and `.lowdepth.txt`, the lowest depth found.
Both files are under the published count and the published depth.

| Function | Published, AND gates / depth | Here, AND gates / depth | Fewest AND under the published depth | Lowest depth |
| --- | --- | --- | --- | --- |
| double multiply | 19,626 / 129 | 5,218 / 227 | [`FP-mul.fewand.txt`](FP-mul.fewand.txt) 5,847 / 121 | [`FP-mul.lowdepth.txt`](FP-mul.lowdepth.txt) 7,856 / 52 |
| double add | 5,385 / 235 | 1,447 / 240 | [`FP-add.fewand.txt`](FP-add.fewand.txt) 1,455 / 232 | [`FP-add.lowdepth.txt`](FP-add.lowdepth.txt) 2,320 / 52 |
| double floor | 651 / 71 | 433 / 90 | [`FP-floor.fewand.txt`](FP-floor.fewand.txt) 457 / 69 | [`FP-floor.lowdepth.txt`](FP-floor.lowdepth.txt) 590 / 26 |
| double ceil | 650 / 71 | 433 / 90 | [`FP-ceil.fewand.txt`](FP-ceil.fewand.txt) 457 / 69 | [`FP-ceil.lowdepth.txt`](FP-ceil.lowdepth.txt) 590 / 26 |
| 64-bit unsigned divide | 4,285 / 2,204 | 3,197 / 2,700 | [`udivide64.fewand.txt`](udivide64.fewand.txt) 3,682 / 2,199 | [`udivide64.lowdepth.txt`](udivide64.lowdepth.txt) 4,222 / 2,144 |

The published figures are from the [Bristol Fashion](https://nigelsmart.github.io/MPC-Circuits/) page, counted by `check.py` from the published files.

AND gates against depth for the multiplier, every point a built circuit:

| AND gates | AND depth | AND gates per level, from the row above |
| --- | --- | --- |
| 5,218 | 227 | |
| 5,325 | 168 | 1.8 |
| 5,847 | 121 | 11.1 |
| 6,086 | 80 | 5.8 |
| 6,395 | 64 | 19.3 |
| 7,124 | 57 | 104 |
| 7,856 | 52 | 146 |

As for the first sixteen, the files are the circuits; the program that built them is kept privately.

What is proved for the ten new files:

- `FP-floor`, `FP-ceil` and `FP-add`, both files of each, are equal to the published circuits and to the ones here on every input, with ABC.
- `udivide64.lowdepth.txt` is equal to the published circuit on every input, with ABC. `udivide64.fewand.txt` rests on testing: 3,000,000 operands against the published circuit and the rules, and every operand pair at 6, 7 and 8 bits. ABC did not finish in 20 minutes, against the published circuit or against the one here.
- `FP-mul` rests on testing: 3,000,000 operands against the published circuit and the rules, 10^9 against the processor, and every input of the small formats. It has no complete equivalence proof. ABC did not finish in 10 minutes for either file against the published circuit. It did not finish in 10 minutes for the lowest-depth file against the one here, nor in 20 minutes for the fewest-AND file.
- All ten files: `check.py` at 3,000,000 operands, nothing differs. For add and multiply, 10^9 operands against the processor, nothing differs. Every input of the 3-2, 4-3 and 3-4 formats (and 5-10 for floor and ceil) against exact arithmetic, and the divider on every pair at 6, 7 and 8 bits, nothing differs.

The same checks, on these files:

```
python3 check.py <folder with the published files> 3000000 1 FP-add,FP-mul,FP-floor,FP-ceil,udivide64 --variant lowdepth
python3 check.py <folder with the published files> 3000000 1 FP-add,FP-mul,FP-floor,FP-ceil,udivide64 --variant fewand
python3 check.py bench <folder with the published files> out --variant lowdepth
abc -c "cec out/FP-add.published.bench out/FP-add.here.bench"
python3 bf2c.py build lowdepth && cc -O1 -ffp-contract=off -I build -o build/native native.c -lm
build/native mul 1000000000 1
```

`--variant` makes `check.py` load `NAME.lowdepth.txt` or `NAME.fewand.txt` in place of `NAME.txt`, and `bf2c.py build fewand` does the same for add and multiply.
One line of `python3 check.py <folder with the published files> 100000 --variant lowdepth`:

```
FP-mul     published  19626 AND, depth  129   here  7856 AND, depth   52   100000 operands: 0 differ from the published circuit, 0 from the rule
```

The workflow runs on the sixteen files above; the ten new files are checked by these commands.

## Files

The sixteen `.txt` files are Bristol Fashion in the basic format, with XOR, AND and INV gates only.
The ten `.fewand.txt` and `.lowdepth.txt` files are in the same format.
The first wires are the inputs and the last wires are the outputs, as in the published files.
