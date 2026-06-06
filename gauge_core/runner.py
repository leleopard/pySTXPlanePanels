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
        send_cmd: Callable[[str], None],
        is_test_mode: bool,
        udp_alive: Callable[[], bool] | None = None,
        on_shutdown: Callable[[], None] | None = None,
        ssaa: int = 4,
    ) -> None:
        w, h = panel.size

        # Resolve target screen via pyglet (Arcade's windowing backend).
        import pyglet.display
        screens = pyglet.display.Display().get_screens()
        target_screen = (
            screens[min(panel.screen_index, len(screens) - 1)]
            if screens else None
        )

        # Always non-MSAA: hardware MSAA is unreliable for python.exe without
        # driver overrides.  AA is provided by the SSAA FBO chain instead.
        super().__init__(
            w, h, panel.name,
            antialiasing=False,
            fullscreen=panel.fullscreen,
            screen=target_screen,
        )

        if panel.background_color is not None:
            self.background_color = panel.background_color
        else:
            self.background_color = arcade.color.BLACK

        self.panel = panel
        # Logical panel dimensions — used by SpriteSheet/ScrollingTape to scale
        # scissor rectangles correctly (they are in panel coords, not screen pixels).
        self._panel_size: tuple[int, int] = panel.size
        self._get_data = get_data
        self._send_cmd = send_cmd
        self._is_test_mode = is_test_mode
        self._udp_alive = udp_alive
        self._on_shutdown = on_shutdown

        # Interactive component gesture state
        self._active_interactive: Any | None = None

        self.test_value = 0.0
        self.test_increment = 1.0
        self._frame_count = 0
        self._last_fps_time = time.time()

        self._no_data_text = arcade.Text(
            text=self.NO_DATA_MESSAGE,
            x=20,
            y=h - 30,
            color=(255, 165, 0, 230),
            font_size=14,
        )
        self._test_overlay = arcade.Text(
            text="",
            x=6,
            y=6,
            color=(0, 230, 0, 220),
            font_size=12,
        ) if is_test_mode else None

        # SSAA FBO chain: ssaa× → ssaa//2× → … → 2× → screen.
        # Each step is a perfect 2:1 GL_LINEAR downsample (N² samples/pixel).
        bc = self.background_color
        self._bg_float = (bc.r / 255.0, bc.g / 255.0, bc.b / 255.0, bc.a / 255.0)
        self._ssaa_chain: list[tuple] = []   # [(fbo, w, h), …] largest first
        if ssaa >= 2:
            ctx = self.ctx
            max_tex = ctx.info.MAX_TEXTURE_SIZE
            # Clamp ssaa so the FBO texture fits within the driver's texture limit.
            # Pi 5 (GLES) caps MAX_TEXTURE_SIZE at 4096; a 1540×920 panel at ssaa=4
            # would need 6160×3680 which exceeds that.
            factor = ssaa
            while factor >= 2 and (w * factor > max_tex or h * factor > max_tex):
                factor //= 2
            while factor >= 2:
                tex = ctx.texture((w * factor, h * factor), components=4)
                fbo = ctx.framebuffer(color_attachments=[tex])
                self._ssaa_chain.append((fbo, w * factor, h * factor))
                factor //= 2

    def on_close(self) -> None:
        if self._on_shutdown is not None:
            self._on_shutdown()
        super().on_close()

    # -- frame loop -------------------------------------------------------

    def on_draw(self) -> None:
        if self._ssaa_chain:
            self._on_draw_ssaa()
        else:
            from pyglet.math import Mat4
            w, h = self.panel.size
            self.clear()
            # Explicitly set panel-size projection so that fullscreen mode (where
            # win.width/height equal the screen resolution, not the panel size)
            # maps sprite positions in panel coords correctly to screen pixels.
            self.ctx.projection_matrix = Mat4.orthogonal_projection(
                0, w, 0, h, -100.0, 100.0
            )
            self._render_scene()
        self._tick_fps()

    def _render_scene(self) -> None:
        """Draw all instruments and overlays into the active framebuffer."""
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

        if not self._is_test_mode and self._udp_alive is not None and not self._udp_alive():
            self._no_data_text.draw()

        if self._test_overlay is not None:
            self._test_overlay.text = (
                f"TEST  value: {self.test_value:.2f}    step: {self.test_increment:.1f}"
                f"    (numpad +/−  ↑↓ ×10  PgUp/Dn ×100  * toggle step)"
            )
            self._test_overlay.draw()

    def _on_draw_ssaa(self) -> None:
        """Render scene into the SSAA FBO chain then blit down to screen."""
        from pyglet.math import Mat4
        from pyglet.gl import (
            glBindFramebuffer, glBlitFramebuffer,
            GL_READ_FRAMEBUFFER, GL_DRAW_FRAMEBUFFER,
            GL_COLOR_BUFFER_BIT, GL_LINEAR,
        )
        w, h = self.panel.size
        ctx = self.ctx

        top_fbo, fw, fh = self._ssaa_chain[0]
        saved_proj = ctx.projection_matrix
        top_fbo.use()
        top_fbo.viewport = (0, 0, fw, fh)
        top_fbo.clear(color_normalized=self._bg_float)
        ctx.projection_matrix = Mat4.orthogonal_projection(0, w, 0, h, -100.0, 100.0)

        self._render_scene()

        # Cascade through intermediate FBOs (each a perfect 2:1 downsample).
        for i in range(len(self._ssaa_chain) - 1):
            src_fbo, sw, sh = self._ssaa_chain[i]
            dst_fbo, dw, dh = self._ssaa_chain[i + 1]
            glBindFramebuffer(GL_READ_FRAMEBUFFER, src_fbo.glo)
            glBindFramebuffer(GL_DRAW_FRAMEBUFFER, dst_fbo.glo)
            glBlitFramebuffer(0, 0, sw, sh, 0, 0, dw, dh, GL_COLOR_BUFFER_BIT, GL_LINEAR)

        last_fbo, lw, lh = self._ssaa_chain[-1]
        ctx.screen.use()
        ctx.projection_matrix = saved_proj
        glBindFramebuffer(GL_READ_FRAMEBUFFER, last_fbo.glo)
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, ctx.screen.glo)
        glBlitFramebuffer(0, 0, lw, lh, 0, 0, w, h, GL_COLOR_BUFFER_BIT, GL_LINEAR)
        glBindFramebuffer(GL_READ_FRAMEBUFFER, ctx.screen.glo)

    def _tick_fps(self) -> None:
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

    # -- Gesture dispatcher -----------------------------------------------

    def _to_panel_coords(self, x: float, y: float) -> tuple[float, float]:
        """Convert Arcade window pixels (y-up from bottom-left) to panel logical coords."""
        pw, ph = self._panel_size
        return x * pw / self.width, y * ph / self.height

    def _all_interactive(self):
        """Yield every InteractiveComponent across all instruments."""
        from gauge_core.interactive import InteractiveComponent
        for inst in self.panel.instruments:
            for comp in inst.components:
                if isinstance(comp, InteractiveComponent):
                    yield comp

    def _hit_test(self, panel_x: float, panel_y: float):
        """Return the topmost interactive component at panel coords, or None."""
        mult = self.panel.hit_padding_multiplier
        # Iterate in reverse draw order so topmost component wins.
        from gauge_core.interactive import InteractiveComponent
        candidates = []
        for inst in self.panel.instruments:
            for comp in inst.components:
                if isinstance(comp, InteractiveComponent):
                    if comp.hit_test(panel_x, panel_y, mult):
                        candidates.append(comp)
        return candidates[-1] if candidates else None

    def on_mouse_press(self, x: float, y: float, button: int, _modifiers: int) -> None:
        if button != arcade.MOUSE_BUTTON_LEFT:
            return
        px, py = self._to_panel_coords(x, y)
        comp = self._hit_test(px, py)
        if comp is not None:
            self._active_interactive = comp
            comp.on_press(px, py)

    def on_mouse_release(self, x: float, y: float, button: int, _modifiers: int) -> None:
        if button != arcade.MOUSE_BUTTON_LEFT:
            return
        if self._active_interactive is not None:
            px, py = self._to_panel_coords(x, y)
            self._active_interactive.on_release(px, py)
            self._active_interactive = None

    def on_mouse_drag(self, x: float, y: float, dx: float, dy: float,
                      _buttons: int, _modifiers: int) -> None:
        if self._active_interactive is None:
            return
        px, py = self._to_panel_coords(x, y)
        pw, ph = self._panel_size
        # Scale dx/dy from screen pixels to panel logical pixels.
        dpx = dx * pw / self.width
        dpy = dy * ph / self.height
        self._active_interactive.on_drag(px, py, dpx, dpy)

    def on_mouse_scroll(self, x: float, y: float, _scroll_x: float, scroll_y: float) -> None:
        px, py = self._to_panel_coords(x, y)
        comp = self._hit_test(px, py)
        if comp is not None:
            comp.on_scroll(px, py, scroll_y)

    def on_touch_begin(self, touch) -> None:
        self.on_mouse_press(touch.x, touch.y, arcade.MOUSE_BUTTON_LEFT, 0)

    def on_touch_end(self, touch) -> None:
        self.on_mouse_release(touch.x, touch.y, arcade.MOUSE_BUTTON_LEFT, 0)

    def on_touch_motion(self, touch) -> None:
        self.on_mouse_drag(touch.x, touch.y, touch.dx, touch.dy,
                           arcade.MOUSE_BUTTON_LEFT, 0)


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

    def send_cmd(self, command: str) -> None:
        self._server.sendXPCmd(command)

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
    p.add_argument(
        "--ssaa", type=int, default=4, choices=[0, 2, 4, 8],
        help="Supersampling AA factor: 0=off, 2=4spp, 4=16spp (default), 8=64spp",
    )
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

    _noop_send_cmd: Callable[[str], None] = lambda _cmd: None

    if args.test:
        data_source = TestDataSource()
        window = PanelWindow(
            panel=panel,
            get_data=data_source,
            send_cmd=_noop_send_cmd,
            is_test_mode=True,
            ssaa=args.ssaa,
        )
        data_source.window = window
    elif args.mock:
        mock = MockDataSource(port=args.mock_port)
        mock.start()
        window = PanelWindow(
            panel=panel,
            get_data=mock,
            send_cmd=_noop_send_cmd,
            is_test_mode=True,
            ssaa=args.ssaa,
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
            send_cmd=udp.send_cmd,
            is_test_mode=False,
            udp_alive=udp.alive,
            on_shutdown=udp.quit,
            ssaa=args.ssaa,
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
