"""Dict-level "resize" for instrument components — scales every geometry
field of a component's raw YAML dict by (sx, sy), the same way
gauge_core's own `apply_scale(scale)` methods scale a live, already-
instantiated component object. Used by InstrumentView's "Preserve
components relative position from centre" / "Scale component sizes"
resize path, which only ever holds raw dicts (`self._components`), never
live component instances — there's no dict->object->apply_scale()->dict
round trip anywhere in this codebase (no inverse "dump object back to
dict" function exists), so this module re-derives the same field lists
directly against dict keys instead.

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

Two independent gates (locked in with the user — these were originally a
single combined operation, split into two checkboxes on request so a user
can move components without resizing them, resize them in place without
moving them, or do both together):
  - `scale_position` gates each type's own anchor field(s) — the field(s)
    that answer "where does this component sit on the canvas": `position`,
    `center`, Polygon's `origin`, a viewport-style field's own [x, y]
    portion. This is the *only* thing "Preserve components relative
    position from centre" controls.
  - `scale_size` gates everything else — every field that answers "how
    big/what shape is this component" (radius, width/height, viewport's
    own [w, h] portion, font sizes, stroke widths, shape point lists,
    lookup-table outputs, etc). This is what "Scale component sizes"
    controls.
  - The directional-vs-scalar factor choice for a given field (described
    above) is completely orthogonal to this split and unaffected by it —
    e.g. FilledRect's `size` is gated by `scale_size` but still scales
    its x/y independently by sx/sy; Arc's `radius` is gated by
    `scale_size` and scales by the scalar min(sx, sy).
  - `Line` is the one type with no separate anchor field at all — its
    `points`/`start`/`end` double as both the component's location AND
    its own shape. See `_resize_line()` for how that's decomposed into an
    anchor (gated by scale_position) plus deltas from that anchor (gated
    by scale_size); with both flags on this reduces to the original
    "scale every point directly" behaviour exactly, so it's a strict
    generalization, not a behavior change, when both boxes are checked.

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


def _scale_points_scalar(points: list, s: float) -> list:
    """Same as _scale_points but with one uniform factor for both x and y —
    for local shape points attached to an element that rotates to an
    arbitrary (usually dataref-driven) angle, e.g. a compass rose's
    bearing-pointer/heading-bug/CDI-symbol shapes. Scaling such a shape
    directionally (different sx vs sy) would distort it differently
    depending on which way it currently happens to be rotated — clearly
    wrong for a shape that's meant to look the same at every angle."""
    return [[x * s, y * s] for x, y in points]


def resize_component(
    comp: dict[str, Any], sx: float, sy: float,
    scale_position: bool = True, scale_size: bool = True,
) -> None:
    """Scale `comp` (a raw component dict, mutated in place) by (sx, sy).
    `scale_position`/`scale_size` independently gate a type's anchor
    field(s) vs. everything else — see the module docstring. Unknown/
    unregistered component types are a no-op — forward-compatible with a
    type added later that doesn't have its own resize function yet,
    rather than crashing."""
    if not scale_position and not scale_size:
        return
    fn = _RESIZERS.get(comp.get("type"))
    if fn is not None:
        fn(comp, sx, sy, scale_position, scale_size)


def _resize_text(comp: dict, sx: float, sy: float,
                  scale_position: bool = True, scale_size: bool = True) -> None:
    if scale_position and "position" in comp:
        comp["position"] = _scale_pair(comp["position"], sx, sy)
    if scale_size:
        s = min(sx, sy)
        if "font_size" in comp:
            comp["font_size"] = comp["font_size"] * s
        if "emphasize_font_size" in comp:
            comp["emphasize_font_size"] = comp["emphasize_font_size"] * s


def _resize_arc(comp: dict, sx: float, sy: float,
                 scale_position: bool = True, scale_size: bool = True) -> None:
    if scale_position and "center" in comp:
        comp["center"] = _scale_pair(comp["center"], sx, sy)
    if scale_size:
        s = min(sx, sy)
        if "radius" in comp:
            comp["radius"] = comp["radius"] * s
        if "width" in comp:
            comp["width"] = comp["width"] * s
    # start_angle/end_angle/tilt_angle/num_segments are angles/counts,
    # not geometry — never scaled, matching Arc.apply_scale().


