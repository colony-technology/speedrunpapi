# EPFL i2c

`i2c` is the I2C controller of the [EPFL combinational benchmark suite](https://github.com/lsils/benchmarks), random/control half: 147 inputs, 142 outputs. The suite keeps the best known LUT-6 results in two tables. On the size table fewer LUTs wins. On the depth table fewer levels wins, then fewer LUTs.

| | LUT-6 | Levels |
| --- | --- | --- |
| Best published, size table (F.-X. Reichl and F. Slivovsky, `i2c_size_2026.blif`) | 173 | 8 |
| [`i2c_size_2027.blif`](i2c_size_2027.blif) | 171 | 9 |
| Best published, depth table (A. Tempia Calvino et al., `i2c_depth_2026.blif`) | 192 | 3 |
| [`i2c_depth_2027.blif`](i2c_depth_2027.blif) | 323 | 2 |

Two levels is the minimum on the depth table: `po028` depends on 24 inputs and one LUT-6 reads 6. What is left open there is the number of LUTs at 2 levels.

The table counts LUTs with two or more inputs and the levels over those, [`../epfl-dec/lutcount.py`](../epfl-dec/lutcount.py): 171 / 9 and 323 / 2 for these netlists, 173 / 8 and 192 / 3 for the published files. ABC's `nd` is higher (186 and 338) because it also counts outputs that are a wire or an inverter of one input and the constant output. ABC's `lev` is 2 for the depth netlist as well: no output sits behind more than two nodes of any kind.

## The depth netlist

Every output is built on its own, from its function and not from the suite's gates.

- 1 output is constant and 14 are one input or its inverse.
- 27 depend on 2 to 6 inputs and are one LUT each.
- 100 depend on 7 to 24 inputs. Each is one LUT-6 over at most six first-level LUT-6s, `f = T(g1, ..., g6)`, every `g` reading at most 6 inputs.

For 97 of those 100 the six `g` were found by a SAT search, [`two_level.py`](two_level.py). The search is told, for every `g` and every input, whether `g` reads that input, and for every input row what `g` gives; a `g` that does not read an input must give the same value on the two rows that differ only there. Before the search, inputs that the output sees only through one AND or one OR are grouped and treated as a single input that costs as many LUT pins as it has members. That shrinks an output of 21 inputs to about 8.

For `po015`, `po040` and `po043` the search did not finish, and the split was written by hand from the output's own formula. Each of the three is a small set of cases chosen by a few control inputs, with a different expression over the other inputs in each case. Two or three of the six `g` say which case holds; the others carry the expressions, and the same `g` is reused across cases that cannot hold together. `po015`, for example, with `a = pi003 + pi129`, `q = pi005 + pi022`, `r = pi009 + pi011`:

```
pi054 = 0:               po015 = a + pi000
pi054 = 1, q or r:       po015 = a + q r + pi056
pi054 = 1, q = r = 0:    po015 = a + OR(pi004, pi006, pi012, pi016, pi017, pi018, pi019)
                                   + OR(pi000, pi008, pi010, pi013, pi014, pi021)
                                     AND (the number of ones among pi007, pi008, pi010, pi013, pi014, pi021 is not 1)
```

That gives 508 LUT-6 at 2 levels: 381 first-level LUTs, 100 second-level LUTs and 27 single LUTs. LUTs are then removed at 2 levels, as described below, down to 323.

## The size netlist

It is the published netlist of F.-X. Reichl and F. Slivovsky with 2 LUTs removed, by the same method. It has 9 levels where the published one has 8; the size table is decided by LUTs.

## Removing LUTs

[`resub2.py`](resub2.py), with [`resub.py`](resub.py), drops a LUT when every LUT that reads it can be rebuilt without it. A LUT is rebuilt over at most six other signals of the netlist. They are searched among all signals outside its own fanout, not in a window around it, by a set cover: for every two input patterns on which the LUT differs, a chosen signal has to differ. On the depth netlist a rebuilt LUT may only read signals that keep every output at 2 levels.

The circuit has 147 inputs, so signals are compared on a sample of input patterns and a rebuilt LUT can be wrong. Every single change is therefore checked on the whole netlist with ABC `cec` against the suite circuit before it is kept. A refused change gives a counterexample, which joins the sample. The netlist is equal to the suite circuit after every kept change.

```
python3 resub2.py i2c START.blif OUT.blif --levels 2     # depth netlist, from the 508 LUT netlist
python3 resub2.py i2c best_results/size/i2c_size_2026.blif OUT.blif
```

It needs numpy, python-sat and ABC (`yosys-abc`, or set `ABC`), and the suite's `random_control/` (or set `EPFL_SUITE`).

## Check

[`prove.py`](prove.py) compares a netlist with the suite's `random_control/i2c.blif` without ABC. For each output it takes every input that either netlist can reach from that output, at most 25 here, and compares the two on all settings of those inputs. That decides each output completely. It needs Python 3 and numpy and takes a minute or two.

```
python3 prove.py random_control/i2c.blif i2c_depth_2027.blif
```

```
nodes by number of inputs: {0: 1, 1: 14, 2: 13, 3: 17, 4: 34, 5: 37, 6: 222}
LUTs with 2 or more inputs: 323
levels, every node counted: 2
levels, nodes with 2 or more inputs counted: 2
142 outputs, each compared on every setting of the inputs it can reach (at most 24 inputs, 132572969 settings in all): 0 outputs differ
PROVED EQUAL
```

```
python3 prove.py random_control/i2c.blif i2c_size_2027.blif
```

```
nodes by number of inputs: {0: 1, 1: 14, 2: 7, 3: 5, 4: 20, 5: 22, 6: 117}
LUTs with 2 or more inputs: 171
levels, every node counted: 9
levels, nodes with 2 or more inputs counted: 9
142 outputs, each compared on every setting of the inputs it can reach (at most 25 inputs, 189411241 settings in all): 0 outputs differ
PROVED EQUAL
```

[`check.py`](check.py) is the check of [`../epfl-router/`](../epfl-router/): 36,864 vectors by simulation, every output by name, then ABC's count and ABC `cec` against the benchmark. It reads [`blifkit.py`](blifkit.py); ABC is `yosys-abc`, or set `ABC`.

```
python3 check.py random_control/i2c.blif i2c_depth_2027.blif --cec-seconds 100
```

```
simulation: 36864 vectors, 0 batches with a mismatch
print_stats: [0m i/o = 147/ 142 lat = 0 nd = 338 edge = 1744 cube = 8076 lev = 2
cec: ['Networks are equivalent.  Time =     0.23 sec']
```

```
python3 check.py random_control/i2c.blif i2c_size_2027.blif --cec-seconds 100
```

```
simulation: 36864 vectors, 0 batches with a mismatch
print_stats: [0m i/o = 147/ 142 lat = 0 nd = 186 edge = 935 cube = 834 lev = 9
cec: ['Networks are equivalent.  Time =     0.06 sec']
```

Against the AIG as well:

```
yosys-abc -c "read_blif i2c_depth_2027.blif; strash; cec -n random_control/i2c.aig"
Networks are equivalent.  Time =     0.25 sec
yosys-abc -c "read_blif i2c_size_2027.blif; strash; cec -n random_control/i2c.aig"
Networks are equivalent.  Time =     0.06 sec
```

The suite's files are from lsils/benchmarks commit `82d8cc6`.
