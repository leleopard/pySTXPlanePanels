"""VectorTape component — procedurally generated scrolling tape.

Used for airspeed, altitude, and heading displays in glass-cockpit panels.
Generates tick marks, labels, and coloured bands each frame from a dataref
value — no pre-rendered texture required.

Coordinate system
-----------------
All positions use Arcade's y-up convention (same as instrument YAML).
``position`` is the screen point at which the *current value* is always
displayed.  For a centred display this equals the viewport centre; it can be
offset for asymmetric layouts.  ``viewport`` is the independent scissor
rectangle that clips ticks and bands; labels are drawn outside the scissor.

YAML schema
-----------
    - type: VectorTape
      name: airspeed_tape
      position: [75, 450]             # where current value appears on screen
      viewport: [10, 120, 140, 630]   # scissor clip [x, y_bottom, w, h]
      scroll_axis: y                  # y (vertical) or x (horizontal)
      pixels_per_unit: 5              # px per value unit (e.g. 5 px/kt)
      tick_side: left                 # left/right (y-axis) or top/bottom (x-axis)
      tick_color: [255, 255, 255]     # default tick color
      ticks:
        - interval: 10
          length: 15
          width: 2
          offset: 0                  # optional: gap (px) between spine and tick start
        - interval: 20
          length: 30
          width: 3
          offset: 0
          color: [255, 220, 100]      # optional per-level override
      labels:
        interval: 20
        font_size: 18
        font: Arial                  # optional font name (Arcade/pyglet font family)
        color: [255, 255, 255]
        format: "{:.0f}"             # Python format string
        offset: 8                    # gap (px) between spine and label edge
        side: left                   # optional: left/right (y) or top/bottom (x)
                                     # default = same as tick_side
      bands:
        - range: [0, 67]             # both endpoints static
          color: [200, 0, 0, 180]
          width: 8
        - range:                     # one or both endpoints dataref-driven
            - dataref: sim/aircraft/view/acf_Vso
              table: [[0, 0], [400, 400]]
              convert_function: null
            - 209                    # static upper bound
          color: [0, 180, 0, 180]
          width: 8
      wrap: 10                         # optional: label digits cycle modulo this
                                     # value (e.g. 10 for a 0-9 counter drum)
      bg_color: [20, 20, 40, 255]    # optional: fill the viewport before drawing
      scroll:
        dataref: sim/cockpit2/gauges/indicators/airspeed_kts_pilot
        table: [[0, 0], [400, 400]]
        convert_function: null        # optional
      visibility:                     # optional
        dataref: ...
        predicate: true_if_over_zero
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

import arcade

from gauge_core.lookup import lookup_piecewise
from gauge_core.registry import get_convert, register_component


def _col(raw) -> tuple[int, int, int, int]:
    if raw is None:
        return (255, 255, 255, 255)
    if len(raw) == 3:
        return (int(raw[0]), int(raw[1]), int(raw[2]), 255)
    return (int(raw[0]), int(raw[1]), int(raw[2]), int(raw[3]))


class _Bug:
    """Polygon marker pinned to a value on the tape, moves with the tape scroll.

    Points are defined in instrument pixel coordinates relative to the anchor
    point on the tape spine (0, 0 = spine at the bug value).  Y is Arcade
    y-up: positive Y is above the anchor.

    When the bug value is outside the visible range the anchor is clamped to
    the top or bottom (y-tape) / left or right (x-tape) edge of the viewport
    so the bug remains visible at the boundary.
    """
    __slots__ = (
        "_value_static", "_dataref", "_table", "_convert",
        "_points", "_color", "_filled", "_width", "_current_value",
    )

    def __init__(
        self,
        value_raw: Any,
        points: list,
        color: tuple,
        filled: bool,
        width: float,
    ) -> None:
        if isinstance(value_raw, dict):
            self._value_static: float | None = None
            self._dataref: Any = _as_dataref(value_raw["dataref"])
            self._table: list = value_raw.get("table", [[0, 0], [1, 1]])
            self._convert: Callable | None = get_convert(value_raw.get("convert_function"))
        else:
            self._value_static = float(value_raw)
            self._dataref = None
            self._table = []
            self._convert = None
        self._points: list[tuple[float, float]] = [
            (float(p[0]), float(p[1])) for p in points
        ]
        self._color: tuple = _col(color)
        self._filled: bool = bool(filled)
        self._width: float = max(1.0, float(width))
        self._current_value: float = self._value_static or 0.0

    def update(self, get_data: Callable) -> None:
        if self._dataref is not None:
            raw = float(get_data(self._dataref))
            if self._convert is not None:
                raw = float(self._convert(raw, get_data))
            self._current_value = lookup_piecewise(self._table, raw) if self._table else raw

    def scale(self, factor: float) -> None:
        self._points = [(x * factor, y * factor) for x, y in self._points]
        self._width = max(1.0, self._width * factor)


def _as_dataref(raw: Any) -> Any:
    return tuple(raw) if isinstance(raw, list) else raw


class _BandEndpoint:
    """A band range endpoint that is resolved from a dataref each frame."""
    __slots__ = ("dataref", "table", "convert_fn", "_cached")

    def __init__(self, dataref: Any, table: list, convert_fn: Callable | None):
        self.dataref = dataref
        self.table = table
        self.convert_fn = convert_fn
        self._cached: float = 0.0

    def resolve(self, get_data: Callable) -> float:
        raw = float(get_data(self.dataref))
        if self.convert_fn is not None:
            raw = float(self.convert_fn(raw, get_data))
        self._cached = lookup_piecewise(self.table, raw)
        return self._cached


def _parse_endpoint(raw: Any) -> float | _BandEndpoint:
    """Parse a band range entry: plain number → float, dict → _BandEndpoint."""
    if isinstance(raw, dict):
        return _BandEndpoint(
            dataref=_as_dataref(raw["dataref"]),
            table=raw.get("table", [[0, 0], [1, 1]]),
            convert_fn=get_convert(raw.get("convert_function")),
        )
    return float(raw)


class VectorTape:
    """Procedurally drawn scrolling tape driven by a dataref."""

    def __init__(
        self,
        name: str,
        position_xy: tuple[float, float],
        viewport: tuple[float, float, float, float],
        axis: str = "y",
        pixels_per_unit: float = 5.0,
        tick_side: str = "left",
        tick_color_default: tuple = (255, 255, 255, 255),
        tick_defs: list[dict] | None = None,
        label_interval: float = 0.0,
        label_font_size: float = 18.0,
        label_color: tuple = (255, 255, 255, 255),
        label_format: str = "{:.0f}",
        label_offset: float = 8.0,
        label_side: str | None = None,
        label_font: str | None = None,
        label_bold: bool = False,
        label_italic: bool = False,
        bands: list[dict] | None = None,
        bugs: list[dict] | None = None,
        wrap: float | None = None,
        bg_color: tuple | None = None,
    ) -> None:
        self.name = name
        self._cx = float(position_xy[0])
        self._cy = float(position_xy[1])
        self._vp_x, self._vp_y, self._vp_w, self._vp_h = (float(v) for v in viewport)
        self._axis = axis
        self._ppu = float(pixels_per_unit)
        self._tick_side = tick_side
        self._tick_color_default = tick_color_default
        self._tick_defs: list[dict] = [dict(td) for td in (tick_defs or [])]
        self._label_interval = float(label_interval)
        self._label_font_size = float(label_font_size)
        self._label_color = label_color
        self._label_format = label_format
        self._label_offset = float(label_offset)
        self._label_side = label_side  # None → fall back to tick_side
        self._label_font = label_font  # None → Arcade default font
        self._label_bold = label_bold
        self._label_italic = label_italic
        self._wrap = float(wrap) if wrap is not None else None
        self._bg_color: tuple | None = _col(bg_color) if bg_color is not None else None
        self._bands: list[dict] = []
        for b in (bands or []):
            rng = b["range"]
            lo = _parse_endpoint(rng[0])
            hi = _parse_endpoint(rng[1])
            self._bands.append({
                "lo": lo,           # float or _BandEndpoint
                "hi": hi,
                "lo_val": lo if isinstance(lo, float) else 0.0,  # resolved cache
                "hi_val": hi if isinstance(hi, float) else 0.0,
                "color": _col(b["color"]),
                "width": float(b.get("width", 8.0)),
                "side": b.get("side"),  # None → follow tick_side
                "dash": float(b["dash"]) if b.get("dash") else 0.0,
            })

        self._bugs: list[_Bug] = [
            _Bug(
                value_raw=b.get("value", 0.0),
                points=b.get("points", []),
                color=b.get("color", [255, 200, 0, 255]),
                filled=bool(b.get("filled", True)),
                width=float(b.get("width", 2.0)),
            )
            for b in (bugs or [])
        ]

        self._current_value: float = 0.0
        self._scroll_dataref: Any = None
        self._scroll_table: list | None = None
        self._scroll_convert: Callable | None = None

        self._visible = True
        self._vis_dataref: Any = None
        self._vis_predicate: Callable | None = None

        # Pool of arcade.Text objects reused each frame to avoid the cost of
        # draw_text (which rebuilds a glyph batch on every call).
        self._label_pool: list[arcade.Text] = []

    # -- configuration --------------------------------------------------------

    def set_scroll(
        self,
        dataref: Any,
        table: list[list[float]],
        convert_function: str | None = None,
    ) -> None:
        self._scroll_dataref = _as_dataref(dataref)
        self._scroll_table = table
        self._scroll_convert = get_convert(convert_function)

    def set_visibility(self, dataref: Any, predicate: str) -> None:
        self._vis_dataref = _as_dataref(dataref)
        self._vis_predicate = get_convert(predicate)
        if self._vis_predicate is None:
            raise ValueError(f"visibility predicate '{predicate}' not found")

    # -- panel composition ----------------------------------------------------

    def apply_scale(self, scale: float) -> None:
        self._cx *= scale;       self._cy *= scale
        self._vp_x *= scale;     self._vp_y *= scale
        self._vp_w *= scale;     self._vp_h *= scale
        self._ppu *= scale
        for td in self._tick_defs:
            td["length"] = float(td["length"]) * scale
            td["width"]  = max(1.0, float(td["width"]) * scale)
            td["offset"] = float(td.get("offset", 0.0)) * scale
        self._label_offset    *= scale
        self._label_font_size *= scale
        self._label_pool.clear()  # font size changed; pool objects are stale
        for band in self._bands:
            band["width"] *= scale
        for bug in self._bugs:
            bug.scale(scale)

    def _label_text(self, v: float) -> str:
        display = v % self._wrap if self._wrap is not None else v
        return self._label_format.format(display)

    def apply_offset(self, dx: float, dy: float) -> None:
        self._cx += dx;  self._cy += dy
        self._vp_x += dx; self._vp_y += dy

    # -- per-frame ------------------------------------------------------------

    def update(self, get_data: Callable[[Any], float]) -> None:
        if self._vis_dataref is not None and self._vis_predicate is not None:
            self._visible = bool(
                self._vis_predicate(float(get_data(self._vis_dataref)), get_data)
            )
        if self._scroll_dataref is not None and self._scroll_table is not None:
            raw = float(get_data(self._scroll_dataref))
            if self._scroll_convert is not None:
                raw = float(self._scroll_convert(raw, get_data))
            self._current_value = lookup_piecewise(self._scroll_table, raw)
        for band in self._bands:
            if isinstance(band["lo"], _BandEndpoint):
                band["lo_val"] = band["lo"].resolve(get_data)
            if isinstance(band["hi"], _BandEndpoint):
                band["hi_val"] = band["hi"].resolve(get_data)
        for bug in self._bugs:
            bug.update(get_data)

    def draw(self) -> None:
        if not self._visible:
            return
        win = arcade.get_window()
        ctx = win.ctx
        vx, vy, vw, vh = self._vp_x, self._vp_y, self._vp_w, self._vp_h
        val = self._current_value

        # Scale panel-space viewport to framebuffer pixels.  In SSAA mode the
        # FBO is ssaa× larger than the logical panel, so raw panel coords would
        # clip to a tiny wrong region near the origin.
        _, _, fvp_w, fvp_h = ctx.viewport
        panel_w, panel_h = getattr(win, "_panel_size", (win.width, win.height))
        sx = fvp_w / panel_w
        sy = fvp_h / panel_h
        scissor = (int(vx * sx), int(vy * sy), int(vw * sx), int(vh * sy))

        if self._bg_color is not None:
            arcade.draw_rect_filled(arcade.LBWH(vx, vy, vw, vh), self._bg_color)

        ctx.scissor = scissor
        if self._axis == "y":
            self._draw_bands_y(vx, vy, vw, vh, val)
            self._draw_ticks_y(vx, vy, vw, vh, val)
            self._draw_bugs_y(vx, vy, vw, vh, val)
        else:
            self._draw_bands_x(vx, vy, vw, vh, val)
            self._draw_ticks_x(vx, vy, vw, vh, val)
            self._draw_bugs_x(vx, vy, vw, vh, val)
        ctx.scissor = None

        # Use the same viewport scissor for labels as for ticks so that labels
        # are clipped to the tape viewport on all four sides.  Labels that are
        # positioned at the edge of the viewport (e.g. drum-digit tapes where
        # text starts at the spine and extends inward) are correctly confined,
        # and labels that sit inside the viewport near one edge are clipped when
        # they scroll off the top or bottom.
        ctx.scissor = scissor
        if self._axis == "y":
            self._draw_labels_y(vx, vy, vw, vh, val)
        else:
            self._draw_labels_x(vx, vy, vw, vh, val)
        ctx.scissor = None

    # -- vertical tape --------------------------------------------------------

    def _draw_bands_y(self, vx, vy, vw, vh, val):
        for band in self._bands:
            bv_min, bv_max = band["lo_val"], band["hi_val"]
            bw = band["width"]
            y_bot = self._cy + (bv_min - val) * self._ppu
            y_top = self._cy + (bv_max - val) * self._ppu
            y_bot = max(y_bot, vy)
            y_top = min(y_top, vy + vh)
            if y_top <= y_bot:
                continue
            side = band.get("side") or self._tick_side
            bx = vx if side == "left" else vx + vw - bw
            dash = float(band.get("dash", 0.0))
            if dash > 0:
                y = y_bot
                on = True
                while y < y_top:
                    seg = min(y + dash, y_top)
                    if on:
                        arcade.draw_rect_filled(arcade.LBWH(bx, y, bw, seg - y), band["color"])
                    y = seg
                    on = not on
            else:
                arcade.draw_rect_filled(arcade.LBWH(bx, y_bot, bw, y_top - y_bot), band["color"])

    def _draw_ticks_y(self, vx, vy, vw, vh, val):
        spine_x  = vx if self._tick_side == "left" else vx + vw
        tick_dir = 1  if self._tick_side == "left" else -1
        half_range = vh / 2 / self._ppu
        v_min = val - half_range - 1
        v_max = val + half_range + 1
        for td in self._tick_defs:
            interval = float(td["interval"])
            length   = float(td["length"])
            width    = max(1.0, float(td["width"]))
            offset   = float(td.get("offset", 0.0))
            color    = _col(td.get("color", self._tick_color_default))
            x0 = spine_x + tick_dir * offset
            x1 = spine_x + tick_dir * (offset + length)
            v = math.floor(v_min / interval) * interval
            while v <= v_max + interval * 0.001:
                y = self._cy + (v - val) * self._ppu
                arcade.draw_line(x0, y, x1, y, color, width)
                v += interval

    def _draw_labels_y(self, vx, vy, vw, vh, val):
        if self._label_interval <= 0:
            return
        # offset is measured from the spine outward so the user can set it to 0
        # and have labels sit flush against the spine, regardless of viewport width.
        spine_x = vx if self._tick_side == "left" else vx + vw
        side = self._label_side if self._label_side is not None else self._tick_side
        if side == "left":
            lx, anchor_x = spine_x - self._label_offset, "right"
        else:
            lx, anchor_x = spine_x + self._label_offset, "left"
        half_range = vh / 2 / self._ppu
        v_min = val - half_range - 1
        v_max = val + half_range + 1
        v = math.floor(v_min / self._label_interval) * self._label_interval
        idx = 0
        while v <= v_max + self._label_interval * 0.001:
            y = self._cy + (v - val) * self._ppu
            if idx >= len(self._label_pool):
                kw: dict = dict(bold=self._label_bold, italic=self._label_italic)
                if self._label_font:
                    kw["font_name"] = self._label_font
                self._label_pool.append(arcade.Text(
                    "", 0, 0,
                    color=self._label_color,
                    font_size=self._label_font_size,
                    anchor_x=anchor_x,
                    anchor_y="center",
                    **kw,
                ))
            t = self._label_pool[idx]
            t.value = self._label_text(v)
            t.x = lx
            t.y = y
            t.draw()
            idx += 1
            v += self._label_interval

    def _draw_bugs_y(self, vx, vy, vw, vh, val):
        if not self._bugs:
            return
        spine_x = vx if self._tick_side == "left" else vx + vw
        for bug in self._bugs:
            anchor_y = self._cy + (bug._current_value - val) * self._ppu
            anchor_y = max(vy, min(vy + vh, anchor_y))
            pts = [(spine_x + px, anchor_y + py) for px, py in bug._points]
            if len(pts) < 3:
                continue
            if bug._filled:
                arcade.draw_polygon_filled(pts, bug._color)
            else:
                arcade.draw_polygon_outline(pts, bug._color, bug._width)

    # -- horizontal tape ------------------------------------------------------

    def _draw_bands_x(self, vx, vy, vw, vh, val):
        for band in self._bands:
            bv_min, bv_max = band["lo_val"], band["hi_val"]
            bh = band["width"]
            x_left  = self._cx + (bv_min - val) * self._ppu
            x_right = self._cx + (bv_max - val) * self._ppu
            x_left  = max(x_left,  vx)
            x_right = min(x_right, vx + vw)
            if x_right <= x_left:
                continue
            side = band.get("side") or self._tick_side
            by = (vy + vh - bh) if side == "top" else vy
            dash = float(band.get("dash", 0.0))
            if dash > 0:
                x = x_left
                on = True
                while x < x_right:
                    seg = min(x + dash, x_right)
                    if on:
                        arcade.draw_rect_filled(arcade.LBWH(x, by, seg - x, bh), band["color"])
                    x = seg
                    on = not on
            else:
                arcade.draw_rect_filled(arcade.LBWH(x_left, by, x_right - x_left, bh), band["color"])

    def _draw_ticks_x(self, vx, vy, vw, vh, val):
        spine_y  = (vy + vh) if self._tick_side == "top" else vy
        tick_dir = -1 if self._tick_side == "top" else 1
        half_range = vw / 2 / self._ppu
        v_min = val - half_range - 1
        v_max = val + half_range + 1
        for td in self._tick_defs:
            interval = float(td["interval"])
            length   = float(td["length"])
            width    = max(1.0, float(td["width"]))
            offset   = float(td.get("offset", 0.0))
            color    = _col(td.get("color", self._tick_color_default))
            y0 = spine_y + tick_dir * offset
            y1 = spine_y + tick_dir * (offset + length)
            v = math.floor(v_min / interval) * interval
            while v <= v_max + interval * 0.001:
                x = self._cx + (v - val) * self._ppu
                arcade.draw_line(x, y0, x, y1, color, width)
                v += interval

    def _draw_bugs_x(self, vx, vy, vw, vh, val):
        if not self._bugs:
            return
        spine_y = (vy + vh) if self._tick_side == "top" else vy
        for bug in self._bugs:
            anchor_x = self._cx + (bug._current_value - val) * self._ppu
            anchor_x = max(vx, min(vx + vw, anchor_x))
            pts = [(anchor_x + px, spine_y + py) for px, py in bug._points]
            if len(pts) < 3:
                continue
            if bug._filled:
                arcade.draw_polygon_filled(pts, bug._color)
            else:
                arcade.draw_polygon_outline(pts, bug._color, bug._width)

    def _draw_labels_x(self, vx, vy, vw, vh, val):
        if self._label_interval <= 0:
            return
        spine_y = (vy + vh) if self._tick_side == "top" else vy
        side = self._label_side if self._label_side is not None else self._tick_side
        if side == "top":
            ly, anchor_y = spine_y + self._label_offset, "bottom"
        else:
            ly, anchor_y = spine_y - self._label_offset, "top"
        half_range = vw / 2 / self._ppu
        v_min = val - half_range - 1
        v_max = val + half_range + 1
        v = math.floor(v_min / self._label_interval) * self._label_interval
        idx = 0
        while v <= v_max + self._label_interval * 0.001:
            x = self._cx + (v - val) * self._ppu
            if idx >= len(self._label_pool):
                kw: dict = dict(bold=self._label_bold, italic=self._label_italic)
                if self._label_font:
                    kw["font_name"] = self._label_font
                self._label_pool.append(arcade.Text(
                    "", 0, 0,
                    color=self._label_color,
                    font_size=self._label_font_size,
                    anchor_x="center",
                    anchor_y=anchor_y,
                    **kw,
                ))
            t = self._label_pool[idx]
            t.value = self._label_text(v)
            t.x = x
            t.y = ly
            t.draw()
            idx += 1
            v += self._label_interval


# -- Factory + registration ---------------------------------------------------

def _vector_tape_factory(
    comp: dict[str, Any],
    base_dir: Path,
    container_size: tuple[int, int] | None = None,
) -> VectorTape:
    tick_defs = []
    for td in comp.get("ticks", []):
        tick_defs.append({
            "interval": float(td["interval"]),
            "length":   float(td["length"]),
            "width":    float(td.get("width", 2.0)),
            "offset":   float(td.get("offset", 0.0)),
            "color":    td.get("color"),  # None → use tape-level default
        })

    lbl  = comp.get("labels", {})
    bands_raw = comp.get("bands", [])
    bands = [
        {
            "range": b["range"],   # kept as-is; _parse_endpoint handles float or dict
            "color": b["color"],
            "width": float(b.get("width", 8.0)),
            "side": b.get("side"),
            "dash": float(b["dash"]) if b.get("dash") else 0.0,
        }
        for b in bands_raw
    ]

    label_side_raw = lbl.get("side")
    tape = VectorTape(
        name=comp["name"],
        position_xy=tuple(comp["position"]),
        viewport=tuple(comp["viewport"]),
        axis=str(comp.get("scroll_axis", "y")),
        pixels_per_unit=float(comp.get("pixels_per_unit", 5.0)),
        tick_side=str(comp.get("tick_side", "left")),
        tick_color_default=_col(comp.get("tick_color")),
        tick_defs=tick_defs,
        label_interval=float(lbl.get("interval", 0)),
        label_font_size=float(lbl.get("font_size", 18.0)),
        label_color=_col(lbl.get("color")),
        label_format=str(lbl.get("format", "{:.0f}")),
        label_offset=float(lbl.get("offset", 8.0)),
        label_side=str(label_side_raw) if label_side_raw is not None else None,
        label_font=str(lbl["font"]) if lbl.get("font") else None,
        label_bold=bool(lbl.get("bold", False)),
        label_italic=bool(lbl.get("italic", False)),
        bands=bands,
        bugs=comp.get("bugs") or [],
        wrap=float(comp["wrap"]) if comp.get("wrap") is not None else None,
        bg_color=comp.get("bg_color"),
    )

    if "scroll" in comp:
        s = comp["scroll"]
        tape.set_scroll(
            dataref=s["dataref"],
            table=s["table"],
            convert_function=s.get("convert_function"),
        )

    if "visibility" in comp:
        v = comp["visibility"]
        tape.set_visibility(v["dataref"], v["predicate"])

    return tape


register_component("VectorTape", _vector_tape_factory)
