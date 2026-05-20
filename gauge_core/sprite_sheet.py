"""SpriteSheet component — frame-indexed sprite grid.

For instruments that store pre-rendered frames in a regular columns × rows
grid on a single texture.  At runtime a dataref value is mapped through a
lookup table to a (possibly fractional) frame index; the full atlas sprite
is repositioned so that frame is centred in a viewport scissor window.

Typical uses
------------
- Compass rose  : 361 heading frames in a 16 × 23 grid, smooth=true so
                  the fractional heading interpolates between adjacent
                  frames giving fluid rotation.
- Digit drums   : 10 digit frames in a 1 × 10 or 10 × 1 grid, smooth=false
                  so digits snap cleanly.

Texture size constraint
-----------------------
The atlas must fit within GL_MAX_TEXTURE_SIZE.  8 192 px per dimension is
the safe cross-platform floor; a 2 048 × 2 048 atlas is the recommended
size for sprite grids and comfortably fits any instrument panel in use.

YAML schema
-----------
    - type: SpriteSheet
      name: compass_rose
      texture: assets/compass_texture.png
      columns: 16
      rows: 23
      frame_width: 120
      frame_height: 66
      # stride_x: 122   # optional; defaults to frame_width.  Use when
      # stride_y: 66    # there are inter-frame gaps in the atlas.
      smooth: true      # optional, default true.  Set false for digit drums.
      position: [760, 66]          # centre of the visible window, instrument coords
      viewport: [700, 33, 120, 66] # scissor clip [x, y, w, h], instrument coords
      animation:
        dataref: sim/flightmodel/position/mag_psi
        table: [[0, 0], [360, 360]]
        convert_function: null     # optional
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import arcade

from gauge_core.lookup import lookup_piecewise
from gauge_core.registry import get_convert, register_component
from gauge_core.textures import load_full_texture


class SpriteSheet:
    """Frame-indexed sprite sheet driven by a dataref."""

    def __init__(
        self,
        name: str,
        atlas_path: Path,
        columns: int,
        rows: int,
        frame_width: int,
        frame_height: int,
        stride_x: int,
        stride_y: int,
        position_xy: tuple[float, float],
        smooth: bool = True,
    ) -> None:
        self.name = name
        self._columns = columns
        self._rows = rows
        self._frame_w = frame_width
        self._frame_h = frame_height
        self._stride_x = stride_x
        self._stride_y = stride_y
        self._smooth = smooth

        texture = load_full_texture(atlas_path)
        self._tex_w = texture.width
        self._tex_h = texture.height

        self.sprite = arcade.Sprite(texture)
        self._base_x = float(position_xy[0])
        self._base_y = float(position_xy[1])
        self._inst_scale: float = 1.0
        self._last_frame: float = 0.0

        self._anim_dataref: Any | None = None
        self._anim_table: list[list[float]] | None = None
        self._anim_convert: Callable | None = None
        self._viewport: tuple[float, float, float, float] | None = None

        self._set_frame(0.0)

    # -- configuration --------------------------------------------------------

    def set_animation(
        self,
        dataref: Any,
        table: list[list[float]],
        convert_function: str | None = None,
    ) -> None:
        self._anim_dataref = dataref
        self._anim_table = table
        self._anim_convert = get_convert(convert_function)

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
        self._set_frame(self._last_frame)

    def apply_offset(self, dx: float, dy: float) -> None:
        self._base_x += dx
        self._base_y += dy
        if self._viewport is not None:
            vx, vy, vw, vh = self._viewport
            self._viewport = (vx + dx, vy + dy, vw, vh)
        self._set_frame(self._last_frame)

    # -- per-frame ------------------------------------------------------------

    def _set_frame(self, frame_value: float) -> None:
        """Position the sprite so frame *frame_value* is centred at base_x/y."""
        self._last_frame = frame_value

        total = self._columns * self._rows
        int_frame = max(0, min(total - 1, int(frame_value)))
        frac = (frame_value - int_frame) if self._smooth else 0.0

        col = int_frame % self._columns
        row = int_frame // self._columns

        # Centre of the target frame in atlas coords (x left-to-right, y down).
        # The fractional part shifts X toward the next column for smooth scroll.
        tx = col * self._stride_x + self._frame_w / 2 - frac * self._stride_x
        ty_down = row * self._stride_y + self._frame_h / 2

        # To bring atlas point (tx, ty_down) to screen position (base_x, base_y):
        #   center_x = base_x - (tx  - tex_w/2) * scale
        #   center_y = base_y - (tex_h/2 - ty_down) * scale
        # (y formula derived from Arcade's y-up / PIL y-down convention)
        s = self._inst_scale
        self.sprite.center_x = self._base_x - (tx - self._tex_w / 2) * s
        self.sprite.center_y = self._base_y - (self._tex_h / 2 - ty_down) * s

    def update(self, get_data: Callable[[Any], float]) -> None:
        if self._anim_dataref is None or self._anim_table is None:
            return
        raw = float(get_data(self._anim_dataref))
        if self._anim_convert is not None:
            raw = float(self._anim_convert(raw, get_data))
        self._set_frame(lookup_piecewise(self._anim_table, raw))

    def draw(self) -> None:
        if not self.sprite.visible:
            return
        if self._viewport is not None:
            vx, vy, vw, vh = self._viewport
            ctx = arcade.get_window().ctx
            ctx.scissor = (int(vx), int(vy), int(vw), int(vh))
            arcade.draw_sprite(self.sprite)
            ctx.scissor = None
        else:
            arcade.draw_sprite(self.sprite)


# -- factory + registration ---------------------------------------------------

def _sprite_sheet_factory(
    comp: dict[str, Any],
    base_dir: Path,
    container_size: tuple[int, int] | None = None,  # noqa: ARG001
) -> SpriteSheet:
    atlas_path = (base_dir / comp["texture"]).resolve()
    frame_w = int(comp["frame_width"])
    frame_h = int(comp["frame_height"])

    sheet = SpriteSheet(
        name=comp["name"],
        atlas_path=atlas_path,
        columns=int(comp["columns"]),
        rows=int(comp["rows"]),
        frame_width=frame_w,
        frame_height=frame_h,
        stride_x=int(comp.get("stride_x", frame_w)),
        stride_y=int(comp.get("stride_y", frame_h)),
        position_xy=tuple(comp["position"]),
        smooth=bool(comp.get("smooth", True)),
    )

    if "animation" in comp:
        anim = comp["animation"]
        dataref = anim["dataref"]
        if isinstance(dataref, list):
            dataref = tuple(dataref)
        sheet.set_animation(
            dataref=dataref,
            table=anim["table"],
            convert_function=anim.get("convert_function"),
        )

    if "viewport" in comp:
        vx, vy, vw, vh = comp["viewport"]
        sheet.set_viewport(float(vx), float(vy), float(vw), float(vh))

    return sheet


register_component("SpriteSheet", _sprite_sheet_factory)
