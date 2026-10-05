<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

swdcap is an SWD **target**. A CMSIS-DAP probe and stock OpenOCD reach registers inside the chip
over two wires, SWCLK and SWDIO, with no JTAG TAP.

The SWD side is the SpinalHDL SWD DMI gateway, unchanged: an ADIv5 SW-DP (`DPIDR 0x0BA11AAB`) and
one access port (`AP_IDR 0x74726976`) with four registers. A host writes a word address to
`DMI_ADDR` and then reads or writes `DMI_DATA`; each access is carried from the SWCLK domain to
the `clk` domain and back, and the DP answers WAIT until it has completed.

| AP offset | Register | Use |
|---|---|---|
| `0x00` | AP_IDR | reads `0x74726976` |
| `0x04` | DMI_ADDR | 10-bit word address |
| `0x08` | DMI_DATA | a read or a write does one access at DMI_ADDR |
| `0x0C` | POSTED_READ | result of the last read |

Behind the gateway:

| DMI word | Register | |
|---|---|---|
| `0x000`–`0x07F` | reserved for a RISC-V Debug Module | reads 0 |
| `0x100` | MAGIC | `0x43445753` (`"SWDC"`) |
| `0x101` | VERSION | `0x00000100` (0.1.0) |
| `0x102` | FEATURES | `0x1`: EIO |
| `0x104` | EIO_WIDTH | `0x0808`: 8 outputs, 8 inputs |
| `0x107` | SCRATCH | read/write, 32 bits |
| `0x200` | EIO_IN | reads `ui_in[7:0]` |
| `0x201` | EIO_OUT | drives `uo_out[7:0]` |

Any other address returns an error, which sets STICKYERR in the DP; the host clears it with an
ABORT write.

`rst_n` resets both clock domains. The SWCLK domain is reset asynchronously, because the two-wire
interface has no reset of its own and the flip-flops power up undefined.

The RTL is generated from <https://github.com/disdi/swdcap>, where the register contract and the
FPGA version of the same design are documented.

## How to test

1. Select the project and start `clk`. With `clk` stopped the DP and the AP still answer, but
   every DMI access returns WAIT.
2. Pulse `rst_n` low and release it.
3. Leave `uio[2]` and `uio[4]` undriven on the demo board's RP2040, and connect the probe.
4. Run OpenOCD at 1 MHz with `openocd/swdcap.cfg` from the swdcap repository:

   ```
   openocd -f interface/cmsis-dap.cfg -c "transport select swd" -c "adapter speed 1000" \
           -f openocd/swdcap.cfg -c init -c swdcap_probe -c shutdown
   ```

   It must report `AP_IDR 0x74726976` and magic `0x43445753`.
5. `swdcap_eio_write <value>` sets `uo_out`, and `swdcap_eio_read` returns `ui_in`.

A debugger that expects a CPU finds the gateway but no Debug Module (`dmstatus` reads 0) and
stops there. `dap info` does not apply: the access port is not a MEM-AP.

## External hardware

- A CMSIS-DAP probe (for example an NXP MCU-Link or a Raspberry Pi Debug Probe) on the
  bidirectional Pmod header: SWCLK on `uio[2]`, SWDIO on `uio[4]`, ground, and the board's 3.3 V
  to the probe's VTREF if the probe has that pin.
- A pull-up of 10 kΩ to 100 kΩ from SWDIO (`uio[4]`) to 3.3 V. The pin has none of its own.
