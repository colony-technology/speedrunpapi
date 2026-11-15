# Quartus Prime Lite 21.1.1 on Cyclone V: three third-party CRC blocks against ours

14 November 2026. Intel Quartus Prime Lite 21.1.1 Build 850, Cyclone V `5CGXFC9E7F35C8`, every design input and output registered, virtual pins, clock constraint 4.000 ns, seeds 1, 2 and 3. Flow: `quartus_map` once, then for each seed `quartus_fit --seed=N` and `quartus_sta`.

The third-party modules were fetched in the job at pinned commits and are not in this folder: ADI hdl `9bac1ed` (`jesd204_crc12`, WIDTH 64), ZipCPU eth10g `3c324ad` (`crc_eqn`, DW 64), OpenTitan `0d2b191` (`prim_crc32`, BytesPerWord 6). OpenTitan's file was changed only in its loop at line 301 so that Quartus would read it (`genvar i;` before it, `i = i + 1` for `++i`, `generate` / `endgenerate` around it).

Ours in three forms: as delivered with `(* keep = "true" *)` on each LUT wire (`ours_keep`), the attributes removed (`ours_nokeep`), and bare `(* keep *)` (`ours_keepbare`).

| block | side | comb. ALUTs | levels, seeds 1 / 2 / 3 | Fmax MHz, seeds 1 / 2 / 3 |
| --- | --- | --- | --- | --- |
| ADI `jesd204_crc12` | theirs | 76 | 3 / 3 / 3 | 244.92 / 245.34 / 237.25 |
| ADI `jesd204_crc12` | ours as delivered | 74 | 3 / 3 / 2 | 210.84 / 245.7 / 226.35 |
| ZipCPU `crc_eqn` | theirs | 738 | 4 / 3 / 3 | 187.3 / 185.15 / 195.35 |
| ZipCPU `crc_eqn` | ours as delivered | 698 | 3 / 2 / 3 | 198.14 / 197.36 / 195.24 |
| OpenTitan `prim_crc32` | theirs | 223 | 8 / 8 / 9 | 94.11 / 94.46 / 91.91 |
| OpenTitan `prim_crc32` | ours as delivered | 150 | 3 / 3 / 3 | 224.27 / 218.87 / 226.4 |

Every row, all forms and seeds, with ALMs, registers and the keep-node counts: `results.md` and `results.json`. Each design's folder holds `colony.map.rpt` and `quartus_map.log`, and per seed the fit, flow and STA reports, the worst-path report, the logs and `measure.txt`.