def _resize_filledrect(comp: dict, sx: float, sy: float,
                        scale_position: bool = True, scale_size: bool = True) -> None:
    if scale_position and "position" in comp:
        comp["position"] = _scale_pair(comp["position"], sx, sy)
    if scale_size:
        if "size" in comp:
            comp["size"] = _scale_pair(comp["size"], sx, sy)
        if "outline_width" in comp:
            comp["outline_width"] = comp["outline_width"] * min(sx, sy)


def _resize_polygon(comp: dict, sx: float, sy: float,
                     scale_position: bool = True, scale_size: bool = True) -> None:
    if scale_position and "origin" in comp:
        comp["origin"] = _scale_pair(comp["origin"], sx, sy)
    if scale_size:
        if "points" in comp:
            comp["points"] = _scale_points(comp["points"], sx, sy)
        s = min(sx, sy)
        if "width" in comp:
            comp["width"] = comp["width"] * s
        if "outline_width" in comp:
            comp["outline_width"] = comp["outline_width"] * s


def _resize_line(comp: dict, sx: float, sy: float,
                  scale_position: bool = True, scale_size: bool = True) -> None:
    # Line has no separate anchor field — points/start/end double as both
    # this component's location AND its own shape. Decompose as an anchor
    # (the first point, or `start`) plus deltas to every other point:
    # scale_position moves the anchor, scale_size scales the deltas (the
    # line's own length/shape) around that fixed anchor. With both flags
    # on this reduces to "scale every point directly by (sx, sy)" exactly
    # — the same result as before this type/size split existed.
    if "points" in comp:
        pts = comp["points"]
        if pts:
            ax, ay = pts[0]
            new_ax, new_ay = (ax * sx, ay * sy) if scale_position else (ax, ay)
            new_pts = [[new_ax, new_ay]]
            for x, y in pts[1:]:
                dx, dy = x - ax, y - ay
                if scale_size:
                    dx, dy = dx * sx, dy * sy
                new_pts.append([new_ax + dx, new_ay + dy])
            comp["points"] = new_pts
    elif "start" in comp:
        x0, y0 = comp["start"]
        new_start = [x0 * sx, y0 * sy] if scale_position else [x0, y0]
        if "end" in comp:
            ex, ey = comp["end"]
            dx, dy = ex - x0, ey - y0
            if scale_size:
                dx, dy = dx * sx, dy * sy
            comp["end"] = [new_start[0] + dx, new_start[1] + dy]
        comp["start"] = new_start
    if scale_size and "width" in comp:
        comp["width"] = comp["width"] * min(sx, sy)


def _resize_vector(comp: dict, sx: float, sy: float,
                    scale_position: bool = True, scale_size: bool = True) -> None:
    if scale_position and "position" in comp:
        comp["position"] = _scale_pair(comp["position"], sx, sy)
    if not scale_size:
        return
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


def _resize_viewport(comp: dict, sx: float, sy: float,
                      scale_position: bool = True, scale_size: bool = True) -> None:
    if "viewport" in comp:
        vx, vy, vw, vh = comp["viewport"]
        if scale_position:
            vx, vy = vx * sx, vy * sy
        if scale_size:
            vw, vh = vw * sx, vh * sy
        comp["viewport"] = [vx, vy, vw, vh]


