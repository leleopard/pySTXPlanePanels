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
        - interval: 20
          length: 30
          width: 3
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
        - range: [0, 67]
          color: [200, 0, 0, 180]
          width: 8
        - range: [67, 200]
          color: [0, 180, 0, 180]
          width: 8
      wrap: 10                         # optional: label digits cycle modulo this
                                     # value (e.g. 10 for a 0-9 counter drum)
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


def _as_dataref(raw: Any) -> Any:
    return tuple(raw) if isinstance(raw, list) else raw


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
        bands: list[dict] | None = None,
        wrap: float | None = None,
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
        self._wrap = float(wrap) if wrap is not None else None
        self._bands: list[dict] = []
        for b in (bands or []):
            self._bands.append({
                "range": list(b["range"]),
                "color": _col(b["color"]),
                "width": float(b.get("width", 8.0)),
            })

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
        self._label_offset    *= scale
        self._label_font_size *= scale
        self._label_pool.clear()  # font size changed; pool objects are stale
        for band in self._bands:
            band["width"] *= scale

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

    def draw(self) -> None:
        if not self._visible:
            return
        ctx = arcade.get_window().ctx
        vx, vy, vw, vh = self._vp_x, self._vp_y, self._vp_w, self._vp_h
        val = self._current_value

        ctx.scissor = (int(vx), int(vy), int(vw), int(vh))
        if self._axis == "y":
            self._draw_bands_y(vx, vy, vw, vh, val)
            self._draw_ticks_y(vx, vy, vw, vh, val)
        else:
            self._draw_bands_x(vx, vy, vw, vh, val)
            self._draw_ticks_x(vx, vy, vw, vh, val)
        ctx.scissor = None

        win = arcade.get_window()
        if self._axis == "y":
            # Clip labels to the viewport's vertical band only; let them span
            # the full window width so they can sit outside the tick viewport.
            ctx.scissor = (0, int(vy), win.width, int(vh))
            self._draw_labels_y(vx, vy, vw, vh, val)
        else:
            # Clip labels to the viewport's horizontal band only.
            ctx.scissor = (int(vx), 0, int(vw), win.height)
            self._draw_labels_x(vx, vy, vw, vh, val)
        ctx.scissor = None

    # -- vertical tape --------------------------------------------------------

    def _draw_bands_y(self, vx, vy, vw, vh, val):
        for band in self._bands:
            bv_min, bv_max = band["range"]
            bw = band["width"]
            y_bot = self._cy + (bv_min - val) * self._ppu
            y_top = self._cy + (bv_max - val) * self._ppu
            y_bot = max(y_bot, vy)
            y_top = min(y_top, vy + vh)
            if y_top <= y_bot:
                continue
            bx = vx if self._tick_side == "left" else vx + vw - bw
            arcade.draw_rect_filled(
                arcade.LBWH(bx, y_bot, bw, y_top - y_bot),
                band["color"],
            )

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
            color    = _col(td.get("color", self._tick_color_default))
            v = math.floor(v_min / interval) * interval
            while v <= v_max + interval * 0.001:
                y = self._cy + (v - val) * self._ppu
                arcade.draw_line(
                    spine_x, y,
                    spine_x + tick_dir * length, y,
                    color, width,
                )
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
                kw: dict = {}
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

    # -- horizontal tape ------------------------------------------------------

    def _draw_bands_x(self, vx, vy, vw, vh, val):
        for band in self._bands:
            bv_min, bv_max = band["range"]
            bh = band["width"]
            x_left  = self._cx + (bv_min - val) * self._ppu
            x_right = self._cx + (bv_max - val) * self._ppu
            x_left  = max(x_left,  vx)
            x_right = min(x_right, vx + vw)
            if x_right <= x_left:
                continue
            by = (vy + vh - bh) if self._tick_side == "top" else vy
            arcade.draw_rect_filled(
                arcade.LBWH(x_left, by, x_right - x_left, bh),
                band["color"],
            )

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
            color    = _col(td.get("color", self._tick_color_default))
            v = math.floor(v_min / interval) * interval
            while v <= v_max + interval * 0.001:
                x = self._cx + (v - val) * self._ppu
                arcade.draw_line(
                    x, spine_y,
                    x, spine_y + tick_dir * length,
                    color, width,
                )
                v += interval

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
                kw: dict = {}
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
            "color":    td.get("color"),  # None → use tape-level default
        })

    lbl  = comp.get("labels", {})
    bands_raw = comp.get("bands", [])
    bands = [
        {
            "range": list(b["range"]),
            "color": b["color"],
            "width": float(b.get("width", 8.0)),
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
        bands=bands,
        wrap=float(comp["wrap"]) if comp.get("wrap") is not None else None,
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
