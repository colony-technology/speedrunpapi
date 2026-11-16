# EPFL ties: three published entries that are optimal

The [EPFL combinational benchmark suite](https://github.com/lsils/benchmarks) keeps the best known LUT-6 results in two tables, by size and by depth. For three entries the published netlist cannot be beaten: no LUT-6 network does better under that table's order. This page gives the floor for each, the argument in full, and the checks of the facts it rests on.

| entry | published, LUT-6 / levels | floor |
| --- | --- | --- |
| `ctrl`, size table | 25 / 2 | 25 LUTs; at 25 LUTs, 2 levels |
| `ctrl`, depth table | 25 / 2 | 2 levels; at 2 levels, 25 LUTs |
| `adder`, size table | 129 / 126 | 129 LUTs; at 129 LUTs, 126 levels |

The tables count LUTs with two or more inputs and the levels over those; constant nodes and single-input nodes (buffers and inverters) are free. [`../epfl-dec/lutcount.py`](../epfl-dec/lutcount.py) gives 25 / 2 for `best_results/size/ctrl_size_2023.blif` and for `best_results/depth/ctrl_depth_2023.blif`, and 129 / 126 for `best_results/size/adder_size_2022.blif`.

## ctrl: 25 / 2 on both tables

`ctrl` has 7 inputs and 26 outputs. From its full truth table ([`ctrl_facts.py`](ctrl_facts.py), output in [`ctrl_facts.txt`](ctrl_facts.txt)):

```
ctrl: 7 inputs, 26 outputs, 128 truth-table rows
constant outputs: sign = 1
non-constant outputs: 25; smallest support 3 inputs
outputs on all 7 inputs: alu_op[0], invA, invB
outputs equal to an input or its complement: none
pairs of outputs equal or complementary: none
```

**LUTs.** `sign` is constant, which the table counts as free. Each of the other 25 outputs is neither a constant, nor an input, nor an inverted input, so it is the output of a node with two or more inputs, possibly through free inverters. Two outputs driven by the same such node would be equal or complementary, and no two are. So any network for `ctrl` has at least 25 LUTs.

**Levels.** `alu_op[0]`, `invA` and `invB` each depend on all 7 inputs, and one LUT-6 reads 6. So any network has at least 2 levels.

The published netlists have 25 LUTs at 2 levels, which meets both floors at once. Under the size table's order (LUTs, then levels) and the depth table's (levels, then LUTs), nothing beats them.

## adder: 129 / 126 on the size table

`adder` adds two 128-bit words, `a` and `b`: 256 inputs, the sum bits `f[0]` to `f[127]` (written `s_i` below) and the carry out `cOut`.

```
yosys-abc -c "read arithmetic/adder.aig; strash; print_supp"
    f[0] : Supp = 2.  f[1] : Supp = 4.  f[2] : Supp = 6.  ...  f[127] : Supp = 256.  cOut : Supp = 256.
yosys-abc -c "read arithmetic/adder.aig; strash; print_supp -s"
Total func supps   =    16768.
Total struct supps =    16768.
```

`s_i` depends on exactly `a_0` to `a_i` and `b_0` to `b_i`, 2(i + 1) inputs, and the functional supports equal the structural ones (2 + 4 + ... + 256 + 256 = 16,768).

**LUTs.** The 128 sum bits have different supports, so no two are equal or complementary. `s_127` and the carry out both read all 256 inputs but differ: with only `a_127` set, `s_127` is 1 and the carry out 0, and with no input set both are 0. None of the 129 outputs is a constant, an input or an inverted input. By the count used for `ctrl`, any network has at least 129 LUTs.

**Levels at 129 LUTs.** With exactly 129 LUTs, every LUT drives an output, so a LUT reads only inputs and other outputs. Take `s_i` with i >= 3, and suppose its LUT reads no output from `s_(i-1)` up. It must read `a_i` and `b_i`, since no output below `s_(i-1)` depends on them. It must also read `a_(i-1)` and `b_(i-1)`, for the same reason. Its last two wires must then give the carry into column i - 1, `c_(i-1) = maj(a_(i-2), b_(i-2), c_(i-2))`, from inputs and outputs `s_0` to `s_(i-2)`. Two wires cannot:
- `a_(i-2)` and `b_(i-2)` miss `c_(i-2)`, which is not constant for i >= 3, and which decides the carry when `a_(i-2) ≠ b_(i-2)`.
- `s_(i-2)` with a wire that does not read `a_(i-2)` or `b_(i-2)`: the cases (0, 0, c) and (1, 1, c) of `(a_(i-2), b_(i-2), c_(i-2))` agree on both wires, and their carries are 0 and 1.
- `s_(i-2)` with `a_(i-2)`: (0, 0, 0) and (0, 1, 1) agree on both, with carries 0 and 1. With `b_(i-2)` the same holds, by symmetry: (0, 0, 0) and (1, 0, 1).
- Any pair without `s_(i-2)`, `a_(i-2)` or `b_(i-2)` does not depend on column i - 2 at all.

So `s_i` reads `s_(i-1)` or a higher output, and by the same argument so does the carry out, reading `s_126` or `s_127`. Going through the LUTs in topological order, each `s_i` is at least one level above `s_(i-1)`, or above a higher output, which is itself at level i or more. With `s_2` at level 1 or more, `s_i` is at level i - 1 or more. So `s_127`, and with it the carry out, is at level 126 or more.

The published netlist has 129 LUTs at 126 levels, so nothing beats it on the size table.

[`adder_step.py`](adder_step.py) checks the step exhaustively on an 8-bit adder (65,536 rows). No LUT reading `a_i`, `b_i` and any four other wires from the inputs and `s_0` to `s_(i-2)` gives `s_i`, while with `s_(i-1)` among the wires one does. Output in [`adder_step.txt`](adder_step.txt):

```
s_3       16 wires to choose from,  1820 sets of four: 0 give it; with s_2: computable
s_4       17 wires to choose from,  2380 sets of four: 0 give it; with s_3: computable
s_5       18 wires to choose from,  3060 sets of four: 0 give it; with s_4: computable
s_6       19 wires to choose from,  3876 sets of four: 0 give it; with s_5: computable
s_7       20 wires to choose from,  4845 sets of four: 0 give it; with s_6: computable
carry out 20 wires to choose from,  4845 sets of four: 0 give it; with s_6: computable
```

The argument above is the proof for 128 bits; the 8-bit run checks its step.

## Commands

```
python3 ctrl_facts.py random_control/ctrl.blif
python3 adder_step.py 8
yosys-abc -c "read arithmetic/adder.aig; strash; print_supp; print_supp -s"
python3 ../epfl-dec/lutcount.py best_results/size/ctrl_size_2023.blif
python3 ../epfl-dec/lutcount.py best_results/depth/ctrl_depth_2023.blif
python3 ../epfl-dec/lutcount.py best_results/size/adder_size_2022.blif
```

`ctrl_facts.py` needs Python 3 and reads [`blifkit.py`](blifkit.py); `adder_step.py` needs NumPy. The suite's files are from lsils/benchmarks commit `3e9df8b`.