def _resize_image_panel(comp: dict, sx: float, sy: float,
                         scale_position: bool = True, scale_size: bool = True) -> None:
    # origin/cliprect are atlas-space (which pixels get cropped from the
    # source texture) — must never scale, or the crop region shifts/grows
    # into unrelated (or out-of-bounds) parts of the source image. The
    # on-screen render size is controlled entirely by the separate `scale`
    # field (added alongside this resize feature specifically because
    # cliprect can't safely double as both crop size and render size).
    if scale_position and "position" in comp:
        comp["position"] = _scale_pair(comp["position"], sx, sy)
    _resize_viewport(comp, sx, sy, scale_position, scale_size)
    if not scale_size:
        return
    if comp.get("resize_to_container"):
        # "Fit to gauge size" already recomputes the sprite's own render
        # size from scratch on every load, straight from cliprect vs. the
        # instrument's own (just-resized) `size:` field — see
        # gauge_core/loader.py's container_size and
        # _image_panel_factory()'s own min(cw/sw, ch/sh) fit. It needs no
        # help from `scale` to track an instrument resize; bumping `scale`
        # here as well would compose on top of that automatic fit and
        # double-count the growth. rotation_center likewise stays untouched
        # for the same reason it can't be right anyway when the sprite's
        # effective size is decided dynamically at load time, not by a
        # static factor we can pre-compute here.
        return
    s = min(sx, sy)
    comp["scale"] = comp.get("scale", 1.0) * s
    rotation = comp.get("rotation")
    if rotation and "rotation_center" in rotation:
        # Relative to the sprite's own local frame, which only has one
        # uniform scale (matching `scale` above, not independently x/y).
        rcx, rcy = rotation["rotation_center"]
        rotation["rotation_center"] = [rcx * s, rcy * s]


def _resize_sprite_sheet(comp: dict, sx: float, sy: float,
                          scale_position: bool = True, scale_size: bool = True) -> None:
    # columns/rows/frame_width/frame_height/stride_x/stride_y/
    # pixels_per_unit are all atlas-space (fixed frame-grid geometry and
    # atlas-pixel shift-per-unit) — never scale, same reasoning as
    # ImagePanel's cliprect/origin.
    if scale_position and "position" in comp:
        comp["position"] = _scale_pair(comp["position"], sx, sy)
    _resize_viewport(comp, sx, sy, scale_position, scale_size)
    if scale_size:
        comp["scale"] = comp.get("scale", 1.0) * min(sx, sy)


def _resize_scrolling_tape(comp: dict, sx: float, sy: float,
                            scale_position: bool = True, scale_size: bool = True) -> None:
    # scroll.table maps a raw dataref value to a pixel offset *into the
    # source texture strip* (atlas-space) — never scales, same reasoning
    # as ImagePanel's cliprect/origin.
    if scale_position and "position" in comp:
        comp["position"] = _scale_pair(comp["position"], sx, sy)
    _resize_viewport(comp, sx, sy, scale_position, scale_size)
    if scale_size:
        comp["scale"] = comp.get("scale", 1.0) * min(sx, sy)


def _resize_rotary_encoder(comp: dict, sx: float, sy: float,
                            scale_position: bool = True, scale_size: bool = True) -> None:
    # background_origin/background_cliprect/face_origin/face_cliprect are
    # atlas-space (which pixels get cropped) — never scale, same reasoning
    # as ImagePanel. Unlike ImagePanel, on-screen render size is already a
    # genuinely separate field here (`size`/`face_size`, fed to
    # sprite.scale_x/y as target_w/cw at construction time), so no new
    # schema field is needed for this type. drag_px_per_step and
    # hit_padding are gesture/interaction tuning, not geometry — left
    # untouched, matching apply_scale()'s own exclusions (neither is
    # scaled there either). `position` is the component's own anchor;
    # `face_offset` is a translation of the face sprite relative to that
    # anchor, so it's anchor-like too — both gated by scale_position.
    # `size`/`face_size`/`face_rotation_center` describe dimensions, gated
    # by scale_size.
    if scale_position:
        if "position" in comp:
            comp["position"] = _scale_pair(comp["position"], sx, sy)
        if "face_offset" in comp:
            comp["face_offset"] = _scale_pair(comp["face_offset"], sx, sy)
    if scale_size:
        if "size" in comp:
            comp["size"] = _scale_pair(comp["size"], sx, sy)
        if "face_size" in comp:
            comp["face_size"] = _scale_pair(comp["face_size"], sx, sy)
        if "face_rotation_center" in comp:
            comp["face_rotation_center"] = _scale_pair(comp["face_rotation_center"], sx, sy)


