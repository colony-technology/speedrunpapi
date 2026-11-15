// colony_crc32_d8 with a concurrent detector: 2 check bits, H rows 32'h3821cee9, 32'hc7df3336 (bit i = o[i]).
// alarm = 1 when the check bits predicted from s, d differ from those computed from o.
// The block instance is unchanged; predictor, checker and alarm share no net with it.
module colony_crc32_d8_sc (
    input  wire [31:0] s,
    input  wire [7:0] d,
    output wire [31:0] o,
    output wire alarm
);
  colony_crc32_d8 u_block (.s(s), .d(d), .o(o));
  (* keep = "true" *) wire p_n0 = s[1] ^ s[8];
  (* keep = "true" *) wire p_n1 = s[2] ^ s[3] ^ s[6] ^ s[7] ^ s[13] ^ s[19];
  (* keep = "true" *) wire p_n2 = s[20] ^ s[21] ^ s[26] ^ d[5] ^ p_n0 ^ p_n1;
  (* keep = "true" *) wire p_n3 = s[0] ^ s[4] ^ s[5] ^ s[9] ^ s[10] ^ s[11];
  (* keep = "true" *) wire p_n4 = s[12] ^ s[14] ^ s[15] ^ s[16] ^ s[17] ^ s[18];
  (* keep = "true" *) wire p_n5 = s[22] ^ s[23] ^ s[27] ^ s[28] ^ s[29] ^ d[2];
  (* keep = "true" *) wire p_n6 = d[3] ^ d[4] ^ p_n0 ^ p_n3 ^ p_n4 ^ p_n5;
  (* keep = "true" *) wire c_n0 = o[0] ^ o[3] ^ o[5] ^ o[6] ^ o[7] ^ o[9];
  (* keep = "true" *) wire c_n1 = o[10] ^ o[11] ^ o[14] ^ o[15] ^ o[16] ^ o[21];
  (* keep = "true" *) wire c_n2 = o[27] ^ o[28] ^ o[29] ^ c_n0 ^ c_n1;
  (* keep = "true" *) wire c_n3 = o[1] ^ o[2] ^ o[4] ^ o[5] ^ o[8] ^ o[9];
  (* keep = "true" *) wire c_n4 = o[12] ^ o[13] ^ o[16] ^ o[17] ^ o[18] ^ o[19];
  (* keep = "true" *) wire c_n5 = o[20] ^ o[22] ^ o[23] ^ o[24] ^ o[25] ^ o[26];
  (* keep = "true" *) wire c_n6 = o[30] ^ o[31] ^ c_n3 ^ c_n4 ^ c_n5;
  (* keep = "true" *) wire a_n0 = 16'h6ff6 >> {c_n6, p_n6, c_n2, p_n2};
  assign alarm = a_n0;
endmodule
