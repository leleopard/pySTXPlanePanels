"""Dict-level "resize" for instrument components — scales every geometry
field of a component's raw YAML dict by (sx, sy), the same way
gauge_core's own `apply_scale(scale)` methods scale a live, already-
instantiated component object. Used by InstrumentView's "Preserve
components relative position from centre" resize path, which only ever
holds raw dicts (`self._components`), never live component instances —
there's no dict->object->apply_scale()->dict round trip anywhere in this
codebase (no inverse "dump object back to dict" function exists), so this
module re-derives the same field lists directly against dict keys instead.

Convention (locked in with the user):
  - sx = new_w / old_w, sy = new_h / old_h — independent, non-uniform
    resize is supported.
  - Directional fields (anything with an inherent x or y — a position
    [x, y], a [w, h] size/viewport/cliprect pair, an [x, y] offset) scale
    the x-component by sx and the y-component by sy, independently.
  - Scalar fields with no inherent x/y axis (radius, line/stroke width,
    font_size, tick/needle length, corner radius, arc width, etc.) scale
    by min(sx, sy) — avoids distorting a circle into an ellipse, or a
    stroke width growing lopsided, when width and height change by
    different amounts. Reduces to plain uniform scaling when sx == sy.
  - Scaling is from the instrument's own origin (0, 0): new_x = old_x *
    sx directly, matching apply_scale() exactly (not centre-relative) —
    this is what makes it preserve each component's *fractional*
    position within the canvas.
  - Colors, counts, angles, booleans, datarefs, convert_functions,
    predicates, and text strings are never touched, same as
    apply_scale()'s own exclusions.

Each per-type function below is built from that type's own apply_scale()
in gauge_core/*.py (the field list) plus its factory function (the literal
YAML key names) — see the plan this was implemented from for the full
per-type field inventory.
"""

from __future__ import annotations

from typing import Any


def _scale_pair(pair: list, sx: float, sy: float) -> list:
    x, y = pair
    return [x * sx, y * sy]


def _scale_points(points: list, sx: float, sy: float) -> list:
    return [[x * sx, y * sy] for x, y in points]


def resize_component(comp: dict[str, Any], sx: float, sy: float) -> None:
    """Scale `comp` (a raw component dict, mutated in place) by (sx, sy).
    Unknown/unregistered component types are a no-op — forward-compatible
    with a type added later that doesn't have its own resize function yet,
    rather than crashing."""
    fn = _RESIZERS.get(comp.get("type"))
    if fn is not None:
        fn(comp, sx, sy)


def _resize_text(comp: dict, sx: float, sy: float) -> None:
    if "position" in comp:
        comp["position"] = _scale_pair(comp["position"], sx, sy)
    s = min(sx, sy)
    if "font_size" in comp:
        comp["font_size"] = comp["font_size"] * s
    if "emphasize_font_size" in comp:
        comp["emphasize_font_size"] = comp["emphasize_font_size"] * s


def _resize_arc(comp: dict, sx: float, sy: float) -> None:
    if "center" in comp:
        comp["center"] = _scale_pair(comp["center"], sx, sy)
    s = min(sx, sy)
    if "radius" in comp:
        comp["radius"] = comp["radius"] * s
    if "width" in comp:
        comp["width"] = comp["width"] * s
    # start_angle/end_angle/tilt_angle/num_segments are angles/counts,
    # not geometry — never scaled, matching Arc.apply_scale().


def _resize_filledrect(comp: dict, sx: float, sy: float) -> None:
    if "position" in comp:
        comp["position"] = _scale_pair(comp["position"], sx, sy)
    if "size" in comp:
        comp["size"] = _scale_pair(comp["size"], sx, sy)
    if "outline_width" in comp:
        comp["outline_width"] = comp["outline_width"] * min(sx, sy)


def _resize_polygon(comp: dict, sx: float, sy: float) -> None:
    if "origin" in comp:
        comp["origin"] = _scale_pair(comp["origin"], sx, sy)
    if "points" in comp:
        comp["points"] = _scale_points(comp["points"], sx, sy)
    s = min(sx, sy)
    if "width" in comp:
        comp["width"] = comp["width"] * s
    if "outline_width" in comp:
        comp["outline_width"] = comp["outline_width"] * s


