# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""HD44780 character display behind a PCF8574 I2C backpack.

Written from scratch for this project (2026-09-14). The two files it replaces
(`lcddriver.py` and `i2c_lib.py`) came from an unknown source, carried a
byte-order mark that made them unparsable for every tool we run, and could not
be published under our own licence. The thin `i2c_lib` wrapper is gone: it had
one user, this file.

WHAT IS ACTUALLY ATTACHED

A 20x4 character display with an HD44780-compatible controller. It has no I2C
of its own; a PCF8574 sits in front of it and turns one I2C byte into eight
output pins. Those pins are wired the way every one of these backpacks is
wired, which is why the bit positions below are constants and not settings:

    bit 7..4   D7..D4   the upper data nibble
    bit 3      backlight
    bit 2      E        enable - its falling edge latches the nibble
    bit 1      RW       always 0 here; we never read from the display
    bit 0      RS       0 = instruction, 1 = character data

Only four data lines are wired, so every byte goes out as two nibbles, high
first. That is not a shortcut - the backpack has no more pins.

WHY THIS NEVER RAISES

The display is a convenience for the person standing at the machine. It is not
a safety device and nothing depends on what it shows. So every write is
wrapped: a failure is logged once and the caller carries on. The alternative
is an installation that stops because a ribbon cable is loose, and that is the
wrong way round.
"""

import logging
import time

logger = logging.getLogger('Punisher')

I2C_ADDRESS = 0x27          # default of the PCF8574 backpack; 0x3F on some
I2C_BUS = 1                 # Raspberry Pi: /dev/i2c-1

COLUMNS = 20
ROWS = 4

# --- bits of the backpack --------------------------------------------------
BACKLIGHT = 0x08
NO_BACKLIGHT = 0x00
PIN_E = 0x04
PIN_RW = 0x02
PIN_RS = 0x01

# --- HD44780 instructions --------------------------------------------------
CLEAR_DISPLAY = 0x01
RETURN_HOME = 0x02
ENTRY_MODE_SET = 0x04
DISPLAY_CONTROL = 0x08
FUNCTION_SET = 0x20
SET_DDRAM_ADDR = 0x80

ENTRY_LEFT = 0x02           # advance the cursor, do not shift the display
DISPLAY_ON = 0x04
MODE_4BIT = 0x00
TWO_LINE = 0x08             # "2 line" mode also drives the 4-line variants
DOTS_5x8 = 0x00

# Start address of each line in display RAM.
#
# The order looks wrong and is not: a 20x4 display is a 20x2 controller used
# twice. Line 3 continues line 1 and line 4 continues line 2, so their
# addresses are the first two plus the line width. Writing past the end of
# line 1 therefore lands in line 3 - which is why every string is cut to
# COLUMNS below instead of being allowed to run over.
LINE_ADDR = (0x00, 0x40, 0x00 + COLUMNS, 0x40 + COLUMNS)


class lcd:
    """The display. The class name stays lowercase: punisher.py calls it."""

    def __init__(self, address=I2C_ADDRESS, bus=I2C_BUS, backlight=True):
        self.address = address
        self.backlight = BACKLIGHT if backlight else NO_BACKLIGHT
        self.ok = False
        self._complained = False
        self._bus = None
        try:
            self._bus = _open_bus(bus)
        except Exception as e:                      # noqa: BLE001
            logger.warning('LCD: I2C bus %s not available (%s) - display off', bus, e)
            return
        self.ok = True
        self._reset()

    # ------------------------------------------------------------------ #
    def _write(self, value):
        """One byte to the backpack. Never raises."""
        if self._bus is None:
            return False
        try:
            self._bus.write_byte(self.address, value | self.backlight)
            return True
        except Exception as e:                      # noqa: BLE001
            # Once, not on every character: a loose cable would otherwise fill
            # the log faster than anything else in the installation.
            if not self._complained:
                self._complained = True
                logger.warning('LCD at 0x%02x does not answer (%s) - display off',
                               self.address, e)
            self.ok = False
            return False

    def _strobe(self, value):
        """Latch a nibble: E high, hold, E low.

        The datasheet asks for 450 ns of enable width and about 37 us to digest
        an instruction. The sleeps here are far longer than that. They are not
        tuned: the display is written a handful of times per second, so there
        is nothing to win by being tight - and a value that is too short fails
        only sometimes, which is the worst kind of failure to chase.
        """
        self._write(value | PIN_E)
        time.sleep(0.0005)
        self._write(value & ~PIN_E)
        time.sleep(0.0002)

    def _send(self, value, mode=0):
        """One byte as two nibbles, high first. mode=PIN_RS for character data."""
        self._strobe(mode | (value & 0xF0))
        self._strobe(mode | ((value << 4) & 0xF0))

    def _reset(self):
        """Bring the controller into 4-bit mode from an unknown state.

        This sequence looks superstitious and is not. After a warm restart of
        the Pi the controller may be in 8-bit mode, in 4-bit mode, or halfway
        through a byte. The three 0x30 nibbles are understood in BOTH modes and
        leave it in 8-bit mode for certain; only then does 0x20 switch it to
        four bits. Without this, a display that was already running comes back
        showing garbage - and only after a restart, which makes it look like a
        hardware fault.
        """
        time.sleep(0.05)                       # the controller needs ~40 ms after power-up
        for _ in range(3):
            self._strobe(0x30)
            time.sleep(0.005)
        self._strobe(0x20)                     # now in 4-bit mode
        self._send(FUNCTION_SET | MODE_4BIT | TWO_LINE | DOTS_5x8)
        self._send(DISPLAY_CONTROL | DISPLAY_ON)
        self._send(ENTRY_MODE_SET | ENTRY_LEFT)
        self._send(CLEAR_DISPLAY)
        time.sleep(0.002)                      # clear is slow (~1.5 ms)

    # --- what the rest of the installation calls ----------------------- #
    def lcd_clear(self):
        self._send(CLEAR_DISPLAY)
        time.sleep(0.002)
        self._send(RETURN_HOME)
        time.sleep(0.002)

    def lcd_display_string(self, text, line=1):
        """Write one line. `line` counts from 1, as the callers expect.

        The text is cut and padded to the display width. Cutting because a
        string that runs over does not wrap where a reader expects it (see
        LINE_ADDR); padding because otherwise the tail of the previous, longer
        text stays on the display and reads as part of the new one - a name
        that half belongs to somebody else.
        """
        try:
            n = int(line)
        except (TypeError, ValueError):
            return
        if not 1 <= n <= ROWS:
            return
        s = str(text)[:COLUMNS].ljust(COLUMNS)
        self._send(SET_DDRAM_ADDR | LINE_ADDR[n - 1])
        for ch in s:
            # The character ROM is not Unicode. Anything outside plain ASCII
            # becomes a space rather than a random glyph from the ROM.
            code = ord(ch)
            self._send(code if 32 <= code < 128 else 32, PIN_RS)

    def lcd_backlight(self, on=True):
        self.backlight = BACKLIGHT if on else NO_BACKLIGHT
        self._write(0)


def _open_bus(bus):
    """smbus2 if it is there, otherwise smbus.

    Two names for the same thing: Raspberry Pi OS ships `smbus` as a system
    package, while pip installs `smbus2`. Asking for one and finding only the
    other is the most common reason a fresh image comes up without a display.
    """
    try:
        import smbus2
        return smbus2.SMBus(bus)
    except ImportError:
        import smbus
        return smbus.SMBus(bus)
