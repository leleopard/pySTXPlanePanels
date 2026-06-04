"""ScrollingTape component — continuously scrolling texture strip.

For instruments that show a moving window over a long texture (e.g. G1000
airspeed and altitude tapes).  The texture represents the full value range
as a continuous strip; a lookup table maps the dataref value to a pixel
scroll offset; a viewport scissor clip confines what is visible.

The scroll direction is either vertical (scroll_axis: y, the common case
for altitude/airspeed tapes) or horizontal (scroll_axis: x).

Texture size constraint
-----------------------
The scroll dimension must not exceed GL_MAX_TEXTURE_SIZE (8 192 px is the
safe cross-platform limit).  A G1000 airspeed tape covering 0–400 kt at
~10 px/kt is 4 000 px — well within that bound.  If a value range requires
a longer strip, split it into sections or reduce px-per-unit.

Key distinction from SpriteSheet
---------------------------------
ScrollingTape uses a single continuous texture with no discrete frames.
SpriteSheet uses a grid of pre-rendered frames.  The visual result can look
similar, but ScrollingTape has no inter-frame boundaries and is the right
choice whenever the texture was authored as a seamless strip.

YAML schema
-----------
    - type: ScrollingTape
      name: airspeed_tape
      texture: assets/airspeed_tape.png
      scroll_axis: y                   # 'y' (default) or 'x'
      position: [50, 450]              # centre of the visible window, instrument coords
      viewport: [0, 300, 100, 300]     # scissor clip [x, y, w, h], instrument coords
      scroll:
        dataref: sim/cockpit2/gauges/indicators/airspeed_kts_pilot
        table: [[0, 0], [300, 3000]]   # value → pixel offset into the texture
        convert_function: null         # optional
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import arcade

from gauge_core.lookup import lookup_piecewise
from gauge_core.registry import get_convert, register_component
from gauge_core.textures import load_full_texture


class ScrollingTape:
    """Single-axis scrolling texture strip driven by a dataref."""

    def __init__(
        self,
        name: str,
        atlas_path: Path,
        scroll_axis: str,
        position_xy: tuple[float, float],
    ) -> None:
        if scroll_axis not in ("x", "y"):
            raise ValueError(f"scroll_axis must be 'x' or 'y', got {scroll_axis!r}")

        self.name = name
        self._axis = scroll_axis

        texture = load_full_texture(atlas_path)
        self._tex_w = texture.width
        self._tex_h = texture.height

        self.sprite = arcade.Sprite(texture)
        self._base_x = float(position_xy[0])
        self._base_y = float(position_xy[1])
        self._inst_scale: float = 1.0
        self._last_offset: float = 0.0

        self._scroll_dataref: Any | None = None
        self._scroll_table: list[list[float]] | None = None
        self._scroll_convert: Callable | None = None
        self._viewport: tuple[float, float, float, float] | None = None

        self._scroll_to(0.0)

    # -- configuration --------------------------------------------------------

    def set_scroll(
        self,
        dataref: Any,
        table: list[list[float]],
        convert_function: str | None = None,
    ) -> None:
        self._scroll_dataref = dataref
        self._scroll_table = table
        self._scroll_convert = get_convert(convert_function)

    def set_viewport(self, x: float, y: float, w: float, h: float) -> None:
        self._viewport = (x, y, w, h)

    # -- panel composition ----------------------------------------------------

    def apply_scale(self, scale: float) -> None:
        self._inst_scale *= scale
        self._base_x *= scale
        self._base_y *= scale
        self.sprite.scale_x *= scale
        self.sprite.scale_y *= scale
        if self._viewport is not None:
            vx, vy, vw, vh = self._viewport
            self._viewport = (vx * scale, vy * scale, vw * scale, vh * scale)
        self._scroll_to(self._last_offset)

    def apply_offset(self, dx: float, dy: float) -> None:
        self._base_x += dx
        self._base_y += dy
        if self._viewport is not None:
            vx, vy, vw, vh = self._viewport
            self._viewport = (vx + dx, vy + dy, vw, vh)
        self._scroll_to(self._last_offset)

    # -- per-frame ------------------------------------------------------------

    def _scroll_to(self, offset_px: float) -> None:
        """Position the sprite so texture pixel *offset_px* is at base_x/y."""
        self._last_offset = offset_px
        s = self._inst_scale
        if self._axis == "y":
            # offset_px is the atlas row (y-down) to centre in the viewport.
            # center_y = base_y - (tex_h/2 - offset_px) * scale
            self.sprite.center_x = self._base_x
            self.sprite.center_y = self._base_y - (self._tex_h / 2 - offset_px) * s
        else:
            # offset_px is the atlas column (x left-to-right) to centre.
            # center_x = base_x - (offset_px - tex_w/2) * scale
            self.sprite.center_x = self._base_x - (offset_px - self._tex_w / 2) * s
            self.sprite.center_y = self._base_y

    def update(self, get_data: Callable[[Any], float]) -> None:
        if self._scroll_dataref is None or self._scroll_table is None:
            return
        raw = float(get_data(self._scroll_dataref))
        if self._scroll_convert is not None:
            raw = float(self._scroll_convert(raw, get_data))
        self._scroll_to(lookup_piecewise(self._scroll_table, raw))

    def draw(self) -> None:
        if not self.sprite.visible:
            return
        if self._viewport is not None:
            vx, vy, vw, vh = self._viewport
            win = arcade.get_window()
            ctx = win.ctx
            # ctx.scissor is in framebuffer pixels; scale from logical coords.
            # ctx.viewport reflects the active FBO (e.g. 4× larger under SSAA).
            _, _, fvp_w, fvp_h = ctx.viewport
            sx = fvp_w / win.width
            sy = fvp_h / win.height
            ctx.scissor = (int(vx * sx), int(vy * sy), int(vw * sx), int(vh * sy))
            arcade.draw_sprite(self.sprite)
            ctx.scissor = None
        else:
            arcade.draw_sprite(self.sprite)


# -- factory + registration ---------------------------------------------------

def _scrolling_tape_factory(
    comp: dict[str, Any],
    base_dir: Path,
    container_size: tuple[int, int] | None = None,  # noqa: ARG001
) -> ScrollingTape:
    atlas_path = (base_dir / comp["texture"]).resolve()

    tape = ScrollingTape(
        name=comp["name"],
        atlas_path=atlas_path,
        scroll_axis=str(comp.get("scroll_axis", "y")),
        position_xy=tuple(comp["position"]),
    )

    if "scroll" in comp:
        scr = comp["scroll"]
        dataref = scr["dataref"]
        if isinstance(dataref, list):
            dataref = tuple(dataref)
        tape.set_scroll(
            dataref=dataref,
            table=scr["table"],
            convert_function=scr.get("convert_function"),
        )

    if "viewport" in comp:
        vx, vy, vw, vh = comp["viewport"]
        tape.set_viewport(float(vx), float(vy), float(vw), float(vh))

    return tape


register_component("ScrollingTape", _scrolling_tape_factory)