def _resize_line(comp: dict, sx: float, sy: float) -> None:
    if "points" in comp:
        comp["points"] = _scale_points(comp["points"], sx, sy)
    else:
        if "start" in comp:
            comp["start"] = _scale_pair(comp["start"], sx, sy)
        if "end" in comp:
            comp["end"] = _scale_pair(comp["end"], sx, sy)
    if "width" in comp:
        comp["width"] = comp["width"] * min(sx, sy)


def _resize_vector(comp: dict, sx: float, sy: float) -> None:
    if "position" in comp:
        comp["position"] = _scale_pair(comp["position"], sx, sy)
    s = min(sx, sy)
    # length: either a static scalar or a {dataref, table, convert_function}
    # lookup — only the table's *output* (px length) column scales, its
    # input column is a raw dataref-domain value, not a pixel size.
    length_cfg = comp.get("length")
    if isinstance(length_cfg, dict):
        table = length_cfg.get("table")
        if table:
            length_cfg["table"] = [[row[0], row[1] * s] for row in table]
    elif length_cfg is not None:
        comp["length"] = length_cfg * s
    # direction is an angle (static or table-driven) — never scaled,
    # matching Vector.apply_scale()'s own exclusion.
    if "width" in comp:
        comp["width"] = comp["width"] * s
    # cap_width/cap_height are measured along/across the vector's own
    # (dataref-driven, arbitrary-angle) local direction, not the
    # instrument's fixed screen x/y axes — scalar, not directional.
    if "cap_width" in comp:
        comp["cap_width"] = comp["cap_width"] * s
    if "cap_height" in comp:
        comp["cap_height"] = comp["cap_height"] * s


def _resize_viewport(comp: dict, sx: float, sy: float) -> None:
    if "viewport" in comp:
        vx, vy, vw, vh = comp["viewport"]
        comp["viewport"] = [vx * sx, vy * sy, vw * sx, vh * sy]


def _resize_image_panel(comp: dict, sx: float, sy: float) -> None:
    # origin/cliprect are atlas-space (which pixels get cropped from the
    # source texture) — must never scale, or the crop region shifts/grows
    # into unrelated (or out-of-bounds) parts of the source image. The
    # on-screen render size is controlled entirely by the separate `scale`
    # field (added alongside this resize feature specifically because
    # cliprect can't safely double as both crop size and render size).
    if "position" in comp:
        comp["position"] = _scale_pair(comp["position"], sx, sy)
    s = min(sx, sy)
    comp["scale"] = comp.get("scale", 1.0) * s
    _resize_viewport(comp, sx, sy)
    rotation = comp.get("rotation")
    if rotation and "rotation_center" in rotation:
        # Relative to the sprite's own local frame, which only has one
        # uniform scale (matching `scale` above, not independently x/y).
        rcx, rcy = rotation["rotation_center"]
        rotation["rotation_center"] = [rcx * s, rcy * s]


def _resize_sprite_sheet(comp: dict, sx: float, sy: float) -> None:
    # columns/rows/frame_width/frame_height/stride_x/stride_y/
    # pixels_per_unit are all atlas-space (fixed frame-grid geometry and
    # atlas-pixel shift-per-unit) — never scale, same reasoning as
    # ImagePanel's cliprect/origin.
    if "position" in comp:
        comp["position"] = _scale_pair(comp["position"], sx, sy)
    comp["scale"] = comp.get("scale", 1.0) * min(sx, sy)
    _resize_viewport(comp, sx, sy)


def _resize_scrolling_tape(comp: dict, sx: float, sy: float) -> None:
    # scroll.table maps a raw dataref value to a pixel offset *into the
    # source texture strip* (atlas-space) — never scales, same reasoning
    # as ImagePanel's cliprect/origin.
    if "position" in comp:
        comp["position"] = _scale_pair(comp["position"], sx, sy)
    comp["scale"] = comp.get("scale", 1.0) * min(sx, sy)
    _resize_viewport(comp, sx, sy)


