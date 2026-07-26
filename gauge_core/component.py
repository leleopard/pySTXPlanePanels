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
    resolve_predicate_name,
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

        # viewport clip (screen-space scissor rectangle: x, y, w, h)
        # specified in instrument coordinates; shifted by apply_offset.
        self._viewport: tuple[float, float, float, float] | None = None

        # scale factor applied by panel composition (default 1.0)
        self._inst_scale: float = 1.0

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

    def set_viewport(self, x: float, y: float, w: float, h: float) -> None:
        """Fix a scissor rectangle (instrument-space coords) that clips this sprite."""
        self._viewport = (x, y, w, h)

    def set_visibility(self, dataref: Any, predicate: str) -> None:
        self._vis_dataref = _as_dataref(dataref)
        self._vis_predicate = get_convert(predicate)
        if self._vis_predicate is None:
            raise ValueError("visibility requires a predicate name")

    def apply_scale(self, scale: float) -> None:
        """Scale the component around the instrument origin. Called before apply_offset."""
        self._inst_scale = scale
        self._base_x *= scale
        self._base_y *= scale
        self.sprite.center_x = self._base_x
        self.sprite.center_y = self._base_y
        self.sprite.scale_x *= scale
        self.sprite.scale_y *= scale
        if self._rot_center is not None:
            rcx, rcy = self._rot_center
            self._rot_center = (rcx * scale, rcy * scale)
        if self._viewport is not None:
            vx, vy, vw, vh = self._viewport
            self._viewport = (vx * scale, vy * scale, vw * scale, vh * scale)

    def apply_offset(self, dx: float, dy: float) -> None:
        """Shift the component's base position. Used by panel composition."""
        self._base_x += dx
        self._base_y += dy
        self.sprite.center_x = self._base_x
        self.sprite.center_y = self._base_y
        if self._viewport is not None:
            vx, vy, vw, vh = self._viewport
            self._viewport = (vx + dx, vy + dy, vw, vh)

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

            tx = amount * math.sin(angle_rad) * self._inst_scale
            ty = amount * math.cos(angle_rad) * self._inst_scale

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

    def draw(self) -> None:
        if not self.sprite.visible:
            return
        if self._viewport is not None:
            vx, vy, vw, vh = self._viewport
            win = arcade.get_window()
            ctx = win.ctx
            _, _, fvp_w, fvp_h = ctx.viewport
            panel_w, panel_h = getattr(win, "_panel_size", (win.width, win.height))
            sx = fvp_w / panel_w
            sy = fvp_h / panel_h
            ctx.scissor = (int(vx * sx), int(vy * sy), int(vw * sx), int(vh * sy))
            arcade.draw_sprite(self.sprite)
            ctx.scissor = None
        else:
            arcade.draw_sprite(self.sprite)


# -- Factory + registry ---------------------------------------------------

def _image_panel_factory(
    comp: dict[str, Any],
    base_dir: Path,
    container_size: tuple[int, int] | None = None,
) -> ImagePanel:
    atlas_path = (base_dir / comp["texture"]).resolve()
    cliprect_wh = tuple(comp["cliprect"])
    panel = ImagePanel(
        name=comp["name"],
        atlas_path=atlas_path,
        origin_xy=tuple(comp["origin"]),
        cliprect_wh=cliprect_wh,
        position_xy=tuple(comp["position"]),
    )

    # Manual render-size multiplier, applied after cropping — distinct from
    # cliprect/origin (atlas-space, define WHICH pixels are cropped, must
    # never scale without corrupting the crop) and from resize_to_container
    # (dynamic, container-driven). Defaults to 1.0 (no behavior change for
    # existing instruments); the designer's resize function is the main
    # consumer, since cliprect itself can't be scaled without breaking the
    # texture crop. Composes multiplicatively with resize_to_container's
    # own dynamic fit, so a manually-tuned scale still applies on top.
    manual_scale = float(comp.get("scale", 1.0))
    if comp.get("resize_to_container") and container_size is not None:
        cw, ch = container_size
        sw, sh = cliprect_wh
        if comp.get("maintain_proportions", True):
            panel.sprite.scale = min(cw / sw, ch / sh) * manual_scale
        else:
            panel.sprite.width = float(cw) * manual_scale
            panel.sprite.height = float(ch) * manual_scale
    elif manual_scale != 1.0:
        panel.sprite.scale = manual_scale

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

    if "viewport" in comp:
        vx, vy, vw, vh = comp["viewport"]
        panel.set_viewport(float(vx), float(vy), float(vw), float(vh))

    if "visibility" in comp:
        vis = comp["visibility"]
        panel.set_visibility(dataref=vis["dataref"], predicate=resolve_predicate_name(vis))

    return panel


register_component("ImagePanel", _image_panel_factory)


# Re-export the registry helper for the loader.
build_component = get_component_factory
