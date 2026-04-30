"""Runner — opens an Arcade window and drives a panel (or single instrument).

A YAML file is detected as a panel if its top-level has an `instruments:`
key; otherwise it's treated as a single instrument and wrapped in a
synthetic Panel of one. From that point the runtime is uniform.

Overlays:
- FPS counter, shown in the window title (matches the original engine).
- "Not receiving X-Plane data" text, shown when running in UDP mode and
  pyxpudpserver reports no live X-Plane peer.
"""

from __future__ import annotations

import argparse
import socket
import sys
import time
from pathlib import Path
from typing import Any, Callable

import arcade
import yaml

from gauge_core.loader import load_instrument
from gauge_core.panel import Panel, load_panel, panel_from_instrument


def _is_panel_yaml(path: Path) -> bool:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return isinstance(data, dict) and "instruments" in data


def load_panel_or_instrument(path: str | Path) -> Panel:
    p = Path(path).resolve()
    if _is_panel_yaml(p):
        return load_panel(p)
    return panel_from_instrument(load_instrument(p))


class PanelWindow(arcade.Window):
    NO_DATA_MESSAGE = "-- !! Not receiving any data from X-Plane !! --"

    def __init__(
        self,
        panel: Panel,
        get_data: Callable[[Any], float],
        is_test_mode: bool,
        udp_alive: Callable[[], bool] | None = None,
    ) -> None:
        w, h = panel.size
        super().__init__(w, h, panel.name)
        if panel.background_color is not None:
            self.background_color = panel.background_color
        else:
            self.background_color = arcade.color.BLACK

        self.panel = panel
        self._get_data = get_data
        self._is_test_mode = is_test_mode
        self._udp_alive = udp_alive

        # Test-mode value (read by TestDataSource if attached).
        self.test_value = 0.0
        self.test_increment = 1.0

        # FPS tracking (updated into the window title; matches original).
        self._frame_count = 0
        self._last_fps_time = time.time()

        # No-data overlay.
        self._no_data_text = arcade.Text(
            text=self.NO_DATA_MESSAGE,
            x=20,
            y=h - 30,
            color=(255, 165, 0, 230),  # orange-ish
            font_size=14,
        )

    # -- frame loop -------------------------------------------------------

    def on_draw(self) -> None:
        self.clear()
        components = self.panel.all_components()
        for comp in components:
            comp.update(self._get_data)
        for comp in components:
            comp.draw()

        # No-data overlay (only when bound to UDP and X-Plane is silent).
        if not self._is_test_mode and self._udp_alive is not None and not self._udp_alive():
            self._no_data_text.draw()

        # FPS counter via window title.
        self._frame_count += 1
        now = time.time()
        elapsed = now - self._last_fps_time
        if elapsed >= 0.5:
            fps = self._frame_count / elapsed
            self.set_caption(f"{self.panel.name} — FPS: {fps:.1f}")
            self._frame_count = 0
            self._last_fps_time = now

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


# -- Data sources ---------------------------------------------------------


class TestDataSource:
    """Returns the window's test_value for any dataref. Used with --test."""

    def __init__(self) -> None:
        self.window: PanelWindow | None = None

    def __call__(self, _dataref: Any) -> float:
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

    def __call__(self, dataref: Any) -> float:
        return float(self._server.getData(dataref))

    def alive(self) -> bool:
        return bool(getattr(self._server, "XPalive", False))


def _parse_addr(s: str) -> tuple[str, int]:
    host, port = s.rsplit(":", 1)
    return host, int(port)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "Run an instrument or panel YAML in an Arcade window. "
            "If the YAML has an `instruments:` key it's treated as a panel; "
            "otherwise as a single instrument."
        ),
    )
    p.add_argument("yaml_path", help="Path to an instrument or panel YAML")
    p.add_argument(
        "--test",
        action="store_true",
        help="Test mode: numpad +/-/*, arrows, and PgUp/PgDn drive the "
        "value across all gauges. No UDP.",
    )
    p.add_argument(
        "--listen",
        default="127.0.0.1:49008",
        help="host:port this app listens on (default 127.0.0.1:49008)",
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

    panel = load_panel_or_instrument(args.yaml_path)

    if args.test:
        data_source = TestDataSource()
        window = PanelWindow(
            panel=panel,
            get_data=data_source,
            is_test_mode=True,
        )
        data_source.window = window
    else:
        udp = UDPDataSource(
            listen=_parse_addr(args.listen),
            xp=_parse_addr(args.xp),
            xp_name=args.xp_name,
        )
        window = PanelWindow(
            panel=panel,
            get_data=udp,
            is_test_mode=False,
            udp_alive=udp.alive,
        )

    arcade.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