def _resize_needle_gauge(comp: dict, sx: float, sy: float,
                          scale_position: bool = True, scale_size: bool = True) -> None:
    s = min(sx, sy)
    if scale_position and "center" in comp:
        comp["center"] = _scale_pair(comp["center"], sx, sy)
    if "needle_viewport" in comp:
        vx, vy, vw, vh = comp["needle_viewport"]
        if scale_position:
            vx, vy = vx * sx, vy * sy
        if scale_size:
            vw, vh = vw * sx, vh * sy
        comp["needle_viewport"] = [vx, vy, vw, vh]

    linear = comp.get("linear")
    if scale_position and linear and "offset" in linear:
        linear["offset"] = _scale_pair(linear["offset"], sx, sy)

    if not scale_size:
        return

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


def _resize_vector_tape(comp: dict, sx: float, sy: float,
                         scale_position: bool = True, scale_size: bool = True) -> None:
    # x_offset/y_offset are literally named screen-space X/Y nudges (per
    # this component's own schema docstring) — always sx/sy respectively,
    # regardless of scroll_axis. `length` and the spine-gap-style offsets
    # (labels.offset, bands.width/offset) are NOT axis-named — their
    # screen axis depends on scroll_axis (confirmed directly against
    # VectorTape._draw_ticks_y/_x, _draw_bands_y/_x, _draw_labels_y/_x):
    # a vertical tape's spine runs along y, so its "across" (perpendicular)
    # direction is x; a horizontal tape swaps the two. pixels_per_unit
    # relates a dataref value to scroll distance along the primary axis —
    # scales by that same "along" factor. `position` is the tape's own
    # anchor (scale_position); everything else here is its own internal
    # geometry (scale_size).
    s = min(sx, sy)
    vertical = str(comp.get("scroll_axis", "y")) == "y"
    along = sy if vertical else sx
    across = sx if vertical else sy

    if scale_position and "position" in comp:
        comp["position"] = _scale_pair(comp["position"], sx, sy)
    _resize_viewport(comp, sx, sy, scale_position, scale_size)

    if not scale_size:
        return

    if "pixels_per_unit" in comp:
        comp["pixels_per_unit"] = comp["pixels_per_unit"] * along

    for td in comp.get("ticks", []):
        if "length" in td:
            td["length"] = td["length"] * across
        if "width" in td:
            td["width"] = td["width"] * s
        if "x_offset" in td:
            td["x_offset"] = td["x_offset"] * sx
        if "y_offset" in td:
            td["y_offset"] = td["y_offset"] * sy
        # interval is a value-domain spacing (dataref units), not pixels —
        # never scales.

    labels = comp.get("labels")
    if labels:
        if "font_size" in labels:
            labels["font_size"] = labels["font_size"] * s
        if "emphasize_font_size" in labels:
            labels["emphasize_font_size"] = labels["emphasize_font_size"] * s
        if "offset" in labels:
            labels["offset"] = labels["offset"] * across

    for band in comp.get("bands", []):
        # range is value-domain (dataref units or a static endpoint) —
        # never scales.
        if "width" in band:
            band["width"] = band["width"] * across
        if "offset" in band:
            band["offset"] = band["offset"] * across
        if "dash" in band:
            band["dash"] = band["dash"] * along

    for bug in comp.get("bugs", []):
        # value (static or {dataref, table}) is value-domain — never
        # scales. points define the bug's own marker shape in ordinary
        # screen x/y offsets from its anchor — directional per point.
        if "points" in bug:
            bug["points"] = _scale_points(bug["points"], sx, sy)
        if "width" in bug:
            bug["width"] = bug["width"] * s


