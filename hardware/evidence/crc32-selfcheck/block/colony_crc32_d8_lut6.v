// CRC-32, polynomial 0x04C11DB7 (IEEE 802.3 frame check sequence), register update.
// Recurrence, applied to d[0] first:  fb = s[31] ^ d[t];  s = (s << 1) ^ (fb ? 32'h04C11DB7 : 0).
// s[i] holds the coefficient of x^i.  Initial value and final complement are outside this block.
// 8 data bits per call, d[0] first.  o = register after d[0] .. d[7] from s.  41 LUT-6, 2 levels.
module colony_crc32_d8_lut6 (
    input  wire [31:0] s,
    input  wire [7:0] d,
    output wire [31:0] o
);
  wire n0; LUT4 #(.INIT(16'h6996)) u0 (.O(n0), .I0(s[24]), .I1(s[30]), .I2(d[1]), .I3(d[7]));
  wire n1; LUT4 #(.INIT(16'h6996)) u1 (.O(n1), .I0(s[25]), .I1(s[31]), .I2(d[0]), .I3(d[6]));
  wire n2; LUT2 #(.INIT(4'h6)) u2 (.O(n2), .I0(s[26]), .I1(d[5]));
  wire n3; LUT2 #(.INIT(4'h6)) u3 (.O(n3), .I0(s[27]), .I1(d[4]));
  wire n4; LUT2 #(.INIT(4'h6)) u4 (.O(n4), .I0(s[28]), .I1(d[3]));
  wire n5; LUT2 #(.INIT(4'h6)) u5 (.O(n5), .I0(s[29]), .I1(d[2]));
  wire n6; LUT2 #(.INIT(4'h6)) u6 (.O(n6), .I0(s[30]), .I1(d[1]));
  wire n7; LUT2 #(.INIT(4'h6)) u7 (.O(n7), .I0(s[31]), .I1(d[0]));
  wire n8; LUT2 #(.INIT(4'h6)) u8 (.O(n8), .I0(s[24]), .I1(d[7]));
  wire n9; LUT2 #(.INIT(4'h6)) u9 (.O(n9), .I0(s[25]), .I1(d[6]));
  wire n10; LUT2 #(.INIT(4'h6)) u10 (.O(n10), .I0(n0), .I1(n1));
  wire n11; LUT3 #(.INIT(8'h96)) u11 (.O(n11), .I0(n0), .I1(n1), .I2(n2));
  wire n12; LUT3 #(.INIT(8'h96)) u12 (.O(n12), .I0(n1), .I1(n2), .I2(n3));
  wire n13; LUT4 #(.INIT(16'h6996)) u13 (.O(n13), .I0(n0), .I1(n2), .I2(n3), .I3(n4));
  wire n14; LUT5 #(.INIT(32'h96696996)) u14 (.O(n14), .I0(n0), .I1(n1), .I2(n3), .I3(n4), .I4(n5));
  wire n15; LUT5 #(.INIT(32'h96696996)) u15 (.O(n15), .I0(n1), .I1(n2), .I2(n4), .I3(n5), .I4(n6));
  wire n16; LUT5 #(.INIT(32'h96696996)) u16 (.O(n16), .I0(n2), .I1(n3), .I2(n5), .I3(n7), .I4(n8));
  wire n17; LUT5 #(.INIT(32'h96696996)) u17 (.O(n17), .I0(s[0]), .I1(n3), .I2(n4), .I3(n8), .I4(n9));
  wire n18; LUT5 #(.INIT(32'h96696996)) u18 (.O(n18), .I0(s[1]), .I1(n2), .I2(n4), .I3(n5), .I4(n9));
  wire n19; LUT5 #(.INIT(32'h96696996)) u19 (.O(n19), .I0(s[2]), .I1(n2), .I2(n3), .I3(n5), .I4(n8));
  wire n20; LUT5 #(.INIT(32'h96696996)) u20 (.O(n20), .I0(s[3]), .I1(n3), .I2(n4), .I3(n8), .I4(n9));
  wire n21; LUT6 #(.INIT(64'h6996966996696996)) u21 (.O(n21), .I0(s[4]), .I1(n0), .I2(n2), .I3(n4), .I4(n5), .I5(n9));
  wire n22; LUT6 #(.INIT(64'h6996966996696996)) u22 (.O(n22), .I0(s[5]), .I1(n1), .I2(n2), .I3(n3), .I4(n5), .I5(n6));
  wire n23; LUT6 #(.INIT(64'h6996966996696996)) u23 (.O(n23), .I0(s[6]), .I1(n2), .I2(n3), .I3(n4), .I4(n6), .I5(n7));
  wire n24; LUT5 #(.INIT(32'h96696996)) u24 (.O(n24), .I0(s[7]), .I1(n3), .I2(n4), .I3(n5), .I4(n7));
  wire n25; LUT4 #(.INIT(16'h6996)) u25 (.O(n25), .I0(s[8]), .I1(n4), .I2(n5), .I3(n8));
  wire n26; LUT4 #(.INIT(16'h6996)) u26 (.O(n26), .I0(s[9]), .I1(n5), .I2(n6), .I3(n9));
  wire n27; LUT4 #(.INIT(16'h6996)) u27 (.O(n27), .I0(s[10]), .I1(n2), .I2(n6), .I3(n7));
  wire n28; LUT3 #(.INIT(8'h96)) u28 (.O(n28), .I0(s[11]), .I1(n3), .I2(n7));
  wire n29; LUT2 #(.INIT(4'h6)) u29 (.O(n29), .I0(s[12]), .I1(n4));
  wire n30; LUT2 #(.INIT(4'h6)) u30 (.O(n30), .I0(s[13]), .I1(n5));
  wire n31; LUT2 #(.INIT(4'h6)) u31 (.O(n31), .I0(s[14]), .I1(n8));
  wire n32; LUT3 #(.INIT(8'h96)) u32 (.O(n32), .I0(s[15]), .I1(n0), .I2(n9));
  wire n33; LUT3 #(.INIT(8'h96)) u33 (.O(n33), .I0(s[16]), .I1(n1), .I2(n2));
  wire n34; LUT3 #(.INIT(8'h96)) u34 (.O(n34), .I0(s[17]), .I1(n2), .I2(n3));
  wire n35; LUT4 #(.INIT(16'h6996)) u35 (.O(n35), .I0(s[18]), .I1(n0), .I2(n3), .I3(n4));
  wire n36; LUT4 #(.INIT(16'h6996)) u36 (.O(n36), .I0(s[19]), .I1(n1), .I2(n4), .I3(n5));
  wire n37; LUT4 #(.INIT(16'h6996)) u37 (.O(n37), .I0(s[20]), .I1(n2), .I2(n5), .I3(n6));
  wire n38; LUT4 #(.INIT(16'h6996)) u38 (.O(n38), .I0(s[21]), .I1(n3), .I2(n6), .I3(n7));
  wire n39; LUT3 #(.INIT(8'h96)) u39 (.O(n39), .I0(s[22]), .I1(n4), .I2(n7));
  wire n40; LUT2 #(.INIT(4'h6)) u40 (.O(n40), .I0(s[23]), .I1(n5));
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
