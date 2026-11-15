// Period of cc_lfsr_16bit from its default seed: reset, then count clock steps until the state comes back.
module tb_period;
  logic clk = 0, rst_n = 0;
  wire [15:0] oh; wire [3:0] bin;
  cc_lfsr_16bit #(.Width(16)) u (.clk_i(clk), .rst_ni(rst_n), .clr_i(1'b0), .en_i(1'b1), .refill_way_oh_o(oh), .refill_way_bin_o(bin));
  logic [15:0] s0; int n;
  initial begin
    #1 rst_n = 1; s0 = u.shift_q; n = 0;
    do begin #1 clk = 1; #1 clk = 0; n++; end while (u.shift_q != s0 && n < 70000);
    $display("period from seed %h: %0d (maximal would be 65535)", s0, n);
    $finish;
  end
endmodule
