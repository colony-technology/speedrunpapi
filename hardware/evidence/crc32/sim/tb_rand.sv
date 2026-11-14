// Simulation against the bit-serial recurrence (proof/reference.v), both forms of every block.
// Per block: the zero vector, every unit vector of the inputs (for be64: for each e, every unit vector of
// s and the live data bits), then +n=N random vectors.  For be64 the random e is uniform on 0..7 and the
// bytes past the valid ones are cleared on the block's side; the reference ignores them.
// Random source: $urandom, seeded by +seed=S.
module tb_rand;
  reg [31:0] s;
  reg [63:0] d;
  reg [2:0] e;
  wire [63:0] dm = d & ~({64{1'b1}} << (64 - 8 * e));
  wire [31:0] r8, r32, r64, rbe, a8, b8, a32, b32, a64, b64, abe, bbe;
  ref_crc32_fixed #(.W(8))  q8  (.s(s), .d(d[7:0]),  .o(r8));
  ref_crc32_fixed #(.W(32)) q32 (.s(s), .d(d[31:0]), .o(r32));
  ref_crc32_fixed #(.W(64)) q64 (.s(s), .d(d),       .o(r64));
  ref_crc32_be64            qbe (.s(s), .d(d), .e(e), .o(rbe));
  colony_crc32_d8        u1 (.s(s), .d(d[7:0]),  .o(a8));
  colony_crc32_d8_lut6   u2 (.s(s), .d(d[7:0]),  .o(b8));
  colony_crc32_d32       u3 (.s(s), .d(d[31:0]), .o(a32));
  colony_crc32_d32_lut6  u4 (.s(s), .d(d[31:0]), .o(b32));
  colony_crc32_d64       u5 (.s(s), .d(d),       .o(a64));
  colony_crc32_d64_lut6  u6 (.s(s), .d(d),       .o(b64));
  colony_crc32_be64      u7 (.s(s), .d(dm), .e(e), .o(abe));
  colony_crc32_be64_lut6 u8 (.s(s), .d(dm), .e(e), .o(bbe));

  int cnt [0:3];
  int bad [0:3];

  task automatic check();
    #1;
    cnt[0]++; cnt[1]++; cnt[2]++; cnt[3]++;
    if (a8 !== r8 || b8 !== r8) bad[0]++;
    if (a32 !== r32 || b32 !== r32) bad[1]++;
    if (a64 !== r64 || b64 !== r64) bad[2]++;
    if (abe !== rbe || bbe !== rbe) bad[3]++;
  endtask

  initial begin
    int n, seed, i, k, live;
    if (!$value$plusargs("n=%d", n)) n = 200000;
    if (!$value$plusargs("seed=%d", seed)) seed = 1;
    void'($urandom(seed));
    for (k = 0; k < 4; k++) begin cnt[k] = 0; bad[k] = 0; end
    // directed: zero and unit vectors.  The fixed blocks see the low bits of d; e cycles through 0..7.
    for (int ee = 0; ee < 8; ee++) begin
      e = 3'(ee);
      s = 0; d = 0; check();
      for (i = 0; i < 32; i++) begin s = 32'd1 << i; d = 0; check(); end
      live = 64 - 8 * ee;
      for (i = 0; i < 64; i++) begin s = 0; d = 64'd1 << i; check(); end
    end
    $display("directed vectors per block %0d", cnt[0]);
    for (i = 0; i < n; i++) begin
      s = $urandom; d = {$urandom, $urandom}; e = 3'($urandom);
      check();
    end
    $display("RAND seed %0d per_block %0d  d8 %0d  d32 %0d  d64 %0d  be64 %0d mismatches", seed, cnt[0], bad[0], bad[1], bad[2], bad[3]);
    $finish;
  end
endmodule
