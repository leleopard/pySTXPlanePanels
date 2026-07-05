"""VectorCompassRose component — rotating compass card for an HSI.

A circular dial with 5°/10° heading ticks and periodic heading labels,
drawn fresh each frame. The whole rose rotates as a rigid body so the
tick for the aircraft's current heading is always at the top (12
o'clock) — the standard rotating-card HSI convention.

Angle convention (Arcade): 0° = right (3 o'clock), CCW positive. For a
compass heading H (0-360, clockwise from North) drawn on a rose whose
current heading is `heading`, the on-screen angle is:

    screen_angle = 90 - H + heading

At heading=0 this puts H=0 at 90° (straight up) and H=90 at 0° (right),
matching a compass face laid out clockwise. Adding `heading` rotates
the whole card counter-clockwise as the aircraft heading increases,
which is the correct visual direction (turn right -> card appears to
rotate left beneath the fixed lubber line at top).

YAML schema
-----------
    - type: VectorCompassRose
      name: hsi_rose
      center: [300, 300]
      radius: 200
      background_color: [20, 20, 30, 255]   # optional; omit → no fill
      show_line: true
      line_color: [255, 255, 255, 255]
      line_width: 2.0
      num_segments: 128                     # optional; circle smoothness

      tick5_length: 8
      tick5_color: [255, 255, 255, 255]
      tick5_width: 1.0
      tick5_position: outside               # inside | outside

      tick10_length: 16
      tick10_color: [255, 255, 255, 255]
      tick10_width: 2.0
      tick10_position: outside

      label_interval: 30                    # degrees between labels
      label_offset: 20                      # px from the circle arc
      label_position: inside                # inside | outside
      label_font: ST_Boeing_PFD
      label_font_size: 14
      label_color: [255, 255, 255, 255]
      label_format: "{:02.0f}"              # applied to heading/10, e.g. 030° → "03"
      label_bold: false
      label_italic: false
      label_emphasize_interval: 30          # optional: headings on this coarser
                                             # interval (must be a multiple of
                                             # label_interval) use a bigger/smaller
                                             # font, e.g. label every 10° but a
                                             # bigger size every 30°
      label_emphasize_font_size: 20         # font size for those headings
      label_anchor_y: center                # baseline | center | top | bottom —
                                             # which part of the label glyph sits at
                                             # the offset point (radius ± offset);
                                             # the rest of the glyph extends from
                                             # there along the label's radial
                                             # (rotated) orientation

      heading:                              # rotates the whole rose
        dataref: sim/cockpit2/gauges/indicators/heading_vacuum_deg_mag_pilot
        convert_function: null              # optional

      track:                                # optional: a line from the centre,
                                             # rotating with the rose like a tick
                                             # (i.e. relative to heading, showing
                                             # crab angle) — omit to not draw one
        dataref: sim/cockpit2/gauges/indicators/track_mag_pilot
        convert_function: null              # optional
        color: [0, 255, 0, 255]
        width: 2.0
        start: 0                            # px from centre where the line starts
        end: 150                            # px from centre where the line ends
        tick_position: 100                  # optional px from centre for a tick
                                             # perpendicular to the line; omit for
                                             # no tick
        tick_length: 20                     # full length of that tick, split
                                             # evenly across the line

      visibility:                           # optional, same as other components
        dataref: ...
        predicate: true_if_over_zero
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

import arcade

from gauge_core.font_utils import resolve_font_for_arcade
from gauge_core.registry import get_convert, register_component, resolve_predicate_name
from gauge_core.vector_primitives import _VecBase, _as_color, _as_dataref


class VectorCompassRose(_VecBase):
    """Rotating compass card: circle + 5°/10° ticks + periodic heading labels."""

    def __init__(
        self,
        name: str,
        center: tuple[float, float],
        radius: float,
        background_color: tuple[int, int, int, int] | None = None,
        show_line: bool = True,
        line_color: tuple[int, int, int, int] = (255, 255, 255, 255),
        line_width: float = 2.0,
        num_segments: int = 128,
        tick5_length: float = 8.0,
        tick5_color: tuple[int, int, int, int] = (255, 255, 255, 255),
        tick5_width: float = 1.0,
        tick5_position: str = "outside",
        tick10_length: float = 16.0,
        tick10_color: tuple[int, int, int, int] = (255, 255, 255, 255),
        tick10_width: float = 2.0,
        tick10_position: str = "outside",
        label_interval: float = 30.0,
        label_offset: float = 20.0,
        label_position: str = "inside",
        label_font: str | None = None,
        label_font_size: float = 14.0,
        label_color: tuple[int, int, int, int] = (255, 255, 255, 255),
        label_format: str = "{:02.0f}",
        label_bold: bool = False,
        label_italic: bool = False,
        label_emphasize_interval: float | None = None,
        label_emphasize_font_size: float | None = None,
        label_anchor_y: str = "center",
    ) -> None:
        self.name = name
        self._cx = float(center[0])
        self._cy = float(center[1])
        self._radius = float(radius)
        self._background_color = background_color
        self._show_line = bool(show_line)
        self._line_color = line_color
        self._line_width = float(line_width)
        self._segments = int(num_segments)

        self._tick5_length = float(tick5_length)
        self._tick5_color = tick5_color
        self._tick5_width = float(tick5_width)
        self._tick5_position = tick5_position

        self._tick10_length = float(tick10_length)
        self._tick10_color = tick10_color
        self._tick10_width = float(tick10_width)
        self._tick10_position = tick10_position

        self._label_interval = max(1, int(label_interval))
        self._label_offset = float(label_offset)
        self._label_position = label_position
        self._label_font = label_font
        self._label_font_size = float(label_font_size)
        self._label_color = label_color
        self._label_format = label_format
        self._label_bold = label_bold
        self._label_italic = label_italic
        # Which part of the label glyph sits at the offset point (radius ±
        # label_offset), in arcade.Text's own anchor_y sense — "center"
        # (default) is the vertical middle, "baseline" the text baseline,
        # "top"/"bottom" the ascender/descender edge.
        self._label_anchor_y = label_anchor_y
        # Optional bigger/smaller font for headings on a coarser interval,
        # e.g. label every 10° but a bigger size every 30°. None → all
        # labels use label_font_size.
        self._label_emphasize_interval = (
            int(label_emphasize_interval) if label_emphasize_interval else None
        )
        self._label_emphasize_font_size = (
            float(label_emphasize_font_size) if label_emphasize_font_size else self._label_font_size
        )
        self._label_pool: list[arcade.Text] = []

        self._heading = 0.0
        self._heading_dr: Any | None = None
        self._heading_convert: Callable | None = None

        # Track indicator (optional; enabled by calling set_track()) — a line
        # from the centre that rotates with the rose like a tick, driven by
        # its own dataref, with an optional perpendicular tick sharing the
        # line's color/width.
        self._show_track = False
        self._track_color: tuple[int, int, int, int] = (0, 255, 0, 255)
        self._track_width = 2.0
        self._track_start = 0.0
        self._track_end = 150.0
        self._track_tick_position: float | None = None
        self._track_tick_length = 20.0
        self._track_angle = 0.0
        self._track_dr: Any | None = None
        self._track_convert: Callable | None = None

        self._init_visibility()

    def set_heading_dataref(self, dataref: Any, convert_fn: str | None = None) -> None:
        self._heading_dr = _as_dataref(dataref)
        if convert_fn:
            self._heading_convert = get_convert(convert_fn)

    def set_track(
        self,
        color: tuple[int, int, int, int],
        width: float,
        start: float,
        end: float,
        tick_position: float | None,
        tick_length: float,
        dataref: Any,
        convert_fn: str | None = None,
    ) -> None:
        self._show_track = True
        self._track_color = color
        self._track_width = float(width)
        self._track_start = float(start)
        self._track_end = float(end)
        self._track_tick_position = float(tick_position) if tick_position is not None else None
        self._track_tick_length = float(tick_length)
        self._track_dr = _as_dataref(dataref)
        if convert_fn:
            self._track_convert = get_convert(convert_fn)

    def apply_scale(self, scale: float) -> None:
        self._cx *= scale; self._cy *= scale
        self._radius *= scale
        self._line_width *= scale
        self._tick5_length *= scale
        self._tick5_width *= scale
        self._tick10_length *= scale
        self._tick10_width *= scale
        self._label_offset *= scale
        self._label_font_size *= scale
        self._label_emphasize_font_size *= scale
        self._label_pool.clear()  # font size changed; pool objects are stale
        self._track_width *= scale
        self._track_start *= scale
        self._track_end *= scale
        if self._track_tick_position is not None:
            self._track_tick_position *= scale
        self._track_tick_length *= scale

    def apply_offset(self, dx: float, dy: float) -> None:
        self._cx += dx; self._cy += dy

    def update(self, get_data: Callable[[Any], float]) -> None:
        self._update_visibility(get_data)
        if self._track_dr is not None:
            raw = float(get_data(self._track_dr))
            if self._track_convert is not None:
                raw = float(self._track_convert(raw, get_data))
            self._track_angle = raw % 360.0
        if self._heading_dr is not None:
            raw = float(get_data(self._heading_dr))
            if self._heading_convert is not None:
                raw = float(self._heading_convert(raw, get_data))
            self._heading = raw % 360.0

    def _point_at(self, heading_deg: float, r: float) -> tuple[float, float]:
        angle = math.radians(90.0 - heading_deg + self._heading)
        return (
            self._cx + r * math.cos(angle),
            self._cy + r * math.sin(angle),
        )

    def draw(self) -> None:
        if not self._visible:
            return

        if self._background_color is not None:
            arcade.draw_circle_filled(
                self._cx, self._cy, self._radius, self._background_color,
                num_segments=self._segments,
            )
        if self._show_line:
            arcade.draw_circle_outline(
                self._cx, self._cy, self._radius, self._line_color,
                self._line_width, num_segments=self._segments,
            )

        for h in range(0, 360, 5):
            is_major = (h % 10) == 0
            length   = self._tick10_length if is_major else self._tick5_length
            position = self._tick10_position if is_major else self._tick5_position
            color    = self._tick10_color if is_major else self._tick5_color
            width    = self._tick10_width if is_major else self._tick5_width
            r0, r1 = (
                (self._radius - length, self._radius) if position == "inside"
                else (self._radius, self._radius + length)
            )
            x0, y0 = self._point_at(h, r0)
            x1, y1 = self._point_at(h, r1)
            arcade.draw_line(x0, y0, x1, y1, color, width)

        r_label = (
            self._radius - self._label_offset if self._label_position == "inside"
            else self._radius + self._label_offset
        )
        idx = 0
        for h in range(0, 360, self._label_interval):
            x, y = self._point_at(h, r_label)
            if idx >= len(self._label_pool):
                kw: dict = dict(bold=self._label_bold, italic=self._label_italic)
                if self._label_font:
                    kw["font_name"] = self._label_font
                self._label_pool.append(arcade.Text(
                    "", 0, 0,
                    color=self._label_color,
                    font_size=self._label_font_size,
                    anchor_x="center",
                    anchor_y=self._label_anchor_y,
                    **kw,
                ))
            t = self._label_pool[idx]
            t.text = self._label_format.format(h / 10.0)
            t.font_size = (
                self._label_emphasize_font_size
                if self._label_emphasize_interval and h % self._label_emphasize_interval == 0
                else self._label_font_size
            )
            t.x, t.y = x, y
            # Radial orientation: baseline tangent to the circle (perpendicular
            # to the radius), with "up" pointing outward along the radius.
            # point_at()'s angle is (90 - h + heading); subtracting the 90
            # unrotated "up" gives the rotation needed to reach it. Negated
            # relative to that derivation: arcade.Text's rendered rotation
            # comes out mirrored versus a plain geometric CCW rotation once
            # it's drawn through the runtime's render pipeline (confirmed by
            # comparing against the designer's PIL preview, which needed no
            # such flip), so the sign is reversed here to compensate.
            t.rotation = h - self._heading
            t.draw()
            idx += 1

        if self._show_track:
            self._draw_track()

    def _draw_track(self) -> None:
        x0, y0 = self._point_at(self._track_angle, self._track_start)
        x1, y1 = self._point_at(self._track_angle, self._track_end)
        arcade.draw_line(x0, y0, x1, y1, self._track_color, self._track_width)
        if self._track_tick_position is not None:
            tx, ty = self._point_at(self._track_angle, self._track_tick_position)
            line_angle = math.radians(90.0 - self._track_angle + self._heading)
            perp = line_angle + math.pi / 2.0
            half = self._track_tick_length / 2.0
            dx, dy = half * math.cos(perp), half * math.sin(perp)
            arcade.draw_line(tx - dx, ty - dy, tx + dx, ty + dy,
                             self._track_color, self._track_width)


def _compass_rose_factory(
    comp: dict[str, Any],
    base_dir: Path,
    container_size: tuple[int, int] | None = None,
) -> VectorCompassRose:
    label_font, label_bold, label_italic = resolve_font_for_arcade(
        comp.get("label_font"), base_dir,
        bold=bool(comp.get("label_bold", False)),
        italic=bool(comp.get("label_italic", False)),
        explicit_file=comp.get("label_font_file"),
    )

    bg = comp.get("background_color")
    rose = VectorCompassRose(
        name=comp["name"],
        center=tuple(comp["center"]),
        radius=float(comp["radius"]),
        background_color=_as_color(bg) if bg is not None else None,
        show_line=bool(comp.get("show_line", True)),
        line_color=_as_color(comp.get("line_color")),
        line_width=float(comp.get("line_width", 2.0)),
        num_segments=int(comp.get("num_segments", 128)),
        tick5_length=float(comp.get("tick5_length", 8.0)),
        tick5_color=_as_color(comp.get("tick5_color")),
        tick5_width=float(comp.get("tick5_width", 1.0)),
        tick5_position=str(comp.get("tick5_position", "outside")),
        tick10_length=float(comp.get("tick10_length", 16.0)),
        tick10_color=_as_color(comp.get("tick10_color")),
        tick10_width=float(comp.get("tick10_width", 2.0)),
        tick10_position=str(comp.get("tick10_position", "outside")),
        label_interval=float(comp.get("label_interval", 30.0)),
        label_offset=float(comp.get("label_offset", 20.0)),
        label_position=str(comp.get("label_position", "inside")),
        label_font=label_font,
        label_font_size=float(comp.get("label_font_size", 14.0)),
        label_color=_as_color(comp.get("label_color")),
        label_format=str(comp.get("label_format", "{:02.0f}")),
        label_bold=label_bold,
        label_italic=label_italic,
        label_emphasize_interval=comp.get("label_emphasize_interval"),
        label_emphasize_font_size=comp.get("label_emphasize_font_size"),
        label_anchor_y=str(comp.get("label_anchor_y", "center")),
    )

    heading_cfg = comp.get("heading")
    if heading_cfg:
        rose.set_heading_dataref(
            heading_cfg["dataref"],
            heading_cfg.get("convert_function"),
        )

    track_cfg = comp.get("track")
    if track_cfg:
        rose.set_track(
            color=_as_color(track_cfg.get("color", [0, 255, 0, 255])),
            width=float(track_cfg.get("width", 2.0)),
            start=float(track_cfg.get("start", 0.0)),
            end=float(track_cfg.get("end", comp.get("radius", 150.0))),
            tick_position=track_cfg.get("tick_position"),
            tick_length=float(track_cfg.get("tick_length", 20.0)),
            dataref=track_cfg["dataref"],
            convert_fn=track_cfg.get("convert_function"),
        )

    if "visibility" in comp:
        v = comp["visibility"]
        rose.set_visibility(v["dataref"], resolve_predicate_name(v))

    return rose


register_component("VectorCompassRose", _compass_rose_factory)
