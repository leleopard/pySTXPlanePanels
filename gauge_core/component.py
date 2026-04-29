"""Component classes built on Arcade sprites.

MVP0 ships only `ImagePanel`, a textured atlas-region sprite with optional
dataref-driven rotation. Translation, visibility, and vector primitives
arrive in later commits.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import arcade
from PIL import Image

from gauge_core.lookup import lookup_piecewise


# Cache so the same atlas isn't decoded multiple times when many components
# share it (which is the norm — one PNG often holds an entire panel).
_ATLAS_CACHE: dict[str, Image.Image] = {}


def _load_atlas(path: Path) -> Image.Image:
    key = str(path)
    if key not in _ATLAS_CACHE:
        _ATLAS_CACHE[key] = Image.open(path).convert("RGBA")
    return _ATLAS_CACHE[key]


class ImagePanel:
    """Single sprite layer cut from a texture atlas.

    Atlas coordinates (`origin`, `cliprect`) follow PIL/Pillow's image
    convention: x grows right, y grows DOWN, (0,0) is the top-left of the
    PNG. Render position uses Arcade's window convention: x grows right,
    y grows UP, (0,0) is the bottom-left.
    """

    def __init__(
        self,
        name: str,
        atlas_path: Path,
        origin_xy: tuple[int, int],
        cliprect_wh: tuple[int, int],
        position_xy: tuple[float, float],
    ) -> None:
        self.name = name

        atlas = _load_atlas(atlas_path)
        x, y = origin_xy
        w, h = cliprect_wh
        region = atlas.crop((x, y, x + w, y + h))
        texture = arcade.Texture(
            region,
            hash=f"{atlas_path}:{x},{y},{w},{h}",
        )

        self.sprite = arcade.Sprite(texture)
        self.sprite.center_x = float(position_xy[0])
        self.sprite.center_y = float(position_xy[1])

        # rotation config (optional)
        self._rotation_dataref: object | None = None
        self._rotation_table: list[list[float]] | None = None

    def set_rotation(self, dataref: object, table: list[list[float]]) -> None:
        """Bind needle rotation to a dataref via a calibration table.

        `dataref` is whatever pyxpudpserver.getData accepts: a string
        ('sim/...') or a (group, index) tuple. `table` is a list of
        [value, angle_degrees] pairs.
        """
        self._rotation_dataref = dataref
        self._rotation_table = table

    def update(self, get_data: Callable[[object], float]) -> None:
        """Refresh sprite state from the data source for this frame."""
        if self._rotation_dataref is not None and self._rotation_table is not None:
            value = float(get_data(self._rotation_dataref))
            angle_deg = lookup_piecewise(self._rotation_table, value)
            # Arcade's sprite.angle rotates clockwise for positive values,
            # which matches aircraft-gauge convention directly. The original
            # OpenGL renderer pre-negated the angle in its rotation matrix
            # to achieve the same effect; here we pass the table value
            # straight through.
            self.sprite.angle = angle_deg
