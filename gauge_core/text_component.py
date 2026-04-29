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

        self.visible = True

        # Optional dataref-driven text
        self._dataref: Any | None = None
        self._format: str | None = None
        self._convert: Callable | None = None
        self._static_text = text

    def set_dataref(
        self,
        dataref: Any,
        text_format: str = "{:.1f}",
        convert_function: str | None = None,
    ) -> None:
        self._dataref = _as_dataref(dataref)
        self._format = text_format
        self._convert = get_convert(convert_function)

    def set_visible(self, visible: bool) -> None:
        self.visible = visible

    def update(self, get_data: Callable[[Any], float]) -> None:
        if self._dataref is not None and self._format is not None:
            value = float(get_data(self._dataref))
            if self._convert is not None:
                value = float(self._convert(value, get_data))
            self.label.text = self._format.format(value)

    def draw(self) -> None:
        if self.visible:
            self.label.draw()


def _text_factory(comp: dict[str, Any], _base_dir: Path) -> Text:
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
    return text


register_component("Text", _text_factory)
