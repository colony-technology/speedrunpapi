module registered_top(input clk, input [31:0] s, input [511:0] d, input [5:0] e, output reg [31:0] o);
reg [31:0] si; reg [511:0] di; reg [5:0] ei; wire [31:0] co;
always @(posedge clk) begin si<=s; di<=d; ei<=e; o<=co; end
crc32_b64_colony_plain u_core(.s(si),.d(di),.e(ei),.o(co));
endmodule
