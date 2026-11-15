// colony_secded39_enc: c = rows of H over d.  17 LUT-6, 2 levels.  Matrix: OpenTitan prim_secded_39_32 (Hsiao).
module colony_secded39_enc (input wire [31:0] d, output wire [6:0] c);
  (* keep = "true" *) wire n0 = d[0] ^ d[5] ^ d[12] ^ d[13] ^ d[25];
  (* keep = "true" *) wire n1 = d[4] ^ d[6] ^ d[17] ^ d[21] ^ d[28];
  (* keep = "true" *) wire n2 = d[1] ^ d[7] ^ d[8] ^ d[20];
  (* keep = "true" *) wire n3 = d[2] ^ d[14] ^ d[22] ^ d[27];
  (* keep = "true" *) wire n4 = d[2] ^ d[8] ^ d[10] ^ d[11] ^ d[15] ^ d[17];
  (* keep = "true" *) wire n5 = d[18] ^ d[26] ^ d[29] ^ n0 ^ n4;
  (* keep = "true" *) wire n6 = d[15] ^ d[19] ^ d[20] ^ d[23] ^ d[25] ^ d[26];
  (* keep = "true" *) wire n7 = d[27] ^ d[30] ^ d[31] ^ n1 ^ n6;
  (* keep = "true" *) wire n8 = d[3] ^ d[5] ^ d[11] ^ d[15] ^ d[16] ^ d[18];
  (* keep = "true" *) wire n9 = d[19] ^ d[21] ^ d[24] ^ d[30] ^ n2 ^ n8;
  (* keep = "true" *) wire n10 = d[0] ^ d[7] ^ d[9] ^ d[10] ^ d[11] ^ d[14];
  (* keep = "true" *) wire n11 = d[16] ^ d[24] ^ d[29] ^ n1 ^ n10;
  (* keep = "true" *) wire n12 = d[1] ^ d[3] ^ d[4] ^ d[9] ^ d[16] ^ d[22];
  (* keep = "true" *) wire n13 = d[23] ^ d[30] ^ d[31] ^ n0 ^ n12;
  (* keep = "true" *) wire n14 = d[3] ^ d[6] ^ d[9] ^ d[13] ^ d[18] ^ d[19];
  (* keep = "true" *) wire n15 = d[23] ^ d[24] ^ d[26] ^ d[29] ^ n3 ^ n14;
  (* keep = "true" *) wire n16 = d[10] ^ d[12] ^ d[28] ^ d[31] ^ n2 ^ n3;
  assign c[0] = n5;
  assign c[1] = n7;
  assign c[2] = n9;
  assign c[3] = n11;
  assign c[4] = n13;
  assign c[5] = n15;
  assign c[6] = n16;
endmodule
