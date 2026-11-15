// colony_crc32_d32 with a concurrent detector: 2 check bits, H rows 32'h66aee762, 32'h9b551ffd (bit i = o[i]).
// alarm = 1 when the check bits predicted from s, d differ from those computed from o.
// The block instance is unchanged; predictor, checker and alarm share no net with it.
module colony_crc32_d32_sc (
    input  wire [31:0] s,
    input  wire [31:0] d,
    output wire [31:0] o,
    output wire alarm
);
  colony_crc32_d32 u_block (.s(s), .d(d), .o(o));
  (* keep = "true" *) wire p_n0 = s[8] ^ s[10] ^ d[21] ^ d[23];
  (* keep = "true" *) wire p_n1 = s[2] ^ s[11] ^ s[13] ^ s[14] ^ s[18] ^ s[24];
  (* keep = "true" *) wire p_n2 = s[29] ^ d[2] ^ d[7] ^ d[13] ^ d[17] ^ d[18];
  (* keep = "true" *) wire p_n3 = d[20] ^ d[29] ^ p_n0 ^ p_n1 ^ p_n2;
  (* keep = "true" *) wire p_n4 = s[0] ^ s[17] ^ s[19] ^ s[20] ^ s[21] ^ d[10];
  (* keep = "true" *) wire p_n5 = d[11] ^ d[12] ^ d[14] ^ d[31] ^ p_n0 ^ p_n4;
  (* keep = "true" *) wire c_n0 = o[5] ^ o[6] ^ o[8] ^ o[9] ^ o[10] ^ o[18];
  (* keep = "true" *) wire c_n1 = o[1] ^ o[13] ^ o[14] ^ o[15] ^ o[17] ^ o[19];
  (* keep = "true" *) wire c_n2 = o[21] ^ o[23] ^ o[25] ^ o[26] ^ o[29] ^ o[30];
  (* keep = "true" *) wire c_n3 = c_n0 ^ c_n1 ^ c_n2;
  (* keep = "true" *) wire c_n4 = o[0] ^ o[2] ^ o[3] ^ o[4] ^ o[7] ^ o[11];
  (* keep = "true" *) wire c_n5 = o[12] ^ o[16] ^ o[20] ^ o[22] ^ o[24] ^ o[25];
  (* keep = "true" *) wire c_n6 = o[27] ^ o[28] ^ o[31] ^ c_n0 ^ c_n4 ^ c_n5;
  (* keep = "true" *) wire a_n0 = 16'h6ff6 >> {c_n6, p_n5, c_n3, p_n3};
  assign alarm = a_n0;
endmodule
