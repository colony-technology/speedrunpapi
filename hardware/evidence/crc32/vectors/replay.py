"""Replays vectors/vectors.txt.

    python3 vectors/replay.py --verilator PATH/verilator --cells PATH/xilinx/cells_sim.v --work BUILD_DIR

1. Software: every CRC32 in the file is recomputed with a bit-serial loop in the block's convention
   (register 32'hFFFFFFFF, each byte least significant bit first, CRC32 = ~bitreverse(register)), which
   does not use zlib, and compared with the file.  The residue after message + FCS is also checked.
2. Hardware: the file is converted to BUILD_DIR/kat.mem and sim/tb_kat.sv is built with Verilator over
   both forms of all four blocks and the reference model, and run.
"""
import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POLY, RESIDUE = 0x04C11DB7, 0xC704DD7B


def serial(data, r=0xFFFFFFFF):
    for byte in data:
        for j in range(8):
            fb = ((r >> 31) & 1) ^ ((byte >> j) & 1)
            r = ((r << 1) & 0xFFFFFFFF) ^ (POLY if fb else 0)
    return r


def rev(x):
    return int("{:032b}".format(x)[::-1], 2)


def load():
    out = []
    for line in (ROOT / "vectors" / "vectors.txt").read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        name, n, hx, crc = line.split()
        m = b"" if hx == "-" else bytes.fromhex(hx)
        assert len(m) == int(n), name
        out.append((name, m, int(crc, 16)))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verilator", default="verilator")
    ap.add_argument("--cells", required=True, help="Yosys share/xilinx/cells_sim.v (LUT1..LUT6 models)")
    ap.add_argument("--work", type=Path, required=True)
    a = ap.parse_args()
    vec = load()
    bad = 0
    for name, m, crc in vec:
        r = serial(m)
        if (~rev(r)) & 0xFFFFFFFF != crc:
            bad += 1
            print("SOFTWARE MISMATCH", name)
        if serial(m + crc.to_bytes(4, "little")) != RESIDUE:
            bad += 1
            print("SOFTWARE RESIDUE", name)
    print("software: %d vectors, %d bytes, %d mismatches" % (len(vec), sum(len(m) for _, m, _ in vec), bad))
    a.work.mkdir(parents=True, exist_ok=True)
    mem = []
    for _, m, crc in vec:
        mem.append("%x %08x" % (len(m), crc))
        mem += ["%02x" % b for b in m]
    mem.append("ffffffff 0")
    (a.work / "kat.mem").write_text("\n".join(mem) + "\n")
    blk = ROOT / "block"
    srcs = [a.cells, str(ROOT / "proof" / "reference.v")] + sorted(str(p) for p in blk.glob("*.v")) + [str(ROOT / "sim" / "tb_kat.sv")]
    r = subprocess.run([a.verilator, "--binary", "--timing", "-Wno-fatal", "-Wno-lint", "-Wno-style", "--top-module", "tb_kat",
                        "-Mdir", str(a.work / "obj_kat"), "-o", "tb_kat"] + srcs, capture_output=True, text=True)
    if r.returncode:
        print(r.stdout[-3000:], r.stderr[-3000:])
        raise SystemExit(2)
    r = subprocess.run([str(a.work / "obj_kat" / "tb_kat"), "+kat=" + str(a.work / "kat.mem")], capture_output=True, text=True)
    print(r.stdout.strip())
    ok = bad == 0 and r.returncode == 0 and " crc_mismatches 0 residue_mismatches 0" in r.stdout
    raise SystemExit(0 if ok else 1)
