// colony_crc32_d32 with a concurrent detector: 2 check bits, H rows 32'h66aee762, 32'h9b551ffd (bit i = o[i]).
// alarm = 1 when the check bits predicted from s, d differ from those computed from o.
// The block instance is unchanged; predictor, checker and alarm share no net with it.
module colony_crc32_d32_sc_lut6 (
    input  wire [31:0] s,
    input  wire [31:0] d,
    output wire [31:0] o,
    output wire alarm
);
  colony_crc32_d32_lut6 u_block (.s(s), .d(d), .o(o));
  wire p_n0; LUT4 #(.INIT(16'h6996)) u_p_n0 (.O(p_n0), .I0(s[8]), .I1(s[10]), .I2(d[21]), .I3(d[23]));
  wire p_n1; LUT6 #(.INIT(64'h6996966996696996)) u_p_n1 (.O(p_n1), .I0(s[2]), .I1(s[11]), .I2(s[13]), .I3(s[14]), .I4(s[18]), .I5(s[24]));
  wire p_n2; LUT6 #(.INIT(64'h6996966996696996)) u_p_n2 (.O(p_n2), .I0(s[29]), .I1(d[2]), .I2(d[7]), .I3(d[13]), .I4(d[17]), .I5(d[18]));
  wire p_n3; LUT5 #(.INIT(32'h96696996)) u_p_n3 (.O(p_n3), .I0(d[20]), .I1(d[29]), .I2(p_n0), .I3(p_n1), .I4(p_n2));
  wire p_n4; LUT6 #(.INIT(64'h6996966996696996)) u_p_n4 (.O(p_n4), .I0(s[0]), .I1(s[17]), .I2(s[19]), .I3(s[20]), .I4(s[21]), .I5(d[10]));
  wire p_n5; LUT6 #(.INIT(64'h6996966996696996)) u_p_n5 (.O(p_n5), .I0(d[11]), .I1(d[12]), .I2(d[14]), .I3(d[31]), .I4(p_n0), .I5(p_n4));
  wire c_n0; LUT6 #(.INIT(64'h6996966996696996)) u_c_n0 (.O(c_n0), .I0(o[5]), .I1(o[6]), .I2(o[8]), .I3(o[9]), .I4(o[10]), .I5(o[18]));
  wire c_n1; LUT6 #(.INIT(64'h6996966996696996)) u_c_n1 (.O(c_n1), .I0(o[1]), .I1(o[13]), .I2(o[14]), .I3(o[15]), .I4(o[17]), .I5(o[19]));
  wire c_n2; LUT6 #(.INIT(64'h6996966996696996)) u_c_n2 (.O(c_n2), .I0(o[21]), .I1(o[23]), .I2(o[25]), .I3(o[26]), .I4(o[29]), .I5(o[30]));
  wire c_n3; LUT3 #(.INIT(8'h96)) u_c_n3 (.O(c_n3), .I0(c_n0), .I1(c_n1), .I2(c_n2));
  wire c_n4; LUT6 #(.INIT(64'h6996966996696996)) u_c_n4 (.O(c_n4), .I0(o[0]), .I1(o[2]), .I2(o[3]), .I3(o[4]), .I4(o[7]), .I5(o[11]));
  wire c_n5; LUT6 #(.INIT(64'h6996966996696996)) u_c_n5 (.O(c_n5), .I0(o[12]), .I1(o[16]), .I2(o[20]), .I3(o[22]), .I4(o[24]), .I5(o[25]));
  wire c_n6; LUT6 #(.INIT(64'h6996966996696996)) u_c_n6 (.O(c_n6), .I0(o[27]), .I1(o[28]), .I2(o[31]), .I3(c_n0), .I4(c_n4), .I5(c_n5));
  wire a_n0; LUT4 #(.INIT(16'h6ff6)) u_a_n0 (.O(a_n0), .I0(p_n3), .I1(c_n3), .I2(p_n5), .I3(c_n6));
  assign alarm = a_n0;
endmodule
