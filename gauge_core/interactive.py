"""Base class for invisible interactive overlay components.

Interactive components (Momentary_Button, Switch, RotaryEncoder) are loaded
and stored alongside visual components in an Instrument.components list.
At runtime they are invisible (draw() is a no-op) but receive gesture events
dispatched by PanelWindow.

Hit-test
--------
The effective hit rectangle is the component's bounding box expanded by
panel.hit_padding_multiplier (default 1.5).  A 40×40 button with
multiplier 1.5 produces a 60×60 hit zone centred on the same point.

send_cmd
--------
Components call arcade.get_window()._send_cmd(command) to fire an X-Plane
command.  PanelWindow wires this to pyxpudpserver.sendXPCmd in UDP mode and
to a no-op in test/mock mode.
"""

from __future__ import annotations

from typing import Any, Callable


class InteractiveComponent:
    """Invisible interactive overlay — base class for all control types."""

    def __init__(
        self,
        name: str,
        position: tuple[float, float],
        size: tuple[float, float],
    ) -> None:
        self.name = name
        self._x = float(position[0])
        self._y = float(position[1])
        self._w = float(size[0])
        self._h = float(size[1])

    # ── panel composition ────────────────────────────────────────────────────

    def apply_scale(self, scale: float) -> None:
        self._x *= scale
        self._y *= scale
        self._w *= scale
        self._h *= scale

    def apply_offset(self, dx: float, dy: float) -> None:
        self._x += dx
        self._y += dy

    # ── hit testing ──────────────────────────────────────────────────────────

    def hit_test(self, panel_x: float, panel_y: float,
                 padding_mult: float = 1.5) -> bool:
        """Return True if (panel_x, panel_y) is within the padded hit rect."""
        extra_w = self._w * (padding_mult - 1.0) / 2
        extra_h = self._h * (padding_mult - 1.0) / 2
        left   = self._x - self._w / 2 - extra_w
        right  = self._x + self._w / 2 + extra_w
        bottom = self._y - self._h / 2 - extra_h
        top    = self._y + self._h / 2 + extra_h
        return left <= panel_x <= right and bottom <= panel_y <= top

    def hit_rect(self, padding_mult: float = 1.5) -> tuple[float, float, float, float]:
        """Return (x, y, w, h) of the padded hit rectangle in panel coords."""
        extra_w = self._w * (padding_mult - 1.0) / 2
        extra_h = self._h * (padding_mult - 1.0) / 2
        return (
            self._x - self._w / 2 - extra_w,
            self._y - self._h / 2 - extra_h,
            self._w + extra_w * 2,
            self._h + extra_h * 2,
        )

    # ── runner interface (same as visual components) ─────────────────────────

    def update(self, get_data: Callable[[Any], float]) -> None:
        pass

    def draw(self) -> None:
        pass  # invisible at runtime

    # ── gesture interface (called by PanelWindow dispatcher) ─────────────────

    def on_press(self, panel_x: float, panel_y: float) -> None:
        """Called when a press/tap begins inside the hit rect."""

    def on_release(self, panel_x: float, panel_y: float) -> None:
        """Called when the press/tap ends (even if pointer drifted outside)."""

    def on_drag(self, panel_x: float, panel_y: float,
                ddx: float, ddy: float) -> None:
        """Called on each mouse-drag or touch-motion event while this component
        is the active (pressed) target.  ddx/ddy are delta pixels in panel coords."""

    def on_scroll(self, panel_x: float, panel_y: float,
                  scroll_y: float) -> None:
        """Called on mouse-scroll wheel while the pointer is over the hit rect.
        scroll_y > 0 = scroll up; < 0 = scroll down."""
