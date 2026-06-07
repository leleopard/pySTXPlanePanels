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

import math
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
        face_off: tuple[float, float] = (0.0, 0.0),
        face_rot_center: tuple[float, float] = (0.0, 0.0),
        show_touch_zones: bool = False,
        hit_padding: float | None = None,
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
        # Face layout offsets — kept in panel coords (scaled but not offset-shifted)
        self._face_off_x, self._face_off_y = float(face_off[0]), float(face_off[1])
        self._face_rot_cx, self._face_rot_cy = float(face_rot_center[0]), float(face_rot_center[1])
        self._show_touch_zones = show_touch_zones
        # None = use panel-level hit_padding_multiplier; a float overrides it for this knob.
        self.hit_padding: float | None = hit_padding

        # Gesture tracking
        self._press_x: float = 0.0
        self._drag_accum: float = 0.0
        self._drag_fired: int = 0

    # ── panel composition ─────────────────────────────────────────────────────

    def apply_scale(self, scale: float) -> None:
        super().apply_scale(scale)
        if self._bg_sprite is not None:
            self._bg_sprite.scale_x *= scale
            self._bg_sprite.scale_y *= scale
            self._bg_sprite.center_x *= scale
            self._bg_sprite.center_y *= scale
        if self._face_sprite is not None:
            # Visual scale only — center is recomputed each frame in update()
            self._face_sprite.scale_x *= scale
            self._face_sprite.scale_y *= scale
        self._face_off_x *= scale
        self._face_off_y *= scale
        self._face_rot_cx *= scale
        self._face_rot_cy *= scale

    def apply_offset(self, dx: float, dy: float) -> None:
        super().apply_offset(dx, dy)
        if self._bg_sprite is not None:
            self._bg_sprite.center_x += dx
            self._bg_sprite.center_y += dy
        # face sprite center is computed from self._x/_y in update()

    # ── runtime interface ─────────────────────────────────────────────────────

    def update(self, get_data: Callable[[Any], float]) -> None:
        if self._face_sprite is None:
            return
        # Determine rotation angle (0 when no dataref configured)
        angle_deg = 0.0
        if self._face_rot_dr is not None and self._face_rot_table is not None:
            raw = float(get_data(self._face_rot_dr))
            if self._face_rot_convert is not None:
                raw = float(self._face_rot_convert(raw, get_data))
            angle_deg = lookup_piecewise(self._face_rot_table, raw)
        self._face_sprite.angle = angle_deg
        # Compute face sprite center each frame from rotation geometry.
        # pivot = component centre + face_rotation_center offset
        # face_at_0 = component centre + face_offset
        # face_pos = pivot + rotate(face_at_0 − pivot, angle)
        cos_a = math.cos(math.radians(angle_deg))
        sin_a = math.sin(math.radians(angle_deg))
        vx = self._face_off_x - self._face_rot_cx
        vy = self._face_off_y - self._face_rot_cy
        px = self._x + self._face_rot_cx
        py = self._y + self._face_rot_cy
        self._face_sprite.center_x = px + vx * cos_a - vy * sin_a
        self._face_sprite.center_y = py + vx * sin_a + vy * cos_a

    def draw(self) -> None:
        if self._bg_sprite is not None:
            arcade.draw_sprite(self._bg_sprite)
        if self._face_sprite is not None:
            arcade.draw_sprite(self._face_sprite)
        if self._show_touch_zones:
            # Use the effective multiplier (per-component override or panel default 1.5)
            eff_mult = self.hit_padding if self.hit_padding is not None else 1.5
            lx, ly, lw, lh = self.hit_rect(eff_mult)
            # CCW = left half (yellow), CW = right half (green)
            arcade.draw_rect_filled(arcade.LBWH(lx,          ly, lw / 2, lh), (255, 220, 0, 100))
            arcade.draw_rect_filled(arcade.LBWH(lx + lw / 2, ly, lw / 2, lh), (0, 200, 80, 100))

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
        if not command:
            return
        try:
            win = arcade.get_window()
            win._send_cmd(command)
            if getattr(win, "_is_test_mode", False):
                print(f"[cmd] {self.name}: {command}", flush=True)
        except Exception as exc:
            print(f"[RotaryEncoder:{self.name}] _fire({command!r}) failed: {exc}")


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

    def _sprite_sized(
        tex_key: str, origin_key: str, clip_key: str,
        target_w: float, target_h: float,
    ) -> arcade.Sprite | None:
        if tex_key not in comp:
            return None
        path     = (base_dir / comp[tex_key]).resolve()
        origin   = tuple(comp.get(origin_key, [0, 0]))
        cliprect = tuple(comp.get(clip_key, [int(target_w), int(target_h)]))
        return _make_sprite(path, origin, cliprect, cx, cy, target_w, target_h)

    bg_sprite = _sprite_sized(
        "background_texture", "background_origin", "background_cliprect", tw, th
    )

    # Face may have its own display size (defaults to component size)
    face_size_raw = comp.get("face_size", size)
    fw, fh = float(face_size_raw[0]), float(face_size_raw[1])
    face_sprite = _sprite_sized(
        "face_texture", "face_origin", "face_cliprect", fw, fh
    )

    face_off_raw = comp.get("face_offset", [0, 0])
    face_rot_ctr_raw = comp.get("face_rotation_center", [0, 0])

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
        face_off=(float(face_off_raw[0]), float(face_off_raw[1])),
        face_rot_center=(float(face_rot_ctr_raw[0]), float(face_rot_ctr_raw[1])),
        show_touch_zones=bool(comp.get("show_touch_zones", False)),
        hit_padding=float(comp["hit_padding"]) if "hit_padding" in comp else None,
    )


register_component("RotaryEncoder", _rotary_encoder_factory)
