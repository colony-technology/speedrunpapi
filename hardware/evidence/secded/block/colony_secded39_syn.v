// colony_secded39_syn: s = rows of H over r.  19 LUT-6, 2 levels.  Matrix: OpenTitan prim_secded_39_32 (Hsiao).
module colony_secded39_syn (input wire [38:0] r, output wire [6:0] s);
  (* keep = "true" *) wire n0 = r[0] ^ r[5] ^ r[12] ^ r[13] ^ r[25];
  (* keep = "true" *) wire n1 = r[4] ^ r[6] ^ r[17] ^ r[21] ^ r[28];
  (* keep = "true" *) wire n2 = r[2] ^ r[8] ^ r[10] ^ r[11] ^ r[15] ^ r[17];
  (* keep = "true" *) wire n3 = r[18] ^ r[26] ^ r[29] ^ r[32] ^ n0 ^ n2;
  (* keep = "true" *) wire n4 = r[15] ^ r[19] ^ r[20] ^ r[23] ^ r[25] ^ r[26];
  (* keep = "true" *) wire n5 = r[27] ^ r[30] ^ r[31] ^ r[33] ^ n1 ^ n4;
  (* keep = "true" *) wire n6 = r[1] ^ r[3] ^ r[5] ^ r[7] ^ r[8] ^ r[11];
  (* keep = "true" *) wire n7 = r[15] ^ r[16] ^ r[18] ^ r[19] ^ r[20] ^ r[21];
  (* keep = "true" *) wire n8 = r[24] ^ r[30] ^ r[34] ^ n6 ^ n7;
  (* keep = "true" *) wire n9 = r[0] ^ r[7] ^ r[9] ^ r[10] ^ r[11] ^ r[14];
  (* keep = "true" *) wire n10 = r[16] ^ r[24] ^ r[29] ^ r[35] ^ n1 ^ n9;
  (* keep = "true" *) wire n11 = r[1] ^ r[3] ^ r[4] ^ r[9] ^ r[16] ^ r[22];
  (* keep = "true" *) wire n12 = r[23] ^ r[30] ^ r[31] ^ r[36] ^ n0 ^ n11;
  (* keep = "true" *) wire n13 = r[2] ^ r[3] ^ r[6] ^ r[9] ^ r[13] ^ r[14];
  (* keep = "true" *) wire n14 = r[18] ^ r[19] ^ r[22] ^ r[23] ^ r[24] ^ r[26];
  (* keep = "true" *) wire n15 = r[27] ^ r[29] ^ r[37] ^ n13 ^ n14;
  (* keep = "true" *) wire n16 = r[1] ^ r[2] ^ r[7] ^ r[8] ^ r[10] ^ r[12];
  (* keep = "true" *) wire n17 = r[14] ^ r[20] ^ r[22] ^ r[27] ^ r[28] ^ r[31];
  (* keep = "true" *) wire n18 = r[38] ^ n16 ^ n17;
  assign s[0] = n3;
  assign s[1] = n5;
  assign s[2] = n8;
  assign s[3] = n10;
  assign s[4] = n12;
  assign s[5] = n15;
  assign s[6] = n18;
endmodule
