// Yosys techmap: Xilinx LUT1..LUT6 primitives to Yosys $lut cells.  O = INIT[{I(k-1), .., I0}], the
// convention of the Xilinx primitive (and of +/xilinx/cells_sim.v, which the simulations use).
module LUT1 #(parameter [1:0]  INIT = 0) (output O, input I0);                               \$lut #(.WIDTH(1), .LUT(INIT)) _TECHMAP_REPLACE_ (.A(I0), .Y(O)); endmodule
module LUT2 #(parameter [3:0]  INIT = 0) (output O, input I0, I1);                           \$lut #(.WIDTH(2), .LUT(INIT)) _TECHMAP_REPLACE_ (.A({I1, I0}), .Y(O)); endmodule
module LUT3 #(parameter [7:0]  INIT = 0) (output O, input I0, I1, I2);                       \$lut #(.WIDTH(3), .LUT(INIT)) _TECHMAP_REPLACE_ (.A({I2, I1, I0}), .Y(O)); endmodule
module LUT4 #(parameter [15:0] INIT = 0) (output O, input I0, I1, I2, I3);                   \$lut #(.WIDTH(4), .LUT(INIT)) _TECHMAP_REPLACE_ (.A({I3, I2, I1, I0}), .Y(O)); endmodule
module LUT5 #(parameter [31:0] INIT = 0) (output O, input I0, I1, I2, I3, I4);               \$lut #(.WIDTH(5), .LUT(INIT)) _TECHMAP_REPLACE_ (.A({I4, I3, I2, I1, I0}), .Y(O)); endmodule
module LUT6 #(parameter [63:0] INIT = 0) (output O, input I0, I1, I2, I3, I4, I5);           \$lut #(.WIDTH(6), .LUT(INIT)) _TECHMAP_REPLACE_ (.A({I5, I4, I3, I2, I1, I0}), .Y(O)); endmodule