def _resize_vector_compass_rose(comp: dict, sx: float, sy: float,
                                 scale_position: bool = True, scale_size: bool = True) -> None:
    # A compass rose is fundamentally radial: ticks/labels/pointers/CDI/
    # deviation-bar/moving_map-active-radial all rotate to arbitrary
    # (usually dataref-driven) angles via _point_at()-style geometry, not
    # fixed instrument x/y axes. Every such radius/offset/length/stroke-
    # width field scales by the single scalar factor `s` (min(sx,sy)),
    # matching how Vector's/NeedleGauge circular's own radial fields were
    # treated in earlier stages — avoids the rose becoming an ellipse, or
    # a rotating shape distorting differently depending on which way it
    # currently happens to be pointing. Only a handful of elements are
    # genuinely screen-fixed (never rotate) and use directional (sx, sy)
    # instead: `heading_marker` (always straight up — confirmed via
    # _draw_heading_marker()'s own comment, "Fixed top-dead-centre... this
    # marker doesn't move"), `center_marker` (fixed at the rose centre),
    # `range_rings.label.offset` (confirmed via _draw_range_label()'s own
    # comment, "Fixed relative to the rose centre"), and moving_map's own
    # symbols/label_offset (confirmed via the moving_map draw loop's own
    # comment, "Symbols stay screen-fixed... like north-up on a paper
    # chart, not the heading-up convention"). That directional-vs-scalar
    # split is orthogonal to the position/size gate below: `center` (and
    # the viewport's own [x, y]) is the rose's *only* true anchor, gated by
    # scale_position; literally everything else — including those
    # "screen-fixed" directional fields — is the rose's own shape/size,
    # gated by scale_size (so resizing the rose in place, with position
    # unchecked, still grows/shrinks those elements around the fixed
    # centre; moving it without resizing, with size unchecked, leaves
    # every one of them exactly as they were, just re-centred).
    s = min(sx, sy)

    if scale_position and "center" in comp:
        comp["center"] = _scale_pair(comp["center"], sx, sy)
    _resize_viewport(comp, sx, sy, scale_position, scale_size)

    if not scale_size:
        return

    if "radius" in comp:
        comp["radius"] = comp["radius"] * s
    for key in (
        "line_width", "tick5_length", "tick5_width", "tick10_length", "tick10_width",
        "label_offset", "label_font_size", "label_emphasize_font_size",
    ):
        if key in comp:
            comp[key] = comp[key] * s

    track = comp.get("track")
    if track:
        for key in ("width", "start", "end", "tick_position", "tick_length"):
            if key in track:
                track[key] = track[key] * s

    bug = comp.get("heading_bug")
    if bug:
        if "radius" in bug:
            bug["radius"] = bug["radius"] * s
        if "points" in bug:
            bug["points"] = _scale_points_scalar(bug["points"], s)
        if "width" in bug:
            bug["width"] = bug["width"] * s
        if "outline_width" in bug:
            bug["outline_width"] = bug["outline_width"] * s
        line = bug.get("line")
        if line:
            if "width" in line:
                line["width"] = line["width"] * s
            if "dash" in line:
                line["dash"] = [line["dash"][0] * s, line["dash"][1] * s]

    rings = comp.get("range_rings")
    if rings:
        if "width" in rings:
            rings["width"] = rings["width"] * s
        label = rings.get("label")
        if label:
            if "offset" in label:
                label["offset"] = _scale_pair(label["offset"], sx, sy)
            if "font_size" in label:
                label["font_size"] = label["font_size"] * s

    marker = comp.get("heading_marker")
    if marker:
        # Always straight up — a pure y-direction distance, not radial.
        if "radius" in marker:
            marker["radius"] = marker["radius"] * sy
        if "points" in marker:
            marker["points"] = _scale_points(marker["points"], sx, sy)
        if "width" in marker:
            marker["width"] = marker["width"] * s
        if "outline_width" in marker:
            marker["outline_width"] = marker["outline_width"] * s

    cm = comp.get("center_marker")
    if cm:
        if "points" in cm:
            cm["points"] = _scale_points(cm["points"], sx, sy)
        if "width" in cm:
            cm["width"] = cm["width"] * s
        if "outline_width" in cm:
            cm["outline_width"] = cm["outline_width"] * s

    for pointer in comp.get("bearing_pointers", []):
        if "offset" in pointer:
            pointer["offset"] = pointer["offset"] * s
        if "points" in pointer:
            pointer["points"] = _scale_points_scalar(pointer["points"], s)
        if "width" in pointer:
            pointer["width"] = pointer["width"] * s
        if "outline_width" in pointer:
            pointer["outline_width"] = pointer["outline_width"] * s
        tail = pointer.get("tail")
        if tail:
            if "offset" in tail:
                tail["offset"] = tail["offset"] * s
            if "points" in tail:
                tail["points"] = _scale_points_scalar(tail["points"], s)
            if "width" in tail:
                tail["width"] = tail["width"] * s
            if "outline_width" in tail:
                tail["outline_width"] = tail["outline_width"] * s

    cdi = comp.get("course_deviation_indicator")
    if cdi:
        for seg_key in ("head", "tail"):
            seg = cdi.get(seg_key)
            if not seg:
                continue
            if "start" in seg:
                seg["start"] = seg["start"] * s
            if "end" in seg:
                seg["end"] = seg["end"] * s
            if "width" in seg:
                seg["width"] = seg["width"] * s
            if "dash" in seg:
                seg["dash"] = [seg["dash"][0] * s, seg["dash"][1] * s]
            symbol = seg.get("symbol")
            if symbol:
                if "offset" in symbol:
                    symbol["offset"] = symbol["offset"] * s
                if "points" in symbol:
                    symbol["points"] = _scale_points_scalar(symbol["points"], s)
                if "width" in symbol:
                    symbol["width"] = symbol["width"] * s
                if "outline_width" in symbol:
                    symbol["outline_width"] = symbol["outline_width"] * s
            label = seg.get("label")
            if label:
                for key in ("offset", "perp_offset", "font_size"):
                    if key in label:
                        label[key] = label[key] * s
                # rotation_offset is an angle — never scales.

        dev_bar = cdi.get("deviation_bar")
        if dev_bar:
            if "points" in dev_bar:
                dev_bar["points"] = _scale_points_scalar(dev_bar["points"], s)
            if "width" in dev_bar:
                dev_bar["width"] = dev_bar["width"] * s
            if "outline_width" in dev_bar:
                dev_bar["outline_width"] = dev_bar["outline_width"] * s
            table = dev_bar.get("table")
            if table:
                # table maps a raw dataref value to a px displacement along
                # the perpendicular-to-course axis (itself rotating) — the
                # output column scales, matching Vector's length-table
                # treatment in stage 1 (there's no separate `scale`-like
                # field for this, unlike ImagePanel/SpriteSheet — scaling
                # the table's own output directly reproduces exactly what
                # apply_scale()'s internal-only _deviation_bar_scale
                # multiplier already does for the live-object case).
                dev_bar["table"] = [[row[0], row[1] * s] for row in table]

        dev_markers = cdi.get("deviation_markers")
        if dev_markers:
            for key in ("spacing", "size", "width"):
                if key in dev_markers:
                    dev_markers[key] = dev_markers[key] * s

    mm = comp.get("moving_map")
    if mm:
        for type_name in ("airport", "vor", "ndb", "waypoint"):
            style = mm.get(type_name)
            if not style:
                continue
            # Map symbols are screen-fixed (north/window-up, never rotated
            # by heading or bearing) — directional, unlike every rotating
            # element above.
            if "points" in style:
                style["points"] = _scale_points(style["points"], sx, sy)
            if "outline_width" in style:
                style["outline_width"] = style["outline_width"] * s
            if "label_font_size" in style:
                style["label_font_size"] = style["label_font_size"] * s
            if "label_offset" in style:
                style["label_offset"] = _scale_pair(style["label_offset"], sx, sy)
            circle = style.get("circle")
            if circle:
                if "radius" in circle:
                    circle["radius"] = circle["radius"] * s
                if "outline_width" in circle:
                    circle["outline_width"] = circle["outline_width"] * s
            active = style.get("active")
            if active:
                # The active-VOR radial itself rotates with course — scalar,
                # same reasoning as the CDI segments above.
                if "width" in active:
                    active["width"] = active["width"] * s
                if "dash" in active:
                    active["dash"] = [active["dash"][0] * s, active["dash"][1] * s]
                active_label = active.get("label")
                if active_label:
                    for key in ("head_offset", "tail_offset", "perp_offset", "font_size"):
                        if key in active_label:
                            active_label[key] = active_label[key] * s
                    # rotation_offset is an angle — never scales.
            # min_runway_length.table is [range_nm, min_length_m] —
            # real-world units, never pixels — never scales.


