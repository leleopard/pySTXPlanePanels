"""RotaryEncoder interactive component.

Combines a visual encoder widget (optional background + rotating face sprite)
with an invisible hit zone that translates mouse/touch gestures into X-Plane
commands.

Visual layers (both optional)
------------------------------
background  — static texture layer (encoder housing / bezel)
face        — texture layer whose rotation tracks a dataref (knob face)

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
      position: [200, 300]          # centre of the widget, instrument coords
      size: [60, 60]                # bounding box; both sprites are scaled to fit
      command_cw:  sim/autopilot/heading_up
      command_ccw: sim/autopilot/heading_down
      drag_px_per_step: 5           # optional, default 5

      # Optional static background (encoder body / bezel)
      background_texture: assets/encoder_bg.png
      background_origin:  [0, 0]    # top-left in the atlas (PIL convention)
      background_cliprect: [120, 120]

      # Optional rotating face (knob surface)
      face_texture: assets/encoder_face.png
      face_origin:  [0, 0]
      face_cliprect: [80, 80]
      face_rotation:
        dataref: sim/cockpit2/autopilot/heading_dial_deg_mag_pilot
        table: [[0, 0], [360, 360]]
        convert_function: null        # optional
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import arcade

from gauge_core.interactive import InteractiveComponent
from gauge_core.lookup import lookup_piecewise
from gauge_core.registry import get_convert, register_component
from gauge_core.textures import load_clipped_texture


def _make_sprite(
    tex_path: Path,
    origin: tuple[int, int],
    cliprect: tuple[int, int],
    center_x: float,
    center_y: float,
    target_w: float,
    target_h: float,
) -> arcade.Sprite:
    """Load a clipped atlas region and create a sprite scaled to target size."""
    texture = load_clipped_texture(tex_path, origin, cliprect)
    sprite = arcade.Sprite(texture)
    sprite.center_x = center_x
    sprite.center_y = center_y
    cw, ch = cliprect
    if cw > 0 and ch > 0:
        sprite.scale_x = target_w / cw
        sprite.scale_y = target_h / ch
    return sprite


class RotaryEncoder(InteractiveComponent):
    """Rotary encoder: visual background + rotating face + interactive hit zone."""

    def __init__(
        self,
        name: str,
        position: tuple[float, float],
        size: tuple[float, float],
        command_cw: str,
        command_ccw: str,
        drag_px_per_step: float = 5.0,
        bg_sprite: arcade.Sprite | None = None,
        face_sprite: arcade.Sprite | None = None,
        face_rot_dataref: Any | None = None,
        face_rot_table: list[list[float]] | None = None,
        face_rot_convert: Callable | None = None,
    ) -> None:
        super().__init__(name, position, size)
        self._cmd_cw  = command_cw
        self._cmd_ccw = command_ccw
        self._drag_threshold = max(0.5, float(drag_px_per_step))

        self._bg_sprite   = bg_sprite
        self._face_sprite = face_sprite
        self._face_rot_dr      = face_rot_dataref
        self._face_rot_table   = face_rot_table
        self._face_rot_convert = face_rot_convert

        # Gesture tracking
        self._press_x: float = 0.0
        self._drag_accum: float = 0.0
        self._drag_fired: int = 0

    # ── panel composition ─────────────────────────────────────────────────────

    def apply_scale(self, scale: float) -> None:
        super().apply_scale(scale)
        for spr in (self._bg_sprite, self._face_sprite):
            if spr is not None:
                spr.scale_x *= scale
                spr.scale_y *= scale
                spr.center_x *= scale
                spr.center_y *= scale

    def apply_offset(self, dx: float, dy: float) -> None:
        super().apply_offset(dx, dy)
        for spr in (self._bg_sprite, self._face_sprite):
            if spr is not None:
                spr.center_x += dx
                spr.center_y += dy

    # ── runtime interface ─────────────────────────────────────────────────────

    def update(self, get_data: Callable[[Any], float]) -> None:
        if self._face_sprite is None or self._face_rot_dr is None:
            return
        if self._face_rot_table is None:
            return
        raw = float(get_data(self._face_rot_dr))
        if self._face_rot_convert is not None:
            raw = float(self._face_rot_convert(raw, get_data))
        self._face_sprite.angle = lookup_piecewise(self._face_rot_table, raw)

    def draw(self) -> None:
        if self._bg_sprite is not None:
            arcade.draw_sprite(self._bg_sprite)
        if self._face_sprite is not None:
            arcade.draw_sprite(self._face_sprite)

    # ── gesture handlers ──────────────────────────────────────────────────────

    def on_press(self, panel_x: float, panel_y: float) -> None:
        self._press_x = panel_x
        self._drag_accum = 0.0
        self._drag_fired = 0

    def on_drag(self, panel_x: float, panel_y: float,
                ddx: float, ddy: float) -> None:
        # y-up: ddy > 0 = finger moved up → CW
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
        if self._drag_fired == 0:
            if self._press_x < self._x:
                self._fire(self._cmd_ccw)
            else:
                self._fire(self._cmd_cw)
        self._drag_accum = 0.0
        self._drag_fired = 0

    def on_scroll(self, panel_x: float, panel_y: float,
                  scroll_y: float) -> None:
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
    base_dir: Path,
    container_size: tuple[int, int] | None,  # noqa: ARG001
) -> RotaryEncoder:
    pos  = tuple(comp["position"])
    size = tuple(comp.get("size", [60, 60]))
    cx, cy = float(pos[0]), float(pos[1])
    tw, th = float(size[0]), float(size[1])

    def _sprite(tex_key: str, origin_key: str, clip_key: str) -> arcade.Sprite | None:
        if tex_key not in comp:
            return None
        path = (base_dir / comp[tex_key]).resolve()
        origin  = tuple(comp.get(origin_key,  [0, 0]))
        cliprect = tuple(comp.get(clip_key, [int(tw), int(th)]))
        return _make_sprite(path, origin, cliprect, cx, cy, tw, th)

    bg_sprite   = _sprite("background_texture", "background_origin", "background_cliprect")
    face_sprite = _sprite("face_texture",       "face_origin",       "face_cliprect")

    face_rot_dr = face_rot_table = face_rot_convert = None
    if "face_rotation" in comp and face_sprite is not None:
        fr = comp["face_rotation"]
        face_rot_dr = fr["dataref"]
        if isinstance(face_rot_dr, list):
            face_rot_dr = tuple(face_rot_dr)
        face_rot_table   = fr["table"]
        face_rot_convert = get_convert(fr.get("convert_function"))

    return RotaryEncoder(
        name=comp["name"],
        position=pos,
        size=size,
        command_cw=str(comp.get("command_cw", "")),
        command_ccw=str(comp.get("command_ccw", "")),
        drag_px_per_step=float(comp.get("drag_px_per_step", 5.0)),
        bg_sprite=bg_sprite,
        face_sprite=face_sprite,
        face_rot_dataref=face_rot_dr,
        face_rot_table=face_rot_table,
        face_rot_convert=face_rot_convert,
    )


register_component("RotaryEncoder", _rotary_encoder_factory)