def _resize_rotary_encoder(comp: dict, sx: float, sy: float) -> None:
    # background_origin/background_cliprect/face_origin/face_cliprect are
    # atlas-space (which pixels get cropped) — never scale, same reasoning
    # as ImagePanel. Unlike ImagePanel, on-screen render size is already a
    # genuinely separate field here (`size`/`face_size`, fed to
    # sprite.scale_x/y as target_w/cw at construction time), so no new
    # schema field is needed for this type. drag_px_per_step and
    # hit_padding are gesture/interaction tuning, not geometry — left
    # untouched, matching apply_scale()'s own exclusions (neither is
    # scaled there either).
    if "position" in comp:
        comp["position"] = _scale_pair(comp["position"], sx, sy)
    if "size" in comp:
        comp["size"] = _scale_pair(comp["size"], sx, sy)
    if "face_size" in comp:
        comp["face_size"] = _scale_pair(comp["face_size"], sx, sy)
    if "face_offset" in comp:
        comp["face_offset"] = _scale_pair(comp["face_offset"], sx, sy)
    if "face_rotation_center" in comp:
        comp["face_rotation_center"] = _scale_pair(comp["face_rotation_center"], sx, sy)


def _resize_needle_gauge(comp: dict, sx: float, sy: float) -> None:
    s = min(sx, sy)
    if "center" in comp:
        comp["center"] = _scale_pair(comp["center"], sx, sy)
    if "radius" in comp:
        comp["radius"] = comp["radius"] * s
    if "arc_width" in comp:
        comp["arc_width"] = comp["arc_width"] * s
    # needle_length/width are radial along the needle's own dataref-driven
    # angle (any direction, not fixed to x or y) — scalar, same reasoning
    # as Vector's length/cap_width in _resize_vector().
    if "needle_length" in comp:
        comp["needle_length"] = comp["needle_length"] * s
    if "needle_width" in comp:
        comp["needle_width"] = comp["needle_width"] * s
    if "needle_viewport" in comp:
        vx, vy, vw, vh = comp["needle_viewport"]
        comp["needle_viewport"] = [vx * sx, vy * sy, vw * sx, vh * sy]

    linear = comp.get("linear")
    if linear:
        # Linear-mode ticks/labels/target are measured along the tape's own
        # primary axis ("off"/label position) vs. across it ("length"/
        # "label_offset", the tick's own extent) — which screen axis each
        # maps to depends on orientation, confirmed directly against
        # NeedleGauge._draw_linear()/_draw_linear_labels()'s real geometry
        # (vertical: off/label-y along y, length/label_offset-x across x;
        # horizontal: the same two swapped).
        vertical = str(linear.get("orientation", "vertical")) == "vertical"
        along = sy if vertical else sx
        across = sx if vertical else sy
        if "offset" in linear:
            linear["offset"] = _scale_pair(linear["offset"], sx, sy)
        if "size" in linear:
            linear["size"] = _scale_pair(linear["size"], sx, sy)
        if "line_width" in linear:
            linear["line_width"] = linear["line_width"] * s
        if "spacing_table" in linear:
            new_rows = []
            for row in linear["spacing_table"]:
                row = list(row)
                # [value, offset, length, width, show_label, font_size, label_offset]
                # — variable length (2/4/7 cols accepted), preserved as-is,
                # only scaling whichever columns are actually present.
                if len(row) > 1:
                    row[1] = row[1] * along
                if len(row) > 2:
                    row[2] = row[2] * across
                if len(row) > 3:
                    row[3] = row[3] * s
                if len(row) > 5:
                    row[5] = row[5] * s
                if len(row) > 6:
                    row[6] = row[6] * across
                new_rows.append(row)
            linear["spacing_table"] = new_rows
        target = linear.get("target")
        if target:
            if "length" in target:
                target["length"] = target["length"] * across
            if "width" in target:
                target["width"] = target["width"] * s


_RESIZERS = {
    "Text": _resize_text,
    "Arc": _resize_arc,
    "FilledRect": _resize_filledrect,
    "Polygon": _resize_polygon,
    "Line": _resize_line,
    "Vector": _resize_vector,
    "ImagePanel": _resize_image_panel,
    "SpriteSheet": _resize_sprite_sheet,
    "ScrollingTape": _resize_scrolling_tape,
    "RotaryEncoder": _resize_rotary_encoder,
    "NeedleGauge": _resize_needle_gauge,
}
