"""AttitudeIndicator component — glass-cockpit ADI with pitch ladder.

Renders:
  - Sky / ground background (rotated with bank)
  - Pitch ladder: lines + labels, translated by pitch, rotated by bank
  - Bank arc scale: fixed arc with tick marks at ±10/20/30/45/60°
  - Roll pointer: triangle that moves with the current bank angle
  - Aircraft reference: fixed wing-stub lines and centre dot
  - All clipped to a configurable viewport rectangle

Coordinate conventions
----------------------
  - ``viewport`` uses the same ``[x, y_bottom, width, height]`` convention as
    ``VectorTape`` (Arcade y-up, bottom-left origin).
  - Positive pitch  = nose up → horizon bar moves below centre.
  - Positive bank   = right bank → background rotates clockwise.
  - Pitch ladder lines at pitch angle ``p`` are labelled with ``|p|``; their
    position relative to centre is ``(p - aircraft_pitch) * pixels_per_degree``.

YAML schema
-----------
    - type: AttitudeIndicator
      name: ai
      viewport: [50, 100, 300, 300]         # [x, y_bottom, w, h]
      pitch_dataref: sim/cockpit2/gauges/indicators/pitch_deg
      roll_dataref:  sim/cockpit2/gauges/indicators/roll_deg
      pixels_per_degree: 8.0
      sky_color:          [0, 100, 180, 255]
      ground_color:       [100, 60,  10, 255]
      horizon_color:      [255, 255, 255]
      horizon_width:      3
      ladder_color:       [255, 255, 255]
      ladder_width:       2
      label_font_size:    14
      bank_arc_color:     [255, 255, 255]
      bank_arc_width:     2
      bank_arc_radius:    0     # 0 → auto: 0.45 * min(viewport_w, viewport_h)
      bank_arc_y_offset:  0     # shift arc centre up (+) or down (−) from viewport centre (px)
      show_arc_bg:        false # filled region above the arc (follows arc contour, fills to top)
      arc_bg_color:       [0, 100, 180, 255]  # omit to default to sky_color
      arc_bg_inset:       0     # gap in px between arc line and bottom edge of background
      show_arc_line:      true  # set false to hide the arc outline and 0° reference mark
      arc_ref_shape:      tick  # "tick" (line) or "arrow" (triangle pointing inward)
      arc_ref_height:     10    # length of tick / height of arrow (px)
      arc_ref_width:      10    # base width of arrow (px); ignored for tick
      arc_ref_filled:     true  # arrow only: false → outline triangle
      arc_ref_line_width: 2     # arrow outline width (px) when arc_ref_filled is false
      arc_ref_offset:     0     # radial shift of mark base from arc (+outward, −inward)
      show_arc_ticks:     true  # set false to hide the ±10/20/30/45/60° tick marks
      bank_tick_10:       6     # tick length in px for the ±10° marks
      bank_tick_20:       6     # tick length in px for the ±20° marks
      bank_tick_30:       10    # tick length in px for the ±30° marks
      bank_tick_45:       6     # tick length in px for the ±45° marks
      bank_tick_60:       6     # tick length in px for the ±60° marks
      ticks_inward:       true  # true → ticks point toward centre; false → outward from arc
      roll_pointer_color:      [255, 255, 255]
      roll_pointer_size:       12    # legacy single-value shorthand; sets both height and width
      roll_pointer_height:     12    # height of triangle (base-to-tip, px)
      roll_pointer_width:      12    # full base width of triangle (px)
      roll_pointer_filled:     true  # false → outline only
      roll_pointer_inward:     true  # true → tip toward centre; false → tip outward from arc
      roll_pointer_line_width: 2     # line width when roll_pointer_filled is false
      roll_pointer_y_offset:   0     # radial shift of pointer base from arc (+outward, −inward)
      corner_radius:           0     # rounded corner radius in px (0 = sharp rectangular viewport)
      corner_bg_color:         [0, 0, 0, 255]  # color used to mask the corners in the runtime
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

import arcade

from gauge_core.lookup import lookup_piecewise
from gauge_core.registry import get_convert, register_component
from gauge_core.vector_primitives import _VecBase, _as_color, _as_dataref


_BANK_TICKS   = [10, 20, 30, 45, 60]  # drawn on both sides (± each)
_LADDER_RANGE = 90   # draw ladder from -90° to +90°


def _rot(x: float, y: float, cos_b: float, sin_b: float,
         cx: float, cy: float) -> tuple[float, float]:
    """Rotate (x, y) around origin by the given cos/sin, then offset to (cx, cy)."""
    return cx + x * cos_b - y * sin_b, cy + x * sin_b + y * cos_b


class AttitudeIndicator(_VecBase):
    """Glass-cockpit attitude indicator with pitch ladder."""

    def __init__(
        self,
        name: str,
        viewport: tuple[float, float, float, float],
        ppu: float = 8.0,
        sky_color: tuple = (0, 100, 180, 255),
        ground_color: tuple = (100, 60, 10, 255),
        horizon_color: tuple = (255, 255, 255, 255),
        horizon_width: float = 3.0,
        ladder_color: tuple = (255, 255, 255, 255),
        ladder_width: float = 2.0,
        label_font_size: int = 14,
        bank_arc_color: tuple = (255, 255, 255, 255),
        bank_arc_width: float = 2.0,
        bank_arc_radius: float = 0.0,
        roll_pointer_color: tuple = (255, 255, 255, 255),
        roll_pointer_height: float = 12.0,
        roll_pointer_width: float = 12.0,
        roll_pointer_filled: bool = True,
        roll_pointer_inward: bool = True,
        roll_pointer_line_width: float = 2.0,
        roll_pointer_y_offset: float = 0.0,
        ladder_step: float = 5.0,
        ladder_hw_4: float = 0.40,
        ladder_hw_2: float = 0.31,
        ladder_hw_1: float = 0.22,
        ladder_font_name: str = "",
        ladder_bold: bool = False,
        ladder_italic: bool = False,
        smoothing: float = 0.0,
        show_reference: bool = True,
        show_arc_line: bool = True,
        arc_ref_shape: str = "tick",
        arc_ref_height: float = 10.0,
        arc_ref_width: float = 10.0,
        arc_ref_filled: bool = True,
        arc_ref_line_width: float = 2.0,
        arc_ref_offset: float = 0.0,
        show_arc_ticks: bool = True,
        bank_arc_y_offset: float = 0.0,
        bank_tick_10: float = 6.0,
        bank_tick_20: float = 6.0,
        bank_tick_30: float = 10.0,
        bank_tick_45: float = 6.0,
        bank_tick_60: float = 6.0,
        ticks_inward: bool = True,
        show_arc_bg: bool = False,
        arc_bg_color: tuple | None = None,
        arc_bg_inset: float = 0.0,
        corner_radius: float = 0.0,
        corner_bg_color: tuple = (0, 0, 0, 255),
    ) -> None:
        self.name = name
        self._vx = float(viewport[0])
        self._vy = float(viewport[1])
        self._vw = float(viewport[2])
        self._vh = float(viewport[3])
        self._ppu         = float(ppu)
        self._sky_color   = sky_color
        self._gnd_color   = ground_color
        self._hor_color   = horizon_color
        self._hor_width   = float(horizon_width)
        self._ldr_color   = ladder_color
        self._ldr_width   = float(ladder_width)
        self._font_size   = int(label_font_size)
        self._arc_color   = bank_arc_color
        self._arc_width   = float(bank_arc_width)
        self._arc_r       = float(bank_arc_radius)
        self._ptr_color   = roll_pointer_color
        self._ptr_h       = float(roll_pointer_height)
        self._ptr_w       = float(roll_pointer_width)
        self._ptr_filled  = bool(roll_pointer_filled)
        self._ptr_inward  = bool(roll_pointer_inward)
        self._ptr_line_w  = float(roll_pointer_line_width)
        self._ptr_y_off   = float(roll_pointer_y_offset)
        self._ladder_step = float(ladder_step)
        self._ladder_hw_4 = float(ladder_hw_4)
        self._ladder_hw_2 = float(ladder_hw_2)
        self._ladder_hw_1 = float(ladder_hw_1)
        self._ladder_font  = str(ladder_font_name)
        self._ladder_bold  = bool(ladder_bold)
        self._ladder_italic = bool(ladder_italic)
        # Clamp to [0, 0.99]: 0 = no smoothing, higher = heavier EMA low-pass.
        self._smooth = max(0.0, min(0.99, float(smoothing)))
        self._show_reference = bool(show_reference)
        self._show_arc_line    = bool(show_arc_line)
        self._arc_ref_shape    = str(arc_ref_shape)
        self._arc_ref_h        = float(arc_ref_height)
        self._arc_ref_w        = float(arc_ref_width)
        self._arc_ref_filled   = bool(arc_ref_filled)
        self._arc_ref_line_w   = float(arc_ref_line_width)
        self._arc_ref_offset   = float(arc_ref_offset)
        self._show_arc_ticks   = bool(show_arc_ticks)
        self._arc_y_offset   = float(bank_arc_y_offset)
        self._tick_lens = {
            10: float(bank_tick_10),
            20: float(bank_tick_20),
            30: float(bank_tick_30),
            45: float(bank_tick_45),
            60: float(bank_tick_60),
        }
        self._ticks_inward = bool(ticks_inward)
        self._show_arc_bg    = bool(show_arc_bg)
        self._arc_bg_color   = arc_bg_color
        self._arc_bg_inset   = float(arc_bg_inset)
        self._corner_radius  = float(corner_radius)
        self._corner_bg_color = corner_bg_color
        # Reusable Text objects — grown lazily on first draw, never recreated.
        self._lbl_pool_r: list[arcade.Text] = []   # right side, anchor_x="left"
        self._lbl_pool_l: list[arcade.Text] = []   # left  side, anchor_x="right"
        self._pitch: float = 0.0
        self._bank:  float = 0.0
        self._pitch_dr:   Any | None      = None
        self._pitch_conv: Callable | None = None
        self._bank_dr:    Any | None      = None
        self._bank_conv:  Callable | None = None
        self._init_visibility()

    # ── dataref wiring ──────────────────────────────────────────────────────

    def set_pitch_dataref(self, dataref: Any,
                          convert_fn: str | None = None) -> None:
        self._pitch_dr = _as_dataref(dataref)
        if convert_fn:
            self._pitch_conv = get_convert(convert_fn)

    def set_roll_dataref(self, dataref: Any,
                         convert_fn: str | None = None) -> None:
        self._bank_dr = _as_dataref(dataref)
        if convert_fn:
            self._bank_conv = get_convert(convert_fn)

    # ── panel composition ───────────────────────────────────────────────────

    def apply_scale(self, scale: float) -> None:
        self._vx *= scale;  self._vy *= scale
        self._vw *= scale;  self._vh *= scale
        self._ppu       *= scale
        self._arc_r        *= scale
        self._arc_y_offset *= scale
        self._ptr_h        *= scale
        self._ptr_w        *= scale
        self._ptr_line_w   *= scale
        self._ptr_y_off    *= scale
        self._tick_lens = {a: v * scale for a, v in self._tick_lens.items()}
        self._hor_width      *= scale
        self._ldr_width      *= scale
        self._arc_width      *= scale
        self._arc_bg_inset   *= scale
        self._arc_ref_h      *= scale
        self._arc_ref_w      *= scale
        self._arc_ref_line_w *= scale
        self._arc_ref_offset *= scale
        self._corner_radius  *= scale
        self._font_size  = max(6, int(self._font_size * scale))

    def apply_offset(self, dx: float, dy: float) -> None:
        self._vx += dx;  self._vy += dy

    # ── per-frame update ────────────────────────────────────────────────────

    def update(self, get_data: Callable[[Any], float]) -> None:
        self._update_visibility(get_data)
        alpha = 1.0 - self._smooth
        if self._pitch_dr is not None:
            raw = float(get_data(self._pitch_dr))
            if self._pitch_conv is not None:
                raw = float(self._pitch_conv(raw, get_data))
            self._pitch = raw if self._smooth == 0.0 else self._pitch + alpha * (raw - self._pitch)
        if self._bank_dr is not None:
            raw = float(get_data(self._bank_dr))
            if self._bank_conv is not None:
                raw = float(self._bank_conv(raw, get_data))
            self._bank = raw if self._smooth == 0.0 else self._bank + alpha * (raw - self._bank)

    # ── draw ────────────────────────────────────────────────────────────────

    def draw(self) -> None:
        if not self._visible:
            return
        vx, vy, vw, vh = self._vx, self._vy, self._vw, self._vh
        cx = vx + vw / 2.0
        cy = vy + vh / 2.0

        bank_rad = math.radians(self._bank)
        cos_b = math.cos(bank_rad)
        sin_b = math.sin(bank_rad)
        pitch_y = -self._pitch * self._ppu
        arc_r  = self._arc_r if self._arc_r > 0.0 else 0.45 * min(vw, vh)
        arc_cy = cy + self._arc_y_offset

        # Clip to the viewport rectangle using the GL scissor test.
        # Scale from logical coords to FBO pixels: in SSAA mode the active FBO
        # is N× larger than the window, so the ratio handles both cases.
        win = arcade.get_window()
        ctx = win.ctx
        fw, fh = ctx.fbo.size
        sx = fw / win.width
        sy = fh / win.height
        ctx.scissor = (int(vx * sx), int(vy * sy), int(vw * sx), int(vh * sy))

        self._draw_background(cx, cy, pitch_y, cos_b, sin_b, vw, vh)
        self._draw_horizon(cx, cy, pitch_y, cos_b, sin_b)
        self._draw_ladder(cx, cy, pitch_y, cos_b, sin_b, vw, lines=True, labels=True)
        if self._show_arc_bg:
            self._draw_arc_background(cx, arc_cy, arc_r)
        if self._show_arc_line or self._show_arc_ticks:
            self._draw_bank_arc(cx, arc_cy, arc_r)
        self._draw_roll_pointer(cx, arc_cy, arc_r)
        if self._show_reference:
            self._draw_reference(cx, cy)
        if self._corner_radius > 0:
            self._draw_corner_cuts(vx, vy, vw, vh)

        ctx.scissor = None  # restore — no scissor for other components

    # ── sub-draw helpers ─────────────────────────────────────────────────────

    def _draw_background(self, cx, cy, pitch_y, cos_b, sin_b, vw, vh) -> None:
        big = (vw + vh) * 2
        sky_pts = [
            _rot(-big, pitch_y,       cos_b, sin_b, cx, cy),
            _rot( big, pitch_y,       cos_b, sin_b, cx, cy),
            _rot( big, pitch_y + big, cos_b, sin_b, cx, cy),
            _rot(-big, pitch_y + big, cos_b, sin_b, cx, cy),
        ]
        gnd_pts = [
            _rot(-big, pitch_y - big, cos_b, sin_b, cx, cy),
            _rot( big, pitch_y - big, cos_b, sin_b, cx, cy),
            _rot( big, pitch_y,       cos_b, sin_b, cx, cy),
            _rot(-big, pitch_y,       cos_b, sin_b, cx, cy),
        ]
        arcade.draw_polygon_filled(sky_pts, self._sky_color)
        arcade.draw_polygon_filled(gnd_pts, self._gnd_color)

    def _draw_horizon(self, cx, cy, pitch_y, cos_b, sin_b) -> None:
        big = 20000.0
        x1, y1 = _rot(-big, pitch_y, cos_b, sin_b, cx, cy)
        x2, y2 = _rot( big, pitch_y, cos_b, sin_b, cx, cy)
        arcade.draw_line(x1, y1, x2, y2, self._hor_color, self._hor_width)

    def _draw_ladder(
        self, cx, cy, pitch_y, cos_b, sin_b, vw,
        *, lines: bool = True, labels: bool = True,
    ) -> None:
        half_vw = vw / 2.0
        hw_4 = half_vw * self._ladder_hw_4
        hw_2 = half_vw * self._ladder_hw_2
        hw_1 = half_vw * self._ladder_hw_1

        n_steps = round(_LADDER_RANGE / self._ladder_step)
        lbl_idx = 0
        for i in range(-n_steps, n_steps + 1):
            if i == 0:
                continue  # horizon is drawn separately
            p = i * self._ladder_step
            y_ai  = pitch_y + p * self._ppu
            abs_i = abs(i)
            if abs_i % 4 == 0:
                hw, lw, labeled = hw_4, self._hor_width, True
            elif abs_i % 2 == 0:
                hw, lw, labeled = hw_2, self._ldr_width, False
            else:
                hw, lw, labeled = hw_1, self._ldr_width, False

            if lines:
                x1, y1 = _rot(-hw, y_ai, cos_b, sin_b, cx, cy)
                x2, y2 = _rot( hw, y_ai, cos_b, sin_b, cx, cy)
                arcade.draw_line(x1, y1, x2, y2, self._ldr_color, lw)

            if labeled:
                if labels:
                    label_text = str(abs(round(p)))
                    gap   = 6
                    lx_r, ly_r = _rot( hw + gap, y_ai, cos_b, sin_b, cx, cy)
                    lx_l, ly_l = _rot(-(hw + gap), y_ai, cos_b, sin_b, cx, cy)
                    rot  = -self._bank  # arcade Text.rotation is CW positive; bank is CCW positive

                    if lbl_idx >= len(self._lbl_pool_r):
                        fkw: dict = {"bold": self._ladder_bold, "italic": self._ladder_italic}
                        if self._ladder_font:
                            fkw["font_name"] = self._ladder_font
                        self._lbl_pool_r.append(arcade.Text(
                            "", 0.0, 0.0, color=self._ldr_color,
                            font_size=self._font_size, anchor_x="left", anchor_y="center",
                            **fkw,
                        ))
                        self._lbl_pool_l.append(arcade.Text(
                            "", 0.0, 0.0, color=self._ldr_color,
                            font_size=self._font_size, anchor_x="right", anchor_y="center",
                            **fkw,
                        ))

                    tr = self._lbl_pool_r[lbl_idx]
                    tr.text = label_text
                    tr.x = lx_r;  tr.y = ly_r;  tr.rotation = rot
                    tr.draw()

                    tl = self._lbl_pool_l[lbl_idx]
                    tl.text = label_text
                    tl.x = lx_l;  tl.y = ly_l;  tl.rotation = rot
                    tl.draw()

                lbl_idx += 1

    def _draw_arc_background(self, cx: float, arc_cy: float, arc_r: float) -> None:
        bg_color = self._arc_bg_color if self._arc_bg_color is not None else self._sky_color
        # Fill the region between the arc contour and the top of the viewport
        # (the "cap" above the arc, not the interior pie sector).
        # arc_bg_inset shrinks the polygon radius so the fill starts that many
        # pixels away from the arc line, leaving a visible gap.
        # Build a GL_TRIANGLE_FAN polygon anchored at the viewport top-centre;
        # all other vertices lie at or below that edge so the fan is valid.
        r_bg     = max(0.0, arc_r - self._arc_bg_inset)
        vx_left  = self._vx
        vx_right = self._vx + self._vw
        vy_top   = self._vy + self._vh
        n = 64
        pts: list[tuple[float, float]] = [(cx, vy_top), (vx_left, vy_top)]
        for i in range(n + 1):
            theta = math.radians(150.0 - 120.0 * i / n)  # 150° → 30° left to right
            pts.append((cx + r_bg * math.cos(theta),
                        arc_cy + r_bg * math.sin(theta)))
        pts.append((vx_right, vy_top))
        arcade.draw_polygon_filled(pts, bg_color)

    def _draw_bank_arc(self, cx, arc_cy, arc_r) -> None:
        if self._show_arc_line:
            # Arc spans ±60° from vertical (upper portion of circle).
            # Arcade angle convention: 0=right, CCW positive.
            # Our ±60° bank arc runs from arcade-angle 30° (upper-right, +60° bank)
            # to 150° (upper-left, -60° bank).
            arcade.draw_arc_outline(
                cx, arc_cy,
                arc_r * 2, arc_r * 2,
                self._arc_color,
                30.0, 150.0,
                self._arc_width,
                num_segments=64,
            )
        # 0° reference mark — drawn whenever bank arc is visible (line or ticks)
        top_y = arc_cy + arc_r + self._arc_ref_offset
        if self._arc_ref_shape == "arrow":
            pts = [(cx, top_y - self._arc_ref_h),
                   (cx - self._arc_ref_w * 0.5, top_y),
                   (cx + self._arc_ref_w * 0.5, top_y)]
            if self._arc_ref_filled:
                arcade.draw_polygon_filled(pts, self._arc_color)
            else:
                arcade.draw_polygon_outline(pts, self._arc_color, self._arc_ref_line_w)
        else:
            arcade.draw_line(cx, top_y - self._arc_ref_h,
                             cx, top_y,
                             self._arc_color, self._arc_width + 1)
        if self._show_arc_ticks:
            # Tick marks at ±10/20/30/45/60°
            for a in _BANK_TICKS:
                for sign in (-1, 1):
                    ba_rad = math.radians(sign * a)
                    tick_len = self._tick_lens[a]
                    if self._ticks_inward:
                        ox = cx + arc_r * math.sin(ba_rad)
                        oy = arc_cy + arc_r * math.cos(ba_rad)
                        ix = cx + (arc_r - tick_len) * math.sin(ba_rad)
                        iy = arc_cy + (arc_r - tick_len) * math.cos(ba_rad)
                    else:
                        ix = cx + arc_r * math.sin(ba_rad)
                        iy = arc_cy + arc_r * math.cos(ba_rad)
                        ox = cx + (arc_r + tick_len) * math.sin(ba_rad)
                        oy = arc_cy + (arc_r + tick_len) * math.cos(ba_rad)
                    arcade.draw_line(ix, iy, ox, oy,
                                     self._arc_color, self._arc_width)

    def _draw_roll_pointer(self, cx, arc_cy, arc_r) -> None:
        bank_rad = math.radians(-self._bank)
        ux =  math.sin(bank_rad)   # outward radial unit vector
        uy =  math.cos(bank_rad)
        px_v = -uy                 # perpendicular (CCW from outward)
        py_v =  ux
        r_ptr = arc_r + self._ptr_y_off   # radial offset shifts base outward (+) or inward (−)
        bx = cx     + r_ptr * ux
        by = arc_cy + r_ptr * uy
        half_w = self._ptr_w * 0.5
        # inward → tip toward centre (−radial); outward → tip away from arc (+radial)
        sign = -1.0 if self._ptr_inward else 1.0
        tip = (bx + sign * ux * self._ptr_h, by + sign * uy * self._ptr_h)
        p1  = (bx + px_v * half_w, by + py_v * half_w)
        p2  = (bx - px_v * half_w, by - py_v * half_w)
        pts = [tip, p1, p2]
        if self._ptr_filled:
            arcade.draw_polygon_filled(pts, self._ptr_color)
        else:
            arcade.draw_polygon_outline(pts, self._ptr_color, self._ptr_line_w)

    def _draw_corner_cuts(self, vx: float, vy: float, vw: float, vh: float) -> None:
        """Overdraw the 4 corner regions outside the rounded rectangle with corner_bg_color.

        Each corner is drawn as a fan of individual triangles (corner → arc[i] → arc[i+1])
        rather than a single polygon call, which avoids Arcade's earclip winding issues.
        """
        r = min(self._corner_radius, vw * 0.5, vh * 0.5)
        n = 32
        # (corner_x, corner_y, arc_cx, arc_cy, a_start_deg, a_end_deg)
        corners = [
            (vx,      vy + vh, vx + r,      vy + vh - r,  90.0, 180.0),  # top-left
            (vx + vw, vy + vh, vx + vw - r, vy + vh - r,   0.0,  90.0),  # top-right
            (vx,      vy,      vx + r,      vy + r,        180.0, 270.0),  # bottom-left
            (vx + vw, vy,      vx + vw - r, vy + r,        270.0, 360.0),  # bottom-right
        ]
        c = self._corner_bg_color
        for corner_x, corner_y, cx, cy, a0, a1 in corners:
            prev_x = cx + r * math.cos(math.radians(a0))
            prev_y = cy + r * math.sin(math.radians(a0))
            for i in range(1, n + 1):
                theta = math.radians(a0 + (a1 - a0) * i / n)
                next_x = cx + r * math.cos(theta)
                next_y = cy + r * math.sin(theta)
                arcade.draw_triangle_filled(corner_x, corner_y,
                                            prev_x, prev_y,
                                            next_x, next_y, c)
                prev_x, prev_y = next_x, next_y

    def _draw_reference(self, cx, cy) -> None:
        # Fixed aircraft reference: two horizontal wing stubs + centre dot.
        stub = 30.0
        gap  =  6.0
        arcade.draw_line(cx - stub - gap, cy, cx - gap, cy, self._ptr_color, 3)
        arcade.draw_line(cx + gap, cy, cx + stub + gap, cy, self._ptr_color, 3)
        arcade.draw_circle_filled(cx, cy, 4, self._ptr_color)


# ── Factory + registration ────────────────────────────────────────────────────

def _ai_factory(
    comp: dict[str, Any],
    base_dir: Path,
    container_size: tuple[int, int] | None = None,
) -> AttitudeIndicator:
    ai = AttitudeIndicator(
        name=comp["name"],
        viewport=tuple(comp["viewport"]),
        ppu=float(comp.get("pixels_per_degree", 8.0)),
        sky_color=_as_color(comp.get("sky_color",   [0, 100, 180])),
        ground_color=_as_color(comp.get("ground_color", [100, 60, 10])),
        horizon_color=_as_color(comp.get("horizon_color")),
        horizon_width=float(comp.get("horizon_width", 3.0)),
        ladder_color=_as_color(comp.get("ladder_color")),
        ladder_width=float(comp.get("ladder_width", 2.0)),
        label_font_size=int(comp.get("label_font_size", 14)),
        bank_arc_color=_as_color(comp.get("bank_arc_color")),
        bank_arc_width=float(comp.get("bank_arc_width", 2.0)),
        bank_arc_radius=float(comp.get("bank_arc_radius", 0.0)),
        roll_pointer_color=_as_color(comp.get("roll_pointer_color")),
        roll_pointer_height=float(comp.get("roll_pointer_height",
                                           comp.get("roll_pointer_size", 12.0))),
        roll_pointer_width=float(comp.get("roll_pointer_width",
                                          comp.get("roll_pointer_size", 12.0))),
        roll_pointer_filled=bool(comp.get("roll_pointer_filled", True)),
        roll_pointer_inward=bool(comp.get("roll_pointer_inward", True)),
        roll_pointer_line_width=float(comp.get("roll_pointer_line_width", 2.0)),
        roll_pointer_y_offset=float(comp.get("roll_pointer_y_offset", 0.0)),
        ladder_step=float(comp.get("ladder_step", 5.0)),
        ladder_hw_4=float(comp.get("ladder_hw_4", 0.40)),
        ladder_hw_2=float(comp.get("ladder_hw_2", 0.31)),
        ladder_hw_1=float(comp.get("ladder_hw_1", 0.22)),
        ladder_font_name=str(comp.get("ladder_font_name", "")),
        ladder_bold=bool(comp.get("ladder_bold", False)),
        ladder_italic=bool(comp.get("ladder_italic", False)),
        smoothing=float(comp.get("smoothing", 0.0)),
        show_reference=bool(comp.get("show_reference", True)),
        show_arc_line=bool(comp.get("show_arc_line", comp.get("show_bank_arc", True))),
        arc_ref_shape=str(comp.get("arc_ref_shape", "tick")),
        arc_ref_height=float(comp.get("arc_ref_height", 10.0)),
        arc_ref_width=float(comp.get("arc_ref_width", 10.0)),
        arc_ref_filled=bool(comp.get("arc_ref_filled", True)),
        arc_ref_line_width=float(comp.get("arc_ref_line_width", 2.0)),
        arc_ref_offset=float(comp.get("arc_ref_offset", 0.0)),
        show_arc_ticks=bool(comp.get("show_arc_ticks", comp.get("show_bank_arc", True))),
        bank_arc_y_offset=float(comp.get("bank_arc_y_offset", 0.0)),
        bank_tick_10=float(comp.get("bank_tick_10", 6.0)),
        bank_tick_20=float(comp.get("bank_tick_20", 6.0)),
        bank_tick_30=float(comp.get("bank_tick_30", 10.0)),
        bank_tick_45=float(comp.get("bank_tick_45", 6.0)),
        bank_tick_60=float(comp.get("bank_tick_60", 6.0)),
        ticks_inward=bool(comp.get("ticks_inward", True)),
        show_arc_bg=bool(comp.get("show_arc_bg", False)),
        arc_bg_color=(_as_color(comp["arc_bg_color"]) if "arc_bg_color" in comp else None),
        arc_bg_inset=float(comp.get("arc_bg_inset", 0.0)),
        corner_radius=float(comp.get("corner_radius", 0.0)),
        corner_bg_color=(_as_color(comp["corner_bg_color"])
                         if "corner_bg_color" in comp else (0, 0, 0, 255)),
    )
    if "pitch_dataref" in comp:
        ai.set_pitch_dataref(comp["pitch_dataref"],
                             comp.get("pitch_convert_function"))
    if "roll_dataref" in comp:
        ai.set_roll_dataref(comp["roll_dataref"],
                            comp.get("roll_convert_function"))
    if "visibility" in comp:
        v = comp["visibility"]
        ai.set_visibility(v["dataref"], v["predicate"])
    return ai


register_component("AttitudeIndicator", _ai_factory)
