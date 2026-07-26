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


_RESIZERS = {
    "Text": _resize_text,
    "Arc": _resize_arc,
    "FilledRect": _resize_filledrect,
    "Polygon": _resize_polygon,
    "Line": _resize_line,
    "Vector": _resize_vector,
}
