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

Angle convention (Arcade): 0° = right (3 o'clock), CCW positive.

YAML schema
-----------
    - type: NeedleGauge
      name: vsi
      center: [265, 265]
      gradation_type: linear        # circular (default) | linear

      needle_length: 130
      needle_width: 2.0
      needle_color: [255, 255, 255, 255]
      needle_angle: -220            # static angle, OR dataref dict:
      # needle_angle:
      #   dataref: sim/cockpit/misc/vvi_fpm
      #   table: [[-6000, -140], [0, 0], [6000, 140]]
      #   convert_function: null

      # Circular mode only (unchanged from the original CircularGauge):
      radius: 200
      start_angle: -220
      end_angle: 40
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
        spacing_table:              # one row = one tick: [value, px offset from centre, length px, width px]
          - [-6, -132, 18, 2.0]
          - [-2, -68, 10, 1.5]
          - [-1, -40, 10, 1.5]
          - [0, 0, 18, 2.0]
          - [1, 40, 10, 1.5]
          - [2, 68, 10, 1.5]
          - [6, 132, 18, 2.0]
        tick_side: left             # left|right (vertical) or top|bottom (horizontal)
        tick_color: [255, 255, 255, 255]   # shared by every tick
        labels:                      # optional; one label per spacing_table row
          format: "{:.0f}"
          font: ST_Boeing_PFD        # optional; blank = designer/OS default
          font_size: 14
          bold: false
          italic: false
          color: [255, 255, 255, 255]
          offset: 8                 # gap from centre past the tick
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
        start_angle: float = -220.0,
        end_angle: float = 40.0,
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
        self._spacing_table: list = []
        self._tick_side = "left"
        self._tick_color: tuple[int, int, int, int] = (255, 255, 255, 255)
        self._label_format = "{:.0f}"
        self._label_font: str | None = None
        self._label_font_size = 14.0
        self._label_bold = False
        self._label_italic = False
        self._label_color: tuple[int, int, int, int] = (255, 255, 255, 255)
        self._label_offset = 8.0
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
            self._label_font_size = float(labels.get("font_size", 14.0))
            self._label_bold = label_bold
            self._label_italic = label_italic
            self._label_color = _as_color(labels.get("color"))
            self._label_offset = float(labels.get("offset", 8.0))
            self._show_labels = True
            self._label_pool.clear()  # font changed; pool objects are stale

    def apply_scale(self, scale: float) -> None:
        self._cx *= scale; self._cy *= scale
        self._radius *= scale
        self._arc_width *= scale
        self._needle_length *= scale
        self._needle_width *= scale
        self._spacing_table = [
            [v, off * scale, length * scale, width * scale]
            for v, off, length, width in self._spacing_table
        ]
        self._linear_offset_x *= scale; self._linear_offset_y *= scale
        self._rect_w *= scale; self._rect_h *= scale
        self._rect_line_width *= scale
        self._label_font_size *= scale
        self._label_offset *= scale
        self._label_pool.clear()  # font size changed; pool objects are stale

    def apply_offset(self, dx: float, dy: float) -> None:
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
        arcade.draw_arc_outline(
            self._cx, self._cy,
            self._radius * 2, self._radius * 2,
            self._arc_color,
            self._start_angle, self._end_angle,
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

        for value, off, length, width in self._spacing_table:
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
        for idx, (value, off, _length, _width) in enumerate(self._spacing_table):
            if idx >= len(self._label_pool):
                kw: dict = dict(bold=self._label_bold, italic=self._label_italic)
                if self._label_font:
                    kw["font_name"] = self._label_font
                self._label_pool.append(arcade.Text(
                    "", 0, 0,
                    color=self._label_color,
                    font_size=self._label_font_size,
                    anchor_x="center", anchor_y="center",
                    **kw,
                ))
            t = self._label_pool[idx]
            t.text = self._label_format.format(value)
            if vertical:
                if side == "left":
                    t.x, t.anchor_x = tx - self._label_offset, "right"
                else:
                    t.x, t.anchor_x = tx + self._label_offset, "left"
                t.y = ty + off
            else:
                t.x = tx + off
                if side == "top":
                    t.y, t.anchor_y = ty + self._label_offset, "bottom"
                else:
                    t.y, t.anchor_y = ty - self._label_offset, "top"
            t.draw()

    def _draw_needle(self) -> None:
        angle_rad = math.radians(self._needle_angle)
        ex = self._cx + self._needle_length * math.cos(angle_rad)
        ey = self._cy + self._needle_length * math.sin(angle_rad)
        arcade.draw_line(self._cx, self._cy, ex, ey,
                         self._needle_color, self._needle_width)


def _parse_spacing_row(row: list) -> list[float]:
    """[value, offset] or [value, offset, length, width]; length/width
    default to a sane minor-tick style when a row omits them."""
    if len(row) >= 4:
        return [float(row[0]), float(row[1]), float(row[2]), float(row[3])]
    return [float(row[0]), float(row[1]), 10.0, 1.5]


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
        start_angle=float(comp.get("start_angle", -220.0)),
        end_angle=float(comp.get("end_angle", 40.0)),
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
