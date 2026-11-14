// CRC-32, polynomial 0x04C11DB7 (IEEE 802.3 frame check sequence), register update.
// Recurrence, applied to d[0] first:  fb = s[31] ^ d[t];  s = (s << 1) ^ (fb ? 32'h04C11DB7 : 0).
// s[i] holds the coefficient of x^i.  Initial value and final complement are outside this block.
// 8 data bits per call, d[0] first.  o = register after d[0] .. d[7] from s.  41 LUT-6, 2 levels.
module colony_crc32_d8 (
    input  wire [31:0] s,
    input  wire [7:0] d,
    output wire [31:0] o
);
  (* keep = "true" *) wire n0 = s[24] ^ s[30] ^ d[1] ^ d[7];
  (* keep = "true" *) wire n1 = s[25] ^ s[31] ^ d[0] ^ d[6];
  (* keep = "true" *) wire n2 = s[26] ^ d[5];
  (* keep = "true" *) wire n3 = s[27] ^ d[4];
  (* keep = "true" *) wire n4 = s[28] ^ d[3];
  (* keep = "true" *) wire n5 = s[29] ^ d[2];
  (* keep = "true" *) wire n6 = s[30] ^ d[1];
  (* keep = "true" *) wire n7 = s[31] ^ d[0];
  (* keep = "true" *) wire n8 = s[24] ^ d[7];
  (* keep = "true" *) wire n9 = s[25] ^ d[6];
  (* keep = "true" *) wire n10 = n0 ^ n1;
  (* keep = "true" *) wire n11 = n0 ^ n1 ^ n2;
  (* keep = "true" *) wire n12 = n1 ^ n2 ^ n3;
  (* keep = "true" *) wire n13 = n0 ^ n2 ^ n3 ^ n4;
  (* keep = "true" *) wire n14 = n0 ^ n1 ^ n3 ^ n4 ^ n5;
  (* keep = "true" *) wire n15 = n1 ^ n2 ^ n4 ^ n5 ^ n6;
  (* keep = "true" *) wire n16 = n2 ^ n3 ^ n5 ^ n7 ^ n8;
  (* keep = "true" *) wire n17 = s[0] ^ n3 ^ n4 ^ n8 ^ n9;
  (* keep = "true" *) wire n18 = s[1] ^ n2 ^ n4 ^ n5 ^ n9;
  (* keep = "true" *) wire n19 = s[2] ^ n2 ^ n3 ^ n5 ^ n8;
  (* keep = "true" *) wire n20 = s[3] ^ n3 ^ n4 ^ n8 ^ n9;
  (* keep = "true" *) wire n21 = s[4] ^ n0 ^ n2 ^ n4 ^ n5 ^ n9;
  (* keep = "true" *) wire n22 = s[5] ^ n1 ^ n2 ^ n3 ^ n5 ^ n6;
  (* keep = "true" *) wire n23 = s[6] ^ n2 ^ n3 ^ n4 ^ n6 ^ n7;
  (* keep = "true" *) wire n24 = s[7] ^ n3 ^ n4 ^ n5 ^ n7;
  (* keep = "true" *) wire n25 = s[8] ^ n4 ^ n5 ^ n8;
  (* keep = "true" *) wire n26 = s[9] ^ n5 ^ n6 ^ n9;
  (* keep = "true" *) wire n27 = s[10] ^ n2 ^ n6 ^ n7;
  (* keep = "true" *) wire n28 = s[11] ^ n3 ^ n7;
  (* keep = "true" *) wire n29 = s[12] ^ n4;
  (* keep = "true" *) wire n30 = s[13] ^ n5;
  (* keep = "true" *) wire n31 = s[14] ^ n8;
  (* keep = "true" *) wire n32 = s[15] ^ n0 ^ n9;
  (* keep = "true" *) wire n33 = s[16] ^ n1 ^ n2;
  (* keep = "true" *) wire n34 = s[17] ^ n2 ^ n3;
  (* keep = "true" *) wire n35 = s[18] ^ n0 ^ n3 ^ n4;
  (* keep = "true" *) wire n36 = s[19] ^ n1 ^ n4 ^ n5;
  (* keep = "true" *) wire n37 = s[20] ^ n2 ^ n5 ^ n6;
  (* keep = "true" *) wire n38 = s[21] ^ n3 ^ n6 ^ n7;
  (* keep = "true" *) wire n39 = s[22] ^ n4 ^ n7;
  (* keep = "true" *) wire n40 = s[23] ^ n5;
  assign o[0] = n0;
  assign o[1] = n10;
  assign o[2] = n11;
  assign o[3] = n12;
  assign o[4] = n13;
  assign o[5] = n14;
  assign o[6] = n15;
  assign o[7] = n16;
  assign o[8] = n17;
  assign o[9] = n18;
  assign o[10] = n19;
  assign o[11] = n20;
  assign o[12] = n21;
  assign o[13] = n22;
  assign o[14] = n23;
  assign o[15] = n24;
  assign o[16] = n25;
  assign o[17] = n26;
  assign o[18] = n27;
  assign o[19] = n28;
  assign o[20] = n29;
  assign o[21] = n30;
  assign o[22] = n31;
  assign o[23] = n32;
  assign o[24] = n33;
  assign o[25] = n34;
  assign o[26] = n35;
  assign o[27] = n36;
  assign o[28] = n37;
  assign o[29] = n38;
  assign o[30] = n39;
  assign o[31] = n40;
endmodule
