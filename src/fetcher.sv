`default_nettype none
`timescale 1ns/1ns

// INSTRUCTION FETCHER
// > Retrieves the instruction at the current PC from global data memory
// > Each core has it's own fetcher
module fetcher #(
    parameter PROGRAM_MEM_ADDR_BITS = 8,
    parameter PROGRAM_MEM_DATA_BITS = 16
) (
    input wire clk,
    input wire reset,
    
    // Execution State
    input reg [2:0] core_state,
    input reg [7:0] current_pc,

    // Program Memory
    output reg mem_read_valid,
    output reg [PROGRAM_MEM_ADDR_BITS-1:0] mem_read_address,
    input reg mem_read_ready,
    input reg [PROGRAM_MEM_DATA_BITS-1:0] mem_read_data,

    // Instruction Buffer
    input wire ibuf_hit,
    input wire [PROGRAM_MEM_DATA_BITS-1:0] ibuf_hit_data,
    output reg ibuf_fill_valid,
    output reg [PROGRAM_MEM_ADDR_BITS-1:0] ibuf_fill_address,
    output reg [PROGRAM_MEM_DATA_BITS-1:0] ibuf_fill_data,

    // Fetcher Output
    output reg [2:0] fetcher_state,
    output reg [PROGRAM_MEM_DATA_BITS-1:0] instruction,
);
    localparam IDLE = 3'b000, 
        FETCHING = 3'b001, 
        FETCHED = 3'b010;
    
    always @(posedge clk) begin
        if (reset) begin
            fetcher_state <= IDLE;
            mem_read_valid <= 0;
            mem_read_address <= 0;
            instruction <= {PROGRAM_MEM_DATA_BITS{1'b0}};
            ibuf_fill_valid <= 0;
            ibuf_fill_address <= 0;
            ibuf_fill_data <= 0;
        end else begin
            // Default: deassert fill pulse
            ibuf_fill_valid <= 0;

            case (fetcher_state)
                IDLE: begin
                    // Start fetching when core_state = FETCH
                    if (core_state == 3'b001) begin
                        if (ibuf_hit) begin
                            // Cache hit: skip memory round-trip
                            fetcher_state <= FETCHED;
                            instruction <= ibuf_hit_data;
                        end else begin
                            // Cache miss: request from program memory
                            fetcher_state <= FETCHING;
                            mem_read_valid <= 1;
                            mem_read_address <= current_pc;
                        end
                    end
                end
                FETCHING: begin
                    // Wait for response from program memory
                    if (mem_read_ready) begin
                        fetcher_state <= FETCHED;
                        instruction <= mem_read_data;
                        mem_read_valid <= 0;
                        // Fill instruction buffer for future lookups
                        ibuf_fill_valid <= 1;
                        ibuf_fill_address <= current_pc;
                        ibuf_fill_data <= mem_read_data;
                    end
                end
                FETCHED: begin
                    // Reset when core_state = DECODE
                    if (core_state == 3'b010) begin 
                        fetcher_state <= IDLE;
                    end
                end
            endcase
        end
    end
endmodule
