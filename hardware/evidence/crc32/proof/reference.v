// Reference models: the CRC-32 bit-serial recurrence, written directly from the definition.
// Not generated.  Used by sat_equiv.py (formal equivalence in Yosys) and by the simulation testbench.
//
//   for t = 0 .. N-1:   fb = r[31] ^ d[t];   r = (r << 1) ^ (fb ? 32'h04C11DB7 : 0)
//
// r[i] is the coefficient of x^i of the register.  d[0] enters first.

module ref_crc32_fixed #(parameter W = 8) (
    input  wire [31:0]  s,
    input  wire [W-1:0] d,
    output reg  [31:0]  o
);
  integer t;
  reg fb;
  always @* begin
    o = s;
    for (t = 0; t < W; t = t + 1) begin
      fb = o[31] ^ d[t];
      o  = {o[30:0], 1'b0} ^ (fb ? 32'h04C11DB7 : 32'h00000000);
    end
  end
endmodule

// 64-bit word, e empty bytes at the top: only the first 64 - 8e bits enter.
module ref_crc32_be64 (
    input  wire [31:0] s,
    input  wire [63:0] d,
    input  wire [2:0]  e,
    output reg  [31:0] o
);
  integer t;
  reg fb;
  always @* begin
    o = s;
    for (t = 0; t < 64; t = t + 1) begin
      if (t < 64 - 8 * e) begin
        fb = o[31] ^ d[t];
        o  = {o[30:0], 1'b0} ^ (fb ? 32'h04C11DB7 : 32'h00000000);
      end
    end
  end
endmodule
