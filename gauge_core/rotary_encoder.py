"""RotaryEncoder interactive component.

An invisible hit zone that translates mouse/touch gestures into a stream of
X-Plane commands (CW / CCW steps).

Gesture model
-------------
Tap left half  → one CCW step  (command_ccw)
Tap right half → one CW  step  (command_cw)
Drag up        → continuous CW  steps (one per drag_px_per_step pixels)
Drag down      → continuous CCW steps
Mouse scroll ↑ → one CW  step per notch
Mouse scroll ↓ → one CCW step per notch

A press that results in a total vertical drag ≥ drag_px_per_step is treated
as a drag (steps fired continuously); a smaller press is treated as a tap
(single step fired on release, direction from left/right half).

YAML schema
-----------
    - type: RotaryEncoder
      name: heading_bug_knob
      position: [200, 300]       # centre of the hit zone, instrument coords
      size: [60, 60]             # bounding box; hit target is size × hit_padding_multiplier
      command_cw:  sim/autopilot/heading_up
      command_ccw: sim/autopilot/heading_down
      drag_px_per_step: 5        # optional, default 5
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import arcade

from gauge_core.interactive import InteractiveComponent
from gauge_core.registry import register_component


class RotaryEncoder(InteractiveComponent):
    """Rotary encoder interactive overlay."""

    def __init__(
        self,
        name: str,
        position: tuple[float, float],
        size: tuple[float, float],
        command_cw: str,
        command_ccw: str,
        drag_px_per_step: float = 5.0,
    ) -> None:
        super().__init__(name, position, size)
        self._cmd_cw  = command_cw
        self._cmd_ccw = command_ccw
        self._drag_threshold = max(0.5, float(drag_px_per_step))

        # Gesture tracking
        self._press_x: float = 0.0     # x coord of the initial press
        self._drag_accum: float = 0.0  # signed running total (+ = up/CW)
        self._drag_fired: int = 0      # commands fired during this drag

    # ── gesture handlers ──────────────────────────────────────────────────────

    def on_press(self, panel_x: float, panel_y: float) -> None:
        self._press_x = panel_x
        self._drag_accum = 0.0
        self._drag_fired = 0

    def on_drag(self, panel_x: float, panel_y: float,
                ddx: float, ddy: float) -> None:
        # y-up: ddy > 0 means finger/cursor moved up → CW
        self._drag_accum += ddy
        while self._drag_accum >= self._drag_threshold:
            self._fire(self._cmd_cw)
            self._drag_accum -= self._drag_threshold
            self._drag_fired += 1
        while self._drag_accum <= -self._drag_threshold:
            self._fire(self._cmd_ccw)
            self._drag_accum += self._drag_threshold
            self._drag_fired += 1

    def on_release(self, panel_x: float, panel_y: float) -> None:
        # If no commands were fired during the drag it was a tap →
        # fire one step based on which half of the knob was pressed.
        if self._drag_fired == 0:
            if self._press_x < self._x:
                self._fire(self._cmd_ccw)
            else:
                self._fire(self._cmd_cw)
        self._drag_accum = 0.0
        self._drag_fired = 0

    def on_scroll(self, panel_x: float, panel_y: float,
                  scroll_y: float) -> None:
        # One command per scroll notch, direction follows scroll direction.
        if scroll_y > 0:
            self._fire(self._cmd_cw)
        elif scroll_y < 0:
            self._fire(self._cmd_ccw)

    # ── internal ──────────────────────────────────────────────────────────────

    def _fire(self, command: str) -> None:
        try:
            arcade.get_window()._send_cmd(command)
        except Exception:
            pass


# ── factory + registration ────────────────────────────────────────────────────

def _rotary_encoder_factory(
    comp: dict[str, Any],
    base_dir: Path,                          # noqa: ARG001
    container_size: tuple[int, int] | None,  # noqa: ARG001
) -> RotaryEncoder:
    pos  = tuple(comp["position"])
    size = tuple(comp.get("size", [60, 60]))
    return RotaryEncoder(
        name=comp["name"],
        position=pos,
        size=size,
        command_cw=str(comp["command_cw"]),
        command_ccw=str(comp["command_ccw"]),
        drag_px_per_step=float(comp.get("drag_px_per_step", 5.0)),
    )


register_component("RotaryEncoder", _rotary_encoder_factory)
