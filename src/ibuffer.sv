`default_nettype none
`timescale 1ns/1ns

// INSTRUCTION BUFFER
// > Direct-mapped cache for program memory instructions
// > Reduces fetch latency by caching recently fetched instructions
// > On a hit, the fetcher skips the memory round-trip entirely
module ibuffer #(
    parameter ADDR_BITS = 8,
    parameter DATA_BITS = 16,
    parameter NUM_ENTRIES = 16
) (
    input wire clk,
    input wire reset,

    // Lookup (combinational)
    input wire                    lookup_valid,
    input wire [ADDR_BITS-1:0]    lookup_address,
    output wire                   hit,
    output wire [DATA_BITS-1:0]   hit_data,

    // Fill (synchronous write on miss resolution)
    input wire                    fill_valid,
    input wire [ADDR_BITS-1:0]    fill_address,
    input wire [DATA_BITS-1:0]    fill_data
);
    localparam INDEX_BITS = $clog2(NUM_ENTRIES);
    localparam TAG_BITS = ADDR_BITS - INDEX_BITS;

    reg                    valid [NUM_ENTRIES-1:0];
    reg [TAG_BITS-1:0]     tag   [NUM_ENTRIES-1:0];
    reg [DATA_BITS-1:0]    data  [NUM_ENTRIES-1:0];

    wire [INDEX_BITS-1:0] lookup_index = lookup_address[INDEX_BITS-1:0];
    wire [TAG_BITS-1:0]   lookup_tag   = lookup_address[ADDR_BITS-1:INDEX_BITS];

    wire [INDEX_BITS-1:0] fill_index = fill_address[INDEX_BITS-1:0];
    wire [TAG_BITS-1:0]   fill_tag   = fill_address[ADDR_BITS-1:INDEX_BITS];

    // Combinational lookup
    assign hit = lookup_valid && valid[lookup_index] && (tag[lookup_index] == lookup_tag);
    assign hit_data = data[lookup_index];

    // Synchronous fill
    always @(posedge clk) begin
        if (reset) begin
            for (int i = 0; i < NUM_ENTRIES; i = i + 1) begin
                valid[i] <= 0;
            end
        end else if (fill_valid) begin
            valid[fill_index] <= 1;
            tag[fill_index] <= fill_tag;
            data[fill_index] <= fill_data;
        end
    end
endmodule
