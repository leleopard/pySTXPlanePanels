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
      show_slip:               false # enable the slip/skid rectangle indicator
      slip_dataref:            sim/cockpit2/gauges/indicators/slip_deg
      slip_color:              [255, 255, 255, 255]
      slip_width:              20    # width of rectangle along the arc (px)
      slip_height:             8     # height of rectangle along the radial direction (px)
      slip_filled:             true  # false → outline only
      slip_line_width:         2     # outline width when slip_filled is false
      slip_offset:             0     # radial shift of rectangle base from arc (+outward, −inward)
      slip_scale:              2.0   # pixels of lateral displacement per unit of the slip dataref

Aircraft reference (centre bug + wing bars):
      show_reference:          true
      centre_bug_points:       []          # list of [x,y] pairs relative to AI centre (empty → legacy dot)
      centre_bug_filled:       true
      centre_bug_fill_color:   [0, 0, 0, 255]
      centre_bug_outline_color: [255, 255, 255, 255]
      centre_bug_outline_width: 2.0
      wing_points:             []          # left wing points; right wing is auto-mirrored (empty → legacy stubs)
      wing_filled:             true
      wing_fill_color:         [0, 0, 0, 255]
      wing_outline_color:      [255, 255, 255, 255]
      wing_outline_width:      2.0

Flight director (cross-pointer / dual-cue):
      show_fd_h_bar:           false # horizontal bar (pitch command)
      fd_pitch_dataref:        sim/cockpit/autopilot/flight_director_pitch
      fd_pitch_convert_function: ~  # optional
      fd_pitch_scale:          8.0  # pixels per dataref unit (matches pixels_per_degree by default)
      fd_h_visibility:         ~    # optional (omit → always visible); either
        dataref:               ~    #   dataref + predicate: <registered convert fn>
        predicate:             true_if_over_zero
                               #   or dataref + operator/value (no convert fn needed):
                               #   dataref: ...
                               #   operator: ">="   # <, <=, ==, !=, >, >=
                               #   value: 0.5
      fd_h_color:              [255, 200, 0, 255]
      fd_h_length:             200  # full bar length in px
      fd_h_width:              3

      show_fd_v_bar:           false # vertical bar (roll command)
      fd_roll_dataref:         sim/cockpit/autopilot/flight_director_roll
      fd_roll_convert_function: ~
      fd_roll_scale:           4.0
      fd_v_visibility:         ~    # same shape as fd_h_visibility
      fd_v_color:              [255, 200, 0, 255]
      fd_v_length:             200
      fd_v_width:              3
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

import arcade
import pyglet

