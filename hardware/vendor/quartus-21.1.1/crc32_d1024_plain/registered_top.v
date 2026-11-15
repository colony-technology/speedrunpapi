module registered_top(input clk, input [31:0] s, input [1023:0] d, output reg [31:0] o);
reg [31:0] si; reg [1023:0] di; wire [31:0] co;
always @(posedge clk) begin si<=s; di<=d; o<=co; end
crc32_d1024_plain u_core(.s(si),.d(di),.o(co));
endmodule
