"""Vector primitive components — Line, Arc, FilledRect, Polygon.

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

from pathlib import Path
from typing import Any, Callable

import arcade

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


register_component("Line", _line_factory)
register_component("Arc", _arc_factory)
register_component("FilledRect", _filledrect_factory)
register_component("Polygon", _polygon_factory)
