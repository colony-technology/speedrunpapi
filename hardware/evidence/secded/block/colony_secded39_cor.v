// colony_secded39_cor: q[j] = r[j] ^ (s == column j); corrected = odd weight of s; uncorrectable = s != 0, even weight.
// Columns of H (OpenTitan prim_secded_39_32, Hsiao): data 19 54 61 34 1a 15 2a 4c 45 38 49 0d 51 31 68 07 1c 0b 25 26 46 0e 70 32 2c 13 23 62 4a 29 16 52; check bits are the unit vectors.
module colony_secded39_cor (input wire [31:0] r, input wire [6:0] s, output wire [31:0] q, output wire corrected, output wire uncorrectable);
  assign q[0] = r[0] ^ (s == 7'h19);
  assign q[1] = r[1] ^ (s == 7'h54);
  assign q[2] = r[2] ^ (s == 7'h61);
  assign q[3] = r[3] ^ (s == 7'h34);
  assign q[4] = r[4] ^ (s == 7'h1a);
  assign q[5] = r[5] ^ (s == 7'h15);
  assign q[6] = r[6] ^ (s == 7'h2a);
  assign q[7] = r[7] ^ (s == 7'h4c);
  assign q[8] = r[8] ^ (s == 7'h45);
  assign q[9] = r[9] ^ (s == 7'h38);
  assign q[10] = r[10] ^ (s == 7'h49);
  assign q[11] = r[11] ^ (s == 7'h0d);
  assign q[12] = r[12] ^ (s == 7'h51);
  assign q[13] = r[13] ^ (s == 7'h31);
  assign q[14] = r[14] ^ (s == 7'h68);
  assign q[15] = r[15] ^ (s == 7'h07);
  assign q[16] = r[16] ^ (s == 7'h1c);
  assign q[17] = r[17] ^ (s == 7'h0b);
  assign q[18] = r[18] ^ (s == 7'h25);
  assign q[19] = r[19] ^ (s == 7'h26);
  assign q[20] = r[20] ^ (s == 7'h46);
  assign q[21] = r[21] ^ (s == 7'h0e);
  assign q[22] = r[22] ^ (s == 7'h70);
  assign q[23] = r[23] ^ (s == 7'h32);
  assign q[24] = r[24] ^ (s == 7'h2c);
  assign q[25] = r[25] ^ (s == 7'h13);
  assign q[26] = r[26] ^ (s == 7'h23);
  assign q[27] = r[27] ^ (s == 7'h62);
  assign q[28] = r[28] ^ (s == 7'h4a);
  assign q[29] = r[29] ^ (s == 7'h29);
  assign q[30] = r[30] ^ (s == 7'h16);
  assign q[31] = r[31] ^ (s == 7'h52);
  assign corrected = ^s;
  assign uncorrectable = (s != 7'h0) & ~(^s);
endmodule
