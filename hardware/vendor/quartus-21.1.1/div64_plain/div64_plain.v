module div64_plain(input [63:0] a, input [63:0] b, output [63:0] q, output [63:0] r);
  assign q = a / b;
  assign r = a % b;
endmodule
