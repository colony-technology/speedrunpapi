# EPFL mem_ctrl

`mem_ctrl` is the memory controller of the [EPFL combinational benchmark suite](https://github.com/lsils/benchmarks), random/control half: 1,204 inputs, 1,231 outputs. The suite keeps the best known LUT-6 results in two tables, by size and by depth.

| | LUT-6 | Levels |
| --- | --- | --- |
| Best published, size table (F.-X. Reichl and F. Slivovsky, `mem_ctrl_size_2026.blif`) | 1669 | 27 |
| [`mem_ctrl_size_2027.blif`](mem_ctrl_size_2027.blif) | 1666 | 27 |
| Best published, depth table (F.-X. Reichl and F. Slivovsky, `mem_ctrl_depth_2026.blif`) | 1716 | 5 |
| [`mem_ctrl_depth_2027.blif`](mem_ctrl_depth_2027.blif) | 1714 | 5 |

Both netlists are the published ones of F.-X. Reichl and F. Slivovsky with LUTs removed, 3 on the size table and 2 on the depth table, at the same levels.

The table counts LUTs with two or more inputs and the levels over those, [`../epfl-dec/lutcount.py`](../epfl-dec/lutcount.py):

```
python3 ../epfl-dec/lutcount.py mem_ctrl_size_2027.blif     # LUTs(>=2 inputs) 1666  levels 27  max fanin 6
python3 ../epfl-dec/lutcount.py mem_ctrl_depth_2027.blif    # LUTs(>=2 inputs) 1714  levels 5  max fanin 6
```

The same count gives 1669 / 27 and 1716 / 5 for the published files. ABC's `nd` is higher (1940 and 1987) because it also counts single-input nodes.

## Check

The ports are named by position (`pi0000` ..., `po0000` ...), as in the published files, so the netlists are compared with the benchmark by order, with ABC `cec -n`; a match by port name does not apply here.

```
yosys-abc -c "cec -n random_control/mem_ctrl.blif mem_ctrl_size_2027.blif"
Networks are equivalent.  Time =    18.64 sec
yosys-abc -c "cec -n random_control/mem_ctrl.aig mem_ctrl_size_2027.blif"
Networks are equivalent.  Time =    19.62 sec
yosys-abc -c "cec -n random_control/mem_ctrl.blif mem_ctrl_depth_2027.blif"
Networks are equivalent.  Time =    11.61 sec
yosys-abc -c "cec -n random_control/mem_ctrl.aig mem_ctrl_depth_2027.blif"
Networks are equivalent.  Time =    11.89 sec
```

The suite's files are from lsils/benchmarks commit `3e9df8b`.
