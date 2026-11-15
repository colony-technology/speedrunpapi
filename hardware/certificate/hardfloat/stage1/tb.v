// Wrapper: HardFloat roundRawFNToRecFN#(W, P), options 0, ports brought out unchanged.
module tb #(parameter W = 3, parameter P = 3) (
    input control, input invalidExc, input infiniteExc,
    input in_isNaN, input in_isInf, input in_isZero, input in_sign,
    input signed [W+1:0] in_sExp, input [P+2:0] in_sig, input [2:0] roundingMode,
    output [W+P:0] out, output [4:0] exceptionFlags);
  roundRawFNToRecFN #(W, P) dut(control, invalidExc, infiniteExc, in_isNaN, in_isInf, in_isZero,
      in_sign, in_sExp, in_sig, roundingMode, out, exceptionFlags);
endmodule
