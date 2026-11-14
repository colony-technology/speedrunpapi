// Icarus testbench: every valid finite nonzero input of roundRawFNToRecFN#(W, P), in the order and the
// line format of harness.cpp's dump: control mode sign sExpCode sig out flags (out, flags in hex).
module tbi;
  parameter W = 3, P = 3;
  reg control, sign;
  reg [W+1:0] sexp;
  reg [P+2:0] sig;
  reg [2:0] mode;
  wire [W+P:0] out;
  wire [4:0] flags;
  integer ctl, mi, sg, u, s, fd;
  reg [2:0] modes [0:5];
  roundRawFNToRecFN #(W, P) dut(control, 1'b0, 1'b0, 1'b0, 1'b0, 1'b0, sign, sexp, sig, mode, out, flags);
  initial begin
    modes[0] = 0; modes[1] = 1; modes[2] = 2; modes[3] = 3; modes[4] = 4; modes[5] = 6;
    fd = $fopen("icarus.dump", "w");
    for (ctl = 0; ctl < 2; ctl = ctl + 1)
      for (mi = 0; mi < 6; mi = mi + 1)
        for (sg = 0; sg < 2; sg = sg + 1)
          for (u = 0; u < (1 << (W + 2)); u = u + 1)
            for (s = (1 << (P + 1)); s < (1 << (P + 3)); s = s + 1) begin
              control = ctl; mode = modes[mi]; sign = sg; sexp = u; sig = s;
              #1 $fwrite(fd, "%0d %0d %0d %0d %0d %0h %0h\n", ctl, modes[mi], sg, u, s, out, flags);
            end
    $fclose(fd);
    $finish;
  end
endmodule
