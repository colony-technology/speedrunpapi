# EPFL router, depth

`router` is the lookahead XY router of the [EPFL combinational benchmark suite](https://github.com/lsils/benchmarks), random/control half: 60 inputs, 30 outputs. This page is its entry for the depth table.

| | LUT-6 | Levels |
| --- | --- | --- |
| Best published, depth table (T. Besson, `router_depth_2022.blif`) | 25 | 3 |
| [`router_depth_2027.blif`](router_depth_2027.blif) | 22 | 3 |

Three levels is the minimum: `outport[1]` and `outport[2]` each depend on all 60 inputs, and two levels of LUT-6 read at most 36. So the depth entry is decided by LUTs at 3 levels.

The table counts LUTs with two or more inputs and the levels over those, [`../epfl-dec/lutcount.py`](../epfl-dec/lutcount.py): 22 / 3 for this netlist and 25 / 3 for `best_results/depth/router_depth_2022.blif`. ABC's `nd` is 49 because it also counts 27 constant nodes, `outport[29:3]`, which the benchmark holds at 0.

## Check

[`check.py`](check.py) compares the netlist with the suite's `random_control/router.blif` on 36,864 vectors, every output by name: 16 x 2,048 random vectors plus the all-zero and all-one vectors. It then counts the netlist with ABC and runs ABC `cec` against the benchmark. It needs Python 3 and reads [`blifkit.py`](blifkit.py); ABC is `yosys-abc`, or set `ABC`.

```
python3 check.py random_control/router.blif router_depth_2027.blif --cec-seconds 50
```

```
simulation: 36864 vectors, 0 batches with a mismatch
print_stats:  i/o = 60/ 30 lat = 0 nd = 49 edge = 124 cube = 170 lev = 3
cec: ['Networks are equivalent.  Time =     0.01 sec']
```

Against the AIG as well:

```
yosys-abc -c "read_blif router_depth_2027.blif; strash; cec -n random_control/router.aig"
Networks are equivalent.  Time =     0.01 sec
```

`yosys-abc -c "read random_control/router.aig; strash; print_supp"` gives 30, 60 and 60 inputs for `outport[0]` to `outport[2]`, and `print_supp -s` finds the functional supports equal to the structural ones (150 in all).

The suite's files are from lsils/benchmarks commit `3e9df8b`.