from gauge_core.lookup import lookup_piecewise
from gauge_core.registry import get_convert, register_component, resolve_predicate_name
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
        show_slip: bool = False,
        slip_color: tuple = (255, 255, 255, 255),
        slip_width: float = 20.0,
        slip_height: float = 8.0,
        slip_filled: bool = True,
        slip_line_width: float = 2.0,
        slip_offset: float = 0.0,
        slip_scale: float = 2.0,
        centre_bug_points: list = (),
        centre_bug_filled: bool = True,
        centre_bug_fill_color: tuple = (0, 0, 0, 255),
        centre_bug_outline_color: tuple = (255, 255, 255, 255),
        centre_bug_outline_width: float = 2.0,
        wing_points: list = (),
        wing_filled: bool = True,
        wing_fill_color: tuple = (0, 0, 0, 255),
        wing_outline_color: tuple = (255, 255, 255, 255),
        wing_outline_width: float = 2.0,
        show_fd_h_bar: bool = False,
        fd_h_color: tuple = (255, 200, 0, 255),
        fd_h_length: float = 200.0,
        fd_h_width: float = 3.0,
        fd_h_scale: float = 8.0,
        show_fd_v_bar: bool = False,
        fd_v_color: tuple = (255, 200, 0, 255),
        fd_v_length: float = 200.0,
        fd_v_width: float = 3.0,
        fd_v_scale: float = 4.0,
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
        self._corner_radius   = float(corner_radius)
        self._corner_bg_color = corner_bg_color
        self._show_slip       = bool(show_slip)
        self._slip_color      = slip_color
        self._slip_w          = float(slip_width)
        self._slip_h          = float(slip_height)
        self._slip_filled     = bool(slip_filled)
        self._slip_line_w     = float(slip_line_width)
        self._slip_offset     = float(slip_offset)
        self._slip_scale      = float(slip_scale)
        self._slip:  float    = 0.0
        self._slip_dr:   Any | None      = None
        self._slip_conv: Callable | None = None
        # Aircraft reference polygons
        self._bug_pts = [(float(p[0]), float(p[1])) for p in (centre_bug_points or [])]
        self._bug_filled = bool(centre_bug_filled)
        self._bug_fill = centre_bug_fill_color
        self._bug_outline = centre_bug_outline_color
        self._bug_outline_w = float(centre_bug_outline_width)
        self._wing_pts = [(float(p[0]), float(p[1])) for p in (wing_points or [])]
        self._wing_filled = bool(wing_filled)
        self._wing_fill = wing_fill_color
        self._wing_outline = wing_outline_color
        self._wing_outline_w = float(wing_outline_width)
        # Flight director — horizontal bar (pitch command)
        self._show_fd_h   = bool(show_fd_h_bar)
        self._fd_h_color  = fd_h_color
        self._fd_h_len    = float(fd_h_length)
        self._fd_h_w      = float(fd_h_width)
        self._fd_h_scale  = float(fd_h_scale)
        self._fd_h_defl:  float          = 0.0
        self._fd_h_vis:   bool           = True
        self._fd_h_dr:    Any | None     = None
        self._fd_h_conv:  Callable | None = None
        self._fd_h_vis_dr: Any | None    = None
        self._fd_h_vis_pred: Callable | None = None
        # Flight director — vertical bar (roll command)
        self._show_fd_v   = bool(show_fd_v_bar)
        self._fd_v_color  = fd_v_color
        self._fd_v_len    = float(fd_v_length)
        self._fd_v_w      = float(fd_v_width)
        self._fd_v_scale  = float(fd_v_scale)
        self._fd_v_defl:  float          = 0.0
        self._fd_v_vis:   bool           = True
        self._fd_v_dr:    Any | None     = None
        self._fd_v_conv:  Callable | None = None
        self._fd_v_vis_dr: Any | None    = None
        self._fd_v_vis_pred: Callable | None = None
        # Reusable Text objects — grown lazily on first draw, never recreated.
        self._lbl_pool_r: list[arcade.Text] = []   # right side, anchor_x="left"
        self._lbl_pool_l: list[arcade.Text] = []   # left  side, anchor_x="right"
        # Shared by every pooled ladder label — same reasoning as
        # VectorCompassRose's own _heading_label_batch/_map_label_batch:
        # each arcade.Text.draw() with no shared batch draws its own
        # private one-label batch, which measured ~180x more expensive
        # than one shared batch drawn once for a comparable label count.
        self._ladder_label_batch = pyglet.graphics.Batch()
        # Baked once (lazily) in local (pitch=0, bank=0) coordinates and
        # positioned/rotated each frame via Sprite.position/.angle, instead
        # of recomputing every ladder line's endpoints in Python and issuing
        # one draw_line() call per line every frame (measured ~6ms/frame on
        # their own). angle = self._bank directly (not e.g. -bank or
        # bank+180) and the bake uses NO y-negation when converting to PIL
        # pixel space — both empirically calibrated against _rot()'s own
        # ground truth via the real PanelWindow pipeline; this is a
        # different convention than VectorCompassRose's tick sprite (which
        # rotates via the compass _point_at() convention, angle=heading+180,
        # bake WITH y-negation) because _rot() has different handedness.
        self._ladder_sprites: arcade.SpriteList | None = None
        self._pitch: float = 0.0
        self._bank:  float = 0.0
        self._pitch_dr:   Any | None      = None
        self._pitch_conv: Callable | None = None
        self._bank_dr:    Any | None      = None
        self._bank_conv:  Callable | None = None
        # Static (rebuilt only when stale — never rebuilt every frame): both
        # depend only on viewport/arc geometry that's fixed after
        # apply_scale(), never on pitch/bank/slip, so there's nothing to
        # recompute per frame at all once built once, lazily, on first draw.
        self._corner_sprites: arcade.SpriteList | None = None
        self._arc_bg_shape: arcade.ShapeElementList | None = None
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

    def set_slip_dataref(self, dataref: Any,
                         convert_fn: str | None = None) -> None:
        self._slip_dr = _as_dataref(dataref)
        if convert_fn:
            self._slip_conv = get_convert(convert_fn)

    def set_fd_h_dataref(self, dataref: Any, convert_fn: str | None = None,
                         vis_dataref: Any = None, vis_predicate: str | None = None) -> None:
        self._fd_h_dr = _as_dataref(dataref)
        if convert_fn:
            self._fd_h_conv = get_convert(convert_fn)
        if vis_dataref:
            self._fd_h_vis_dr = _as_dataref(vis_dataref)
        if vis_predicate:
            self._fd_h_vis_pred = get_convert(vis_predicate)

    def set_fd_v_dataref(self, dataref: Any, convert_fn: str | None = None,
                         vis_dataref: Any = None, vis_predicate: str | None = None) -> None:
        self._fd_v_dr = _as_dataref(dataref)
        if convert_fn:
            self._fd_v_conv = get_convert(convert_fn)
        if vis_dataref:
            self._fd_v_vis_dr = _as_dataref(vis_dataref)
        if vis_predicate:
            self._fd_v_vis_pred = get_convert(vis_predicate)

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
        self._slip_w         *= scale
        self._slip_h         *= scale
        self._slip_line_w    *= scale
        self._slip_offset    *= scale
        self._slip_scale     *= scale
        self._fd_h_len   *= scale
        self._fd_h_w     *= scale
        self._fd_h_scale *= scale
        self._fd_v_len   *= scale
        self._fd_v_w     *= scale
        self._fd_v_scale *= scale
        self._bug_pts = [(x * scale, y * scale) for x, y in self._bug_pts]
        self._bug_outline_w *= scale
        self._wing_pts = [(x * scale, y * scale) for x, y in self._wing_pts]
        self._wing_outline_w *= scale
        self._font_size  = max(6, int(self._font_size * scale))
        # Built lazily on first draw, which always happens after every
        # apply_scale()/apply_offset() call in the normal load path — but
        # if that ever changes, stale pre-scale geometry must not survive.
        self._corner_sprites = None
        self._arc_bg_shape = None
        self._ladder_sprites = None

    def apply_offset(self, dx: float, dy: float) -> None:
        self._vx += dx;  self._vy += dy
        self._corner_sprites = None
        self._arc_bg_shape = None
        # _ladder_sprites is NOT invalidated here: its baked geometry is in
        # local (pitch=0, bank=0) coordinates, never in absolute vx/vy
        # terms — the per-frame Sprite.position call already re-derives the
        # correct screen position from the current cx/cy each draw.

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
        if self._slip_dr is not None:
            raw = float(get_data(self._slip_dr))
            if self._slip_conv is not None:
                raw = float(self._slip_conv(raw, get_data))
            self._slip = raw
        if self._show_fd_h and self._fd_h_dr is not None:
            raw = float(get_data(self._fd_h_dr))
            if self._fd_h_conv is not None:
                raw = float(self._fd_h_conv(raw, get_data))
            self._fd_h_defl = raw * self._fd_h_scale
            if self._fd_h_vis_dr is not None:
                vis_raw = float(get_data(self._fd_h_vis_dr))
                self._fd_h_vis = bool(
                    self._fd_h_vis_pred(vis_raw, get_data)
                    if self._fd_h_vis_pred else vis_raw
                )
        if self._show_fd_v and self._fd_v_dr is not None:
            raw = float(get_data(self._fd_v_dr))
            if self._fd_v_conv is not None:
                raw = float(self._fd_v_conv(raw, get_data))
            self._fd_v_defl = raw * self._fd_v_scale
            if self._fd_v_vis_dr is not None:
                vis_raw = float(get_data(self._fd_v_vis_dr))
                self._fd_v_vis = bool(
                    self._fd_v_vis_pred(vis_raw, get_data)
                    if self._fd_v_vis_pred else vis_raw
                )

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
        if self._show_reference:
            self._draw_reference_wings(cx, cy)   # wings render below FD bars
        if self._show_fd_h or self._show_fd_v:
            self._draw_flight_director(cx, cy)
        if self._show_arc_bg:
            if self._arc_bg_shape is None:
                self._build_arc_bg_shape(cx, arc_cy, arc_r)
            self._arc_bg_shape.draw()
        if self._show_arc_line or self._show_arc_ticks:
            self._draw_bank_arc(cx, arc_cy, arc_r)
        if self._show_slip:
            self._draw_slip_indicator(cx, arc_cy, arc_r)
        self._draw_roll_pointer(cx, arc_cy, arc_r)
        if self._show_reference:
            self._draw_reference_bug(cx, cy)     # centre bug renders above FD bars
        if self._corner_radius > 0:
            if self._corner_sprites is None:
                self._build_corner_sprite(vx, vy, vw, vh)
            self._corner_sprites.draw()

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

    def _build_ladder_line_sprite(self, vw: float) -> None:
        # Local (pitch=0, bank=0) coordinates — positioned/rotated each
        # frame via Sprite.position/.angle instead of recomputing every
        # line's endpoints and issuing one draw_line() call per line every
        # frame. See _ladder_sprites' own comment for the calibrated
        # bake/rotation convention (no y-negation, angle = self._bank).
        from PIL import Image, ImageDraw

        half_vw = vw / 2.0
        hw_4 = half_vw * self._ladder_hw_4
        hw_2 = half_vw * self._ladder_hw_2
        hw_1 = half_vw * self._ladder_hw_1
        max_hw = max(hw_4, hw_2, hw_1)

        n_steps = round(_LADDER_RANGE / self._ladder_step)
        max_y = n_steps * self._ladder_step * self._ppu
        pad = max(self._hor_width, self._ldr_width, 1.0) + 2.0
        w_px = max(2, int(round((max_hw + pad) * 2.0)))
        h_px = max(2, int(round((max_y + pad) * 2.0)))
        img = Image.new("RGBA", (w_px, h_px), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        cx_px, cy_px = w_px / 2.0, h_px / 2.0

        for i in range(-n_steps, n_steps + 1):
            if i == 0:
                continue  # horizon is drawn separately
            p = i * self._ladder_step
            local_y = p * self._ppu
            abs_i = abs(i)
            if abs_i % 4 == 0:
                hw, lw = hw_4, self._hor_width
            elif abs_i % 2 == 0:
                hw, lw = hw_2, self._ldr_width
            else:
                hw, lw = hw_1, self._ldr_width
            p0 = (cx_px - hw, cy_px + local_y)
            p1 = (cx_px + hw, cy_px + local_y)
            draw.line([p0, p1], fill=self._ldr_color, width=max(1, int(round(lw))))

        tex = arcade.Texture(img, hash=f"ai_ladder:{id(self)}")
        self._ladder_sprites = arcade.SpriteList()
        self._ladder_sprites.append(arcade.Sprite(tex))

    def _draw_ladder(
        self, cx, cy, pitch_y, cos_b, sin_b, vw,
        *, lines: bool = True, labels: bool = True,
    ) -> None:
        half_vw = vw / 2.0
        hw_4 = half_vw * self._ladder_hw_4
        hw_2 = half_vw * self._ladder_hw_2
        hw_1 = half_vw * self._ladder_hw_1

        if lines:
            if self._ladder_sprites is None:
                self._build_ladder_line_sprite(vw)
            sp = self._ladder_sprites[0]
            sp.position = _rot(0.0, pitch_y, cos_b, sin_b, cx, cy)
            sp.angle = self._bank
            self._ladder_sprites.draw()

        n_steps = round(_LADDER_RANGE / self._ladder_step)
        lbl_idx = 0
        for i in range(-n_steps, n_steps + 1):
            if i == 0:
                continue  # horizon is drawn separately
            p = i * self._ladder_step
            y_ai  = pitch_y + p * self._ppu
            abs_i = abs(i)
            if abs_i % 4 == 0:
                hw, labeled = hw_4, True
            elif abs_i % 2 == 0:
                hw, labeled = hw_2, False
            else:
                hw, labeled = hw_1, False

            if labeled:
                if labels:
                    gap   = 6
                    lx_r, ly_r = _rot( hw + gap, y_ai, cos_b, sin_b, cx, cy)
                    lx_l, ly_l = _rot(-(hw + gap), y_ai, cos_b, sin_b, cx, cy)
                    rot  = -self._bank  # arcade Text.rotation is CW positive; bank is CCW positive

                    if lbl_idx >= len(self._lbl_pool_r):
                        # A given pool slot always represents the same pitch
                        # value p (i doesn't change frame to frame, only
                        # self._pitch/self._bank do), so label_text is
                        # correct forever once set here — see
                        # VectorCompassRose's identical heading-label fix
                        # for the measured cost of reassigning text/font
                        # every frame anyway (~8ms for 36 labels there vs
                        # ~0.09ms updating only x/y/rotation).
                        label_text = str(abs(round(p)))
                        fkw: dict = {"bold": self._ladder_bold, "italic": self._ladder_italic}
                        if self._ladder_font:
                            fkw["font_name"] = self._ladder_font
                        self._lbl_pool_r.append(arcade.Text(
                            label_text, 0.0, 0.0, color=self._ldr_color,
                            font_size=self._font_size, anchor_x="left", anchor_y="center",
                            batch=self._ladder_label_batch,
                            **fkw,
                        ))
                        self._lbl_pool_l.append(arcade.Text(
                            label_text, 0.0, 0.0, color=self._ldr_color,
                            font_size=self._font_size, anchor_x="right", anchor_y="center",
                            batch=self._ladder_label_batch,
                            **fkw,
                        ))

                    tr = self._lbl_pool_r[lbl_idx]
                    tr.x = lx_r;  tr.y = ly_r;  tr.rotation = rot

                    tl = self._lbl_pool_l[lbl_idx]
                    tl.x = lx_l;  tl.y = ly_l;  tl.rotation = rot

                lbl_idx += 1

        if labels:
            self._ladder_label_batch.draw()

    def _build_arc_bg_shape(self, cx: float, arc_cy: float, arc_r: float) -> None:
        # This shape depends only on viewport/arc geometry (all fixed after
        # apply_scale()) — never on pitch/bank/slip — so it's built once and
        # cached, instead of rebuilding a 67-vertex polygon's throwaway VBO
        # every single frame (measured ~6.9ms/frame on its own for just this
        # one draw_polygon_filled() call).
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
        shapes = arcade.shape_list.ShapeElementList()
        shapes.append(arcade.shape_list.create_polygon(pts, bg_color))
        self._arc_bg_shape = shapes

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

    def _draw_slip_indicator(self, cx: float, arc_cy: float, arc_r: float) -> None:
        """Draw the slip/skid rectangle.

        Rotates with the roll pointer and displaces laterally (along the arc)
        by slip_scale × slip_dataref_value pixels.
        Positive slip_deg (nose right of relative wind) moves the indicator
        in the −perpendicular direction (left at bank=0, matching ball convention).
        """
        bank_rad = math.radians(-self._bank)
        ux =  math.sin(bank_rad)   # radial outward unit vector (same as roll pointer)
        uy =  math.cos(bank_rad)
        px_v = -uy                 # perpendicular, CCW from outward
        py_v =  ux

        r_slip = arc_r + self._slip_offset
        disp   = self._slip * self._slip_scale
        ctr_x  = cx     + r_slip * ux + disp * px_v
        ctr_y  = arc_cy + r_slip * uy + disp * py_v

        hw, hh = self._slip_w * 0.5, self._slip_h * 0.5
        pts = [
            (ctr_x + hw * px_v + hh * ux, ctr_y + hw * py_v + hh * uy),
            (ctr_x - hw * px_v + hh * ux, ctr_y - hw * py_v + hh * uy),
            (ctr_x - hw * px_v - hh * ux, ctr_y - hw * py_v - hh * uy),
            (ctr_x + hw * px_v - hh * ux, ctr_y + hw * py_v - hh * uy),
        ]
        if self._slip_filled:
            arcade.draw_polygon_filled(pts, self._slip_color)
        else:
            for i in range(4):
                x1, y1 = pts[i]
                x2, y2 = pts[(i + 1) % 4]
                arcade.draw_line(x1, y1, x2, y2, self._slip_color, self._slip_line_w)

    def _draw_flight_director(self, cx: float, cy: float) -> None:
        """Draw FD cross-pointer bars in screen space (no bank rotation)."""
        if self._show_fd_h and self._fd_h_vis:
            half = self._fd_h_len / 2.0
            bar_y = cy + self._fd_h_defl
            arcade.draw_line(cx - half, bar_y, cx + half, bar_y,
                             self._fd_h_color, self._fd_h_w)
        if self._show_fd_v and self._fd_v_vis:
            half = self._fd_v_len / 2.0
            bar_x = cx + self._fd_v_defl
            arcade.draw_line(bar_x, cy - half, bar_x, cy + half,
                             self._fd_v_color, self._fd_v_w)

    def _build_corner_sprite(self, vx: float, vy: float, vw: float, vh: float) -> None:
        """Bake the 4 corner-cut regions to one texture, once — this shape
        depends only on viewport geometry and corner_radius (fixed after
        apply_scale()), never on pitch/bank/slip, so there's nothing to
        recompute per frame. Previously 128 individual draw_triangle_filled()
        calls (4 corners x 32 segments) every frame, measured ~12.4ms/frame
        on its own — by far the single biggest cost in this component.
        PIL's rounded_rectangle() cut out of a solid corner_bg_color square
        reproduces the same rounded-corner mask directly, with no
        earclip/winding concerns at all (unlike a single concave polygon
        covering all 4 corners, which is why the original code used a
        triangle fan in the first place)."""
        from PIL import Image, ImageDraw

        r = min(self._corner_radius, vw * 0.5, vh * 0.5)
        w_px = max(2, int(round(vw)))
        h_px = max(2, int(round(vh)))
        img = Image.new("RGBA", (w_px, h_px), self._corner_bg_color)
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([0, 0, w_px - 1, h_px - 1], radius=int(round(r)), fill=(0, 0, 0, 0))
        tex = arcade.Texture(img, hash=f"ai_corners:{id(self)}")
        self._corner_sprites = arcade.SpriteList()
        sp = arcade.Sprite(tex)
        sp.position = (vx + vw / 2.0, vy + vh / 2.0)
        self._corner_sprites.append(sp)

    def _draw_reference_wings(self, cx, cy) -> None:
        """Wing bars — drawn below FD bars.  Legacy stubs only if neither polygon is configured."""
        if self._wing_pts:
            for sign in (1.0, -1.0):
                pts = [(cx + sign * x, cy + y) for x, y in self._wing_pts]
                if self._wing_filled:
                    arcade.draw_polygon_filled(pts, self._wing_fill)
                arcade.draw_polygon_outline(pts, self._wing_outline, self._wing_outline_w)
        elif not self._bug_pts:
            stub = 30.0; gap = 6.0
            arcade.draw_line(cx - stub - gap, cy, cx - gap, cy, self._ptr_color, 3)
            arcade.draw_line(cx + gap, cy, cx + stub + gap, cy, self._ptr_color, 3)

    def _draw_reference_bug(self, cx, cy) -> None:
        """Centre bug — drawn above FD bars.  Legacy dot only if neither polygon is configured."""
        if self._bug_pts:
            pts = [(cx + x, cy + y) for x, y in self._bug_pts]
            if self._bug_filled:
                arcade.draw_polygon_filled(pts, self._bug_fill)
            arcade.draw_polygon_outline(pts, self._bug_outline, self._bug_outline_w)
        elif not self._wing_pts:
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
        show_slip=bool(comp.get("show_slip", False)),
        slip_color=_as_color(comp.get("slip_color")),
        slip_width=float(comp.get("slip_width", 20.0)),
        slip_height=float(comp.get("slip_height", 8.0)),
        slip_filled=bool(comp.get("slip_filled", True)),
        slip_line_width=float(comp.get("slip_line_width", 2.0)),
        slip_offset=float(comp.get("slip_offset", 0.0)),
        slip_scale=float(comp.get("slip_scale", 2.0)),
        centre_bug_points=comp.get("centre_bug_points", []),
        centre_bug_filled=bool(comp.get("centre_bug_filled", True)),
        centre_bug_fill_color=_as_color(comp.get("centre_bug_fill_color", [0, 0, 0])),
        centre_bug_outline_color=_as_color(comp.get("centre_bug_outline_color", [255, 255, 255])),
        centre_bug_outline_width=float(comp.get("centre_bug_outline_width", 2.0)),
        wing_points=comp.get("wing_points", []),
        wing_filled=bool(comp.get("wing_filled", True)),
        wing_fill_color=_as_color(comp.get("wing_fill_color", [0, 0, 0])),
        wing_outline_color=_as_color(comp.get("wing_outline_color", [255, 255, 255])),
        wing_outline_width=float(comp.get("wing_outline_width", 2.0)),
        show_fd_h_bar=bool(comp.get("show_fd_h_bar", False)),
        fd_h_color=_as_color(comp.get("fd_h_color", [255, 200, 0])),
        fd_h_length=float(comp.get("fd_h_length", 200.0)),
        fd_h_width=float(comp.get("fd_h_width", 3.0)),
        fd_h_scale=float(comp.get("fd_h_scale", 8.0)),
        show_fd_v_bar=bool(comp.get("show_fd_v_bar", False)),
        fd_v_color=_as_color(comp.get("fd_v_color", [255, 200, 0])),
        fd_v_length=float(comp.get("fd_v_length", 200.0)),
        fd_v_width=float(comp.get("fd_v_width", 3.0)),
        fd_v_scale=float(comp.get("fd_v_scale", 4.0)),
    )
    if "pitch_dataref" in comp:
        ai.set_pitch_dataref(comp["pitch_dataref"],
                             comp.get("pitch_convert_function"))
    if "roll_dataref" in comp:
        ai.set_roll_dataref(comp["roll_dataref"],
                            comp.get("roll_convert_function"))
    if "slip_dataref" in comp:
        ai.set_slip_dataref(comp["slip_dataref"],
                            comp.get("slip_convert_function"))
    if "fd_pitch_dataref" in comp:
        fd_h_vis = comp.get("fd_h_visibility")
        ai.set_fd_h_dataref(
            comp["fd_pitch_dataref"],
            comp.get("fd_pitch_convert_function"),
            fd_h_vis.get("dataref") if fd_h_vis else None,
            resolve_predicate_name(fd_h_vis) if fd_h_vis else None,
        )
    if "fd_roll_dataref" in comp:
        fd_v_vis = comp.get("fd_v_visibility")
        ai.set_fd_v_dataref(
            comp["fd_roll_dataref"],
            comp.get("fd_roll_convert_function"),
            fd_v_vis.get("dataref") if fd_v_vis else None,
            resolve_predicate_name(fd_v_vis) if fd_v_vis else None,
        )
    if "visibility" in comp:
        v = comp["visibility"]
        ai.set_visibility(v["dataref"], resolve_predicate_name(v))
    return ai


register_component("AttitudeIndicator", _ai_factory)
