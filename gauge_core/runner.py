"""Standalone single-instrument runner.

Opens an Arcade window sized to the instrument, draws every frame, and
either reads values from X-Plane via pyxpudpserver or — in test mode —
from numpad keystrokes.
"""

from __future__ import annotations

import argparse
import socket
import sys
from typing import Callable

import arcade

from gauge_core.loader import Instrument, load_instrument


class InstrumentWindow(arcade.Window):
    def __init__(
        self,
        instrument: Instrument,
        get_data: Callable[[object], float],
    ) -> None:
        w, h = instrument.size
        super().__init__(w, h, instrument.name)
        self.background_color = arcade.color.BLACK

        self.instrument = instrument
        self._get_data = get_data

        # Test-mode value (only consulted by TestDataSource; harmless otherwise).
        self.test_value = 0.0
        self.test_increment = 1.0

    def on_draw(self) -> None:
        self.clear()
        for comp in self.instrument.components:
            comp.update(self._get_data)
        for comp in self.instrument.components:
            comp.draw()

    def on_key_press(self, key: int, modifiers: int) -> None:
        if key == arcade.key.ESCAPE:
            self.close()
        elif key == arcade.key.NUM_ADD:
            self.test_value += self.test_increment
        elif key == arcade.key.NUM_SUBTRACT:
            self.test_value -= self.test_increment
        elif key == arcade.key.NUM_MULTIPLY:
            self.test_increment = 0.1 if self.test_increment == 1.0 else 1.0
        elif key == arcade.key.UP:
            self.test_value += 10.0
        elif key == arcade.key.DOWN:
            self.test_value -= 10.0
        elif key == arcade.key.PAGEUP:
            self.test_value += 100.0
        elif key == arcade.key.PAGEDOWN:
            self.test_value -= 100.0


class TestDataSource:
    """Returns the window's test_value for any dataref. Used with --test."""

    def __init__(self) -> None:
        self.window: InstrumentWindow | None = None

    def __call__(self, _dataref: object) -> float:
        if self.window is None:
            return 0.0
        return self.window.test_value


class UDPDataSource:
    def __init__(
        self,
        listen: tuple[str, int],
        xp: tuple[str, int],
        xp_name: str,
    ) -> None:
        import pyxpudpserver as xpudp

        self._server = xpudp.pyXPUDPServer
        self._server.initialiseUDP(listen, xp, xp_name)
        self._server.start()

    def __call__(self, dataref: object) -> float:
        return float(self._server.getData(dataref))


def _parse_addr(s: str) -> tuple[str, int]:
    host, port = s.rsplit(":", 1)
    return host, int(port)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Run a single instrument YAML in an Arcade window."
    )
    p.add_argument("instrument", help="Path to an instrument YAML file")
    p.add_argument(
        "--test",
        action="store_true",
        help="Test mode: numpad +/-/*, arrows, and PgUp/PgDn drive the value. No UDP.",
    )
    p.add_argument(
        "--listen",
        default="127.0.0.1:49008",
        help="host:port this app listens on for X-Plane UDP (default 127.0.0.1:49008)",
    )
    p.add_argument(
        "--xp",
        default="127.0.0.1:49000",
        help="host:port of X-Plane (default 127.0.0.1:49000)",
    )
    p.add_argument(
        "--xp-name",
        default=socket.gethostname(),
        help="Computer name X-Plane expects (defaults to local hostname)",
    )
    args = p.parse_args(argv)

    instrument = load_instrument(args.instrument)

    if args.test:
        data_source = TestDataSource()
        window = InstrumentWindow(instrument, data_source)
        data_source.window = window
    else:
        data_source = UDPDataSource(
            listen=_parse_addr(args.listen),
            xp=_parse_addr(args.xp),
            xp_name=args.xp_name,
        )
        window = InstrumentWindow(instrument, data_source)

    arcade.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
