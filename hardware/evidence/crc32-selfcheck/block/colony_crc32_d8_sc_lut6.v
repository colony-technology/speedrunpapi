// colony_crc32_d8 with a concurrent detector: 2 check bits, H rows 32'h3821cee9, 32'hc7df3336 (bit i = o[i]).
// alarm = 1 when the check bits predicted from s, d differ from those computed from o.
// The block instance is unchanged; predictor, checker and alarm share no net with it.
module colony_crc32_d8_sc_lut6 (
    input  wire [31:0] s,
    input  wire [7:0] d,
    output wire [31:0] o,
    output wire alarm
);
  colony_crc32_d8_lut6 u_block (.s(s), .d(d), .o(o));
  wire p_n0; LUT2 #(.INIT(4'h6)) u_p_n0 (.O(p_n0), .I0(s[1]), .I1(s[8]));
  wire p_n1; LUT6 #(.INIT(64'h6996966996696996)) u_p_n1 (.O(p_n1), .I0(s[2]), .I1(s[3]), .I2(s[6]), .I3(s[7]), .I4(s[13]), .I5(s[19]));
  wire p_n2; LUT6 #(.INIT(64'h6996966996696996)) u_p_n2 (.O(p_n2), .I0(s[20]), .I1(s[21]), .I2(s[26]), .I3(d[5]), .I4(p_n0), .I5(p_n1));
  wire p_n3; LUT6 #(.INIT(64'h6996966996696996)) u_p_n3 (.O(p_n3), .I0(s[0]), .I1(s[4]), .I2(s[5]), .I3(s[9]), .I4(s[10]), .I5(s[11]));
  wire p_n4; LUT6 #(.INIT(64'h6996966996696996)) u_p_n4 (.O(p_n4), .I0(s[12]), .I1(s[14]), .I2(s[15]), .I3(s[16]), .I4(s[17]), .I5(s[18]));
  wire p_n5; LUT6 #(.INIT(64'h6996966996696996)) u_p_n5 (.O(p_n5), .I0(s[22]), .I1(s[23]), .I2(s[27]), .I3(s[28]), .I4(s[29]), .I5(d[2]));
  wire p_n6; LUT6 #(.INIT(64'h6996966996696996)) u_p_n6 (.O(p_n6), .I0(d[3]), .I1(d[4]), .I2(p_n0), .I3(p_n3), .I4(p_n4), .I5(p_n5));
  wire c_n0; LUT6 #(.INIT(64'h6996966996696996)) u_c_n0 (.O(c_n0), .I0(o[0]), .I1(o[3]), .I2(o[5]), .I3(o[6]), .I4(o[7]), .I5(o[9]));
  wire c_n1; LUT6 #(.INIT(64'h6996966996696996)) u_c_n1 (.O(c_n1), .I0(o[10]), .I1(o[11]), .I2(o[14]), .I3(o[15]), .I4(o[16]), .I5(o[21]));
  wire c_n2; LUT5 #(.INIT(32'h96696996)) u_c_n2 (.O(c_n2), .I0(o[27]), .I1(o[28]), .I2(o[29]), .I3(c_n0), .I4(c_n1));
  wire c_n3; LUT6 #(.INIT(64'h6996966996696996)) u_c_n3 (.O(c_n3), .I0(o[1]), .I1(o[2]), .I2(o[4]), .I3(o[5]), .I4(o[8]), .I5(o[9]));
  wire c_n4; LUT6 #(.INIT(64'h6996966996696996)) u_c_n4 (.O(c_n4), .I0(o[12]), .I1(o[13]), .I2(o[16]), .I3(o[17]), .I4(o[18]), .I5(o[19]));
  wire c_n5; LUT6 #(.INIT(64'h6996966996696996)) u_c_n5 (.O(c_n5), .I0(o[20]), .I1(o[22]), .I2(o[23]), .I3(o[24]), .I4(o[25]), .I5(o[26]));
  wire c_n6; LUT5 #(.INIT(32'h96696996)) u_c_n6 (.O(c_n6), .I0(o[30]), .I1(o[31]), .I2(c_n3), .I3(c_n4), .I4(c_n5));
  wire a_n0; LUT4 #(.INIT(16'h6ff6)) u_a_n0 (.O(a_n0), .I0(p_n2), .I1(c_n2), .I2(p_n6), .I3(c_n6));
  assign alarm = a_n0;
endmodule
