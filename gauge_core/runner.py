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

_DEFAULT_CONFIG = "config.yaml"


def _load_config(config_path: str | None) -> dict:
    """Load UDP settings from a config YAML. Returns {} if file not found."""
    path = Path(config_path) if config_path else Path(_DEFAULT_CONFIG)
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("udp", {})

from gauge_core.loader import load_instrument
from gauge_core.mock_source import DEFAULT_MOCK_PORT, MockDataSource
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
        on_shutdown: Callable[[], None] | None = None,
    ) -> None:
        w, h = panel.size
        super().__init__(w, h, panel.name, antialiasing=True, samples=8)
        # GL_LINE_SMOOTH + NICEST hint give per-primitive sub-pixel antialiasing
        # for draw_line / draw_arc on drivers that expose the compatibility
        # extension; MSAA (samples=8) covers the rest.
        from pyglet.gl import (
            glEnable, glHint, glBlendFunc,
            GL_LINE_SMOOTH, GL_LINE_SMOOTH_HINT, GL_NICEST,
            GL_BLEND, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA,
        )
        glEnable(GL_LINE_SMOOTH)
        glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        if panel.background_color is not None:
            self.background_color = panel.background_color
        else:
            self.background_color = arcade.color.BLACK

        self.panel = panel
        self._get_data = get_data
        self._is_test_mode = is_test_mode
        self._udp_alive = udp_alive
        self._on_shutdown = on_shutdown

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

        # Test-mode overlay: shows current test value and step so the user
        # can see what value is being fed to all datarefs.
        self._test_overlay = arcade.Text(
            text="",
            x=6,
            y=6,
            color=(0, 230, 0, 220),
            font_size=12,
        ) if is_test_mode else None

    def on_close(self) -> None:
        if self._on_shutdown is not None:
            self._on_shutdown()
        super().on_close()

    # -- frame loop -------------------------------------------------------

    def on_draw(self) -> None:
        self.clear()

        # Each instrument can declare an instrument-wide visibility
        # predicate; if it evaluates False the instrument's components
        # are skipped entirely (used by radios when unpowered). Skipped
        # in test mode so every gauge is visible regardless of the
        # numpad-driven test value — power-toggle behaviour is best
        # verified against a live X-Plane.
        for inst in self.panel.instruments:
            if (
                not self._is_test_mode
                and inst.visibility is not None
                and not inst.visibility.is_visible(self._get_data)
            ):
                continue
            for comp in inst.components:
                comp.update(self._get_data)
            for comp in inst.components:
                comp.draw()

        # No-data overlay (only when bound to UDP and X-Plane is silent).
        if not self._is_test_mode and self._udp_alive is not None and not self._udp_alive():
            self._no_data_text.draw()

        # Test-mode overlay: live value + step.
        if self._test_overlay is not None:
            self._test_overlay.text = (
                f"TEST  value: {self.test_value:.2f}    step: {self.test_increment:.1f}"
                f"    (numpad +/−  ↑↓ ×10  PgUp/Dn ×100  * toggle step)"
            )
            self._test_overlay.draw()

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

    def quit(self) -> None:
        self._server.quit()


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
        "--mock",
        action="store_true",
        help="Mock mode: receive per-dataref values from the test harness "
        "(gauge_test_harness) over a local UDP socket. No X-Plane needed.",
    )
    p.add_argument(
        "--mock-port",
        type=int,
        default=DEFAULT_MOCK_PORT,
        help=f"Local UDP port MockDataSource listens on (default {DEFAULT_MOCK_PORT}).",
    )
    p.add_argument(
        "--config",
        default=None,
        help=f"Path to config YAML (default: ./{_DEFAULT_CONFIG} if present)",
    )
    p.add_argument("--listen", default=None, help="host:port this app listens on")
    p.add_argument("--xp", default=None, help="host:port of X-Plane")
    p.add_argument("--xp-name", default=None, help="Computer name X-Plane expects")
    args = p.parse_args(argv)

    # Merge: config file supplies base values; CLI args override.
    cfg = _load_config(args.config)
    listen_host = cfg.get("listen_host", "127.0.0.1")
    listen_port = cfg.get("listen_port", 49008)
    xp_host = cfg.get("xplane_host", "127.0.0.1")
    xp_port = cfg.get("xplane_port", 49000)
    xp_name = cfg.get("xplane_name") or socket.gethostname()

    if args.listen:
        listen_host, listen_port = _parse_addr(args.listen)
        listen_port = int(listen_port)
    if args.xp:
        xp_host, xp_port = _parse_addr(args.xp)
        xp_port = int(xp_port)
    if args.xp_name:
        xp_name = args.xp_name

    panel = load_panel_or_instrument(args.yaml_path)

    # Panel YAML udp.listen_port overrides config.yaml (CLI still wins).
    if panel.udp_listen_port is not None and args.listen is None:
        listen_port = panel.udp_listen_port

    udp: UDPDataSource | None = None
    mock: MockDataSource | None = None
    if args.test:
        data_source = TestDataSource()
        window = PanelWindow(
            panel=panel,
            get_data=data_source,
            is_test_mode=True,
        )
        data_source.window = window
    elif args.mock:
        mock = MockDataSource(port=args.mock_port)
        mock.start()
        window = PanelWindow(
            panel=panel,
            get_data=mock,
            is_test_mode=True,
        )
    else:
        udp = UDPDataSource(
            listen=(listen_host, listen_port),
            xp=(xp_host, xp_port),
            xp_name=xp_name,
        )
        window = PanelWindow(
            panel=panel,
            get_data=udp,
            is_test_mode=False,
            udp_alive=udp.alive,
            on_shutdown=udp.quit,
        )

    try:
        arcade.run()
    finally:
        # Ensure sockets are always released — covers Ctrl+C, terminal kill,
        # and any path that doesn't go through on_close() (e.g. KeyboardInterrupt
        # propagating out of arcade.run before the window dispatches on_close).
        if udp is not None:
            try:
                udp.quit()
            except Exception:
                pass
        if mock is not None:
            try:
                mock.stop()
            except Exception:
                pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
