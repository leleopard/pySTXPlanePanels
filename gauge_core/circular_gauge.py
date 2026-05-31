"""CircularGauge component — arc scale + dataref-driven needle.

Simple analogue gauge: a fixed arc marks the scale range; a needle line
rotates from the centre, driven by a dataref via a piecewise lookup table.

Angle convention (Arcade): 0° = right (3 o'clock), CCW positive.
A typical full-range airspeed indicator spanning from ~220° left of bottom
to ~40° right of bottom would use start_angle=-220, end_angle=40.

YAML schema
-----------
    - type: CircularGauge
      name: airspeed
      center: [250, 250]
      radius: 200
      start_angle: -220        # arc start (0=right, CCW positive)
      end_angle:    40         # arc end
      arc_color: [255, 255, 255, 255]
      arc_width: 3.0
      num_segments: 64         # optional
      needle_length: 180       # px from centre to needle tip
      needle_width: 2.0
      needle_color: [255, 255, 255, 255]
      needle_angle: -220       # static angle, OR dataref dict:
      # needle_angle:
      #   dataref: sim/cockpit2/gauges/indicators/airspeed_kts_pilot
      #   table: [[0, -220], [300, 40]]
      #   convert_function: null
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

import arcade

from gauge_core.lookup import lookup_piecewise
from gauge_core.registry import get_convert, register_component
from gauge_core.vector_primitives import _VecBase, _as_color, _as_dataref


class CircularGauge(_VecBase):
    """Arc scale with a dataref-driven needle line."""

    def __init__(
        self,
        name: str,
        center: tuple[float, float],
        radius: float,
        start_angle: float,
        end_angle: float,
        arc_color: tuple[int, int, int, int],
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

    def apply_scale(self, scale: float) -> None:
        self._cx *= scale; self._cy *= scale
        self._radius *= scale
        self._arc_width *= scale
        self._needle_length *= scale
        self._needle_width *= scale

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
        arcade.draw_arc_outline(
            self._cx, self._cy,
            self._radius * 2, self._radius * 2,
            self._arc_color,
            self._start_angle, self._end_angle,
            self._arc_width,
            0.0,
            self._segments,
        )
        angle_rad = math.radians(self._needle_angle)
        ex = self._cx + self._needle_length * math.cos(angle_rad)
        ey = self._cy + self._needle_length * math.sin(angle_rad)
        arcade.draw_line(self._cx, self._cy, ex, ey,
                         self._needle_color, self._needle_width)


def _circular_gauge_factory(
    comp: dict[str, Any],
    base_dir: Path,
    container_size=None,
) -> CircularGauge:
    angle_cfg = comp.get("needle_angle")
    static_angle = (
        None if isinstance(angle_cfg, dict)
        else (float(angle_cfg) if angle_cfg is not None else None)
    )
    cg = CircularGauge(
        name=comp["name"],
        center=tuple(comp["center"]),
        radius=float(comp["radius"]),
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
        cg.set_needle_dataref(
            _as_dataref(angle_cfg["dataref"]),
            angle_cfg.get("table", []),
            angle_cfg.get("convert_function"),
        )
    if "visibility" in comp:
        v = comp["visibility"]
        cg.set_visibility(v["dataref"], v["predicate"])
    return cg


register_component("CircularGauge", _circular_gauge_factory)
