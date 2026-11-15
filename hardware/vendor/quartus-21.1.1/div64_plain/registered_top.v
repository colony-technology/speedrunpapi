module registered_top(input clk, input [63:0] a, input [63:0] b, output reg [63:0] q, output reg [63:0] r);
reg [63:0] ai,bi; wire [63:0] cq,cr;
always @(posedge clk) begin ai<=a; bi<=b; q<=cq; r<=cr; end
div64_plain u_core(.a(ai),.b(bi),.q(cq),.r(cr));
endmodule
