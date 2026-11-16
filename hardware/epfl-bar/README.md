# EPFL bar

`bar` is the barrel shifter of the [EPFL combinational benchmark suite](https://github.com/lsils/benchmarks): 135 inputs (128 data bits, a 7-bit shift), 128 outputs. The suite keeps the best known LUT-6 results in two tables, by size and by depth.

| | LUT-6 | Levels |
| --- | --- | --- |
| Best published, size and depth tables: the 2015 entry (`bar_size_2015.blif`) | 512 | 4 |
| [`bar_size_2027.blif`](bar_size_2027.blif) | 487 | 4 |
| [`bar_depth_2027.blif`](bar_depth_2027.blif), the same netlist | 487 | 4 |

The counts are `nd` and `lev` from ABC `print_stats`. The netlist has no constant nodes and no buffers, so these are also the table's numbers. On the depth table it has the same 4 levels as the best published and fewer LUTs.

## Check

[`check.py`](check.py) compares the netlist with the suite's `arithmetic/bar.blif` on 36,864 vectors, every output by name: 16 x 2,048 random vectors plus the all-zero and all-one vectors. It then counts the netlist with ABC and runs ABC `cec` against the benchmark. It needs Python 3 and reads [`blifkit.py`](blifkit.py); ABC is `yosys-abc`, or set `ABC`.

```
python3 check.py arithmetic/bar.blif bar_size_2027.blif --cec-seconds 50
```

```
simulation: 36864 vectors, 0 batches with a mismatch
print_stats:  i/o = 135/ 128 lat = 0 nd = 487 edge = 2901 cube = 1944 lev = 4
cec: ['Networks are equivalent.  Time =     2.73 sec']
```

The suite's file is from lsils/benchmarks commit `3e9df8b`. `bar_depth_2027.blif` is byte for byte `bar_size_2027.blif`.
