# SPDX-FileCopyrightText: © 2026 Saket Sinha
# SPDX-License-Identifier: Apache-2.0

"""
swdcap driven over the SWD wire protocol by a small host model, the way a CMSIS-DAP probe does it.

The host bit-bangs SWCLK on uio_in[2] and SWDIO on uio[4]. It sets SWDIO while SWCLK is low and
samples the target's data while low; the target acts on rising edges. The debug clock free-runs on
clk, so every DMI access crosses the gateway's clock-domain crossing and the host retries on WAIT.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Timer

SWCLK_BIT = 2
SWDIO_BIT = 4

ACK_OK = 1
ACK_WAIT = 2
ACK_FAULT = 4

# DP registers (A[3:2])
DP_DPIDR_ABORT = 0
DP_CTRL_STAT = 1
DP_RDBUFF = 3

# Gateway AP registers (A[3:2])
AP_IDR = 0
AP_DMI_ADDR = 1
AP_DMI_DATA = 2

DPIDR_VALUE = 0x0BA11AAB
AP_IDR_VALUE = 0x74726976

# DMI word addresses
ID_MAGIC = 0x0100
ID_VERSION = 0x0101
ID_FEATURES = 0x0102
ID_EIO_WIDTH = 0x0104
ID_SCRATCH = 0x0107
EIO_IN = 0x0200
EIO_OUT = 0x0201
ELA_CTRL = 0x0300  # not generated: every access must return an error

MAGIC = 0x43445753  # "SWDC"
VERSION = 0x00000100  # 0.1.0
FEATURES = 0x1  # EIO only
EIO_WIDTH = 0x0808  # 8 out, 8 in
DMI_ADDR_BITS = 10


class SwdHost:
    def __init__(self, dut, swclk_period_ns=1000):
        self.dut = dut
        self.quarter = swclk_period_ns // 4
        self.uio_in = 0

    def _set(self, bit, value):
        if value:
            self.uio_in |= 1 << bit
        else:
            self.uio_in &= ~(1 << bit)
        self.dut.uio_in.value = self.uio_in

    async def step(self, bit):
        """One SWCLK cycle. Returns (target data, target output enable) as sampled while low."""
        self._set(SWCLK_BIT, 0)
        await Timer(self.quarter, unit="ns")
        self._set(SWDIO_BIT, bit)
        await Timer(self.quarter, unit="ns")
        out = (int(self.dut.uio_out.value) >> SWDIO_BIT) & 1
        oe = (int(self.dut.uio_oe.value) >> SWDIO_BIT) & 1
        self._set(SWCLK_BIT, 1)
        await Timer(2 * self.quarter, unit="ns")
        return out, oe

    async def idle(self, n):
        for _ in range(n):
            await self.step(0)

    async def line_reset(self):
        for _ in range(52):
            await self.step(1)
        await self.idle(2)

    async def _header(self, ap, read, addr):
        a2 = addr & 1
        a3 = (addr >> 1) & 1
        parity = ap ^ read ^ a2 ^ a3
        for bit in (1, ap, read, a2, a3, parity, 0, 1):
            _, oe = await self.step(bit)
            assert not oe, "the target must not drive during the packet request"
        await self.step(0)  # turnaround, host to target

    async def _ack(self):
        ack = 0
        for i in range(3):
            bit, oe = await self.step(0)
            assert oe, "the target must drive all three ACK bits"
            ack |= bit << i
        return ack

    async def transact_read(self, ap, addr):
        await self._header(ap, 1, addr)
        ack = await self._ack()
        if ack != ACK_OK:
            _, oe = await self.step(0)
            assert not oe, "the data phase must be skipped on WAIT or FAULT"
            return ack, None
        data = 0
        parity = 0
        for i in range(32):
            bit, oe = await self.step(0)
            assert oe, "the target must drive the read data"
            data |= bit << i
            parity ^= bit
        bit, oe = await self.step(0)
        assert oe and bit == parity, "read data parity"
        _, oe = await self.step(0)  # turnaround, target to host
        assert not oe, "the target must release SWDIO after the read data"
        return ack, data

    async def transact_write(self, ap, addr, data):
        await self._header(ap, 0, addr)
        ack = await self._ack()
        _, oe = await self.step(0)  # turnaround, target to host
        assert not oe, "the target must release SWDIO after the ACK"
        if ack != ACK_OK:
            return ack
        parity = 0
        for i in range(32):
            bit = (data >> i) & 1
            parity ^= bit
            await self.step(bit)
        await self.step(parity)
        return ack

    # DP and AP accesses, retried on WAIT

    async def dp_read(self, addr):
        ack, data = await self.transact_read(0, addr)
        assert ack == ACK_OK, f"DP read {addr}: ack {ack}"
        return data

    async def sticky_err(self):
        return bool((await self.dp_read(DP_CTRL_STAT)) & (1 << 5))

    async def abort_sticky_err(self):
        assert await self.transact_write(0, DP_DPIDR_ABORT, 1 << 2) == ACK_OK, "ABORT write refused"

    async def rdbuff(self, tries=400):
        """Wait for the outstanding access. Returns its data, or None when it ended in an error."""
        for _ in range(tries):
            ack, data = await self.transact_read(0, DP_RDBUFF)
            if ack == ACK_OK:
                return data
            if ack == ACK_FAULT:
                return None
            assert ack == ACK_WAIT, f"RDBUFF: ack {ack}"
            await self.idle(2)
        raise AssertionError("RDBUFF never completed")

    async def ap_write(self, addr, data, tries=400):
        for _ in range(tries):
            ack = await self.transact_write(1, addr, data)
            if ack != ACK_WAIT:
                return ack
            await self.idle(2)
        raise AssertionError(f"AP write {addr} never accepted")

    async def ap_read(self, addr, tries=400):
        for _ in range(tries):
            ack, _ = await self.transact_read(1, addr)
            if ack != ACK_WAIT:
                break
            await self.idle(2)
        else:
            raise AssertionError(f"AP read {addr} never accepted")
        assert ack == ACK_OK, f"AP read {addr}: ack {ack}"
        return await self.rdbuff()

    # DMI accesses through the gateway

    async def dmi_read(self, address):
        """Returns the data, or None when the access returned an error (STICKYERR is then set)."""
        assert await self.ap_write(AP_DMI_ADDR, address) == ACK_OK, "DMI_ADDR write refused"
        return await self.ap_read(AP_DMI_DATA)

    async def dmi_write(self, address, data):
        """Returns True when the write completed without an error."""
        assert await self.ap_write(AP_DMI_ADDR, address) == ACK_OK, "DMI_ADDR write refused"
        assert await self.ap_write(AP_DMI_DATA, data) == ACK_OK, "DMI_DATA write refused"
        return await self.rdbuff() is not None

    async def read(self, address):
        data = await self.dmi_read(address)
        assert data is not None, f"DMI read of {address:#06x} returned an error"
        return data


async def pulse_reset(dut):
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)


async def start(dut):
    """Power-up order of the demo board: clock running, reset pulsed, then the probe connects."""
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())  # 50 MHz debug clock
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    await pulse_reset(dut)
    host = SwdHost(dut)  # 1 MHz SWCLK
    await host.line_reset()
    return host


@cocotb.test()
async def test_identify(dut):
    """A host finds the DP, the gateway AP and the swdcap ID window."""
    host = await start(dut)
    assert await host.dp_read(DP_DPIDR_ABORT) == DPIDR_VALUE, "DPIDR"
    assert await host.ap_read(AP_IDR) == AP_IDR_VALUE, "AP_IDR"
    assert await host.read(ID_MAGIC) == MAGIC, "MAGIC"
    assert await host.read(ID_VERSION) == VERSION, "VERSION"
    assert await host.read(ID_FEATURES) == FEATURES, "FEATURES"
    assert await host.read(ID_EIO_WIDTH) == EIO_WIDTH, "EIO_WIDTH"

    # DMI_ADDR stores exactly the implemented address bits.
    assert await host.ap_write(AP_DMI_ADDR, 0xFFFFFFFF) == ACK_OK
    assert await host.ap_read(AP_DMI_ADDR) == (1 << DMI_ADDR_BITS) - 1, "DMI_ADDR width"

    # The range kept for a RISC-V Debug Module reads 0, so dmstatus.version says "no DM".
    assert await host.read(0x11) == 0, "dmstatus"


@cocotb.test()
async def test_scratch(dut):
    """SCRATCH resets to 0 and holds what the host writes."""
    host = await start(dut)
    assert await host.read(ID_SCRATCH) == 0, "SCRATCH after reset"
    for value in (0xA5A5A5A5, 0x5A5A5A5A, 0xFFFFFFFF, 0):
        assert await host.dmi_write(ID_SCRATCH, value), "SCRATCH write"
        assert await host.read(ID_SCRATCH) == value, "SCRATCH read-back"


@cocotb.test()
async def test_eio(dut):
    """EIO_OUT drives uo_out and EIO_IN reads ui_in."""
    host = await start(dut)
    assert int(dut.uo_out.value) == 0, "uo_out after reset"
    for value in (0x01, 0x80, 0xA5, 0x5A, 0xFF, 0x00):
        assert await host.dmi_write(EIO_OUT, value), "EIO_OUT write"
        assert int(dut.uo_out.value) == value, "uo_out"
        assert await host.read(EIO_OUT) == value, "EIO_OUT read-back"
    for value in (0x01, 0x80, 0xC3, 0x3C, 0xFF, 0x00):
        dut.ui_in.value = value
        await ClockCycles(dut.clk, 4)  # two-flop synchroniser
        assert await host.read(EIO_IN) == value, "EIO_IN"
    # A write to the read-only EIO_IN is ignored without an error.
    assert await host.dmi_write(EIO_IN, 0xFF)
    assert not await host.sticky_err()


@cocotb.test()
async def test_error_and_abort(dut):
    """A window that is not generated returns an error; ABORT clears it and the link works again."""
    host = await start(dut)
    assert await host.dmi_read(ELA_CTRL) is None, "a read of 0x0300 must return an error"
    assert await host.sticky_err(), "STICKYERR must be set after a DMI error"
    await host.abort_sticky_err()
    assert not await host.sticky_err(), "ABORT must clear STICKYERR"
    assert await host.read(ID_MAGIC) == MAGIC, "the next access after ABORT must work"

    assert not await host.dmi_write(ELA_CTRL, 0x12345678), "a write of 0x0300 must return an error"
    assert await host.sticky_err()
    await host.abort_sticky_err()
    assert await host.read(ID_MAGIC) == MAGIC


@cocotb.test()
async def test_reset_clears_both_domains(dut):
    """rst_n clears the debug-clock registers and, asynchronously, the SWCLK domain."""
    host = await start(dut)
    assert await host.dmi_write(ID_SCRATCH, 0xA5A5A5A5)
    assert await host.dmi_write(EIO_OUT, 0xFF)
    assert await host.dmi_read(ELA_CTRL) is None  # leaves STICKYERR set
    assert await host.ap_write(AP_DMI_ADDR, 0x155) == ACK_FAULT, "AP accesses FAULT while sticky"
    await host.abort_sticky_err()
    assert await host.ap_write(AP_DMI_ADDR, 0x155) == ACK_OK
    assert await host.dmi_read(ELA_CTRL) is None  # STICKYERR again, DMI_ADDR = 0x300

    await pulse_reset(dut)  # SWCLK is stopped, as on the demo board
    assert int(dut.uo_out.value) == 0, "uo_out after the reset"
    await host.line_reset()

    assert not await host.sticky_err(), "the reset must clear STICKYERR without an ABORT"
    # First AP access after the reset: nothing has rewritten DMI_ADDR yet.
    assert await host.ap_read(AP_DMI_ADDR) == 0, "the reset must reach DMI_ADDR in the SWCLK domain"
    assert await host.read(ID_SCRATCH) == 0, "SCRATCH after the reset"
    assert await host.read(EIO_OUT) == 0, "EIO_OUT after the reset"
