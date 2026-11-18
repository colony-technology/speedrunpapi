# EPFL int2float, depth

`int2float` is the int to float converter of the [EPFL combinational benchmark suite](https://github.com/lsils/benchmarks), random/control half: 11 inputs, 7 outputs. This page is its entry for the depth table. On that table fewer levels wins, then fewer LUTs.

| | LUT-6 | Levels |
| --- | --- | --- |
| Best published, depth table (F.-X. Reichl and F. Slivovsky, `int2float_depth_2026.blif`) | 23 | 2 |
| [`int2float_depth_2027.blif`](int2float_depth_2027.blif) | 22 | 2 |

Two levels is the minimum: every output depends on 9 or 11 inputs and one LUT-6 reads 6. So the entry is decided by LUTs at 2 levels.

The table counts LUTs with two or more inputs and the levels over those, [`../epfl-dec/lutcount.py`](../epfl-dec/lutcount.py): 22 / 2 for this netlist and 23 / 2 for `best_results/depth/int2float_depth_2026.blif`.

## How it was made

The netlist is the published one of F.-X. Reichl and F. Slivovsky with one LUT removed.

The published netlist has 16 first-level LUTs and 7 second-level LUTs, one per output. [`resub.py`](resub.py) holds every signal as its value on all 2,048 inputs. For an output it looks for another set of at most six signals, among all inputs and all first-level LUTs, that still fixes the output on every input; the second-level LUT is then rebuilt over that set. The search is a set cover: for every two inputs on which the output differs, a chosen signal has to differ.

`M[3]` was the only reader of the first-level LUT `new_n21`. It is rebuilt over `B[3]` and four first-level LUTs that other outputs already use, and `new_n21` is dropped: 15 first-level LUTs and 7 second-level LUTs, 22 in all. `M[1]`, `E[1]` and `E[2]` are also rebuilt over other signals along the way, at the same count.

```
python3 resub.py best_results/depth/int2float_depth_2026.blif step.blif --levels 2 --iters 0 --seed 4
python3 rename_ports.py step.blif random_control/int2float.blif int2float_depth_2027.blif int2float
```

The second line gives the ports the suite's names, by position; the published file names them `n2` to `n49`. The two lines give this netlist byte for byte. `resub.py` needs numpy and python-sat.

## Check

[`prove.py`](prove.py) compares the netlist with the suite's `random_control/int2float.blif` on every input, output by output, without ABC. It needs Python 3 and numpy.

```
python3 prove.py random_control/int2float.blif int2float_depth_2027.blif
```

```
nodes by number of inputs: {4: 1, 5: 1, 6: 20}
LUTs with 2 or more inputs: 22
levels, every node counted: 2
levels, nodes with 2 or more inputs counted: 2
7 outputs, each compared on every setting of the inputs it can reach (at most 11 inputs, 11264 settings in all): 0 outputs differ
PROVED EQUAL
```

[`check.py`](check.py) is the check of [`../epfl-router/`](../epfl-router/): 36,864 vectors by simulation, every output by name, then ABC's count and ABC `cec` against the benchmark. It reads [`blifkit.py`](blifkit.py); ABC is `yosys-abc`, or set `ABC`.

```
python3 check.py random_control/int2float.blif int2float_depth_2027.blif --cec-seconds 60
```

```
simulation: 36864 vectors, 0 batches with a mismatch
print_stats:  i/o = 11/ 7 lat = 0 nd = 22 edge = 129 cube = 283 lev = 2
cec: ['Networks are equivalent.  Time =     0.01 sec']
```

Against the AIG as well:

```
yosys-abc -c "read_blif int2float_depth_2027.blif; strash; cec -n random_control/int2float.aig"
Networks are equivalent.  Time =     0.01 sec
```

The suite's files are from lsils/benchmarks commit `82d8cc6`.
