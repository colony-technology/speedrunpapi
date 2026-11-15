#!/usr/bin/env python3
"""The emitter against bvfsm's integer semantics: the module bv2v emits for DESC at length N is simulated
by Icarus on input vectors, and every output (and `valid`) is compared with bvfsm.evaluate.
Vectors: every input when the input space is at most 2^16 words, else COUNT random ones (seed 1; vectors
under ones_below/onehot assumptions are drawn from their valid sets three times in four).
usage: emitcheck.py DESC N [COUNT]"""
import itertools
import os
import shutil
import random
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bv2v  # noqa: E402
import bvfsm  # noqa: E402

OSS = os.environ.get("EDA_BIN") or os.path.dirname(shutil.which("iverilog") or "iverilog")


def main():
    d = bvfsm.Desc(sys.argv[1])
    N = int(sys.argv[2])
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 20000
    vin = [(nm, N + n.woff, n) for nm, n in d.inputs_vec]
    sin = [nm for nm, _ in d.inputs_sc]
    total_bits = sum(w for _, w, _ in vin) + len(sin)
    rng = random.Random(1)
    cases = []
    if total_bits <= 16:
        for vals in itertools.product(*[range(1 << w) for _, w, _ in vin], *[range(2) for _ in sin]):
            cases.append(vals)
    else:
        for _ in range(count):
            vals = []
            for nm, w, n in vin:
                if n in d.thermo and rng.random() < 0.75:
                    vals.append((1 << rng.randrange(w + 1)) - 1)
                elif n in d.onehot and rng.random() < 0.75:
                    vals.append(1 << rng.randrange(w))
                else:
                    vals.append(rng.getrandbits(w))
            vals += [rng.randrange(2) for _ in sin]
            cases.append(tuple(vals))
    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "dut.v"), "w").write(bv2v.emit(d, N, "dut"))
        outs = [(nm, 1 if n.scalar else N + n.woff) for nm, n in d.outputs] + [("valid", 1)]
        decl = "\n".join("  reg [%d:0] %s;" % (w - 1, nm) for nm, w, _ in vin) + "\n" + \
               "\n".join("  reg %s;" % nm for nm in sin) + "\n" + \
               "\n".join("  wire [%d:0] o_%s;" % (w - 1, nm) for nm, w in outs)
        conn = ", ".join([".%s(%s)" % (nm, nm) for nm, _, _ in vin] + [".%s(%s)" % (nm, nm) for nm in sin] +
                         [".%s(o_%s)" % (nm, nm) for nm, _ in outs])
        names = [nm for nm, _, _ in vin] + sin
        tb = """module tb;
%s
  integer fd, fo, r;
  dut u(%s);
  initial begin
    fd = $fopen("%s/in.txt", "r"); fo = $fopen("%s/out.txt", "w");
    while (!$feof(fd)) begin
      r = $fscanf(fd, "%s\\n", %s);
      #1 $fwrite(fo, "%s\\n", %s);
    end
    $fclose(fo); $finish;
  end
endmodule
""" % (decl, conn, tmp, tmp, " ".join(["%h"] * len(names)), ", ".join(names),
       " ".join(["%h"] * len(outs)), ", ".join("o_" + nm for nm, _ in outs))
        open(os.path.join(tmp, "tb.v"), "w").write(tb)
        open(os.path.join(tmp, "in.txt"), "w").write("".join(" ".join("%x" % v for v in c) + "\n" for c in cases))
        subprocess.run([OSS + "/iverilog", "-g2005", "-o", os.path.join(tmp, "s.vvp"),
                        os.path.join(tmp, "dut.v"), os.path.join(tmp, "tb.v")], check=True)
        subprocess.run([OSS + "/vvp", "-n", os.path.join(tmp, "s.vvp")], check=True, capture_output=True)
        got = [line.split() for line in open(os.path.join(tmp, "out.txt"))]
    bad = 0
    for c, g in zip(cases, got):
        vv = {nm: c[i] for i, (nm, _, _) in enumerate(vin)}
        ss = {nm: c[len(vin) + i] for i, nm in enumerate(sin)}
        ok, o = bvfsm.evaluate(d, N, vv, ss)
        want = [o[nm] for nm, _ in outs[:-1]] + [int(ok)]
        if [int(x, 16) for x in g] != want:
            bad += 1
            if bad <= 5:
                print("DIFF N=%d inputs %s emitted %s semantics %s" % (N, c, g, want))
    print("emitted %s at N=%d: %d vectors%s, %d differences" % (os.path.basename(d.path), N, len(cases),
          " (all)" if total_bits <= 16 else " (random)", bad))
    return 1 if bad or len(got) != len(cases) else 0


if __name__ == "__main__":
    sys.exit(main())
