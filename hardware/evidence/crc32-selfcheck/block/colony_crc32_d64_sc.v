// colony_crc32_d64 with a concurrent detector: 2 check bits, H rows 32'h9f8b6d47, 32'he0f4bafa (bit i = o[i]).
// alarm = 1 when the check bits predicted from s, d differ from those computed from o.
// The block instance is unchanged; predictor, checker and alarm share no net with it.
module colony_crc32_d64_sc (
    input  wire [31:0] s,
    input  wire [63:0] d,
    output wire [31:0] o,
    output wire alarm
);
  colony_crc32_d64 u_block (.s(s), .d(d), .o(o));
  (* keep = "true" *) wire p_n0 = s[5] ^ s[6] ^ s[10] ^ s[21] ^ s[25] ^ s[27];
  (* keep = "true" *) wire p_n1 = s[29] ^ d[2] ^ d[4] ^ d[6] ^ d[10] ^ d[21];
  (* keep = "true" *) wire p_n2 = d[25] ^ d[26] ^ d[32] ^ d[36] ^ d[46] ^ d[53];
  (* keep = "true" *) wire p_n3 = d[59] ^ p_n0 ^ p_n1 ^ p_n2;
  (* keep = "true" *) wire p_n4 = s[8] ^ s[9] ^ s[11] ^ s[22] ^ s[23] ^ s[24];
  (* keep = "true" *) wire p_n5 = d[7] ^ d[8] ^ d[9] ^ d[20] ^ d[22] ^ d[23];
  (* keep = "true" *) wire p_n6 = d[35] ^ d[41] ^ d[47] ^ d[50] ^ d[55] ^ d[63];
  (* keep = "true" *) wire p_n7 = p_n4 ^ p_n5 ^ p_n6 ^ p_n3;
  (* keep = "true" *) wire p_n8 = s[4] ^ s[12] ^ s[13] ^ s[16] ^ s[18] ^ s[20];
  (* keep = "true" *) wire p_n9 = s[26] ^ s[30] ^ d[1] ^ d[5] ^ d[11] ^ d[13];
  (* keep = "true" *) wire p_n10 = d[15] ^ d[18] ^ d[19] ^ d[27] ^ d[33] ^ d[34];
  (* keep = "true" *) wire p_n11 = d[38] ^ d[39] ^ d[44] ^ d[48] ^ d[49] ^ d[57];
  (* keep = "true" *) wire p_n12 = d[58] ^ d[62] ^ p_n8 ^ p_n9 ^ p_n10 ^ p_n11;
  (* keep = "true" *) wire p_n13 = p_n3 ^ p_n12;
  (* keep = "true" *) wire c_n0 = o[1] ^ o[6] ^ o[11] ^ o[13] ^ o[23] ^ o[31];
  (* keep = "true" *) wire c_n1 = o[0] ^ o[2] ^ o[8] ^ o[10] ^ o[14] ^ o[16];
  (* keep = "true" *) wire c_n2 = o[17] ^ o[19] ^ o[24] ^ o[25] ^ o[26] ^ o[27];
  (* keep = "true" *) wire c_n3 = o[28] ^ c_n0 ^ c_n1 ^ c_n2;
  (* keep = "true" *) wire c_n4 = o[3] ^ o[4] ^ o[5] ^ o[7] ^ o[9] ^ o[12];
  (* keep = "true" *) wire c_n5 = o[15] ^ o[18] ^ o[20] ^ o[21] ^ o[22] ^ o[29];
  (* keep = "true" *) wire c_n6 = o[30] ^ c_n0 ^ c_n4 ^ c_n5;
  (* keep = "true" *) wire a_n0 = 16'h6ff6 >> {c_n6, p_n13, c_n3, p_n7};
  assign alarm = a_n0;
endmodule
