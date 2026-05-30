"""Vector primitive components — Line, Arc, FilledRect, Polygon, Vector.

These are statically-positioned shapes rendered via Arcade's draw_* API each
frame.  They are suitable for dial artwork, bezel decorations, and as the
building blocks for compound glass-cockpit instrument types.

All primitives support:
  - apply_scale / apply_offset  (panel composition)
  - visibility block            (same predicate schema as ImagePanel)

YAML schema examples
--------------------
    - type: Line
      name: horizon_line
      start: [50, 250]
      end: [450, 250]
      color: [255, 255, 255, 200]
      width: 2

    - type: Arc
      name: bank_arc
      center: [250, 250]
      radius: 220
      start_angle: -60
      end_angle: 60
      color: [255, 255, 255]
      width: 2
      tilt_angle: 0       # optional; rotates the arc sweep in the plane
      num_segments: 64    # optional; default 64

    - type: FilledRect
      name: sky_background
      position: [250, 350]   # centre of the rectangle
      size: [400, 200]
      color: [30, 120, 200]

    - type: Polygon
      name: speed_arrow
      points: [[240, 10], [250, 0], [260, 10]]
      color: [255, 200, 0]
      filled: true

Colors are [r, g, b] or [r, g, b, a] in 0-255 range.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

import arcade

from gauge_core.lookup import lookup_piecewise
from gauge_core.registry import get_convert, register_component


def _as_color(raw: Any) -> tuple[int, int, int, int]:
    """Accept [r,g,b] or [r,g,b,a] in 0-255; default alpha = 255."""
    if raw is None:
        return (255, 255, 255, 255)
    if len(raw) == 3:
        return (int(raw[0]), int(raw[1]), int(raw[2]), 255)
    return (int(raw[0]), int(raw[1]), int(raw[2]), int(raw[3]))


def _as_dataref(raw: Any) -> Any:
    if isinstance(raw, list):
        return tuple(raw)
    return raw


class _VecBase:
    """Shared visibility + scale/offset support for all vector primitives."""

    name: str
    _visible: bool
    _vis_dataref: Any | None
    _vis_predicate: Callable | None

    def _init_visibility(self) -> None:
        self._visible = True
        self._vis_dataref = None
        self._vis_predicate = None

    def set_visibility(self, dataref: Any, predicate: str) -> None:
        self._vis_dataref = _as_dataref(dataref)
        self._vis_predicate = get_convert(predicate)
        if self._vis_predicate is None:
            raise ValueError(f"visibility predicate '{predicate}' not found in registry")

    def _update_visibility(self, get_data: Callable[[Any], float]) -> None:
        if self._vis_dataref is not None and self._vis_predicate is not None:
            self._visible = bool(self._vis_predicate(float(get_data(self._vis_dataref)), get_data))

    def update(self, get_data: Callable[[Any], float]) -> None:
        self._update_visibility(get_data)

    # Subclasses must implement these
    def apply_scale(self, scale: float) -> None: ...
    def apply_offset(self, dx: float, dy: float) -> None: ...
    def draw(self) -> None: ...


# ---------------------------------------------------------------------------
# Line
# ---------------------------------------------------------------------------

class Line(_VecBase):
    """Straight line between two points."""

    def __init__(
        self,
        name: str,
        start: tuple[float, float],
        end: tuple[float, float],
        color: tuple[int, int, int, int],
        width: float = 1.0,
    ) -> None:
        self.name = name
        self._x1, self._y1 = float(start[0]), float(start[1])
        self._x2, self._y2 = float(end[0]), float(end[1])
        self._color = color
        self._width = float(width)
        self._init_visibility()

    def apply_scale(self, scale: float) -> None:
        self._x1 *= scale; self._y1 *= scale
        self._x2 *= scale; self._y2 *= scale
        self._width *= scale

    def apply_offset(self, dx: float, dy: float) -> None:
        self._x1 += dx; self._y1 += dy
        self._x2 += dx; self._y2 += dy

    def draw(self) -> None:
        if not self._visible:
            return
        arcade.draw_line(self._x1, self._y1, self._x2, self._y2,
                         self._color, self._width)


# ---------------------------------------------------------------------------
# Arc
# ---------------------------------------------------------------------------

class Arc(_VecBase):
    """Circular arc (open, not filled)."""

    def __init__(
        self,
        name: str,
        center: tuple[float, float],
        radius: float,
        start_angle: float,
        end_angle: float,
        color: tuple[int, int, int, int],
        width: float = 1.0,
        tilt_angle: float = 0.0,
        num_segments: int = 64,
    ) -> None:
        self.name = name
        self._cx, self._cy = float(center[0]), float(center[1])
        self._radius = float(radius)
        self._start_angle = float(start_angle)
        self._end_angle = float(end_angle)
        self._color = color
        self._width = float(width)
        self._tilt = float(tilt_angle)
        self._segments = int(num_segments)
        self._init_visibility()

    def apply_scale(self, scale: float) -> None:
        self._cx *= scale; self._cy *= scale
        self._radius *= scale
        self._width *= scale

    def apply_offset(self, dx: float, dy: float) -> None:
        self._cx += dx; self._cy += dy

    def draw(self) -> None:
        if not self._visible:
            return
        # arcade.draw_arc_outline: center_x, center_y, width, height,
        #   color, start_angle, end_angle, border_width, tilt_angle, num_segments
        arcade.draw_arc_outline(
            self._cx, self._cy,
            self._radius * 2, self._radius * 2,
            self._color,
            self._start_angle, self._end_angle,
            self._width,
            self._tilt,
            self._segments,
        )


# ---------------------------------------------------------------------------
# FilledRect
# ---------------------------------------------------------------------------

class FilledRect(_VecBase):
    """Solid filled rectangle, positioned by its centre, with optional outline."""

    def __init__(
        self,
        name: str,
        position: tuple[float, float],
        size: tuple[float, float],
        color: tuple[int, int, int, int],
        outline_color: tuple[int, int, int, int] | None = None,
        outline_width: float = 1.0,
    ) -> None:
        self.name = name
        self._cx, self._cy = float(position[0]), float(position[1])
        self._w, self._h = float(size[0]), float(size[1])
        self._color = color
        self._outline_color = outline_color
        self._outline_width = float(outline_width)
        self._init_visibility()

    def apply_scale(self, scale: float) -> None:
        self._cx *= scale; self._cy *= scale
        self._w *= scale; self._h *= scale
        self._outline_width *= scale

    def apply_offset(self, dx: float, dy: float) -> None:
        self._cx += dx; self._cy += dy

    def draw(self) -> None:
        if not self._visible:
            return
        rect = arcade.XYWH(self._cx, self._cy, self._w, self._h)
        arcade.draw_rect_filled(rect, self._color)
        if self._outline_color is not None:
            arcade.draw_rect_outline(rect, self._outline_color, self._outline_width)


# ---------------------------------------------------------------------------
# Polygon
# ---------------------------------------------------------------------------

class Polygon(_VecBase):
    """Filled or outlined polygon defined by an explicit point list.

    When ``filled=True`` an optional outline can be drawn on top of the fill
    via ``outline_color`` / ``outline_width``.  When ``filled=False`` the
    primary ``color`` and ``width`` define the outline; ``outline_*`` are
    ignored (the outline IS the drawing in that case).
    """

    def __init__(
        self,
        name: str,
        points: list[tuple[float, float]],
        color: tuple[int, int, int, int],
        filled: bool = True,
        width: float = 1.0,
        outline_color: tuple[int, int, int, int] | None = None,
        outline_width: float = 1.0,
    ) -> None:
        self.name = name
        self._points: list[tuple[float, float]] = [
            (float(x), float(y)) for x, y in points
        ]
        self._color = color
        self._filled = filled
        self._width = float(width)
        self._outline_color = outline_color
        self._outline_width = float(outline_width)
        self._init_visibility()

    def apply_scale(self, scale: float) -> None:
        self._points = [(x * scale, y * scale) for x, y in self._points]
        self._width *= scale
        self._outline_width *= scale

    def apply_offset(self, dx: float, dy: float) -> None:
        self._points = [(x + dx, y + dy) for x, y in self._points]

    def draw(self) -> None:
        if not self._visible:
            return
        if self._filled:
            arcade.draw_polygon_filled(self._points, self._color)
            if self._outline_color is not None:
                arcade.draw_polygon_outline(self._points, self._outline_color, self._outline_width)
        else:
            arcade.draw_polygon_outline(self._points, self._color, self._width)


# ---------------------------------------------------------------------------
# Vector
# ---------------------------------------------------------------------------

class Vector(_VecBase):
    """Arrow defined by a position, direction (degrees), and length (pixels).

    Direction follows the standard Arcade convention: 0° = right/east,
    counterclockwise positive.  Both direction and length can be driven by
    datarefs via a lookup table, independently of each other.

    YAML schema
    -----------
    Static::

        - type: Vector
          name: wind_arrow
          position: [300, 300]
          direction: 90.0        # static degrees (0=right, CCW)
          length: 60.0           # static pixels
          color: [255, 200, 0, 255]
          width: 2.0

    Dataref-driven::

        - type: Vector
          name: speed_trend
          position: [110, 307]
          direction:
            dataref: sim/cockpit2/gauges/indicators/airspeed_kts_pilot
            table: [[0, 90], [300, 90]]
          length:
            dataref: sim/cockpit2/gauges/indicators/airspeed_kts_pilot
            table: [[0, 5], [300, 120]]
          color: [0, 255, 100, 255]
          width: 3.0
    """

    def __init__(
        self,
        name: str,
        position: tuple[float, float],
        color: tuple[int, int, int, int],
        width: float = 1.0,
        static_direction: float | None = None,
        static_length: float | None = None,
        cap: str = "none",
        cap_width: float = 10.0,
        cap_height: float = 5.0,
        cap_filled: bool = True,
    ) -> None:
        self.name = name
        self._px, self._py = float(position[0]), float(position[1])
        self._color = color
        self._width = float(width)
        self._dir = float(static_direction) if static_direction is not None else 0.0
        self._len = float(static_length) if static_length is not None else 50.0
        self._cap = str(cap) if cap else "none"
        self._cap_width = float(cap_width)
        self._cap_height = float(cap_height)
        self._cap_filled = bool(cap_filled)
        self._dir_dataref: Any | None = None
        self._dir_table: list = []
        self._dir_convert: Callable | None = None
        self._len_dataref: Any | None = None
        self._len_table: list = []
        self._len_convert: Callable | None = None
        self._init_visibility()

    def set_direction_dataref(
        self,
        dataref: Any,
        table: list,
        convert_fn: str | None = None,
    ) -> None:
        self._dir_dataref = dataref
        self._dir_table = table
        if convert_fn:
            self._dir_convert = get_convert(convert_fn)

    def set_length_dataref(
        self,
        dataref: Any,
        table: list,
        convert_fn: str | None = None,
    ) -> None:
        self._len_dataref = dataref
        self._len_table = table
        if convert_fn:
            self._len_convert = get_convert(convert_fn)

    def apply_scale(self, scale: float) -> None:
        self._px *= scale; self._py *= scale
        self._len *= scale
        self._width *= scale
        self._cap_width *= scale
        self._cap_height *= scale

    def apply_offset(self, dx: float, dy: float) -> None:
        self._px += dx; self._py += dy

    def update(self, get_data: Callable[[Any], float]) -> None:
        self._update_visibility(get_data)
        if self._dir_dataref is not None:
            raw = float(get_data(self._dir_dataref))
            if self._dir_convert is not None:
                raw = float(self._dir_convert(raw, get_data))
            self._dir = lookup_piecewise(self._dir_table, raw) if self._dir_table else raw
        if self._len_dataref is not None:
            raw = float(get_data(self._len_dataref))
            if self._len_convert is not None:
                raw = float(self._len_convert(raw, get_data))
            self._len = lookup_piecewise(self._len_table, raw) if self._len_table else raw

    def draw(self) -> None:
        if not self._visible or self._len == 0:
            return
        angle_rad = math.radians(self._dir)
        sign = 1.0 if self._len >= 0 else -1.0
        # Absolute tip position
        ex = self._px + self._len * math.cos(angle_rad)
        ey = self._py + self._len * math.sin(angle_rad)
        # Shaft endpoint: shorten by cap height for triangle so total length is preserved
        if self._cap == "triangle":
            sx = self._px + (self._len - sign * self._cap_height) * math.cos(angle_rad)
            sy = self._py + (self._len - sign * self._cap_height) * math.sin(angle_rad)
        else:
            sx, sy = ex, ey
        arcade.draw_line(self._px, self._py, sx, sy, self._color, self._width)
        if self._cap != "none":
            # Unit vectors relative to direction of travel (accounts for negative length)
            ux = sign * math.cos(angle_rad)
            uy = sign * math.sin(angle_rad)
            bx = -ux;  by = -uy                  # backward: tip → origin
            perp_x = -uy; perp_y = ux            # perpendicular (90° CCW from forward)
            half_w = self._cap_width / 2.0
            if self._cap == "triangle":
                p1 = (ex + bx * self._cap_height + perp_x * half_w,
                      ey + by * self._cap_height + perp_y * half_w)
                p2 = (ex + bx * self._cap_height - perp_x * half_w,
                      ey + by * self._cap_height - perp_y * half_w)
                pts = [(ex, ey), p1, p2]
                if self._cap_filled:
                    arcade.draw_polygon_filled(pts, self._color)
                else:
                    arcade.draw_polygon_outline(pts, self._color, self._width)
            elif self._cap == "bar":
                arcade.draw_line(
                    ex + perp_x * half, ey + perp_y * half,
                    ex - perp_x * half, ey - perp_y * half,
                    self._color, self._width,
                )


# ---------------------------------------------------------------------------
# Factories + registration
# ---------------------------------------------------------------------------

def _line_factory(comp: dict, base_dir: Path, container_size=None) -> Line:
    line = Line(
        name=comp["name"],
        start=tuple(comp["start"]),
        end=tuple(comp["end"]),
        color=_as_color(comp.get("color")),
        width=float(comp.get("width", 1.0)),
    )
    if "visibility" in comp:
        v = comp["visibility"]
        line.set_visibility(v["dataref"], v["predicate"])
    return line


def _arc_factory(comp: dict, base_dir: Path, container_size=None) -> Arc:
    arc = Arc(
        name=comp["name"],
        center=tuple(comp["center"]),
        radius=float(comp["radius"]),
        start_angle=float(comp["start_angle"]),
        end_angle=float(comp["end_angle"]),
        color=_as_color(comp.get("color")),
        width=float(comp.get("width", 1.0)),
        tilt_angle=float(comp.get("tilt_angle", 0.0)),
        num_segments=int(comp.get("num_segments", 64)),
    )
    if "visibility" in comp:
        v = comp["visibility"]
        arc.set_visibility(v["dataref"], v["predicate"])
    return arc


def _filledrect_factory(comp: dict, base_dir: Path, container_size=None) -> FilledRect:
    oc = comp.get("outline_color")
    rect = FilledRect(
        name=comp["name"],
        position=tuple(comp["position"]),
        size=tuple(comp["size"]),
        color=_as_color(comp.get("color")),
        outline_color=_as_color(oc) if oc is not None else None,
        outline_width=float(comp.get("outline_width", 1.0)),
    )
    if "visibility" in comp:
        v = comp["visibility"]
        rect.set_visibility(v["dataref"], v["predicate"])
    return rect


def _polygon_factory(comp: dict, base_dir: Path, container_size=None) -> Polygon:
    oc = comp.get("outline_color")
    poly = Polygon(
        name=comp["name"],
        points=[tuple(p) for p in comp["points"]],
        color=_as_color(comp.get("color")),
        filled=bool(comp.get("filled", True)),
        width=float(comp.get("width", 1.0)),
        outline_color=_as_color(oc) if oc is not None else None,
        outline_width=float(comp.get("outline_width", 1.0)),
    )
    if "visibility" in comp:
        v = comp["visibility"]
        poly.set_visibility(v["dataref"], v["predicate"])
    return poly


def _vector_factory(comp: dict, base_dir: Path, container_size=None) -> Vector:
    dir_cfg = comp.get("direction", 0.0)
    len_cfg = comp.get("length", 50.0)
    static_dir = None if isinstance(dir_cfg, dict) else float(dir_cfg)
    static_len = None if isinstance(len_cfg, dict) else float(len_cfg)
    vec = Vector(
        name=comp["name"],
        position=tuple(comp.get("position", [0, 0])),
        color=_as_color(comp.get("color")),
        width=float(comp.get("width", 1.0)),
        static_direction=static_dir,
        static_length=static_len,
        cap=str(comp.get("cap", "none")),
        cap_width=float(comp.get("cap_width", 10.0)),
        cap_height=float(comp.get("cap_height", comp.get("cap_width", 10.0) / 2.0)),
        cap_filled=bool(comp.get("cap_filled", True)),
    )
    if isinstance(dir_cfg, dict):
        vec.set_direction_dataref(
            _as_dataref(dir_cfg["dataref"]),
            dir_cfg.get("table", []),
            dir_cfg.get("convert_function"),
        )
    if isinstance(len_cfg, dict):
        vec.set_length_dataref(
            _as_dataref(len_cfg["dataref"]),
            len_cfg.get("table", []),
            len_cfg.get("convert_function"),
        )
    if "visibility" in comp:
        vis = comp["visibility"]
        vec.set_visibility(vis["dataref"], vis["predicate"])
    return vec


register_component("Line", _line_factory)
register_component("Arc", _arc_factory)
register_component("FilledRect", _filledrect_factory)
register_component("Polygon", _polygon_factory)
register_component("Vector", _vector_factory)
