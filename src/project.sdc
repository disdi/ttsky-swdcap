# Two clocks, asynchronous to each other: the debug clock on clk and SWCLK on uio_in[2].
# SWCLK is constrained at 4 MHz; the probe is meant to start at 1 MHz.
create_clock -name clk   -period 20  [get_ports {clk}]
create_clock -name swclk -period 250 [get_ports {uio_in[2]}]
set_clock_groups -asynchronous -group {clk} -group {swclk}

set_clock_uncertainty 0.25 [all_clocks]
set_clock_transition 0.15 [all_clocks]
set_timing_derate -early 0.95
set_timing_derate -late 1.05

# SWDIO belongs to SWCLK. The host changes it while SWCLK is low and samples it while low.
set_input_delay  -clock swclk 20 [get_ports {uio_in[4]}]
set_output_delay -clock swclk 20 [get_ports {uio_out[4] uio_oe[4]}]

# EIO and the reset belong to the debug clock.
set_input_delay  -clock clk 4 [get_ports {ui_in[*] rst_n ena}]
set_output_delay -clock clk 4 [get_ports {uo_out[*]}]

set_driving_cell -lib_cell sky130_fd_sc_hd__inv_2 -pin Y [all_inputs]
set_load 0.033 [all_outputs]
set_max_fanout 10 [current_design]
