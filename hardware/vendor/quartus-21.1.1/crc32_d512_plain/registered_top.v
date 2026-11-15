module registered_top(input clk, input [31:0] s, input [511:0] d, output reg [31:0] o);
reg [31:0] si; reg [511:0] di; wire [31:0] co;
always @(posedge clk) begin si<=s; di<=d; o<=co; end
crc32_d512_plain u_core(.s(si),.d(di),.o(co));
endmodule
