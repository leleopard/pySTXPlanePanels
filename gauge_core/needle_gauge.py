"""NeedleGauge component — a dataref-driven needle against a circular or
linear scale.

The needle is always a line rotating from a centre point, driven by a
dataref via a piecewise lookup table (unchanged mechanism regardless of
gradation type). The scale around it is either:

- circular (default): a fixed arc, same as this component's original
  behaviour. Tick/label support for this mode is a deferred follow-up.
- linear: a vertical or horizontal tape of ticks + labels next to which the
  needle sweeps (e.g. a VSI-style vertical speed tape). Every row of the
  `spacing_table` is one fully-styled tick (value, pixel offset from
  centre, length, width) — no interval-based generation and no
  interpolation between rows, so the table is exactly what gets drawn, one
  row in, one tick out. This is a deliberate simplification: an earlier
  version walked from the table's min to max value at a fixed interval,
  interpolating a position for any value that wasn't an explicit
  breakpoint — which meant adding a single new row (e.g. extending the
  table from 1,2 to 1,2,6) silently grew *unwanted* interpolated ticks at
  3, 4, 5 too. Labels use the same one-row-one-label rule. The needle's
  own value->angle table remains a separate, independently-calibrated
  lookup (unchanged mechanism).

Angle convention: 0° = up (12 o'clock), clockwise positive — this is
this component's own "clock face" convention (needle_angle, static
needle angle, and the circular arc's start_angle/end_angle all share
it), distinct from Arcade's native math convention (0° = right, CCW+)
used elsewhere in this codebase (Arc, Vector, VectorCompassRose, etc.).
Internally converted via math_angle = 90 - clock_angle wherever Arcade
APIs need the native convention.

YAML schema
-----------
    - type: NeedleGauge
      name: vsi
      center: [265, 265]
      gradation_type: linear        # circular (default) | linear

      needle_length: 130
      needle_width: 2.0
      needle_color: [255, 255, 255, 255]
      needle_angle: -130            # static angle, OR dataref dict:
      # needle_angle:
      #   dataref: sim/cockpit/misc/vvi_fpm
      #   table: [[-6000, -140], [0, 0], [6000, 140]]
      #   convert_function: null
      needle_viewport: [-40, -40, 200, 200]  # optional; [dx, dy, w, h] —
                                     # RELATIVE to `center` (same "offset
                                     # from pivot" convention as the linear
                                     # tape's own `offset` below), not an
                                     # absolute instrument-space rectangle.
                                     # Scissor-clips ONLY the needle line —
                                     # the arc/tape/ticks/labels are
                                     # unaffected. Omit for no clipping.

      # Circular mode only (unchanged from the original CircularGauge):
      radius: 200
      start_angle: -130
      end_angle: 130
      arc_color: [255, 255, 255, 255]
      arc_width: 3.0
      num_segments: 64              # optional

      # Linear mode only:
      linear:
        orientation: vertical       # vertical | horizontal
        offset: [0, -80]            # optional; shifts the tape's own centre line away
                                     # from the needle's pivot (`center` above stays the
                                     # needle's rotation point, unaffected by this).
                                     # Ticks, labels, and the background rect below are
                                     # all positioned relative to this shifted centre.
        size: [40, 280]             # optional; background rect width/height, centred
                                     # on the (possibly offset) tape centre line — only
                                     # relevant if background_color or line_color is set
        background_color: [20, 20, 30, 220]   # optional; omit = no rect drawn
        line_color: [255, 255, 255, 255]      # optional outline for the rect
        line_width: 2.0
        # Gradation Table (designer name for spacing_table below): one row =
        # one tick: [value, px offset from centre, length px, width px,
        # show_label, label font size, label px offset]. The last three
        # columns are optional per row (default show_label=true, font
        # size=14, offset=8) and let each tick's label be toggled and
        # independently sized/positioned; label px offset may be negative
        # to pull the label back over the tick/tape instead of away from it.
        spacing_table:
          - [-6, -132, 18, 2.0, true, 14, 8]
          - [-2, -68, 10, 1.5, true, 14, 8]
          - [-1, -40, 10, 1.5, true, 14, 8]
          - [0, 0, 18, 2.0, true, 14, 8]
          - [1, 40, 10, 1.5, true, 14, 8]
          - [2, 68, 10, 1.5, true, 14, 8]
          - [6, 132, 18, 2.0, true, 14, 8]
        tick_side: left             # left|right (vertical) or top|bottom (horizontal)
        tick_color: [255, 255, 255, 255]   # shared by every tick
        labels:                      # optional; enables labels (per-row show_label
                                     # above still gates each individual tick).
                                     # font_size/offset are NOT set here — they're
                                     # per-row in spacing_table above. Everything
                                     # else here (family/bold/italic/color) is global.
          format: "{:.0f}"
          font: ST_Boeing_PFD        # optional; blank = designer/OS default
          bold: false
          italic: false
          color: [255, 255, 255, 255]
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

import arcade

from gauge_core.font_utils import resolve_font_for_arcade
from gauge_core.lookup import lookup_piecewise
from gauge_core.registry import get_convert, register_component, resolve_predicate_name
from gauge_core.vector_primitives import _VecBase, _as_color, _as_dataref


class NeedleGauge(_VecBase):
    """Dataref-driven needle against a circular arc or a linear tape scale."""

    def __init__(
        self,
        name: str,
        center: tuple[float, float],
        gradation_type: str = "circular",
        radius: float = 100.0,
        start_angle: float = -130.0,
        end_angle: float = 130.0,
        arc_color: tuple[int, int, int, int] = (255, 255, 255, 255),
        arc_width: float = 2.0,
        num_segments: int = 64,
        needle_length: float = 150.0,
        needle_width: float = 2.0,
        needle_color: tuple[int, int, int, int] = (255, 255, 255, 255),
        static_needle_angle: float | None = None,
    ) -> None:
        self.name = name
        self._cx = float(center[0])
        self._cy = float(center[1])
        self._gradation_type = gradation_type

        self._radius = float(radius)
        self._start_angle = float(start_angle)
        self._end_angle = float(end_angle)
        self._arc_color = arc_color
        self._arc_width = float(arc_width)
        self._segments = int(num_segments)

        self._needle_length = float(needle_length)
        self._needle_width = float(needle_width)
        self._needle_color = needle_color
        self._needle_angle = float(static_needle_angle) if static_needle_angle is not None else float(start_angle)
        self._needle_dr: Any | None = None
        self._needle_table: list = []
        self._needle_convert: Callable | None = None
        # Scissor rectangle confining ONLY the needle line — the arc/tape/
        # ticks/labels are unaffected. [dx, dy, w, h], relative to (cx, cy)
        # (same "offset from pivot" convention as the linear tape's own
        # `offset` field) rather than absolute instrument-space, so the box
        # stays meaningful if the gauge is repositioned as a whole.
        self._needle_viewport: tuple[float, float, float, float] | None = None

        # Linear mode (optional; enabled by calling set_linear()). Each
        # spacing_table row is [value, offset, length, width] — one row,
        # one fully-styled tick, no interval-based generation.
        self._orientation = "vertical"
        # Offset of the tape's own centre line away from the needle pivot
        # (self._cx, self._cy) — the needle keeps rotating from the pivot
        # regardless; only the tape (rect + ticks + labels) shifts.
        self._linear_offset_x = 0.0
        self._linear_offset_y = 0.0
        self._rect_w = 0.0
        self._rect_h = 0.0
        self._rect_bg_color: tuple[int, int, int, int] | None = None
        self._rect_line_color: tuple[int, int, int, int] | None = None
        self._rect_line_width = 1.0
        # Each row: [value, offset, length, width, show_label, font_size, label_offset].
        self._spacing_table: list = []
        self._tick_side = "left"
        self._tick_color: tuple[int, int, int, int] = (255, 255, 255, 255)
        # Global label styling (family/bold/italic/color/format); font size
        # and pixel offset are per-row, see _spacing_table above.
        self._label_format = "{:.0f}"
        self._label_font: str | None = None
        self._label_bold = False
        self._label_italic = False
        self._label_color: tuple[int, int, int, int] = (255, 255, 255, 255)
        self._show_labels = False
        self._label_pool: list[arcade.Text] = []

        self._init_visibility()

    def set_needle_dataref(
        self,
        dataref: Any,
        table: list,
        convert_fn: str | None = None,
    ) -> None:
        self._needle_dr = _as_dataref(dataref)
        self._needle_table = table
        if convert_fn:
            self._needle_convert = get_convert(convert_fn)

    def set_needle_viewport(self, offset_x: float, offset_y: float, w: float, h: float) -> None:
        """Scissor rectangle confining only the needle line, positioned at
        (cx + offset_x, cy + offset_y) — relative to the pivot, not an
        absolute instrument-space rectangle (same convention as the linear
        tape's own `offset`)."""
        self._needle_viewport = (offset_x, offset_y, w, h)

    def set_linear(
        self,
        orientation: str,
        spacing_table: list,
        tick_side: str,
        labels: dict | None,
        tick_color: tuple[int, int, int, int] | None = None,
        label_font: str | None = None,
        label_bold: bool = False,
        label_italic: bool = False,
        offset: tuple[float, float] = (0.0, 0.0),
        rect_size: tuple[float, float] = (0.0, 0.0),
        rect_background_color: tuple[int, int, int, int] | None = None,
        rect_line_color: tuple[int, int, int, int] | None = None,
        rect_line_width: float = 1.0,
    ) -> None:
        self._orientation = orientation
        self._spacing_table = spacing_table
        self._tick_side = tick_side
        self._linear_offset_x, self._linear_offset_y = float(offset[0]), float(offset[1])
        self._rect_w, self._rect_h = float(rect_size[0]), float(rect_size[1])
        self._rect_bg_color = rect_background_color
        self._rect_line_color = rect_line_color
        self._rect_line_width = float(rect_line_width)
        if tick_color is not None:
            self._tick_color = tick_color
        if labels:
            self._label_format = str(labels.get("format", "{:.0f}"))
            self._label_font = label_font
            self._label_bold = label_bold
            self._label_italic = label_italic
            self._label_color = _as_color(labels.get("color"))
            self._show_labels = True
            self._label_pool.clear()  # font changed; pool objects are stale

    def apply_scale(self, scale: float) -> None:
        self._cx *= scale; self._cy *= scale
        self._radius *= scale
        self._arc_width *= scale
        self._needle_length *= scale
        self._needle_width *= scale
        self._spacing_table = [
            [v, off * scale, length * scale, width * scale,
             show_label, font_size * scale, label_offset * scale]
            for v, off, length, width, show_label, font_size, label_offset in self._spacing_table
        ]
        self._linear_offset_x *= scale; self._linear_offset_y *= scale
        self._rect_w *= scale; self._rect_h *= scale
        self._rect_line_width *= scale
        self._label_pool.clear()  # font size changed; pool objects are stale
        if self._needle_viewport is not None:
            vx, vy, vw, vh = self._needle_viewport
            self._needle_viewport = (vx * scale, vy * scale, vw * scale, vh * scale)

    def apply_offset(self, dx: float, dy: float) -> None:
        # _needle_viewport (like _linear_offset_x/_y) is relative to
        # (cx, cy), so it needs no adjustment here — it moves with the
        # pivot automatically.
        self._cx += dx; self._cy += dy

    def update(self, get_data: Callable[[Any], float]) -> None:
        self._update_visibility(get_data)
        if self._needle_dr is not None:
            raw = float(get_data(self._needle_dr))
            if self._needle_convert is not None:
                raw = float(self._needle_convert(raw, get_data))
            self._needle_angle = (
                lookup_piecewise(self._needle_table, raw)
                if self._needle_table else raw
            )

    def draw(self) -> None:
        if not self._visible:
            return
        if self._gradation_type == "linear":
            self._draw_linear()
        else:
            self._draw_circular()
        self._draw_needle()

    def _draw_circular(self) -> None:
        # start_angle/end_angle are in this component's clock convention
        # (0°=up, CW+); Arcade's draw_arc_outline wants its native math
        # convention (0°=right, CCW+) — convert via 90 - clock_angle. Arcade
        # silently draws nothing if the first angle it's given isn't
        # numerically smaller than the second (confirmed empirically), and
        # since an outline has no directionality, sorting is always safe.
        m1, m2 = 90.0 - self._start_angle, 90.0 - self._end_angle
        arcade.draw_arc_outline(
            self._cx, self._cy,
            self._radius * 2, self._radius * 2,
            self._arc_color,
            min(m1, m2), max(m1, m2),
            self._arc_width,
            0.0,
            self._segments,
        )

    def _draw_linear(self) -> None:
        if not self._spacing_table:
            return
        vertical = self._orientation == "vertical"
        side = self._tick_side
        # Ticks/labels/rect are all anchored to the tape's own centre line,
        # which may be shifted away from the needle's pivot (self._cx/_cy).
        tx = self._cx + self._linear_offset_x
        ty = self._cy + self._linear_offset_y

        if self._rect_bg_color is not None or self._rect_line_color is not None:
            rect = arcade.XYWH(tx, ty, self._rect_w, self._rect_h)
            if self._rect_bg_color is not None:
                arcade.draw_rect_filled(rect, self._rect_bg_color)
            if self._rect_line_color is not None:
                arcade.draw_rect_outline(rect, self._rect_line_color, self._rect_line_width)

        for value, off, length, width, _show_label, _font_size, _label_offset in self._spacing_table:
            if vertical:
                x0, x1 = (tx - length, tx) if side == "left" else (tx, tx + length)
                y = ty + off
                arcade.draw_line(x0, y, x1, y, self._tick_color, width)
            else:
                y0, y1 = (ty, ty + length) if side == "top" else (ty - length, ty)
                x = tx + off
                arcade.draw_line(x, y0, x, y1, self._tick_color, width)

        if self._show_labels:
            self._draw_linear_labels(vertical, side, tx, ty)

    def _draw_linear_labels(self, vertical: bool, side: str, tx: float, ty: float) -> None:
        for idx, (value, off, _length, _width, show_label, font_size, label_offset) in enumerate(self._spacing_table):
            # Pool slot reserved by table index regardless of visibility, so
            # a hidden row never shifts a later row's pooled Text object.
            if idx >= len(self._label_pool):
                kw: dict = dict(bold=self._label_bold, italic=self._label_italic)
                if self._label_font:
                    kw["font_name"] = self._label_font
                self._label_pool.append(arcade.Text(
                    "", 0, 0,
                    color=self._label_color,
                    font_size=font_size,
                    anchor_x="center", anchor_y="center",
                    **kw,
                ))
            if not show_label:
                continue
            t = self._label_pool[idx]
            t.text = self._label_format.format(value)
            t.font_size = font_size
            if vertical:
                if side == "left":
                    t.x, t.anchor_x = tx - label_offset, "right"
                else:
                    t.x, t.anchor_x = tx + label_offset, "left"
                t.y = ty + off
            else:
                t.x = tx + off
                if side == "top":
                    t.y, t.anchor_y = ty + label_offset, "bottom"
                else:
                    t.y, t.anchor_y = ty - label_offset, "top"
            t.draw()

    def _draw_needle(self) -> None:
        # 0°=up, CW+ (this component's clock convention): direction vector
        # is (sin, cos) rather than the usual (cos, sin).
        angle_rad = math.radians(self._needle_angle)
        ex = self._cx + self._needle_length * math.sin(angle_rad)
        ey = self._cy + self._needle_length * math.cos(angle_rad)
        if self._needle_viewport is None:
            arcade.draw_line(self._cx, self._cy, ex, ey,
                             self._needle_color, self._needle_width)
            return
        # Scissor-clip just the needle line — same idiom as ImagePanel's and
        # ScrollingTape's viewport clip (gauge_core/component.py), except
        # the rect is relative to the pivot (see set_needle_viewport()).
        off_x, off_y, vw, vh = self._needle_viewport
        vx, vy = self._cx + off_x, self._cy + off_y
        win = arcade.get_window()
        ctx = win.ctx
        _, _, fvp_w, fvp_h = ctx.viewport
        panel_w, panel_h = getattr(win, "_panel_size", (win.width, win.height))
        sx = fvp_w / panel_w
        sy = fvp_h / panel_h
        ctx.scissor = (int(vx * sx), int(vy * sy), int(vw * sx), int(vh * sy))
        arcade.draw_line(self._cx, self._cy, ex, ey,
                         self._needle_color, self._needle_width)
        ctx.scissor = None


def _parse_spacing_row(row: list) -> list:
    """Row shapes accepted, oldest to newest — each pads forward with sane
    defaults so older 2/4-column rows keep working unmodified:
      [value, offset]
      [value, offset, length, width]
      [value, offset, length, width, show_label, font_size, label_offset]
    """
    value, off = float(row[0]), float(row[1])
    length = float(row[2]) if len(row) > 2 else 10.0
    width = float(row[3]) if len(row) > 3 else 1.5
    show_label = bool(row[4]) if len(row) > 4 else True
    font_size = float(row[5]) if len(row) > 5 else 14.0
    label_offset = float(row[6]) if len(row) > 6 else 8.0
    return [value, off, length, width, show_label, font_size, label_offset]


def _needle_gauge_factory(
    comp: dict[str, Any],
    base_dir: Path,
    container_size=None,
) -> NeedleGauge:
    angle_cfg = comp.get("needle_angle")
    static_angle = (
        None if isinstance(angle_cfg, dict)
        else (float(angle_cfg) if angle_cfg is not None else None)
    )
    ng = NeedleGauge(
        name=comp["name"],
        center=tuple(comp["center"]),
        gradation_type=str(comp.get("gradation_type", "circular")),
        radius=float(comp.get("radius", 100.0)),
        start_angle=float(comp.get("start_angle", -130.0)),
        end_angle=float(comp.get("end_angle", 130.0)),
        arc_color=_as_color(comp.get("arc_color") or comp.get("color")),
        arc_width=float(comp.get("arc_width", 2.0)),
        num_segments=int(comp.get("num_segments", 64)),
        needle_length=float(comp.get("needle_length", 150.0)),
        needle_width=float(comp.get("needle_width", 2.0)),
        needle_color=_as_color(comp.get("needle_color") or comp.get("color")),
        static_needle_angle=static_angle,
    )
    if isinstance(angle_cfg, dict):
        ng.set_needle_dataref(
            _as_dataref(angle_cfg["dataref"]),
            angle_cfg.get("table", []),
            angle_cfg.get("convert_function"),
        )

    nv = comp.get("needle_viewport")
    if nv:
        ng.set_needle_viewport(*[float(v) for v in nv])

    linear_cfg = comp.get("linear")
    if linear_cfg:
        tick_color = linear_cfg.get("tick_color")
        labels_cfg = linear_cfg.get("labels") or {}
        label_font, label_bold, label_italic = resolve_font_for_arcade(
            labels_cfg.get("font"), base_dir,
            bold=bool(labels_cfg.get("bold", False)),
            italic=bool(labels_cfg.get("italic", False)),
            explicit_file=labels_cfg.get("font_file"),
        )
        rect_bg = linear_cfg.get("background_color")
        rect_line = linear_cfg.get("line_color")
        ng.set_linear(
            orientation=str(linear_cfg.get("orientation", "vertical")),
            spacing_table=[_parse_spacing_row(p) for p in linear_cfg.get("spacing_table", [])],
            tick_side=str(linear_cfg.get("tick_side", "left")),
            labels=linear_cfg.get("labels"),
            tick_color=_as_color(tick_color) if tick_color is not None else None,
            label_font=label_font,
            label_bold=label_bold,
            label_italic=label_italic,
            offset=tuple(linear_cfg.get("offset", [0.0, 0.0])),
            rect_size=tuple(linear_cfg.get("size", [0.0, 0.0])),
            rect_background_color=_as_color(rect_bg) if rect_bg is not None else None,
            rect_line_color=_as_color(rect_line) if rect_line is not None else None,
            rect_line_width=float(linear_cfg.get("line_width", 1.0)),
        )

    if "visibility" in comp:
        v = comp["visibility"]
        ng.set_visibility(v["dataref"], resolve_predicate_name(v))
    return ng


register_component("NeedleGauge", _needle_gauge_factory)
