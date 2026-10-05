![](../../workflows/gds/badge.svg) ![](../../workflows/docs/badge.svg) ![](../../workflows/test/badge.svg) ![](../../workflows/fpga/badge.svg)

# swdcap on Tiny Tapeout

An SWD debug port in 1x2 SKY130 tiles: a CMSIS-DAP probe and stock OpenOCD identify the chip over
SWCLK and SWDIO and read and drive 8 + 8 pins through it.

- [Project documentation](docs/info.md): how it works, the registers, how to test it
- Design and register contract: <https://github.com/disdi/swdcap>

## What is in this repository

| Path | |
|---|---|
| `src/SwdcapTop.v` | Generated netlist, copied from swdcap `gen/silicon/SwdcapTop.v`. Do not edit it; regenerate it there (`sbt "runMain swdcap.SwdcapTopSiliconVerilog"`) and copy it again. Its header records the SpinalHDL and swdcap commits |
| `src/tt_um_disdi_swdcap.v` | Tiny Tapeout wrapper: SWCLK on `uio[2]`, SWDIO on `uio[4]`, EIO on `ui_in` / `uo_out` |
| `src/project.sdc` | Two asynchronous clocks, `clk` and SWCLK. `src/config.json` passes it to LibreLane |
| `test/test.py` | cocotb test with an SWD host model: identify, SCRATCH, EIO, error and ABORT, reset |
| `info.yaml` | Tiny Tapeout project description and pinout |

## Test

```
cd test
pip install -r requirements.txt
make -B
```

The same test runs on the hardened netlist with `make -B GATES=yes`; see [test/README.md](test/README.md).

## Harden locally

Set the flow up as in the Tiny Tapeout [local hardening guide](https://www.tinytapeout.com/guides/local-hardening/), with `tt-support-tools` cloned as `tt/`, then:

```
./tt/tt_tool.py --create-user-config
./tt/tt_tool.py --harden
./tt/tt_tool.py --print-warnings
```

## What is Tiny Tapeout?

Tiny Tapeout is an educational project that aims to make it easier and cheaper than ever to get your digital and analog designs manufactured on a real chip.

To learn more and get started, visit https://tinytapeout.com.
