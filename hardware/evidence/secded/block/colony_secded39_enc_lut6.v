// colony_secded39_enc: c = rows of H over d.  17 LUT-6, 2 levels.  Matrix: OpenTitan prim_secded_39_32 (Hsiao).
module colony_secded39_enc_lut6 (input wire [31:0] d, output wire [6:0] c);
  wire n0; LUT5 #(.INIT(32'h96696996)) u0 (.O(n0), .I0(d[0]), .I1(d[5]), .I2(d[12]), .I3(d[13]), .I4(d[25]));
  wire n1; LUT5 #(.INIT(32'h96696996)) u1 (.O(n1), .I0(d[4]), .I1(d[6]), .I2(d[17]), .I3(d[21]), .I4(d[28]));
  wire n2; LUT4 #(.INIT(16'h6996)) u2 (.O(n2), .I0(d[1]), .I1(d[7]), .I2(d[8]), .I3(d[20]));
  wire n3; LUT4 #(.INIT(16'h6996)) u3 (.O(n3), .I0(d[2]), .I1(d[14]), .I2(d[22]), .I3(d[27]));
  wire n4; LUT6 #(.INIT(64'h6996966996696996)) u4 (.O(n4), .I0(d[2]), .I1(d[8]), .I2(d[10]), .I3(d[11]), .I4(d[15]), .I5(d[17]));
  wire n5; LUT5 #(.INIT(32'h96696996)) u5 (.O(n5), .I0(d[18]), .I1(d[26]), .I2(d[29]), .I3(n0), .I4(n4));
  wire n6; LUT6 #(.INIT(64'h6996966996696996)) u6 (.O(n6), .I0(d[15]), .I1(d[19]), .I2(d[20]), .I3(d[23]), .I4(d[25]), .I5(d[26]));
  wire n7; LUT5 #(.INIT(32'h96696996)) u7 (.O(n7), .I0(d[27]), .I1(d[30]), .I2(d[31]), .I3(n1), .I4(n6));
  wire n8; LUT6 #(.INIT(64'h6996966996696996)) u8 (.O(n8), .I0(d[3]), .I1(d[5]), .I2(d[11]), .I3(d[15]), .I4(d[16]), .I5(d[18]));
  wire n9; LUT6 #(.INIT(64'h6996966996696996)) u9 (.O(n9), .I0(d[19]), .I1(d[21]), .I2(d[24]), .I3(d[30]), .I4(n2), .I5(n8));
  wire n10; LUT6 #(.INIT(64'h6996966996696996)) u10 (.O(n10), .I0(d[0]), .I1(d[7]), .I2(d[9]), .I3(d[10]), .I4(d[11]), .I5(d[14]));
  wire n11; LUT5 #(.INIT(32'h96696996)) u11 (.O(n11), .I0(d[16]), .I1(d[24]), .I2(d[29]), .I3(n1), .I4(n10));
  wire n12; LUT6 #(.INIT(64'h6996966996696996)) u12 (.O(n12), .I0(d[1]), .I1(d[3]), .I2(d[4]), .I3(d[9]), .I4(d[16]), .I5(d[22]));
  wire n13; LUT5 #(.INIT(32'h96696996)) u13 (.O(n13), .I0(d[23]), .I1(d[30]), .I2(d[31]), .I3(n0), .I4(n12));
  wire n14; LUT6 #(.INIT(64'h6996966996696996)) u14 (.O(n14), .I0(d[3]), .I1(d[6]), .I2(d[9]), .I3(d[13]), .I4(d[18]), .I5(d[19]));
  wire n15; LUT6 #(.INIT(64'h6996966996696996)) u15 (.O(n15), .I0(d[23]), .I1(d[24]), .I2(d[26]), .I3(d[29]), .I4(n3), .I5(n14));
  wire n16; LUT6 #(.INIT(64'h6996966996696996)) u16 (.O(n16), .I0(d[10]), .I1(d[12]), .I2(d[28]), .I3(d[31]), .I4(n2), .I5(n3));
  assign c[0] = n5;
  assign c[1] = n7;
  assign c[2] = n9;
  assign c[3] = n11;
  assign c[4] = n13;
  assign c[5] = n15;
  assign c[6] = n16;
endmodule
