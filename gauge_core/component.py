"""Component classes built on Arcade sprites.

`ImagePanel` is the textured-atlas-region sprite used by every C172
instrument. It supports four optional transforms, all driven by X-Plane
datarefs and calibrated through piecewise-linear lookup tables:

- `rotation`: needle / wheel / horizon rotation around a pivot point
  (sprite centre by default, or an offset declared in `rotation_center`).
- `translation`: linear movement, optionally locked to the rotation
  angle so e.g. the artificial-horizon pitch line tracks the roll.
- `visibility`: predicate-driven on/off (annunciator lights).

Atlas coordinates use PIL convention (top-left origin, y down). Render
positions use Arcade convention (bottom-left origin, y up).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

import arcade
from PIL import Image

from gauge_core.lookup import lookup_piecewise
from gauge_core.registry import (
    get_component_factory,
    get_convert,
    register_component,
)


# Cache so the same atlas isn't decoded multiple times when many components
# share it (the norm — one PNG often holds an entire panel).
_ATLAS_CACHE: dict[str, Image.Image] = {}


def _load_atlas(path: Path) -> Image.Image:
    key = str(path)
    if key not in _ATLAS_CACHE:
        _ATLAS_CACHE[key] = Image.open(path).convert("RGBA")
    return _ATLAS_CACHE[key]


def _as_dataref(raw: Any) -> Any:
    """YAML lists become legacy (group, index) tuples; strings pass through."""
    if isinstance(raw, list):
        return tuple(raw)
    return raw


class ImagePanel:
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
        self._base_x = float(position_xy[0])
        self._base_y = float(position_xy[1])
        self.sprite.center_x = self._base_x
        self.sprite.center_y = self._base_y

        # rotation
        self._rot_dataref: Any | None = None
        self._rot_table: list[list[float]] | None = None
        self._rot_convert: Callable | None = None
        self._rot_center: tuple[float, float] | None = None

        # translation
        self._tr_dataref: Any | None = None
        self._tr_table: list[list[float]] | None = None
        self._tr_convert: Callable | None = None
        self._tr_angle_deg: float | None = None
        self._tr_add_to_rotation_deg: float = 0.0

        # visibility
        self._vis_dataref: Any | None = None
        self._vis_predicate: Callable | None = None

    # -- transform setters -------------------------------------------------

    def set_rotation(
        self,
        dataref: Any,
        table: list[list[float]],
        convert_function: str | None = None,
        rotation_center: tuple[float, float] | None = None,
    ) -> None:
        self._rot_dataref = _as_dataref(dataref)
        self._rot_table = table
        self._rot_convert = get_convert(convert_function)
        self._rot_center = (
            (float(rotation_center[0]), float(rotation_center[1]))
            if rotation_center is not None
            else None
        )

    def set_translation(
        self,
        dataref: Any,
        table: list[list[float]],
        convert_function: str | None = None,
        translation_angle_deg: float | None = None,
        add_angle_to_rotation_deg: float = 0.0,
    ) -> None:
        self._tr_dataref = _as_dataref(dataref)
        self._tr_table = table
        self._tr_convert = get_convert(convert_function)
        self._tr_angle_deg = translation_angle_deg
        self._tr_add_to_rotation_deg = float(add_angle_to_rotation_deg)

    def set_visibility(self, dataref: Any, predicate: str) -> None:
        self._vis_dataref = _as_dataref(dataref)
        self._vis_predicate = get_convert(predicate)
        if self._vis_predicate is None:
            raise ValueError("visibility requires a predicate name")

    # -- per-frame update --------------------------------------------------

    def update(self, get_data: Callable[[Any], float]) -> None:
        # rotation first — translation may depend on the resulting angle.
        rotation_deg = 0.0
        if self._rot_dataref is not None and self._rot_table is not None:
            raw = float(get_data(self._rot_dataref))
            if self._rot_convert is not None:
                raw = float(self._rot_convert(raw, get_data))
            rotation_deg = lookup_piecewise(self._rot_table, raw)
            # Arcade sprite.angle is clockwise-positive, matching aircraft
            # gauge convention — pass the table value straight through.
            self.sprite.angle = rotation_deg

        # translation
        tx, ty = 0.0, 0.0
        if self._tr_dataref is not None and self._tr_table is not None:
            raw = float(get_data(self._tr_dataref))
            if self._tr_convert is not None:
                raw = float(self._tr_convert(raw, get_data))
            amount = lookup_piecewise(self._tr_table, raw)

            if self._tr_angle_deg is not None:
                angle_rad = math.radians(self._tr_angle_deg)
            else:
                # Default: translate in the direction of the current
                # rotation, plus an optional offset. Matches the
                # rot_angle + addRotAngleForTranslation behaviour from the
                # original OpenGL renderer.
                angle_rad = math.radians(rotation_deg + self._tr_add_to_rotation_deg)

            tx = amount * math.sin(angle_rad)
            ty = amount * math.cos(angle_rad)

        # off-centre rotation pivot
        if self._rot_center is not None:
            # rotation_center is a vector (in sprite-local coords, before
            # rotation) from the sprite centre to the pivot. We keep the
            # pivot fixed in world space and move the sprite centre to
            # wherever the rotation puts it.
            rcx, rcy = self._rot_center
            pivot_x = self._base_x + tx + rcx
            pivot_y = self._base_y + ty + rcy
            offset_x = -rcx
            offset_y = -rcy
            angle_rad = math.radians(rotation_deg)
            cos_a = math.cos(angle_rad)
            sin_a = math.sin(angle_rad)
            # Clockwise rotation in Arcade's y-up coords:
            #   (x, y) → (x cos + y sin, -x sin + y cos)
            new_x = offset_x * cos_a + offset_y * sin_a
            new_y = -offset_x * sin_a + offset_y * cos_a
            self.sprite.center_x = pivot_x + new_x
            self.sprite.center_y = pivot_y + new_y
        else:
            self.sprite.center_x = self._base_x + tx
            self.sprite.center_y = self._base_y + ty

        # visibility
        if self._vis_dataref is not None and self._vis_predicate is not None:
            value = float(get_data(self._vis_dataref))
            self.sprite.visible = bool(self._vis_predicate(value, get_data))


# -- Factory + registry ---------------------------------------------------

def _image_panel_factory(comp: dict[str, Any], base_dir: Path) -> ImagePanel:
    atlas_path = (base_dir / comp["texture"]).resolve()
    panel = ImagePanel(
        name=comp["name"],
        atlas_path=atlas_path,
        origin_xy=tuple(comp["origin"]),
        cliprect_wh=tuple(comp["cliprect"]),
        position_xy=tuple(comp["position"]),
    )

    if "rotation" in comp:
        rot = comp["rotation"]
        panel.set_rotation(
            dataref=rot["dataref"],
            table=rot["table"],
            convert_function=rot.get("convert_function"),
            rotation_center=(
                tuple(rot["rotation_center"]) if "rotation_center" in rot else None
            ),
        )

    if "translation" in comp:
        tr = comp["translation"]
        panel.set_translation(
            dataref=tr["dataref"],
            table=tr["table"],
            convert_function=tr.get("convert_function"),
            translation_angle_deg=tr.get("translation_angle"),
            add_angle_to_rotation_deg=tr.get("add_angle_to_rotation", 0.0),
        )

    if "visibility" in comp:
        vis = comp["visibility"]
        panel.set_visibility(dataref=vis["dataref"], predicate=vis["predicate"])

    return panel


register_component("ImagePanel", _image_panel_factory)


# Re-export the registry helper for the loader.
build_component = get_component_factory
