// colony_crc32_d64 with a concurrent detector: 2 check bits, H rows 32'h9f8b6d47, 32'he0f4bafa (bit i = o[i]).
// alarm = 1 when the check bits predicted from s, d differ from those computed from o.
// The block instance is unchanged; predictor, checker and alarm share no net with it.
module colony_crc32_d64_sc_lut6 (
    input  wire [31:0] s,
    input  wire [63:0] d,
    output wire [31:0] o,
    output wire alarm
);
  colony_crc32_d64_lut6 u_block (.s(s), .d(d), .o(o));
  wire p_n0; LUT6 #(.INIT(64'h6996966996696996)) u_p_n0 (.O(p_n0), .I0(s[5]), .I1(s[6]), .I2(s[10]), .I3(s[21]), .I4(s[25]), .I5(s[27]));
  wire p_n1; LUT6 #(.INIT(64'h6996966996696996)) u_p_n1 (.O(p_n1), .I0(s[29]), .I1(d[2]), .I2(d[4]), .I3(d[6]), .I4(d[10]), .I5(d[21]));
  wire p_n2; LUT6 #(.INIT(64'h6996966996696996)) u_p_n2 (.O(p_n2), .I0(d[25]), .I1(d[26]), .I2(d[32]), .I3(d[36]), .I4(d[46]), .I5(d[53]));
  wire p_n3; LUT4 #(.INIT(16'h6996)) u_p_n3 (.O(p_n3), .I0(d[59]), .I1(p_n0), .I2(p_n1), .I3(p_n2));
  wire p_n4; LUT6 #(.INIT(64'h6996966996696996)) u_p_n4 (.O(p_n4), .I0(s[8]), .I1(s[9]), .I2(s[11]), .I3(s[22]), .I4(s[23]), .I5(s[24]));
  wire p_n5; LUT6 #(.INIT(64'h6996966996696996)) u_p_n5 (.O(p_n5), .I0(d[7]), .I1(d[8]), .I2(d[9]), .I3(d[20]), .I4(d[22]), .I5(d[23]));
  wire p_n6; LUT6 #(.INIT(64'h6996966996696996)) u_p_n6 (.O(p_n6), .I0(d[35]), .I1(d[41]), .I2(d[47]), .I3(d[50]), .I4(d[55]), .I5(d[63]));
  wire p_n7; LUT4 #(.INIT(16'h6996)) u_p_n7 (.O(p_n7), .I0(p_n4), .I1(p_n5), .I2(p_n6), .I3(p_n3));
  wire p_n8; LUT6 #(.INIT(64'h6996966996696996)) u_p_n8 (.O(p_n8), .I0(s[4]), .I1(s[12]), .I2(s[13]), .I3(s[16]), .I4(s[18]), .I5(s[20]));
  wire p_n9; LUT6 #(.INIT(64'h6996966996696996)) u_p_n9 (.O(p_n9), .I0(s[26]), .I1(s[30]), .I2(d[1]), .I3(d[5]), .I4(d[11]), .I5(d[13]));
  wire p_n10; LUT6 #(.INIT(64'h6996966996696996)) u_p_n10 (.O(p_n10), .I0(d[15]), .I1(d[18]), .I2(d[19]), .I3(d[27]), .I4(d[33]), .I5(d[34]));
  wire p_n11; LUT6 #(.INIT(64'h6996966996696996)) u_p_n11 (.O(p_n11), .I0(d[38]), .I1(d[39]), .I2(d[44]), .I3(d[48]), .I4(d[49]), .I5(d[57]));
  wire p_n12; LUT6 #(.INIT(64'h6996966996696996)) u_p_n12 (.O(p_n12), .I0(d[58]), .I1(d[62]), .I2(p_n8), .I3(p_n9), .I4(p_n10), .I5(p_n11));
  wire p_n13; LUT2 #(.INIT(4'h6)) u_p_n13 (.O(p_n13), .I0(p_n3), .I1(p_n12));
  wire c_n0; LUT6 #(.INIT(64'h6996966996696996)) u_c_n0 (.O(c_n0), .I0(o[1]), .I1(o[6]), .I2(o[11]), .I3(o[13]), .I4(o[23]), .I5(o[31]));
  wire c_n1; LUT6 #(.INIT(64'h6996966996696996)) u_c_n1 (.O(c_n1), .I0(o[0]), .I1(o[2]), .I2(o[8]), .I3(o[10]), .I4(o[14]), .I5(o[16]));
  wire c_n2; LUT6 #(.INIT(64'h6996966996696996)) u_c_n2 (.O(c_n2), .I0(o[17]), .I1(o[19]), .I2(o[24]), .I3(o[25]), .I4(o[26]), .I5(o[27]));
  wire c_n3; LUT4 #(.INIT(16'h6996)) u_c_n3 (.O(c_n3), .I0(o[28]), .I1(c_n0), .I2(c_n1), .I3(c_n2));
  wire c_n4; LUT6 #(.INIT(64'h6996966996696996)) u_c_n4 (.O(c_n4), .I0(o[3]), .I1(o[4]), .I2(o[5]), .I3(o[7]), .I4(o[9]), .I5(o[12]));
  wire c_n5; LUT6 #(.INIT(64'h6996966996696996)) u_c_n5 (.O(c_n5), .I0(o[15]), .I1(o[18]), .I2(o[20]), .I3(o[21]), .I4(o[22]), .I5(o[29]));
  wire c_n6; LUT4 #(.INIT(16'h6996)) u_c_n6 (.O(c_n6), .I0(o[30]), .I1(c_n0), .I2(c_n4), .I3(c_n5));
  wire a_n0; LUT4 #(.INIT(16'h6ff6)) u_a_n0 (.O(a_n0), .I0(p_n7), .I1(c_n3), .I2(p_n13), .I3(c_n6));
  assign alarm = a_n0;
endmodule