def _resize_attitude_indicator(comp: dict, sx: float, sy: float,
                                scale_position: bool = True, scale_size: bool = True) -> None:
    # Like the compass rose, the horizon/pitch-ladder assembly and every
    # element mounted on the bank arc (ticks, roll pointer, slip indicator)
    # rotate together to an arbitrary bank angle (_rot() in
    # gauge_core/attitude_indicator.py) — scalar (min(sx,sy)), confirmed via
    # _draw_ladder/_draw_bank_arc/_draw_roll_pointer/_draw_slip_indicator.
    # A handful of elements _draw_bank_arc's own geometry proves are
    # screen-fixed (the 0-deg reference mark, always at the arc's
    # top-dead-centre regardless of bank) and the two "drawn in screen
    # space (no bank rotation)" FD bars / bug / wing overlays use
    # directional (sx, sy) instead — orthogonal to the position/size gate
    # below: unlike the compass rose, this type has no separate `center`
    # field at all, so `viewport`'s own [x, y] is its *only* anchor
    # (scale_position); every other field, including those "screen-fixed"
    # directional ones, is its own internal geometry (scale_size).
    s = min(sx, sy)

    if "viewport" in comp:
        vx, vy, vw, vh = comp["viewport"]
        if scale_position:
            vx, vy = vx * sx, vy * sy
        if scale_size:
            vw, vh = vw * sx, vh * sy
        comp["viewport"] = [vx, vy, vw, vh]

    if not scale_size:
        return

    for key in (
        "pixels_per_degree", "horizon_width", "ladder_width", "label_font_size",
        "bank_arc_width", "bank_arc_radius",
        "roll_pointer_height", "roll_pointer_width", "roll_pointer_size",
        "roll_pointer_line_width", "roll_pointer_y_offset",
        "bank_arc_y_offset",
        "bank_tick_10", "bank_tick_20", "bank_tick_30", "bank_tick_45", "bank_tick_60",
        "arc_ref_line_width",
        "arc_bg_inset", "corner_radius",
        "slip_width", "slip_height", "slip_line_width", "slip_offset", "slip_scale",
        "centre_bug_outline_width", "wing_outline_width",
        "fd_h_width", "fd_v_width",
    ):
        if key in comp:
            comp[key] = comp[key] * s

    # 0-deg reference mark on the bank arc — fixed at the arc's top-dead-
    # centre regardless of bank (unlike the ticks/pointer above, this is
    # never rotated), so arc_ref_height/offset are true vertical extents and
    # arc_ref_width a true horizontal half-width.
    if "arc_ref_height" in comp:
        comp["arc_ref_height"] = comp["arc_ref_height"] * sy
    if "arc_ref_width" in comp:
        comp["arc_ref_width"] = comp["arc_ref_width"] * sx
    if "arc_ref_offset" in comp:
        comp["arc_ref_offset"] = comp["arc_ref_offset"] * sy

    # FD bars are drawn "in screen space (no bank rotation)" per
    # _draw_flight_director()'s own comment. The h-bar is a horizontal line
    # (length along x) whose deflection moves it vertically; the v-bar is
    # vertical (length along y) whose deflection moves it horizontally — so
    # each bar's own length follows its axis, while its dataref->pixel scale
    # follows the perpendicular (deflection) axis.
    if "fd_h_length" in comp:
        comp["fd_h_length"] = comp["fd_h_length"] * sx
    if "fd_h_scale" in comp:
        comp["fd_h_scale"] = comp["fd_h_scale"] * sy
    if "fd_v_length" in comp:
        comp["fd_v_length"] = comp["fd_v_length"] * sy
    if "fd_v_scale" in comp:
        comp["fd_v_scale"] = comp["fd_v_scale"] * sx

    # Reference bug/wings are fixed screen overlays (_draw_reference_bug/
    # _draw_reference_wings, drawn straight off cx,cy with no bank rotation)
    # — directional per-point scaling, not scalar.
    if "centre_bug_points" in comp:
        comp["centre_bug_points"] = _scale_points(comp["centre_bug_points"], sx, sy)
    if "wing_points" in comp:
        comp["wing_points"] = _scale_points(comp["wing_points"], sx, sy)

    # ladder_step (degrees), ladder_hw_4/2/1 (ratios of viewport width, not
    # absolute pixels) are not geometry — never scaled, matching
    # AttitudeIndicator.apply_scale()'s own exclusions.


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
    "VectorTape": _resize_vector_tape,
    "VectorCompassRose": _resize_vector_compass_rose,
    "AttitudeIndicator": _resize_attitude_indicator,
}
