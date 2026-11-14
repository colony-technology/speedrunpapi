// Known-answer replay.  Reads the file named by +kat=PATH (written by vectors/replay.py):
//   records "LENGTH CRC32 BYTE BYTE ..." in hex, ended by LENGTH = ffffffff.
// For each message and each of 9 paths, the register starts at 32'hFFFFFFFF, the message is fed through
// the path, and ~bitreverse(register) must equal CRC32.  Then the message followed by its FCS (CRC32 least
// significant byte first) is fed again and the register must equal the residue 32'hC704DD7B.
// Paths: 0 reference model, 8 bits per step; 1/2 d8 assigns/lut6; 3/4 d32 + d8 tail; 5/6 d64 + d8 tail;
//        7/8 be64 with e on the last word.
module tb_kat;
  localparam [31:0] RESIDUE = 32'hC704DD7B;
  reg [31:0] s8, s32, s64, sbe;
  reg [7:0] d8;
  reg [31:0] d32;
  reg [63:0] d64, dbe;
  reg [2:0] ebe;
  wire [31:0] o8r, o8p, o8l, o32p, o32l, o64p, o64l, obep, obel;
  ref_crc32_fixed #(.W(8)) r8 (.s(s8), .d(d8), .o(o8r));
  colony_crc32_d8        a8 (.s(s8), .d(d8), .o(o8p));
  colony_crc32_d8_lut6   b8 (.s(s8), .d(d8), .o(o8l));
  colony_crc32_d32       a32 (.s(s32), .d(d32), .o(o32p));
  colony_crc32_d32_lut6  b32 (.s(s32), .d(d32), .o(o32l));
  colony_crc32_d64       a64 (.s(s64), .d(d64), .o(o64p));
  colony_crc32_d64_lut6  b64 (.s(s64), .d(d64), .o(o64l));
  colony_crc32_be64      abe (.s(sbe), .d(dbe), .e(ebe), .o(obep));
  colony_crc32_be64_lut6 bbe (.s(sbe), .d(dbe), .e(ebe), .o(obel));

  reg [7:0] m [0:16383];

  task automatic step8(input int f, input [31:0] s, input [7:0] b, output [31:0] o);
    s8 = s; d8 = b; #1; o = (f == 0) ? o8r : (f == 1) ? o8p : o8l;
  endtask

  task automatic run(input int p, input int n, output [31:0] st);
    int i, k, j;
    st = 32'hFFFFFFFF;
    i = 0;
    if (p >= 3 && p <= 4) begin
      while (n - i >= 4) begin
        s32 = st; d32 = {m[i + 3], m[i + 2], m[i + 1], m[i]}; #1; st = (p == 3) ? o32p : o32l; i += 4;
      end
    end else if (p >= 5 && p <= 6) begin
      while (n - i >= 8) begin
        s64 = st; d64 = {m[i + 7], m[i + 6], m[i + 5], m[i + 4], m[i + 3], m[i + 2], m[i + 1], m[i]}; #1;
        st = (p == 5) ? o64p : o64l; i += 8;
      end
    end else if (p >= 7) begin
      while (i < n) begin
        k = (n - i < 8) ? n - i : 8;
        dbe = 64'd0;
        for (j = 0; j < k; j++) dbe[8 * j +: 8] = m[i + j];
        ebe = 3'(8 - k); sbe = st; #1; st = (p == 7) ? obep : obel; i += k;
      end
    end
    while (i < n) begin                                   // paths 0..2, and the byte tail of 3..6
      step8((p == 0) ? 0 : (p % 2 == 1) ? 1 : 2, st, m[i], st); i++;
    end
  endtask

  function automatic [31:0] rev(input [31:0] x);
    for (int q = 0; q < 32; q++) rev[q] = x[31 - q];
  endfunction

  initial begin
    string path;
    int fd, rc, n, j, p, nvec, bad, badres, nbytes;
    reg [31:0] exp, st, b;
    nvec = 0; bad = 0; badres = 0; nbytes = 0;
    if (!$value$plusargs("kat=%s", path)) $fatal(1, "no +kat=");
    fd = $fopen(path, "r");
    if (fd == 0) $fatal(1, "cannot open %s", path);
    forever begin
      rc = $fscanf(fd, "%h %h", n, exp);
      if (rc != 2 || n == 32'hFFFFFFFF) break;
      for (j = 0; j < n; j++) begin rc = $fscanf(fd, "%h", b); m[j] = b[7:0]; end
      for (j = 0; j < 4; j++) m[n + j] = exp[8 * j +: 8];
      for (p = 0; p < 9; p++) begin
        run(p, n, st);
        if (~rev(st) !== exp) begin bad++; $display("MISMATCH vector %0d path %0d got %08x want %08x", nvec, p, ~rev(st), exp); end
        run(p, n + 4, st);
        if (st !== RESIDUE) begin badres++; $display("RESIDUE vector %0d path %0d got %08x", nvec, p, st); end
      end
      nvec++; nbytes += n;
    end
    $display("KAT vectors %0d bytes %0d paths 9 crc_mismatches %0d residue_mismatches %0d", nvec, nbytes, bad, badres);
    $finish;
  end
endmodule
