/*
 * Copyright (c) 2026 Saket Sinha
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

// swdcap on Tiny Tapeout: an SWD debug port (SW-DP and the SpinalHDL SWD DMI gateway) with an
// ID window and 8 + 8 bits of EIO behind it.
//
//   SWCLK    uio[2]   bidirectional Pmod pin 3, driven by the probe
//   SWDIO    uio[4]   bidirectional Pmod pin 7, needs an external pull-up
//   EIO in   ui_in    read by the host at DMI 0x0200
//   EIO out  uo_out   written by the host at DMI 0x0201
//
// clk is the debug clock and must be running. rst_n resets both the debug clock domain and,
// asynchronously, the SWCLK domain.
module tt_um_disdi_swdcap (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, so you can ignore it
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

  wire swdio_o;
  wire swdio_oe;

  SwdcapTop swdcap (
      .swclk   (uio_in[2]),
      .swdio_i (uio_in[4]),
      .swdio_o (swdio_o),
      .swdio_oe(swdio_oe),
      .eio_in  (ui_in),
      .eio_out (uo_out),
      .reset   (!rst_n),
      .clk     (clk)
  );

  // Only uio[4] is ever driven, and only while the target owns SWDIO.
  assign uio_out = {3'b000, swdio_o, 4'b0000};
  assign uio_oe  = {3'b000, swdio_oe, 4'b0000};

  // List all unused inputs to prevent warnings
  wire _unused = &{ena, uio_in[7:5], uio_in[3], uio_in[1:0], 1'b0};

endmodule
