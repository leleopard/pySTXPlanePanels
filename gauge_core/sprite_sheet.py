"""SpriteSheet component — frame-indexed sprite grid.

For instruments that store pre-rendered frames in a regular columns × rows
grid on a single texture.  At runtime a dataref value is mapped through a
lookup table to a frame index; the full atlas sprite is repositioned so
that frame is centred in a viewport scissor window.

Frame selection
---------------
The animation table maps the raw dataref to an intermediate value V.
    frame_index = floor(V / units_per_frame)
    sub_frac    = (V % units_per_frame) / units_per_frame   [0, 1)

units_per_frame (default 1.0) decouples how many table-output units
constitute one full sprite step.  When smooth=true, sub_frac drives a
pixel-level shift of sub_frac × frame_width within the current frame,
giving fluid sub-unit animation without jumping past adjacent frames.

Typical uses
------------
- Wet compass   : 361 heading frames in a 16 × 23 grid.
                  table [[0,0],[360,360]], units_per_frame 1.0, smooth true.
                  sub_frac = fractional degree → shifts up to frame_width px.
- Digit drums   : 10 digit frames in a 1 × 10 grid.
                  units_per_frame 1.0, smooth false (digits snap cleanly).

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
      # stride_x: 122       # optional; defaults to frame_width.
      # stride_y: 66        # optional; defaults to frame_height.
      smooth: true          # optional, default true.  False = snap only.
      units_per_frame: 1.0  # optional, default 1.0.  Table-output units per frame.
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
        units_per_frame: float = 1.0,
    ) -> None:
        self.name = name
        self._columns = columns
        self._rows = rows
        self._frame_w = frame_width
        self._frame_h = frame_height
        self._stride_x = stride_x
        self._stride_y = stride_y
        self._smooth = smooth
        self._units_per_frame = max(float(units_per_frame), 1e-9)

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
        """Position the sprite so the frame at *frame_value* is centred at base_x/y.

        frame_value is the animation table output (raw table units).
        Dividing by units_per_frame converts it to a fractional frame index:
          int_frame  = floor(frame_value / units_per_frame)  → which cell in the grid
          sub_frac   = fractional remainder, normalised to [0, 1)
                     → how far to shift within that frame (smooth only)

        Smooth shift is sub_frac × frame_width (the frame's own pixel width),
        so 1 full unit-step moves the viewport by exactly one frame width.
        """
        self._last_frame = frame_value

        total = self._columns * self._rows
        fv_scaled = frame_value / self._units_per_frame          # fractional frame index
        int_frame = max(0, min(total - 1, int(fv_scaled)))
        sub_frac = (fv_scaled - int_frame) if self._smooth else 0.0

        col = int_frame % self._columns
        row = int_frame // self._columns

        # Centre of the target frame in atlas coords (x left-to-right, y down).
        #
        # Smooth interpolation rules:
        #   columns == 1  → frames go top-to-bottom; interpolate in Y.
        #   columns  > 1  → interpolate in X only when the next frame is in the
        #                   same row.  At row boundaries applying sub_frac in X
        #                   would push the viewport past the atlas right edge and
        #                   show empty pixels — snap to the integer frame instead.
        if sub_frac > 0.0 and self._columns == 1:
            # Vertical strip: sub-frame precision by sliding in Y.
            tx = self._frame_w / 2
            ty_down = fv_scaled * self._stride_y + self._frame_h / 2
        elif sub_frac > 0.0 and (int_frame + 1) // self._columns == row:
            # Horizontal grid, next frame in same row: safe to interpolate in X.
            # Shift = sub_frac × frame_width (the frame's own pixel width).
            tx = col * self._stride_x + self._frame_w / 2 + sub_frac * self._frame_w
            ty_down = row * self._stride_y + self._frame_h / 2
        else:
            # Row boundary or smooth=False: snap to the integer frame.
            tx = col * self._stride_x + self._frame_w / 2
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
        units_per_frame=float(comp.get("units_per_frame", 1.0)),
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
