"""NeedleGauge component — a dataref-driven needle against a circular or
linear scale.

The needle is always a line rotating from a centre point, driven by a
dataref via a piecewise lookup table (unchanged mechanism regardless of
gradation type). The scale around it is either:

- circular (default): a fixed arc, same as this component's original
  behaviour. Tick/label support for this mode is a deferred follow-up.
- linear: a vertical or horizontal tape of ticks + labels next to which the
  needle sweeps (e.g. a VSI-style vertical speed tape). Tick/label pixel
  position is driven by an explicit user-authored `spacing_table`
  (value -> pixel offset from centre, interpolated piecewise-linearly via
  lookup_piecewise) rather than a uniform-pixels-per-unit or log formula —
  real-world tapes like a VSI are hand-tuned, not a clean mathematical
  curve. The needle's own value->angle table is calibrated independently
  of the tick spacing table.

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
        spacing_table:              # value -> px offset from centre
          - [-6, -132]
          - [-2, -68]
          - [-1, -40]
          - [0, 0]
          - [1, 40]
          - [2, 68]
          - [6, 132]
        tick_side: left             # left|right (vertical) or top|bottom (horizontal)
        tick_color: [255, 255, 255, 255]   # shared default; a group may override via color:
        ticks:
          - interval: 1             # minor ticks, positioned via spacing_table
            length: 10
            width: 1.5
          - interval: 2             # a second group, e.g. thicker major ticks
            length: 18
            width: 2.0
        labels:
          interval: 1
          format: "{:.0f}"
          font_size: 14
          color: [255, 255, 255, 255]
          offset: 8                 # gap from centre past the tick
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

import arcade

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

        # Linear mode (optional; enabled by calling set_linear()).
        self._orientation = "vertical"
        self._spacing_table: list = []
        self._tick_side = "left"
        self._ticks: list[dict] = []
        self._tick_color: tuple[int, int, int, int] = (255, 255, 255, 255)
        self._label_interval = 1.0
        self._label_format = "{:.0f}"
        self._label_font_size = 14.0
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
        ticks: list[dict],
        labels: dict | None,
        tick_color: tuple[int, int, int, int] | None = None,
    ) -> None:
        self._orientation = orientation
        self._spacing_table = spacing_table
        self._tick_side = tick_side
        self._ticks = ticks
        if tick_color is not None:
            self._tick_color = tick_color
        if labels:
            self._label_interval = float(labels.get("interval", 1.0))
            self._label_format = str(labels.get("format", "{:.0f}"))
            self._label_font_size = float(labels.get("font_size", 14.0))
            self._label_color = _as_color(labels.get("color"))
            self._label_offset = float(labels.get("offset", 8.0))
            self._show_labels = True

    def apply_scale(self, scale: float) -> None:
        self._cx *= scale; self._cy *= scale
        self._radius *= scale
        self._arc_width *= scale
        self._needle_length *= scale
        self._needle_width *= scale
        self._spacing_table = [[v, off * scale] for v, off in self._spacing_table]
        for group in self._ticks:
            group["length"] = float(group.get("length", 10.0)) * scale
            group["width"] = float(group.get("width", 1.0)) * scale
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

    def _value_to_offset(self, value: float) -> float:
        return lookup_piecewise(self._spacing_table, value)

    def _draw_linear(self) -> None:
        if not self._spacing_table:
            return
        v_min = self._spacing_table[0][0]
        v_max = self._spacing_table[-1][0]
        vertical = self._orientation == "vertical"
        side = self._tick_side

        for group in self._ticks:
            interval = float(group.get("interval", 1.0))
            if interval <= 0:
                continue
            length = float(group.get("length", 10.0))
            width = float(group.get("width", 1.0))
            color = group.get("color") or self._tick_color
            v = v_min
            while v <= v_max + interval * 0.001:
                off = self._value_to_offset(v)
                if vertical:
                    x0, x1 = (self._cx - length, self._cx) if side == "left" else (self._cx, self._cx + length)
                    y = self._cy + off
                    arcade.draw_line(x0, y, x1, y, color, width)
                else:
                    y0, y1 = (self._cy, self._cy + length) if side == "top" else (self._cy - length, self._cy)
                    x = self._cx + off
                    arcade.draw_line(x, y0, x, y1, color, width)
                v += interval

        if self._show_labels:
            self._draw_linear_labels(v_min, v_max, vertical, side)

    def _draw_linear_labels(self, v_min: float, v_max: float, vertical: bool, side: str) -> None:
        interval = self._label_interval
        if interval <= 0:
            return
        idx = 0
        v = v_min
        while v <= v_max + interval * 0.001:
            off = self._value_to_offset(v)
            if idx >= len(self._label_pool):
                self._label_pool.append(arcade.Text(
                    "", 0, 0,
                    color=self._label_color,
                    font_size=self._label_font_size,
                    anchor_x="center", anchor_y="center",
                ))
            t = self._label_pool[idx]
            t.text = self._label_format.format(v)
            if vertical:
                if side == "left":
                    t.x, t.anchor_x = self._cx - self._label_offset, "right"
                else:
                    t.x, t.anchor_x = self._cx + self._label_offset, "left"
                t.y = self._cy + off
            else:
                t.x = self._cx + off
                if side == "top":
                    t.y, t.anchor_y = self._cy + self._label_offset, "bottom"
                else:
                    t.y, t.anchor_y = self._cy - self._label_offset, "top"
            t.draw()
            idx += 1
            v += interval

    def _draw_needle(self) -> None:
        angle_rad = math.radians(self._needle_angle)
        ex = self._cx + self._needle_length * math.cos(angle_rad)
        ey = self._cy + self._needle_length * math.sin(angle_rad)
        arcade.draw_line(self._cx, self._cy, ex, ey,
                         self._needle_color, self._needle_width)


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
        ticks = [
            {
                "interval": float(t.get("interval", 1.0)),
                "length": float(t.get("length", 10.0)),
                "width": float(t.get("width", 1.0)),
                "color": _as_color(t["color"]) if t.get("color") is not None else None,
            }
            for t in linear_cfg.get("ticks", [])
        ]
        tick_color = linear_cfg.get("tick_color")
        ng.set_linear(
            orientation=str(linear_cfg.get("orientation", "vertical")),
            spacing_table=[[float(p[0]), float(p[1])] for p in linear_cfg.get("spacing_table", [])],
            tick_side=str(linear_cfg.get("tick_side", "left")),
            ticks=ticks,
            labels=linear_cfg.get("labels"),
            tick_color=_as_color(tick_color) if tick_color is not None else None,
        )

    if "visibility" in comp:
        v = comp["visibility"]
        ng.set_visibility(v["dataref"], resolve_predicate_name(v))
    return ng


register_component("NeedleGauge", _needle_gauge_factory)
