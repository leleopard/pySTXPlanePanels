"""Text component — static label or dataref-driven readout.

Wraps `arcade.Text`. For the C172 six-pack the gauge faces have text
baked into the PNG so this component is not required for any instrument
YAML, but it's the building block the panel runtime uses for status
overlays (FPS counter, "no XP data" warning), and it's available for
future glass-cockpit numeric readouts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import arcade

from gauge_core.registry import (
    get_convert,
    register_component,
)


# Cache of font files we've already registered with pyglet so each TTF is
# loaded at most once, even when many components reference it.
_FONT_FILES_LOADED: set[str] = set()


def _ensure_font_loaded(font_path: Path) -> None:
    key = str(font_path.resolve())
    if key in _FONT_FILES_LOADED:
        return
    arcade.load_font(key)
    _FONT_FILES_LOADED.add(key)


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
    ) -> None:
        self.name = name
        # arcade.Text font_name accepts a tuple of fallbacks too; use the
        # default if the caller passes nothing.
        kwargs: dict[str, Any] = dict(
            text=text,
            x=float(position_xy[0]),
            y=float(position_xy[1]),
            color=color,
            font_size=font_size,
            anchor_x=anchor_x,
            anchor_y=anchor_y,
        )
        if font_name:
            kwargs["font_name"] = font_name
        self.label = arcade.Text(**kwargs)

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
        self._static_text = text

        # Optional dataref-driven visibility (mirrors ImagePanel behaviour)
        self._vis_dataref: Any | None = None
        self._vis_predicate: Callable | None = None

    def set_dataref(
        self,
        dataref: Any,
        text_format: str = "{:.1f}",
        convert_function: str | None = None,
    ) -> None:
        self._dataref = _as_dataref(dataref)
        self._format = text_format
        self._convert = get_convert(convert_function)

    def set_visibility(self, dataref: Any, predicate: str) -> None:
        self._vis_dataref = _as_dataref(dataref)
        self._vis_predicate = get_convert(predicate)
        if self._vis_predicate is None:
            raise ValueError("visibility requires a predicate name")

    def set_visible(self, visible: bool) -> None:
        self.visible = visible

    def apply_offset(self, dx: float, dy: float) -> None:
        """Shift the label position. Used by panel composition."""
        self._x += dx
        self._y += dy
        self._pos_dirty = True

    def update(self, get_data: Callable[[Any], float]) -> None:
        if self._pos_dirty:
            self.label.x = self._x
            self.label.y = self._y
            self._pos_dirty = False

        if self._dataref is not None and self._format is not None:
            value = float(get_data(self._dataref))
            if self._convert is not None:
                value = float(self._convert(value, get_data))
            self.label.text = self._format.format(value)

        if self._vis_dataref is not None and self._vis_predicate is not None:
            value = float(get_data(self._vis_dataref))
            self.visible = bool(self._vis_predicate(value, get_data))

    def draw(self) -> None:
        if self.visible:
            self.label.draw()


def _text_factory(comp: dict[str, Any], base_dir: Path) -> Text:
    # If the YAML supplies a `font_file` it's resolved relative to the
    # instrument YAML and registered with pyglet so the family name passed
    # in `font_name` resolves to the bundled TTF rather than a system font.
    if "font_file" in comp:
        font_path = (base_dir / comp["font_file"]).resolve()
        _ensure_font_loaded(font_path)

    text = Text(
        name=comp["name"],
        position_xy=tuple(comp["position"]),
        text=comp.get("text", ""),
        font_name=comp.get("font_name"),
        font_size=float(comp.get("font_size", 12.0)),
        color=_as_color(comp.get("color")),
        anchor_x=comp.get("anchor_x", "left"),
        anchor_y=comp.get("anchor_y", "baseline"),
    )
    if "dataref" in comp:
        text.set_dataref(
            dataref=comp["dataref"],
            text_format=comp.get("text_format", "{:.1f}"),
            convert_function=comp.get("convert_function"),
        )
    if "visibility" in comp:
        vis = comp["visibility"]
        text.set_visibility(dataref=vis["dataref"], predicate=vis["predicate"])
    return text


register_component("Text", _text_factory)
