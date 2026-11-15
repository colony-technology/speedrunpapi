# Quartus Prime Lite 21.1.1 on Cyclone V: CRC-32 and divider runs

**Run date:** 2026-11-12 22:16 UTC.

**Tool:** Quartus Prime Lite 21.1.1 Build 850 (Linux x86-64), from supplied Quartus archive. **Part:** Cyclone V `5CGXFC9E7F35C8`.

**Method:** Each combinational source core is enclosed in synchronous input and output registers on one rising-edge `clk`. `udiv` uses `WIDTH=64`. The FPGA project uses virtual interface pins to bypass package I/O limits without removing registers. SDC `create_clock -period 10.000` and `derive_clock_uncertainty`. Default Quartus synthesis and fitter effort; one processor per project for bounded 4 GiB workspace memory. All runs performed in one hosted Linux x86-64 workspace.

**Flow:** `quartus_map colony -c colony`; `quartus_fit colony -c colony`; `quartus_sta colony -c colony`. Quartus standard compile flow produces native `.map.rpt`, `.fit.rpt`, `.sta.rpt` files. STA Fmax at the worst of slow 85°C/0°C timing corners is converted to `1000/Fmax` ns. Timings reflect post-fit timing model, not physical board measurements.

## Native Quartus results

| Registered module | ALMs | Combinational ALUTs | DSP blocks | Registers | Worst slow Fmax MHz | Reg-to-reg period ns | Flow |
|:--|--:|--:|--:|--:|--:|--:|:--|
| `crc32_d512_plain` | 1081 | 776 | 0 | 576 | 108.48 | 9.218 | map / fit / STA passed |
| `crc32_d512_colony_keep` | 1203 | 844 | 0 | 576 | 109.9 | 9.099 | map / fit / STA passed |
| `crc32_d1024_plain` | 2019 | 1384 | 0 | 1088 | 109.75 | 9.112 | map / fit / STA passed |
| `crc32_d1024_colony_keep` | 2112 | 1302 | 0 | 1088 | 108.47 | 9.219 | map / fit / STA passed |
| `crc32_b64_colony_plain` | 1506 | 1331 | 0 | 582 | 44.16 | 22.645 | map / fit / STA passed |
| `div64_plain` | 5094 | 8633 | 0 | 256 | 4.03 | 248.139 | map / fit / STA passed |
| `udiv` | 1350 | 2420 | 0 | 256 | 3.83 | 261.097 | map / fit / STA passed |
| `udivf64` | 1866 | 2800 | 35 | 256 | 6.26 | 159.744 | map / fit / STA passed |

## Matched CRC comparison

| Width | Plain ALMs | Colony ALMs | Plain MHz | Colony MHz | ALM ratio Colony / plain |
|--:|--:|--:|--:|--:|--:|
| 512 | 1081 | 1203 | 108.48 | 109.90 | 1.113× |
| 1024 | 2019 | 2112 | 109.75 | 108.47 | 1.046× |

## Keep-node survival (native Quartus post-fit database)

CRC-512: source marked nodes 803; pre-synthesis 803; post-synthesis 803; post-fitter 803. Quartus native `get_names -filter {*|n*} -observable_type <phase>`.
CRC-1024: source marked nodes 1296; pre-synthesis 1296; post-synthesis 1296; post-fitter 1296. Quartus native `get_names -filter {*|n*} -observable_type <phase>`.

## Reproducibility and raw reports

- Source: `colony-vendor-run.zip`. The `*_xilinx.v` files are excluded as directed; 8 technology-neutral modules included.
- Original extracted HDL and registered wrapper `registered_top.v`, `colony.qsf`, `colony.sdc` accompany reports.
- Native raw reports: `<module>/colony.map.rpt`, `<module>/colony.fit.rpt`, `<module>/colony.sta.rpt`; execution diagnostics are `quartus_map.log`, `quartus_fit.log`, `quartus_sta.log`.
- Per-stage exit codes in `quartus_map.exit`, `quartus_fit.exit`, and `quartus_sta.exit` where available. Missing numbers mean that flow stage failed or did not finish.
- Linux installation: reconstructed archive from five parts, 2,050,282,016 bytes; removed 32,837 AppleDouble (`._*`) metadata companion files to prevent Quartus Tcl startup errors. No RTL files changed.
- Quartus-reassembled archive SHA-256: `a9436d57280552bcdbeb41851b9eff59e416b297701c714bd63cae32149f4ca0`.

**Timing interpretation:** A constrained register-to-register clock exists. Virtual input and output pins are not provided external arrival/departure delays; Quartus warns that the full design is not constrained for external I/O timing. The requested register-to-register Fmax is measured from the common register clock.
