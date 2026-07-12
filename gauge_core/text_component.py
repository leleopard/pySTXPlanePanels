"""Text component — static label or dataref-driven readout.

Wraps `arcade.Text`. For the C172 six-pack the gauge faces have text
baked into the PNG so this component is not required for any instrument
YAML, but it's the building block the panel runtime uses for status
overlays (FPS counter, "no XP data" warning), and it's available for
future glass-cockpit numeric readouts.

Dataref modes (mutually exclusive, both require `position` + `dataref`):
  - Numeric (default): `dataref` is read as a single float, optionally
    passed through `convert_function`/`absolute_value`, then formatted via
    `text_format` (a Python format spec, e.g. "{:.0f}").
  - Character array: set `char_count` to a positive int instead. For an
    X-Plane string/byte-array dataref (e.g. a nav station ident like
    "IOM") that can't be read as a single float over the UDP RREF
    protocol — X-Plane DOES support per-character access via array-index
    syntax on the dataref path (`dataref[0]`, `dataref[1]`, ...), each
    answered as the raw ASCII byte value. `char_count` subscribes to that
    many indexed sub-datarefs and joins their `chr()` values into the
    label text directly (no `text_format` involved), stopping at the
    first byte <= 0 (null terminator / unfilled padding), the same way a
    C string would.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import arcade

from gauge_core.emphasize import split_at_place
from gauge_core.font_utils import resolve_font_for_arcade
from gauge_core.registry import (
    get_convert,
    register_component,
    resolve_predicate_name,
)


def _as_dataref(raw: Any) -> Any:
    if isinstance(raw, list):
        return tuple(raw)
    return raw


def _as_color(raw: Any) -> tuple[int, int, int, int]:
    """Accept [r,g,b] or [r,g,b,a] in 0..255 ints; default alpha = 255."""
    if raw is None:
        return (255, 255, 255, 255)
    if len(raw) == 3:
        return (int(raw[0]), int(raw[1]), int(raw[2]), 255)
    return (int(raw[0]), int(raw[1]), int(raw[2]), int(raw[3]))


class Text:
    def __init__(
        self,
        name: str,
        position_xy: tuple[float, float],
        text: str = "",
        font_name: str | None = None,
        font_size: float = 12.0,
        color: tuple[int, int, int, int] = (255, 255, 255, 255),
        anchor_x: str = "left",
        anchor_y: str = "baseline",
        bold: bool = False,
        italic: bool = False,
        emphasize_place: float | None = None,
        emphasize_font_size: float | None = None,
    ) -> None:
        self.name = name
        # Overall alignment intent (left/center/right). When emphasizing,
        # both label objects are manually positioned with anchor_x="left"
        # and this is applied to their combined width instead.
        self._anchor_x_mode = anchor_x
        self._emphasize_place = float(emphasize_place) if emphasize_place else None

        label_anchor_x = "left" if self._emphasize_place else anchor_x

        # arcade.Text font_name accepts a tuple of fallbacks too; use the
        # default if the caller passes nothing.
        kwargs: dict[str, Any] = dict(
            text=text,
            x=float(position_xy[0]),
            y=float(position_xy[1]),
            color=color,
            font_size=font_size,
            anchor_x=label_anchor_x,
            anchor_y=anchor_y,
            bold=bold,
            italic=italic,
        )
        if font_name:
            kwargs["font_name"] = font_name
        self.label = arcade.Text(**kwargs)

        # Second label for the emphasized (usually larger) leading digits,
        # e.g. the "30" in "30,000" ft. Only created when configured; laid
        # out adjacent to self.label each time the dataref value changes.
        self.label_hi: arcade.Text | None = None
        if self._emphasize_place:
            hi_kwargs = dict(kwargs)
            hi_kwargs["text"] = ""
            hi_kwargs["font_size"] = emphasize_font_size or font_size
            self.label_hi = arcade.Text(**hi_kwargs)

        # Track position separately so apply_offset() can be called before
        # the Arcade window is created (arcade.Text is lazily GPU-initialised;
        # accessing its .x/.y property triggers _init_deferred() which
        # requires an active window).
        self._x = float(position_xy[0])
        self._y = float(position_xy[1])
        self._pos_dirty = False

        self.visible = True

        # Optional dataref-driven text
        self._dataref: Any | None = None
        self._format: str | None = None
        self._convert: Callable | None = None
        self._absolute_value = False
        self._static_text = text

        # Optional character-array mode (mutually exclusive with the plain
        # numeric dataref above) — for X-Plane string/byte-array datarefs
        # that can't be read as a single float (e.g. a nav station ident
        # like "IOM"). Subscribes to dataref[0]..dataref[N-1] as N separate
        # scalar datarefs and joins their ASCII codes into text.
        self._char_datarefs: list[Any] = []

        # Optional dataref-driven visibility (mirrors ImagePanel behaviour)
        self._vis_dataref: Any | None = None
        self._vis_predicate: Callable | None = None

    def set_dataref(
        self,
        dataref: Any,
        text_format: str = "{:.1f}",
        convert_function: str | None = None,
        absolute_value: bool = False,
    ) -> None:
        self._dataref = _as_dataref(dataref)
        self._format = text_format
        self._convert = get_convert(convert_function)
        self._absolute_value = bool(absolute_value)

    def set_char_array_dataref(self, dataref: Any, char_count: int) -> None:
        """`dataref` must be a plain X-Plane dataref path string (not a
        (group, index) tuple) — each character is requested as its own
        scalar dataref via X-Plane's array-index syntax, e.g.
        "sim/.../nav1_dme_id[0]", "...[1]", ... which X-Plane answers with
        the raw byte value (ASCII code) at that array position."""
        count = max(1, int(char_count))
        self._char_datarefs = [f"{dataref}[{i}]" for i in range(count)]

    def set_visibility(self, dataref: Any, predicate: str) -> None:
        self._vis_dataref = _as_dataref(dataref)
        self._vis_predicate = get_convert(predicate)
        if self._vis_predicate is None:
            raise ValueError("visibility requires a predicate name")

    def set_visible(self, visible: bool) -> None:
        self.visible = visible

    def apply_scale(self, scale: float) -> None:
        """Scale the label position and size around the instrument origin."""
        self._x *= scale
        self._y *= scale
        self.label.font_size *= scale
        if self.label_hi is not None:
            self.label_hi.font_size *= scale
        self._pos_dirty = True

    def apply_offset(self, dx: float, dy: float) -> None:
        """Shift the label position. Used by panel composition."""
        self._x += dx
        self._y += dy
        self._pos_dirty = True

    def _layout_emphasized(self) -> None:
        """Position label_hi and label side-by-side, honoring anchor_x_mode.

        Both are created with anchor_x="left"; this computes their combined
        width and positions the pair so it aligns as if it were one run of
        text anchored left/center/right at self._x, per the original
        anchor_x the caller configured.
        """
        hi_w = self.label_hi.content_width
        lo_w = self.label.content_width
        total = hi_w + lo_w
        if self._anchor_x_mode == "right":
            start = self._x - total
        elif self._anchor_x_mode == "center":
            start = self._x - total / 2
        else:
            start = self._x
        self.label_hi.x = start
        self.label_hi.y = self._y
        self.label.x = start + hi_w
        self.label.y = self._y

    def update(self, get_data: Callable[[Any], float]) -> None:
        if self._pos_dirty:
            if self.label_hi is None:
                self.label.x = self._x
            self.label.y = self._y
            self._pos_dirty = False

        if self._char_datarefs:
            chars = []
            for dr in self._char_datarefs:
                code = int(get_data(dr))
                if code <= 0:
                    break  # null terminator / unfilled padding — stop, like a C string
                chars.append(chr(code))
            self.label.text = "".join(chars)
        elif self._dataref is not None and self._format is not None:
            value = float(get_data(self._dataref))
            if self._convert is not None:
                value = float(self._convert(value, get_data))
            if self._absolute_value:
                value = abs(value)
            if self.label_hi is not None:
                hi_text, lo_text = split_at_place(value, self._emphasize_place)
                self.label_hi.text = hi_text
                self.label.text = lo_text
                self._layout_emphasized()
            else:
                self.label.text = self._format.format(value)

        if self._vis_dataref is not None and self._vis_predicate is not None:
            value = float(get_data(self._vis_dataref))
            self.visible = bool(self._vis_predicate(value, get_data))

    def draw(self) -> None:
        if self.visible:
            self.label.draw()
            if self.label_hi is not None:
                self.label_hi.draw()


def _text_factory(
    comp: dict[str, Any],
    base_dir: Path,
    container_size: tuple[int, int] | None = None,  # noqa: ARG001
) -> Text:
    font_name, bold, italic = resolve_font_for_arcade(
        comp.get("font_name"), base_dir,
        bold=bool(comp.get("bold", False)),
        italic=bool(comp.get("italic", False)),
        explicit_file=comp.get("font_file"),
    )

    text = Text(
        name=comp["name"],
        position_xy=tuple(comp["position"]),
        text=comp.get("text", ""),
        font_name=font_name,
        font_size=float(comp.get("font_size", 12.0)),
        color=_as_color(comp.get("color")),
        anchor_x=comp.get("anchor_x", "left"),
        anchor_y=comp.get("anchor_y", "baseline"),
        bold=bold,
        italic=italic,
        emphasize_place=comp.get("emphasize_place"),
        emphasize_font_size=comp.get("emphasize_font_size"),
    )
    if "dataref" in comp:
        char_count = comp.get("char_count")
        if char_count:
            text.set_char_array_dataref(dataref=comp["dataref"], char_count=int(char_count))
        else:
            text.set_dataref(
                dataref=comp["dataref"],
                text_format=comp.get("text_format", "{:.1f}"),
                convert_function=comp.get("convert_function"),
                absolute_value=bool(comp.get("absolute_value", False)),
            )
    if "visibility" in comp:
        vis = comp["visibility"]
        text.set_visibility(dataref=vis["dataref"], predicate=resolve_predicate_name(vis))
    return text


register_component("Text", _text_factory)
