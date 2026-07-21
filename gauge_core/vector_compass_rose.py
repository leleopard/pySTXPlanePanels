"""VectorCompassRose component — rotating compass card for an HSI.

A circular dial with 5°/10° heading ticks and periodic heading labels,
drawn fresh each frame. The whole rose rotates as a rigid body so the
tick for the aircraft's current heading is always at the top (12
o'clock) — the standard rotating-card HSI convention.

Angle convention (Arcade): 0° = right (3 o'clock), CCW positive. For a
compass heading H (0-360, clockwise from North) drawn on a rose whose
current heading is `heading`, the on-screen angle is:

    screen_angle = 90 - H + heading

At heading=0 this puts H=0 at 90° (straight up) and H=90 at 0° (right),
matching a compass face laid out clockwise. Adding `heading` rotates
the whole card counter-clockwise as the aircraft heading increases,
which is the correct visual direction (turn right -> card appears to
rotate left beneath the fixed lubber line at top).

YAML schema
-----------
    - type: VectorCompassRose
      name: hsi_rose
      center: [300, 300]
      radius: 200
      background_color: [20, 20, 30, 255]   # optional; omit → no fill
      show_line: true
      line_color: [255, 255, 255, 255]
      line_width: 2.0
      num_segments: 128                     # optional; circle smoothness

      tick5_length: 8
      tick5_color: [255, 255, 255, 255]
      tick5_width: 1.0
      tick5_position: outside               # inside | outside

      tick10_length: 16
      tick10_color: [255, 255, 255, 255]
      tick10_width: 2.0
      tick10_position: outside

      label_interval: 30                    # degrees between labels
      label_offset: 20                      # px from the circle arc
      label_position: inside                # inside | outside
      label_font: ST_Boeing_PFD
      label_font_size: 14
      label_color: [255, 255, 255, 255]
      label_format: "{:02.0f}"              # applied to heading/10, e.g. 030° → "03"
      label_bold: false
      label_italic: false
      label_emphasize_interval: 30          # optional: headings on this coarser
                                             # interval (must be a multiple of
                                             # label_interval) use a bigger/smaller
                                             # font, e.g. label every 10° but a
                                             # bigger size every 30°
      label_emphasize_font_size: 20         # font size for those headings
      label_anchor_y: center                # baseline | center | top | bottom —
                                             # which part of the label glyph sits at
                                             # the offset point (radius ± offset);
                                             # the rest of the glyph extends from
                                             # there along the label's radial
                                             # (rotated) orientation

      heading:                              # rotates the whole rose
        dataref: sim/cockpit2/gauges/indicators/heading_vacuum_deg_mag_pilot
        convert_function: null              # optional

      track:                                # optional: a line from the centre,
                                             # rotating with the rose like a tick
                                             # (i.e. relative to heading, showing
                                             # crab angle) — omit to not draw one
        dataref: sim/cockpit2/gauges/indicators/track_mag_pilot
        convert_function: null              # optional
        color: [0, 255, 0, 255]
        width: 2.0
        start: 0                            # px from centre where the line starts
        end: 150                            # px from centre where the line ends
        tick_position: 100                  # optional px from centre for a tick
                                             # perpendicular to the line; omit for
                                             # no tick
        tick_length: 20                     # full length of that tick, split
                                             # evenly across the line

      viewport: [10, 0, 500, 100]            # optional scissor clip [x, y_bottom, w, h];
                                             # confines the rose to a rectangular window
                                             # (e.g. a partial arc peeking from behind
                                             # other panel artwork) instead of drawing
                                             # its full extent unclipped

      heading_bug:                           # optional: e.g. the autopilot selected-heading
                                             # bug — a polygon marker on the arc, positioned
                                             # by its own dataref (not the rose's own heading)
                                             # and rotating with the rose like a tick; clipped
                                             # by `viewport` the same as everything else, so it
                                             # disappears when rotated past the visible arc
        dataref: sim/cockpit/autopilot/heading_mag
        convert_function: null              # optional
        radius: 210                         # px from centre where the bug's local origin sits
        points: [[0, 0], [-8, -18], [8, -18]]  # relative to that origin, in the bug's own
                                             # unrotated local space where +y points radially
                                             # outward (away from the rose centre) at heading=0
        color: [255, 255, 255, 255]
        filled: true
        width: 2.0                         # stroke width when filled: false
        outline_color: null                # optional outline drawn on top when filled: true
        outline_width: 1.0
        line:                               # optional: a radial spoke from
                                             # the rose centre out to the
                                             # bug's own position, drawn
                                             # underneath the bug symbol
          color: [255, 255, 255, 255]
          width: 2.0
          dash: [8.0, 4.0]                 # optional [on_px, off_px];
                                             # omit (or null) for a solid line

      range_rings:                           # optional: evenly-spaced concentric circles
                                             # inside the rose, e.g. radar/HSI range rings
        count: 3                            # 1-10; spacing is auto-calculated so all
                                             # gaps are equal: ring k sits at
                                             # k * radius / count, so the outermost
                                             # ring (k = count) lands on the rose's
                                             # own radius
        color: [255, 255, 255, 120]
        width: 1.0
        half: full                           # optional: full (default) | top | bottom —
                                             # draws only the upper or lower half of each
                                             # ring instead of the full circle (e.g. a
                                             # weather-radar-style HSI that only ever
                                             # shows the top half of the compass card)
        label:                               # optional: a dataref-driven range-selection
                                             # readout (e.g. the cockpit's selected radar/
                                             # nav range), fixed in screen space — does not
                                             # rotate with heading, like heading_marker
          dataref: sim/cockpit/radios/nav1_range
          convert_function: null            # optional; applied to the raw dataref
                                             # value BEFORE table (same order as
                                             # needle_angle elsewhere in this codebase)
          table: [[0, 10], [1, 20], [2, 40]]  # optional piecewise-linear lookup,
                                             # e.g. a range-selector index -> the
                                             # actual displayed range; omit to use
                                             # the (possibly converted) raw value directly
          format: "{:.0f}"
          offset: [0, -180]                 # px, relative to the rose centre (x-right,
                                             # y-up); NOT relative to the ring radii
          font: ST_Boeing_PFD                # optional; blank = designer/OS default
          font_size: 14
          bold: false
          italic: false
          color: [255, 255, 255, 255]
          anchor_x: center                   # left | center | right — which part of
                                             # the glyph sits at the offset point
          anchor_y: center                   # baseline | center | top | bottom

      heading_marker:                        # optional: fixed lubber-line/index polygon at
                                             # top-dead-centre — no dataref, since it never
                                             # rotates (the rose rotates underneath it, so
                                             # whatever heading ends up at the top is read off
                                             # this marker)
        radius: 210                         # px from centre where the marker's local origin sits
        points: [[0, 0], [-8, 18], [8, 18]]   # relative to that origin, in plain screen space
                                             # (no rotation applied)
        color: [255, 255, 0, 255]
        filled: true
        width: 2.0                         # stroke width when filled: false
        outline_color: null                # optional outline drawn on top when filled: true
        outline_width: 1.0

      center_marker:                         # optional: a fixed reference mark drawn
                                             # directly at the rose centre (e.g. an
                                             # aircraft symbol) — no dataref, no radius
                                             # offset, and never rotates
        points: [[-5, 0], [5, 0], [0, 8]]     # relative to the rose centre (cx, cy),
                                             # in plain screen space (no rotation applied)
        color: [255, 255, 255, 255]
        filled: true
        width: 2.0                         # stroke width when filled: false
        outline_color: null                # optional outline drawn on top when filled: true
        outline_width: 1.0
        clip: true                          # optional, default true; whether this marker
                                             # is confined by the component's own `viewport`
                                             # clip like everything else, or always drawn
                                             # regardless of the viewport

      bearing_pointers:                      # optional: dataref-driven RMI/RBI-style
                                             # bearing pointers (e.g. VOR1, VOR2, ADF1,
                                             # ADF2) — polygons that sit on the rose's own
                                             # circle and rotate with the rose like a tick,
                                             # positioned by their own bearing dataref (not
                                             # the rose's own heading), same mechanism as
                                             # heading_bug but as a list (any number/names)
                                             # and each independently visibility-gated
        - name: VOR1                        # for reference only, not used by rendering
          dataref: sim/cockpit/radios/nav1_dir_degt
          convert_function: null            # optional
          offset: 0                          # px from the rose's own circle (radius) —
                                             # 0 sits right on the circle edge, negative
                                             # moves inward, positive moves outward
          points: [[0, 0], [-8, -18], [8, -18]]  # relative to that position, in the
                                             # pointer's own unrotated local space where
                                             # +y points radially outward (away from the
                                             # rose centre) at heading=0
          color: [255, 255, 255, 255]
          filled: true
          width: 2.0                         # stroke width when filled: false
          outline_color: null                # optional outline drawn on top when filled: true
          outline_width: 1.0
          visibility:                         # optional; omit to always show this pointer
            dataref: sim/cockpit2/radios/actuators/HSI_source_select_pilot
            predicate: true_if_equals_1
          preview_angle: 20                   # optional, designer-only: which bearing
                                             # (degrees) this pointer is drawn at in the
                                             # designer's static preview, since there's no
                                             # live dataref value there — purely a
                                             # designer convenience, has NO effect on the
                                             # running panel (the real dataref drives the
                                             # angle at runtime, as always)
          tail:                               # optional: a second polygon diametrically
                                             # opposite the head (bearing + 180°), sharing
                                             # the head's dataref/visibility — e.g. the
                                             # tail/fletching of a real RMI/RBI needle
            offset: 0
            points: [[0, 0], [-6, 10], [6, 10]]
            color: [255, 255, 255, 255]
            filled: true
            width: 2.0
            outline_color: null
            outline_width: 1.0

      course_deviation_indicator:            # optional: a two-segment course
                                             # line (head towards the course
                                             # angle, tail diametrically
                                             # opposite) rotating with the
                                             # rose around its own centre,
                                             # positioned by a course dataref
                                             # — the classic CDI course line
                                             # on an HSI. Deviation dots are a
                                             # planned follow-up, not
                                             # implemented yet.
        dataref: sim/cockpit/radios/nav1_obs_deg_mag_pilot
        convert_function: null              # optional
        visibility:                        # optional; shows/hides the whole
                                             # CDI (head/tail/deviation_bar/
                                             # deviation_markers together),
                                             # same convention as
                                             # bearing_pointers
          dataref: ...
          predicate: true_if_over_zero
        preview_angle: 0                    # optional, designer-only: which
                                             # course angle this is drawn at
                                             # in the designer's static
                                             # preview, since there's no live
                                             # dataref value there — purely a
                                             # designer convenience, has NO
                                             # effect on the running panel
        head:                                # segment towards the course angle
          start: 20                          # px from the rose centre
          end: 180                           # px from the rose centre
          color: [255, 255, 255, 255]
          width: 2.0
          dash: [6, 4]                       # optional [on_px, off_px]; omit
                                             # (or null) for a solid line
          symbol:                            # optional: a polygon at this
                                             # segment's own angle (head:
                                             # course angle; tail: +180°) —
                                             # e.g. an arrowhead at the tip
            offset: 180                      # px from the rose centre where
                                             # the symbol's local origin
                                             # sits (independent of the
                                             # line's own end, though
                                             # usually matches it)
            points: [[0, 0], [-8, -14], [8, -14]]  # relative to that origin,
                                             # in the symbol's own unrotated
                                             # local space where +y points
                                             # radially outward — same
                                             # convention as bearing_pointers
            color: [255, 255, 255, 255]
            filled: true
            width: 2.0                      # stroke width when filled: false
            outline_color: null             # optional outline when filled: true
            outline_width: 1.0
        tail:                                # segment diametrically opposite
                                             # (course + 180°)
          start: 20
          end: 180
          color: [255, 255, 255, 255]
          width: 2.0
          dash: null
          symbol: null                      # optional, same shape as head's

        deviation_bar:                       # optional: a polygon that
                                             # translates from the rose
                                             # centre along the line
                                             # perpendicular to the course
                                             # line, by a dataref-driven px
                                             # amount — the classic CDI
                                             # left/right deviation bar
          dataref: sim/cockpit/radios/nav1_hdef_dot
          preview_deviation: 50             # optional, designer-only: px
                                             # translation shown in the
                                             # designer's static preview,
                                             # since there's no live dataref
                                             # value there — purely a
                                             # designer convenience, has NO
                                             # effect on the running panel;
                                             # default is radius / 3
          convert_function: null            # optional; applied to the raw
                                             # dataref value BEFORE table
                                             # (same order as needle_angle
                                             # elsewhere in this codebase)
          table: [[0, 0], [1, 40], [-1, -40]]  # optional piecewise-linear
                                             # lookup, e.g. dots-of-deviation
                                             # -> actual px translation; omit
                                             # to use the (possibly
                                             # converted) raw value directly
                                             # as px — positive moves toward
                                             # (course_angle + 90°); flip
                                             # sign via convert_function/table
                                             # if a given dataref runs the
                                             # other way
          points: [[-4, -30], [4, -30], [4, 30], [-4, 30]]  # relative to the
                                             # bar's own (translated) origin,
                                             # oriented ALONG the course line
                                             # (+y outward), same convention
                                             # as bearing_pointers/symbols
          color: [255, 255, 255, 255]
          filled: true
          width: 2.0
          outline_color: null
          outline_width: 1.0

        deviation_markers:                   # optional: 4 fixed reference
                                             # marks (2 each side) on the
                                             # same perpendicular-to-course
                                             # axis as the deviation bar —
                                             # the classic CDI dots/ticks.
                                             # Not dataref-driven themselves
                                             # (no sliding) — only rotate
                                             # with the CDI's own course angle
          shape: circle                     # circle (default, unfilled) | tick
          spacing: 40                       # px between adjacent markers;
                                             # they sit at ±spacing and
                                             # ±2*spacing from centre
          size: 4                           # circle radius, or tick half-length
          width: 2.0                        # circle outline stroke width,
                                             # or tick line width
          color: [255, 255, 255, 255]

      moving_map:                            # optional: airports/VORs/NDBs
                                             # positioned by their real GPS
                                             # coordinates relative to the
                                             # aircraft's own GPS position —
                                             # position is heading-up rotated
                                             # like everything else on this
                                             # rose, but each symbol itself
                                             # is screen-fixed (like a paper-
                                             # chart icon, not a radial
                                             # needle) — never rotated by
                                             # heading or by its individual
                                             # bearing from the aircraft; a
                                             # symbol's "up" is always the
                                             # window's own +Y direction.
                                             # Scaled so the rose's outer
                                             # edge equals TWICE whatever
                                             # range range_rings.label is
                                             # currently showing (matches
                                             # the real EFIS convention: the
                                             # displayed range is the half-
                                             # range ring, not the edge) —
                                             # requires that to be configured
                                             # (no range, no map). Drawn
                                             # UNDERNEATH every other rose
                                             # element (right after the
                                             # optional background fill).
                                             # Positions come from a local
                                             # cache built via Settings ->
                                             # Navigation Data... in the
                                             # designer — see gauge_core/navdata.py.
        gps_lat_dataref: sim/flightmodel/position/latitude
        gps_lon_dataref: sim/flightmodel/position/longitude
        max_per_type: 60                    # optional cap per feature type,
                                             # closest-first, so a dense area
                                             # at a large range doesn't flood
                                             # the frame with draw calls.
                                             # Polygons are cheap (batched
                                             # into one draw call); `label:
                                             # true` labels are the expensive
                                             # part (individual text draws,
                                             # ~0.1-0.15ms each) — keep this
                                             # conservative for types with
                                             # labels enabled, especially over
                                             # dense areas
        visibility:                         # optional; independent of the
                                             # whole rose's own visibility,
                                             # same as bearing_pointers
          dataref: ...
          predicate: true_if_over_zero
        airport:                            # optional per-type styling;
                                             # omit a type to hide it. Either
                                             # points or circle (or both)
                                             # must be set for a type to draw.
                                             # fill and outline are
                                             # independent — enable either,
                                             # both, or neither, each with
                                             # its own color (outline also
                                             # has its own width). Same
                                             # convention for the polygon
                                             # and the circle below.
          icao_only: true                   # airport type only — X-Plane's
                                             # apt.dat includes tens of
                                             # thousands of genuine but
                                             # uncharted/private airfields
                                             # with non-ICAO idents (e.g.
                                             # X-Plane-invented "XEG4CM" or
                                             # the US FAA's local 3-4 char
                                             # LID scheme); true keeps only
                                             # real 4-letter ICAO idents,
                                             # matching a real charted EFIS.
                                             # Set false to show everything
                                             # X-Plane knows about.
          visibility:                        # optional; independently
                                             # shows/hides this whole
                                             # feature type — separate from
                                             # moving_map's own overall
                                             # visibility, same convention
                                             # as bearing_pointers
            dataref: ...
            predicate: true_if_over_zero
          points: [[-4, 0], [0, 4], [4, 0], [0, -4]]  # relative to the
                                             # feature's own screen position,
                                             # screen-fixed (never rotated) —
                                             # optional; omit for a circle-
                                             # only symbol
          filled: true
          color: [255, 255, 255, 200]        # fill color, used when filled: true
          outline: false
          outline_color: [255, 255, 255, 255]  # used when outline: true
          outline_width: 1.0                  # used when outline: true
          circle:                           # optional; drawn centred on the
                                             # feature's own screen position,
                                             # UNDERNEATH the polygon (so a
                                             # symbol can combine a circle
                                             # background with a polygon
                                             # glyph on top)
            radius: 6.0
            filled: false
            color: [255, 255, 255, 200]
            outline: true
            outline_color: [255, 255, 255, 200]
            outline_width: 1.5
          label: true                       # optional ident label — stays
                                             # upright (not rotated), unlike
                                             # the polygon itself
          label_font_size: 10.0
          label_color: [255, 255, 255, 200]
          label_font: null                   # optional; blank = designer/OS default
          label_offset: [6.0, 0.0]           # optional; [x, y] from the
                                             # symbol's own screen position,
                                             # y-up (matches every other
                                             # offset in this schema);
                                             # default nudges the label to
                                             # the right of the symbol
        vor:                                 # same shape as airport:
          points: [[-5, -5], [5, -5], [5, 5], [-5, 5]]
          filled: false
          outline: true
          outline_color: [0, 200, 255, 200]
          outline_width: 1.5
          active:                            # optional; recolors whichever
                                             # VOR's ident matches a live
                                             # "tuned station" string
                                             # dataref, and draws a dashed
                                             # course radial THROUGH that
                                             # VOR's own position, capped at
                                             # the rose's own edge in both
                                             # directions (course and its
                                             # reciprocal) — NOT the
                                             # rose-centred CDI course line
            ident_dataref: sim/cockpit2/radios/indicators/nav1_nav_id
                                             # a plain dataref path (not a
                                             # (group, index) tuple) — read
                                             # char-by-char via X-Plane's
                                             # array-index syntax, same
                                             # mechanism as Text's
                                             # char_count mode
            ident_char_count: 4              # how many characters to read
            color: [255, 60, 60, 255]        # overrides every color slot
                                             # on the matched candidate
                                             # (fill/outline/circle alike)
            course_dataref: sim/cockpit/radios/nav1_obs_deg_mag_pilot
            convert_function: null           # optional
            dash: [8.0, 4.0]                 # optional [on_px, off_px];
                                             # omit (or null) for a solid line
            width: 2.0
        ndb:                                 # same shape as airport:
          points: [[0, -5], [5, 4], [-5, 4]]
          filled: true
          color: [255, 200, 0, 200]
        waypoint:                            # same shape as airport: — en
                                             # route fixes are MUCH denser
                                             # than airports/navaids (~200k
                                             # worldwide vs tens of
                                             # thousands), so keep
                                             # max_per_type conservative if
                                             # this type is enabled,
                                             # especially with labels on
          points: [[-3, -3], [3, -3], [3, 3], [-3, 3]]
          filled: false
          outline: true
          outline_color: [180, 180, 180, 150]
          width: 1.0

      visibility:                           # optional, same as other components
        dataref: ...
        predicate: true_if_over_zero
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

import arcade
import pyglet

from gauge_core import geo, navdata
from gauge_core.font_utils import resolve_font_for_arcade
from gauge_core.lookup import lookup_piecewise
from gauge_core.registry import get_convert, register_component, resolve_predicate_name
from gauge_core.vector_primitives import _VecBase, _as_color, _as_dataref


class _BearingPointer:
    """One dataref-driven bearing pointer (e.g. VOR1/VOR2/ADF1/ADF2) — a
    polygon on the rose's own circle that rotates with the rose like a tick,
    positioned by its own bearing dataref (same mechanism as heading_bug),
    with an independent visibility dataref/predicate rather than sharing the
    whole rose's.

    Optionally has a second polygon (the "tail") diametrically opposite the
    head — bearing + 180° — sharing the same dataref/visibility, matching a
    real RMI/RBI needle's head+tail shape."""

    def __init__(
        self,
        name: str,
        dataref: Any,
        convert_fn: Callable | None,
        offset: float,
        points: list[tuple[float, float]],
        color: tuple[int, int, int, int],
        filled: bool,
        width: float,
        outline_color: tuple[int, int, int, int] | None,
        outline_width: float,
        vis_dataref: Any | None,
        vis_predicate: Callable | None,
        tail_offset: float = 0.0,
        tail_points: list[tuple[float, float]] | None = None,
        tail_color: tuple[int, int, int, int] = (255, 255, 255, 255),
        tail_filled: bool = True,
        tail_width: float = 2.0,
        tail_outline_color: tuple[int, int, int, int] | None = None,
        tail_outline_width: float = 1.0,
    ) -> None:
        self.name = name
        self.dataref = dataref
        self.convert_fn = convert_fn
        self.offset = float(offset)
        self.points = [(float(x), float(y)) for x, y in points]
        self.color = color
        self.filled = bool(filled)
        self.width = float(width)
        self.outline_color = outline_color
        self.outline_width = float(outline_width)
        self.vis_dataref = vis_dataref
        self.vis_predicate = vis_predicate
        self.angle = 0.0
        self.visible = True
        self.tail_offset = float(tail_offset)
        self.tail_points = [(float(x), float(y)) for x, y in (tail_points or [])]
        self.tail_color = tail_color
        self.tail_filled = bool(tail_filled)
        self.tail_width = float(tail_width)
        self.tail_outline_color = tail_outline_color
        self.tail_outline_width = float(tail_outline_width)


class _CdiSegment:
    """One line segment (head or tail) of a course_deviation_indicator — a
    line from the rose centre out to `end` at the segment's own angle
    (`_draw_cdi()` passes `cdi_angle` for head, `cdi_angle + 180` for tail),
    with an optional polygon symbol (e.g. an arrowhead) at that same angle."""

    def __init__(
        self,
        start: float,
        end: float,
        color: tuple[int, int, int, int],
        width: float,
        dash: tuple[float, float] | None,
        symbol_offset: float = 0.0,
        symbol_points: list[tuple[float, float]] | None = None,
        symbol_color: tuple[int, int, int, int] = (255, 255, 255, 255),
        symbol_filled: bool = True,
        symbol_width: float = 2.0,
        symbol_outline_color: tuple[int, int, int, int] | None = None,
        symbol_outline_width: float = 1.0,
    ) -> None:
        self.start = float(start)
        self.end = float(end)
        self.color = color
        self.width = float(width)
        self.dash = tuple(dash) if dash else None
        self.symbol_offset = float(symbol_offset)
        self.symbol_points = [(float(x), float(y)) for x, y in (symbol_points or [])]
        self.symbol_color = symbol_color
        self.symbol_filled = bool(symbol_filled)
        self.symbol_width = float(symbol_width)
        self.symbol_outline_color = symbol_outline_color
        self.symbol_outline_width = float(symbol_outline_width)


def _bake_map_icon(style: "_MapFeatureStyle", oversample: int = 4) -> None:
    """Rasterize a moving_map feature's polygon + circle to two textures:
    the icon's normal (already-colored) appearance, and a white silhouette
    used to tint the one "active" candidate (e.g. the tuned VOR) via
    Sprite.color. Runs lazily on first draw, i.e. after apply_scale() has
    already finalized style.points/circle_radius, so the baked geometry
    reflects the panel's final configured scale with no separate runtime
    scale factor needed beyond style.icon_scale (which only undoes the
    fixed oversample factor below, for crisper edges than 1:1 baking).

    Baking once and drawing via a pooled SpriteList (per-instance position
    updates only) is dramatically cheaper than rebuilding vertex geometry
    and re-uploading a VBO for every visible feature every frame — measured
    ~9ms/frame at 180 features for the old ShapeElementList path versus a
    handful of cheap position writes here.
    """
    from PIL import Image, ImageDraw

    pts = style.points
    r = style.circle_radius
    if not pts and r <= 0.0:
        return

    pad = max(
        style.outline_width if style.outline else 0.0,
        style.circle_outline_width if style.circle_outline else 0.0,
        1.0,
    ) + 1.0
    xs = [x for x, _y in pts] + ([-r, r] if r > 0.0 else [])
    ys = [y for _x, y in pts] + ([-r, r] if r > 0.0 else [])
    half_w = max(abs(min(xs)), abs(max(xs))) + pad
    half_h = max(abs(min(ys)), abs(max(ys))) + pad
    w_px = max(2, int(round(half_w * 2 * oversample)))
    h_px = max(2, int(round(half_h * 2 * oversample)))
    cx_px, cy_px = w_px / 2.0, h_px / 2.0
    white = (255, 255, 255, 255)

    def to_px(x: float, y: float) -> tuple[float, float]:
        # style.points are y-up (matches every other point list in this
        # schema); PIL is y-down — same flip canvas.py's own static
        # preview already applies for these same symbols.
        return (cx_px + x * oversample, cy_px - y * oversample)

    def render(active: bool) -> arcade.Texture:
        img = Image.new("RGBA", (w_px, h_px), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        if r > 0.0:
            d = r * 2.0 * oversample
            bbox = [cx_px - d / 2, cy_px - d / 2, cx_px + d / 2, cy_px + d / 2]
            if style.circle_filled:
                draw.ellipse(bbox, fill=white if active else style.circle_color)
            if style.circle_outline:
                ow = max(1, int(round(style.circle_outline_width * oversample)))
                draw.ellipse(bbox, outline=white if active else style.circle_outline_color, width=ow)

        if pts:
            poly = [to_px(x, y) for x, y in pts]
            if style.filled:
                draw.polygon(poly, fill=white if active else style.color)
            if style.outline:
                # draw.polygon(outline=, width>1) leaves gaps at concave/
                # sharp vertices — same issue already fixed in canvas.py's
                # static preview; a closed line() polyline doesn't.
                ow = max(1, int(round(style.outline_width * oversample)))
                draw.line(poly + [poly[0]], fill=white if active else style.outline_color, width=ow)

        key = f"mapicon:{id(style)}:{'active' if active else 'normal'}"
        return arcade.Texture(img, hash=key)

    style.icon_texture = render(active=False)
    style.icon_texture_active = render(active=True)
    style.icon_scale = 1.0 / oversample


def _ray_circle_exit(ox: float, oy: float, dx: float, dy: float,
                      cx: float, cy: float, r: float) -> tuple[float, float]:
    """Point where a ray from (ox, oy) in unit direction (dx, dy) exits the
    circle centred at (cx, cy) with radius r. Used for the active-VOR
    course line, which starts at the VOR's own screen position (inside the
    rose) and must stop exactly at the rose's own edge rather than running
    off to infinity. Assumes the origin is inside (or on) the circle —
    true here since map features are only plotted within the rose's own
    radius in the first place — so the forward root always exists."""
    fx, fy = ox - cx, oy - cy
    b_half = fx * dx + fy * dy
    c = fx * fx + fy * fy - r * r
    disc = max(0.0, b_half * b_half - c)
    t = -b_half + math.sqrt(disc)
    return (ox + t * dx, oy + t * dy)


def _arc_points(
    cx: float, cy: float, radius: float, start_deg: float, end_deg: float, num_segments: int,
) -> list[tuple[float, float]]:
    """Points along a circle/arc from start_deg to end_deg (standard math
    convention: 0 = +x axis, counter-clockwise — matches arcade's own
    draw_arc_outline internally, confirmed by reading its source), for
    building a static outline once via create_line_strip/create_line_loop
    instead of calling draw_circle_outline/draw_arc_outline (which rebuild
    their own throwaway VBO) every frame."""
    n = max(2, int(num_segments))
    span = end_deg - start_deg
    return [
        (
            cx + radius * math.cos(math.radians(start_deg + span * i / n)),
            cy + radius * math.sin(math.radians(start_deg + span * i / n)),
        )
        for i in range(n + 1)
    ]


class _MapFeatureStyle:
    """Polygon + optional circle + optional label styling for one
    moving_map feature type (airport/vor/ndb/waypoint). Fill and outline
    are independent toggles for both the polygon and the circle — either,
    both, or neither can be enabled, each with its own color (and the
    outline its own width). The circle (if radius > 0) is centred on the
    feature's own screen position and drawn underneath the polygon, so a
    symbol can combine both (e.g. a circle background with a polygon glyph
    on top). Either points or a circle (or both) must be set for the type
    to render at all. `icao_only` (meaningful for the airport type only —
    other types don't use 4-letter ICAO idents at all) drops candidates
    whose ident isn't a real 4-letter ICAO code, filtering out the huge
    number of genuine but uncharted/private airfields X-Plane's own
    database carries that would never appear on a real EFIS. `vis_dataref`/
    `vis_predicate` independently show/hide this whole feature type (e.g. a
    range-selector knob position, same convention as bearing_pointers'
    per-pointer visibility) — separate from the moving_map's own overall
    visibility gate. `active_*` (meaningful for the vor type — the "tuned
    VOR" concept) recolors whichever candidate's ident matches a live
    string dataref (e.g. the active nav radio's station ident) and draws a
    dashed course radial through that candidate's own screen position, at
    an angle from a course dataref, capped at the rose's own edge in both
    directions (the course and its reciprocal) — a VOR radial overlay, not
    the rose-centred CDI course line."""

    def __init__(
        self,
        points: list[tuple[float, float]],
        filled: bool,
        color: tuple[int, int, int, int],
        outline: bool,
        outline_color: tuple[int, int, int, int],
        outline_width: float,
        label: bool,
        label_font_size: float,
        label_color: tuple[int, int, int, int],
        label_font: str | None,
        label_bold: bool = False,
        label_italic: bool = False,
        label_offset: tuple[float, float] = (6.0, 0.0),
        circle_radius: float = 0.0,
        circle_filled: bool = True,
        circle_color: tuple[int, int, int, int] = (255, 255, 255, 255),
        circle_outline: bool = False,
        circle_outline_color: tuple[int, int, int, int] = (255, 255, 255, 255),
        circle_outline_width: float = 1.0,
        icao_only: bool = True,
        vis_dataref: Any | None = None,
        vis_predicate: Callable | None = None,
        active_ident_datarefs: list[Any] | None = None,
        active_color: tuple[int, int, int, int] = (255, 0, 0, 255),
        active_course_dataref: Any | None = None,
        active_course_convert: Callable | None = None,
        active_dash: tuple[float, float] | None = None,
        active_width: float = 2.0,
    ) -> None:
        self.points = [(float(x), float(y)) for x, y in points]
        self.icao_only = bool(icao_only)
        self.vis_dataref = vis_dataref
        self.vis_predicate = vis_predicate
        self.visible = True
        self.filled = bool(filled)
        self.color = color
        self.outline = bool(outline)
        self.outline_color = outline_color
        self.outline_width = float(outline_width)
        self.label = bool(label)
        self.label_font_size = float(label_font_size)
        self.label_color = label_color
        self.label_font = label_font
        self.label_bold = bool(label_bold)
        self.label_italic = bool(label_italic)
        self.label_offset_x, self.label_offset_y = float(label_offset[0]), float(label_offset[1])
        self.circle_radius = float(circle_radius)
        self.circle_filled = bool(circle_filled)
        self.circle_color = circle_color
        self.circle_outline = bool(circle_outline)
        self.circle_outline_color = circle_outline_color
        self.circle_outline_width = float(circle_outline_width)
        self.active_ident_datarefs = list(active_ident_datarefs or [])
        self.active_color = active_color
        self.active_course_dataref = active_course_dataref
        self.active_course_convert = active_course_convert
        self.active_dash = tuple(active_dash) if active_dash else None
        self.active_width = float(active_width)
        self.active_ident = ""     # updated per-frame in update()
        self.active_course = 0.0  # updated per-frame in update()
        # Own pool, not shared across styles — each style may have its own
        # label_font, which (unlike font_size/color/position) can only be
        # set at arcade.Text construction time, so pool objects can't be
        # reused across styles with different fonts.
        self.label_pool: list[arcade.Text] = []
        # Icon rendering: baked once (lazily, see _bake_map_icon) into a
        # SpriteList of pooled sprites, rather than rebuilding polygon/
        # circle vertex geometry every frame — see _bake_map_icon's own
        # docstring for why.
        self.icon_texture: arcade.Texture | None = None
        self.icon_texture_active: arcade.Texture | None = None
        self.icon_scale: float = 1.0
        self.icon_sprites: arcade.SpriteList | None = None


class VectorCompassRose(_VecBase):
    """Rotating compass card: circle + 5°/10° ticks + periodic heading labels."""

    def __init__(
        self,
        name: str,
        center: tuple[float, float],
        radius: float,
        background_color: tuple[int, int, int, int] | None = None,
        show_line: bool = True,
        line_color: tuple[int, int, int, int] = (255, 255, 255, 255),
        line_width: float = 2.0,
        num_segments: int = 128,
        tick5_length: float = 8.0,
        tick5_color: tuple[int, int, int, int] = (255, 255, 255, 255),
        tick5_width: float = 1.0,
        tick5_position: str = "outside",
        tick10_length: float = 16.0,
        tick10_color: tuple[int, int, int, int] = (255, 255, 255, 255),
        tick10_width: float = 2.0,
        tick10_position: str = "outside",
        label_interval: float = 30.0,
        label_offset: float = 20.0,
        label_position: str = "inside",
        label_font: str | None = None,
        label_font_size: float = 14.0,
        label_color: tuple[int, int, int, int] = (255, 255, 255, 255),
        label_format: str = "{:02.0f}",
        label_bold: bool = False,
        label_italic: bool = False,
        label_emphasize_interval: float | None = None,
        label_emphasize_font_size: float | None = None,
        label_anchor_y: str = "center",
        viewport: tuple[float, float, float, float] | None = None,
    ) -> None:
        self.name = name
        self._cx = float(center[0])
        self._cy = float(center[1])
        self._radius = float(radius)
        self._background_color = background_color
        self._show_line = bool(show_line)
        self._line_color = line_color
        self._line_width = float(line_width)
        self._segments = int(num_segments)

        self._tick5_length = float(tick5_length)
        self._tick5_color = tick5_color
        self._tick5_width = float(tick5_width)
        self._tick5_position = tick5_position

        self._tick10_length = float(tick10_length)
        self._tick10_color = tick10_color
        self._tick10_width = float(tick10_width)
        self._tick10_position = tick10_position

        self._label_interval = max(1, int(label_interval))
        self._label_offset = float(label_offset)
        self._label_position = label_position
        self._label_font = label_font
        self._label_font_size = float(label_font_size)
        self._label_color = label_color
        self._label_format = label_format
        self._label_bold = label_bold
        self._label_italic = label_italic
        # Which part of the label glyph sits at the offset point (radius ±
        # label_offset), in arcade.Text's own anchor_y sense — "center"
        # (default) is the vertical middle, "baseline" the text baseline,
        # "top"/"bottom" the ascender/descender edge.
        self._label_anchor_y = label_anchor_y
        # Optional bigger/smaller font for headings on a coarser interval,
        # e.g. label every 10° but a bigger size every 30°. None → all
        # labels use label_font_size.
        self._label_emphasize_interval = (
            int(label_emphasize_interval) if label_emphasize_interval else None
        )
        self._label_emphasize_font_size = (
            float(label_emphasize_font_size) if label_emphasize_font_size else self._label_font_size
        )
        self._label_pool: list[arcade.Text] = []
        # Shared by every pooled heading label (mirrors moving_map's own
        # _map_label_batch — see that field's comment for why one shared
        # pyglet Batch, drawn once, is dramatically cheaper than each
        # label calling Text.draw() individually). Kept separate from
        # _map_label_batch (different lifetime/content) rather than reused.
        self._heading_label_batch = pyglet.graphics.Batch()
        # Static (rebuilt only when stale — never rebuilt every frame):
        # the background disc (ShapeElementList — create_ellipse_filled
        # works correctly), and the outline circle + range rings + tick
        # marks (baked once to a PIL texture and drawn as a Sprite,
        # NOT via ShapeElementList's create_line/create_line_strip/
        # create_line_loop — confirmed by direct pixel-read testing,
        # including through the real PanelWindow render pipeline, that
        # those render nothing or land at the wrong position in this
        # Arcade version; create_polygon/create_ellipse_filled and plain
        # Sprite drawing are unaffected). The circle/rings never rotate
        # (baked once, drawn at Sprite.position = (cx, cy), angle 0); the
        # ticks DO rotate with heading, so they're baked once as a single
        # texture and rotated via Sprite.angle each frame instead of
        # recomputing 72 line endpoints in Python — angle = heading + 180
        # (not just heading), an offset empirically calibrated against
        # _point_at()'s own ground truth across multiple headings, since
        # Arcade's PIL-to-texture loading doesn't flip vertically the way
        # a naive reading of "Y-up local coords" would assume.
        self._bg_shape: arcade.ShapeElementList | None = None
        self._ring_sprites: arcade.SpriteList | None = None
        self._tick_sprites: arcade.SpriteList | None = None

        # Optional scissor clip [x, y_bottom, w, h] in panel coords; None means
        # draw the full rose unclipped (the pre-existing behaviour).
        self._viewport = tuple(float(v) for v in viewport) if viewport is not None else None

        self._heading = 0.0
        self._heading_dr: Any | None = None
        self._heading_convert: Callable | None = None

        # Track indicator (optional; enabled by calling set_track()) — a line
        # from the centre that rotates with the rose like a tick, driven by
        # its own dataref, with an optional perpendicular tick sharing the
        # line's color/width.
        self._show_track = False
        self._track_color: tuple[int, int, int, int] = (0, 255, 0, 255)
        self._track_width = 2.0
        self._track_start = 0.0
        self._track_end = 150.0
        self._track_tick_position: float | None = None
        self._track_tick_length = 20.0
        self._track_angle = 0.0
        self._track_dr: Any | None = None
        self._track_convert: Callable | None = None

        # Heading bug (optional; enabled by calling set_heading_bug()) — a
        # polygon marker (e.g. the autopilot selected-heading bug) that sits
        # on the arc at its own dataref-driven heading and rotates with the
        # rose, like a tick or the track indicator.
        self._show_bug = False
        self._bug_radius = 0.0
        self._bug_points: list[tuple[float, float]] = []
        self._bug_color: tuple[int, int, int, int] = (255, 255, 255, 255)
        self._bug_filled = True
        self._bug_width = 2.0
        self._bug_outline_color: tuple[int, int, int, int] | None = None
        self._bug_outline_width = 1.0
        self._bug_heading = 0.0
        self._bug_dr: Any | None = None
        self._bug_convert: Callable | None = None
        # Optional line from the rose centre out to the bug's own position
        # (like a radial spoke pointing at the bug), enabled by passing
        # line_color to set_heading_bug().
        self._bug_line_shown = False
        self._bug_line_color: tuple[int, int, int, int] = (255, 255, 255, 255)
        self._bug_line_width = 2.0
        self._bug_line_dash: tuple[float, float] | None = None

        # Range rings (optional; enabled by calling set_range_rings()) —
        # evenly-spaced concentric circles inside the rose, e.g. radar range
        # rings. Centred on the rose (rotation-invariant), so no heading
        # bookkeeping is needed — just a count/color/width/half.
        self._ring_count = 0
        self._ring_color: tuple[int, int, int, int] = (255, 255, 255, 255)
        self._ring_width = 1.0
        self._ring_half = "full"

        # Range-selection label (optional; enabled by calling
        # set_range_label()) — a dataref-driven text readout (e.g. the
        # cockpit's selected radar/nav range), fixed in screen space
        # relative to the rose centre — like heading_marker, it does not
        # rotate with heading.
        self._range_label_dr: Any | None = None
        self._range_label_convert: Callable | None = None
        self._range_label_table: list = []
        self._range_label_format = "{:.0f}"
        self._range_label_offset_x = 0.0
        self._range_label_offset_y = 0.0
        self._range_label_font: str | None = None
        self._range_label_font_size = 14.0
        self._range_label_bold = False
        self._range_label_italic = False
        self._range_label_color: tuple[int, int, int, int] = (255, 255, 255, 255)
        self._range_label_anchor_x = "center"
        self._range_label_anchor_y = "center"
        self._range_label_value = 0.0
        self._range_label_text_obj: arcade.Text | None = None

        # Heading marker (optional; enabled by calling set_heading_marker())
        # — a fixed lubber-line/index polygon at top-dead-centre. Unlike the
        # heading bug, it never rotates and has no dataref: the rose rotates
        # underneath it, so whatever heading is at the top is read off it.
        self._show_marker = False
        self._marker_radius = 0.0
        self._marker_points: list[tuple[float, float]] = []
        self._marker_color: tuple[int, int, int, int] = (255, 255, 255, 255)
        self._marker_filled = True
        self._marker_width = 2.0
        self._marker_outline_color: tuple[int, int, int, int] | None = None
        self._marker_outline_width = 1.0

        # Centre marker (optional; enabled by calling set_center_marker()) —
        # a fixed reference mark (e.g. an aircraft symbol) drawn directly at
        # the rose centre. Like heading_marker it never rotates and has no
        # dataref, but unlike heading_marker its points are relative to the
        # centre directly (no radius offset), and its viewport-clip behaviour
        # is independently configurable rather than always following the
        # component's own `viewport`.
        self._show_center_marker = False
        self._center_marker_points: list[tuple[float, float]] = []
        self._center_marker_color: tuple[int, int, int, int] = (255, 255, 255, 255)
        self._center_marker_filled = True
        self._center_marker_width = 2.0
        self._center_marker_outline_color: tuple[int, int, int, int] | None = None
        self._center_marker_outline_width = 1.0
        self._center_marker_clip = True

        # Bearing pointers (optional; added via add_bearing_pointer()) —
        # e.g. VOR1/VOR2/ADF1/ADF2 RMI/RBI-style needles, each independently
        # dataref-positioned and visibility-gated.
        self._bearing_pointers: list[_BearingPointer] = []

        # Course deviation indicator (optional; enabled by calling
        # set_course_deviation_indicator()) — a two-segment course line
        # (head towards the course angle, tail diametrically opposite)
        # rotating with the rose around its own centre, positioned by a
        # course dataref, each segment optionally carrying a polygon symbol
        # (e.g. an arrowhead). Deviation dots are a planned follow-up, not
        # implemented here.
        self._show_cdi = False
        self._cdi_dr: Any | None = None
        self._cdi_convert: Callable | None = None
        self._cdi_angle = 0.0
        self._cdi_head: _CdiSegment | None = None
        self._cdi_tail: _CdiSegment | None = None
        self._cdi_vis_dr: Any | None = None
        self._cdi_vis_predicate: Callable | None = None
        self._cdi_visible = True

        # Deviation bar (optional; enabled by calling set_deviation_bar()) —
        # a polygon that translates from the rose centre along the line
        # perpendicular to the CDI's own course line, by a dataref-driven px
        # amount (positive = cdi_angle + 90°, i.e. to the right of the
        # course looking outward; flip sign via convert_function if a given
        # dataref's convention runs the other way). Requires
        # course_deviation_indicator to be configured — uses its angle.
        self._deviation_bar_dr: Any | None = None
        self._deviation_bar_convert: Callable | None = None
        self._deviation_bar_table: list = []
        self._deviation_bar_scale = 1.0
        self._deviation_bar_value = 0.0
        self._deviation_bar_points: list[tuple[float, float]] = []
        self._deviation_bar_color: tuple[int, int, int, int] = (255, 255, 255, 255)
        self._deviation_bar_filled = True
        self._deviation_bar_width = 2.0
        self._deviation_bar_outline_color: tuple[int, int, int, int] | None = None
        self._deviation_bar_outline_width = 1.0

        # Deviation markers (optional; enabled by calling
        # set_deviation_markers()) — 4 fixed reference marks (2 each side),
        # unfilled circles or ticks, on the same perpendicular-to-course
        # axis as the deviation bar, at ±spacing and ±2*spacing from centre.
        # Not dataref-driven themselves — only rotate with the CDI's own
        # course angle, like everything else on this shared axis.
        self._dev_markers_shown = False
        self._dev_markers_shape = "circle"
        self._dev_markers_spacing = 40.0
        self._dev_markers_size = 4.0
        self._dev_markers_width = 2.0
        self._dev_markers_color: tuple[int, int, int, int] = (255, 255, 255, 255)

        # Moving map (optional; enabled by calling set_moving_map()) —
        # airports/VORs/NDBs positioned by their real GPS coordinates
        # relative to the aircraft's own GPS position, heading-up rotated
        # like every other element on this rose, scaled to whatever range
        # range_rings.label is currently showing (self._range_label_value).
        # Independently visibility-gated, like a bearing pointer, not tied
        # to the whole rose's own visibility.
        self._map_shown = False
        self._map_gps_lat_dr: Any | None = None
        self._map_gps_lon_dr: Any | None = None
        self._map_lat = 0.0
        self._map_lon = 0.0
        self._map_max_per_type = 60
        self._map_styles: dict[str, _MapFeatureStyle] = {}
        self._map_vis_dr: Any | None = None
        self._map_vis_predicate: Callable | None = None
        self._map_visible = True
        # Shared across every style's label_pool — pyglet's own docs warn
        # that calling Text.draw() per-label with no shared batch means
        # each one draws its own private one-label batch (measured
        # ~20.7ms/frame for 180 individually-drawn labels versus ~0.1ms/
        # frame for the same 180 labels sharing one batch, drawn via a
        # single batch.draw() call) — pooled labels not needed this frame
        # are hidden via Text.visible = False (confirmed this excludes
        # them from the batch's draw cost) rather than removed.
        self._map_label_batch = pyglet.graphics.Batch()

        self._init_visibility()

    def set_heading_dataref(self, dataref: Any, convert_fn: str | None = None) -> None:
        self._heading_dr = _as_dataref(dataref)
        if convert_fn:
            self._heading_convert = get_convert(convert_fn)

    def set_track(
        self,
        color: tuple[int, int, int, int],
        width: float,
        start: float,
        end: float,
        tick_position: float | None,
        tick_length: float,
        dataref: Any,
        convert_fn: str | None = None,
    ) -> None:
        self._show_track = True
        self._track_color = color
        self._track_width = float(width)
        self._track_start = float(start)
        self._track_end = float(end)
        self._track_tick_position = float(tick_position) if tick_position is not None else None
        self._track_tick_length = float(tick_length)
        self._track_dr = _as_dataref(dataref)
        if convert_fn:
            self._track_convert = get_convert(convert_fn)

    def set_heading_bug(
        self,
        radius: float,
        points: list[tuple[float, float]],
        color: tuple[int, int, int, int],
        filled: bool,
        width: float,
        outline_color: tuple[int, int, int, int] | None,
        outline_width: float,
        dataref: Any,
        convert_fn: str | None = None,
        line_color: tuple[int, int, int, int] | None = None,
        line_width: float = 2.0,
        line_dash: tuple[float, float] | None = None,
    ) -> None:
        self._show_bug = True
        self._bug_radius = float(radius)
        self._bug_points = [(float(x), float(y)) for x, y in points]
        self._bug_color = color
        self._bug_filled = bool(filled)
        self._bug_width = float(width)
        self._bug_outline_color = outline_color
        self._bug_outline_width = float(outline_width)
        self._bug_dr = _as_dataref(dataref)
        if convert_fn:
            self._bug_convert = get_convert(convert_fn)
        self._bug_line_shown = line_color is not None
        if line_color is not None:
            self._bug_line_color = line_color
        self._bug_line_width = float(line_width)
        self._bug_line_dash = tuple(line_dash) if line_dash else None

    def set_heading_marker(
        self,
        radius: float,
        points: list[tuple[float, float]],
        color: tuple[int, int, int, int],
        filled: bool,
        width: float,
        outline_color: tuple[int, int, int, int] | None,
        outline_width: float,
    ) -> None:
        self._show_marker = True
        self._marker_radius = float(radius)
        self._marker_points = [(float(x), float(y)) for x, y in points]
        self._marker_color = color
        self._marker_filled = bool(filled)
        self._marker_width = float(width)
        self._marker_outline_color = outline_color
        self._marker_outline_width = float(outline_width)

    def set_center_marker(
        self,
        points: list[tuple[float, float]],
        color: tuple[int, int, int, int],
        filled: bool,
        width: float,
        outline_color: tuple[int, int, int, int] | None,
        outline_width: float,
        clip: bool = True,
    ) -> None:
        self._show_center_marker = True
        self._center_marker_points = [(float(x), float(y)) for x, y in points]
        self._center_marker_color = color
        self._center_marker_filled = bool(filled)
        self._center_marker_width = float(width)
        self._center_marker_outline_color = outline_color
        self._center_marker_outline_width = float(outline_width)
        self._center_marker_clip = bool(clip)

    def add_bearing_pointer(
        self,
        name: str,
        dataref: Any,
        convert_fn: str | None,
        offset: float,
        points: list[tuple[float, float]],
        color: tuple[int, int, int, int],
        filled: bool,
        width: float,
        outline_color: tuple[int, int, int, int] | None,
        outline_width: float,
        vis_dataref: Any | None = None,
        vis_predicate: str | None = None,
        tail_offset: float = 0.0,
        tail_points: list[tuple[float, float]] | None = None,
        tail_color: tuple[int, int, int, int] = (255, 255, 255, 255),
        tail_filled: bool = True,
        tail_width: float = 2.0,
        tail_outline_color: tuple[int, int, int, int] | None = None,
        tail_outline_width: float = 1.0,
    ) -> None:
        self._bearing_pointers.append(_BearingPointer(
            name=name,
            dataref=_as_dataref(dataref),
            convert_fn=get_convert(convert_fn) if convert_fn else None,
            offset=offset,
            points=points,
            color=color,
            filled=filled,
            width=width,
            outline_color=outline_color,
            outline_width=outline_width,
            vis_dataref=_as_dataref(vis_dataref) if vis_dataref is not None else None,
            vis_predicate=get_convert(vis_predicate) if vis_predicate else None,
            tail_offset=tail_offset,
            tail_points=tail_points,
            tail_color=tail_color,
            tail_filled=tail_filled,
            tail_width=tail_width,
            tail_outline_color=tail_outline_color,
            tail_outline_width=tail_outline_width,
        ))

    def set_course_deviation_indicator(
        self,
        dataref: Any,
        convert_fn: str | None,
        head: _CdiSegment,
        tail: _CdiSegment,
        vis_dataref: Any | None = None,
        vis_predicate: str | None = None,
    ) -> None:
        self._show_cdi = True
        self._cdi_dr = _as_dataref(dataref)
        if convert_fn:
            self._cdi_convert = get_convert(convert_fn)
        self._cdi_head = head
        self._cdi_tail = tail
        self._cdi_vis_dr = _as_dataref(vis_dataref) if vis_dataref is not None else None
        self._cdi_vis_predicate = get_convert(vis_predicate) if vis_predicate else None

    def set_deviation_bar(
        self,
        dataref: Any,
        convert_fn: str | None,
        points: list[tuple[float, float]],
        color: tuple[int, int, int, int],
        filled: bool,
        width: float,
        outline_color: tuple[int, int, int, int] | None,
        outline_width: float,
        table: list | None = None,
    ) -> None:
        self._deviation_bar_dr = _as_dataref(dataref)
        if convert_fn:
            self._deviation_bar_convert = get_convert(convert_fn)
        self._deviation_bar_table = table or []
        self._deviation_bar_points = [(float(x), float(y)) for x, y in points]
        self._deviation_bar_color = color
        self._deviation_bar_filled = bool(filled)
        self._deviation_bar_width = float(width)
        self._deviation_bar_outline_color = outline_color
        self._deviation_bar_outline_width = float(outline_width)

    def set_deviation_markers(
        self,
        shape: str,
        spacing: float,
        size: float,
        width: float,
        color: tuple[int, int, int, int],
    ) -> None:
        self._dev_markers_shown = True
        self._dev_markers_shape = shape if shape in ("circle", "tick") else "circle"
        self._dev_markers_spacing = float(spacing)
        self._dev_markers_size = float(size)
        self._dev_markers_width = float(width)
        self._dev_markers_color = color

    def set_moving_map(
        self,
        gps_lat_dataref: Any,
        gps_lon_dataref: Any,
        max_per_type: int,
        styles: dict[str, _MapFeatureStyle],
        vis_dataref: Any | None = None,
        vis_predicate: str | None = None,
    ) -> None:
        self._map_shown = True
        self._map_gps_lat_dr = _as_dataref(gps_lat_dataref)
        self._map_gps_lon_dr = _as_dataref(gps_lon_dataref)
        self._map_max_per_type = max(1, int(max_per_type))
        self._map_styles = styles
        self._map_vis_dr = _as_dataref(vis_dataref) if vis_dataref is not None else None
        self._map_vis_predicate = get_convert(vis_predicate) if vis_predicate else None

    def set_range_rings(
        self,
        count: int,
        color: tuple[int, int, int, int],
        width: float,
        half: str = "full",
    ) -> None:
        self._ring_count = max(1, min(10, int(count)))
        self._ring_color = color
        self._ring_width = float(width)
        self._ring_half = half if half in ("top", "bottom") else "full"

    def set_range_label(
        self,
        dataref: Any,
        convert_fn: str | None,
        format_str: str,
        offset: tuple[float, float],
        font: str | None,
        font_size: float,
        bold: bool,
        italic: bool,
        color: tuple[int, int, int, int],
        table: list | None = None,
        anchor_x: str = "center",
        anchor_y: str = "center",
    ) -> None:
        self._range_label_dr = _as_dataref(dataref)
        if convert_fn:
            self._range_label_convert = get_convert(convert_fn)
        self._range_label_table = table or []
        self._range_label_format = format_str
        self._range_label_offset_x, self._range_label_offset_y = float(offset[0]), float(offset[1])
        self._range_label_font = font
        self._range_label_font_size = float(font_size)
        self._range_label_bold = bool(bold)
        self._range_label_italic = bool(italic)
        self._range_label_color = color
        self._range_label_anchor_x = anchor_x
        self._range_label_anchor_y = anchor_y
        self._range_label_text_obj = None  # style changed; pool object is stale

    def apply_scale(self, scale: float) -> None:
        self._cx *= scale; self._cy *= scale
        self._radius *= scale
        self._line_width *= scale
        self._tick5_length *= scale
        self._tick5_width *= scale
        self._tick10_length *= scale
        self._tick10_width *= scale
        self._label_offset *= scale
        self._label_font_size *= scale
        self._label_emphasize_font_size *= scale
        self._label_pool.clear()  # font size changed; pool objects are stale
        # Static geometry caches are all built lazily on first draw, which
        # always happens after every apply_scale() call in the normal
        # load path — but if that ever changes, stale pre-scale geometry
        # must not survive, same principle as _label_pool.clear() above.
        self._bg_shape = None
        self._ring_sprites = None
        self._tick_sprites = None
        self._ring_width *= scale
        self._range_label_offset_x *= scale; self._range_label_offset_y *= scale
        self._range_label_font_size *= scale
        self._range_label_text_obj = None  # font size changed; pool object is stale
        self._track_width *= scale
        self._track_start *= scale
        self._track_end *= scale
        if self._track_tick_position is not None:
            self._track_tick_position *= scale
        self._track_tick_length *= scale
        self._bug_radius *= scale
        self._bug_points = [(x * scale, y * scale) for x, y in self._bug_points]
        self._bug_width *= scale
        self._bug_outline_width *= scale
        self._bug_line_width *= scale
        if self._bug_line_dash is not None:
            self._bug_line_dash = (self._bug_line_dash[0] * scale, self._bug_line_dash[1] * scale)
        self._marker_radius *= scale
        self._marker_points = [(x * scale, y * scale) for x, y in self._marker_points]
        self._marker_width *= scale
        self._marker_outline_width *= scale
        self._center_marker_points = [(x * scale, y * scale) for x, y in self._center_marker_points]
        self._center_marker_width *= scale
        self._center_marker_outline_width *= scale
        for p in self._bearing_pointers:
            p.offset *= scale
            p.points = [(x * scale, y * scale) for x, y in p.points]
            p.width *= scale
            p.outline_width *= scale
            p.tail_offset *= scale
            p.tail_points = [(x * scale, y * scale) for x, y in p.tail_points]
            p.tail_width *= scale
            p.tail_outline_width *= scale
        for seg in (self._cdi_head, self._cdi_tail):
            if seg is None:
                continue
            seg.start *= scale; seg.end *= scale
            seg.width *= scale
            if seg.dash is not None:
                seg.dash = (seg.dash[0] * scale, seg.dash[1] * scale)
            seg.symbol_offset *= scale
            seg.symbol_points = [(x * scale, y * scale) for x, y in seg.symbol_points]
            seg.symbol_width *= scale
            seg.symbol_outline_width *= scale
        self._deviation_bar_scale *= scale
        self._deviation_bar_points = [(x * scale, y * scale) for x, y in self._deviation_bar_points]
        self._deviation_bar_width *= scale
        self._deviation_bar_outline_width *= scale
        self._dev_markers_spacing *= scale
        self._dev_markers_size *= scale
        self._dev_markers_width *= scale
        for style in self._map_styles.values():
            style.points = [(x * scale, y * scale) for x, y in style.points]
            style.outline_width *= scale
            style.label_font_size *= scale
            style.label_offset_x *= scale; style.label_offset_y *= scale
            style.circle_radius *= scale
            style.circle_outline_width *= scale
            style.active_width *= scale
            style.label_pool.clear()  # font size changed; pool objects are stale
        if self._viewport is not None:
            vx, vy, vw, vh = self._viewport
            self._viewport = (vx * scale, vy * scale, vw * scale, vh * scale)

    def apply_offset(self, dx: float, dy: float) -> None:
        self._cx += dx; self._cy += dy
        if self._viewport is not None:
            vx, vy, vw, vh = self._viewport
            self._viewport = (vx + dx, vy + dy, vw, vh)

    def update(self, get_data: Callable[[Any], float]) -> None:
        self._update_visibility(get_data)
        if self._track_dr is not None:
            raw = float(get_data(self._track_dr))
            if self._track_convert is not None:
                raw = float(self._track_convert(raw, get_data))
            self._track_angle = raw % 360.0
        if self._bug_dr is not None:
            raw = float(get_data(self._bug_dr))
            if self._bug_convert is not None:
                raw = float(self._bug_convert(raw, get_data))
            self._bug_heading = raw % 360.0
        if self._heading_dr is not None:
            raw = float(get_data(self._heading_dr))
            if self._heading_convert is not None:
                raw = float(self._heading_convert(raw, get_data))
            self._heading = raw % 360.0
        if self._range_label_dr is not None:
            raw = float(get_data(self._range_label_dr))
            if self._range_label_convert is not None:
                raw = float(self._range_label_convert(raw, get_data))
            self._range_label_value = (
                lookup_piecewise(self._range_label_table, raw)
                if self._range_label_table else raw
            )
        for p in self._bearing_pointers:
            raw = float(get_data(p.dataref))
            if p.convert_fn is not None:
                raw = float(p.convert_fn(raw, get_data))
            p.angle = raw % 360.0
            if p.vis_dataref is not None and p.vis_predicate is not None:
                p.visible = bool(p.vis_predicate(float(get_data(p.vis_dataref)), get_data))
        if self._cdi_dr is not None:
            raw = float(get_data(self._cdi_dr))
            if self._cdi_convert is not None:
                raw = float(self._cdi_convert(raw, get_data))
            self._cdi_angle = raw % 360.0
            if self._cdi_vis_dr is not None and self._cdi_vis_predicate is not None:
                self._cdi_visible = bool(self._cdi_vis_predicate(float(get_data(self._cdi_vis_dr)), get_data))
        if self._deviation_bar_dr is not None:
            raw = float(get_data(self._deviation_bar_dr))
            if self._deviation_bar_convert is not None:
                raw = float(self._deviation_bar_convert(raw, get_data))
            if self._deviation_bar_table:
                raw = lookup_piecewise(self._deviation_bar_table, raw)
            self._deviation_bar_value = raw * self._deviation_bar_scale
        if self._map_gps_lat_dr is not None:
            self._map_lat = float(get_data(self._map_gps_lat_dr))
            self._map_lon = float(get_data(self._map_gps_lon_dr))
            if self._map_vis_dr is not None and self._map_vis_predicate is not None:
                self._map_visible = bool(self._map_vis_predicate(float(get_data(self._map_vis_dr)), get_data))
            for style in self._map_styles.values():
                if style.vis_dataref is not None and style.vis_predicate is not None:
                    style.visible = bool(style.vis_predicate(float(get_data(style.vis_dataref)), get_data))
                if style.active_ident_datarefs:
                    chars = []
                    for dr in style.active_ident_datarefs:
                        code = int(get_data(dr))
                        if code <= 0:
                            break  # null terminator / unfilled padding — stop, like a C string
                        chars.append(chr(code))
                    style.active_ident = "".join(chars)
                if style.active_course_dataref is not None:
                    raw = float(get_data(style.active_course_dataref))
                    if style.active_course_convert is not None:
                        raw = float(style.active_course_convert(raw, get_data))
                    style.active_course = raw % 360.0

    def _point_at(self, heading_deg: float, r: float) -> tuple[float, float]:
        angle = math.radians(90.0 - heading_deg + self._heading)
        return (
            self._cx + r * math.cos(angle),
            self._cy + r * math.sin(angle),
        )

    def draw(self) -> None:
        if not self._visible:
            return

        if self._viewport is not None:
            win = arcade.get_window()
            ctx = win.ctx
            vx, vy, vw, vh = self._viewport
            # Scale panel-space viewport to framebuffer pixels — see VectorTape's
            # draw() for why (SSAA renders into a larger-than-logical-panel FBO).
            _, _, fvp_w, fvp_h = ctx.viewport
            panel_w, panel_h = getattr(win, "_panel_size", (win.width, win.height))
            sx = fvp_w / panel_w
            sy = fvp_h / panel_h
            ctx.scissor = (int(vx * sx), int(vy * sy), int(vw * sx), int(vh * sy))

        self._draw_all()

        if self._viewport is not None:
            ctx.scissor = None

        # Drawn last, outside the scissor block, only when the marker has
        # opted out of clipping — the clipped case is handled inside
        # _draw_all() instead, so it still respects draw order relative to
        # the other rose elements.
        if self._show_center_marker and not self._center_marker_clip:
            self._draw_center_marker()

    def _build_bg_shape(self) -> None:
        shapes = arcade.shape_list.ShapeElementList()
        shapes.append(arcade.shape_list.create_ellipse_filled(
            self._cx, self._cy, self._radius * 2.0, self._radius * 2.0,
            self._background_color, num_segments=self._segments,
        ))
        self._bg_shape = shapes

    def _build_ring_sprites(self, oversample: int = 4) -> None:
        # Baked once to a PIL texture and drawn as a single static Sprite
        # (position (cx, cy), angle 0 — the outline circle/rings never
        # rotate) rather than via ShapeElementList's create_line-family
        # calls, which were confirmed (by direct pixel-read testing,
        # including through the real PanelWindow pipeline) to render
        # nothing or land at the wrong screen position in this Arcade
        # version. Points are generated with the same _arc_points() used
        # everywhere else in this file for consistency, then converted to
        # PIL's y-down pixel space the same way _bake_map_icon() already
        # does for moving_map icons.
        #
        # Baked at `oversample`x resolution then displayed at Sprite scale
        # 1/oversample (same technique _bake_map_icon() already uses) —
        # PIL's own line/arc drawing has no antialiasing at all, so baking
        # at native 1:1 resolution (the first version of this fix) produced
        # visibly jagged rings/ticks despite the runtime's own SSAA chain,
        # since supersampling only smooths detail that was actually present
        # in the source at a finer resolution than the final downsample.
        from PIL import Image, ImageDraw

        pad = max(
            self._line_width if self._show_line else 0.0,
            self._ring_width if self._ring_count else 0.0,
            1.0,
        ) + 2.0
        half = self._radius + pad
        size_px = max(2, int(round(half * 2.0)))
        max_tex = arcade.get_window().ctx.info.MAX_TEXTURE_SIZE
        while oversample >= 2 and size_px * oversample > max_tex:
            oversample //= 2
        os_px = size_px * oversample
        img = Image.new("RGBA", (os_px, os_px), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        cx_px = cy_px = os_px / 2.0

        def polyline(points: list[tuple[float, float]], color, width: float) -> None:
            pts_px = [(cx_px + x * oversample, cy_px - y * oversample) for x, y in points]
            draw.line(pts_px, fill=color, width=max(1, int(round(width * oversample))))

        if self._show_line:
            polyline(
                _arc_points(0.0, 0.0, self._radius, 0.0, 360.0, self._segments),
                self._line_color, self._line_width,
            )
        if self._ring_count:
            spacing = self._radius / self._ring_count
            for k in range(1, self._ring_count + 1):
                r = k * spacing
                if self._ring_half == "top":
                    polyline(
                        _arc_points(0.0, 0.0, r, 0.0, 180.0, self._segments),
                        self._ring_color, self._ring_width,
                    )
                elif self._ring_half == "bottom":
                    polyline(
                        _arc_points(0.0, 0.0, r, 180.0, 360.0, self._segments),
                        self._ring_color, self._ring_width,
                    )
                else:
                    polyline(
                        _arc_points(0.0, 0.0, r, 0.0, 360.0, self._segments),
                        self._ring_color, self._ring_width,
                    )

        tex = arcade.Texture(img, hash=f"rose_ring:{id(self)}")
        self._ring_sprites = arcade.SpriteList()
        self._ring_sprites.append(arcade.Sprite(tex, scale=1.0 / oversample))

    def _build_tick_sprites(self) -> None:
        # Baked once to a PIL texture (local, heading=0 reference) and
        # rotated via Sprite.angle each frame instead of recomputing 72
        # line endpoints in Python and issuing 72 individual draw_line()
        # calls (measured ~6ms/frame on their own) — same reasoning as
        # _build_ring_sprites() for why this is a Sprite, not a
        # ShapeElementList of create_line() shapes.
        #
        # angle = self._heading directly at draw time, and the bake below
        # uses NO y-negation when converting to PIL pixel space. An earlier
        # version used y-negation (matching _bake_map_icon(), which never
        # rotates) plus angle = heading + 180, calibrated only against a
        # single test point sitting exactly on the local Y-axis (h=0) — a
        # blind spot, since a point with local x=0 is invariant under an
        # x-axis mirror and can't reveal one. That combination is actually
        # a *reflection* composed with a rotation, not a pure rotation (the
        # same root cause AttitudeIndicator's pitch-ladder sprite needed
        # "no y-negation" for) — it happened to reproduce _point_at()'s
        # position correctly at that one axis point, but mirrored every
        # other tick left-right, making the whole rose appear to rotate in
        # the opposite direction as heading changed. Re-derived and
        # verified against 5 different h values (0/45/90/135/225) at 3
        # headings each (15 combinations, all exact) this time.
        #
        # Baked at `oversample`x resolution then displayed at Sprite scale
        # 1/oversample — see _build_ring_sprites()'s own comment for why
        # (PIL's line drawing has no antialiasing at all, so a native-
        # resolution bake looked visibly jagged despite the runtime's own
        # SSAA chain).
        from PIL import Image, ImageDraw

        oversample = 4
        max_len = max(self._tick5_length, self._tick10_length)
        half = self._radius + max_len + 2.0
        size_px = max(2, int(round(half * 2.0)))
        max_tex = arcade.get_window().ctx.info.MAX_TEXTURE_SIZE
        while oversample >= 2 and size_px * oversample > max_tex:
            oversample //= 2
        os_px = size_px * oversample
        img = Image.new("RGBA", (os_px, os_px), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        cx_px = cy_px = os_px / 2.0

        for h in range(0, 360, 5):
            is_major = (h % 10) == 0
            length   = self._tick10_length if is_major else self._tick5_length
            position = self._tick10_position if is_major else self._tick5_position
            color    = self._tick10_color if is_major else self._tick5_color
            width    = self._tick10_width if is_major else self._tick5_width
            r0, r1 = (
                (self._radius - length, self._radius) if position == "inside"
                else (self._radius, self._radius + length)
            )
            local_angle = math.radians(90.0 - h)
            x0, y0 = r0 * math.cos(local_angle), r0 * math.sin(local_angle)
            x1, y1 = r1 * math.cos(local_angle), r1 * math.sin(local_angle)
            p0 = (cx_px + x0 * oversample, cy_px + y0 * oversample)
            p1 = (cx_px + x1 * oversample, cy_px + y1 * oversample)
            draw.line([p0, p1], fill=color, width=max(1, int(round(width * oversample))))

        tex = arcade.Texture(img, hash=f"rose_ticks:{id(self)}")
        self._tick_sprites = arcade.SpriteList()
        self._tick_sprites.append(arcade.Sprite(tex, scale=1.0 / oversample))

    def _draw_all(self) -> None:
        if self._background_color is not None:
            if self._bg_shape is None:
                self._build_bg_shape()
            self._bg_shape.draw()

        if self._map_shown and self._map_visible:
            self._draw_moving_map()

        if self._show_line or self._ring_count:
            if self._ring_sprites is None:
                self._build_ring_sprites()
            self._ring_sprites[0].position = (self._cx, self._cy)
            self._ring_sprites.draw()

        if self._tick_sprites is None:
            self._build_tick_sprites()
        tick_sprite = self._tick_sprites[0]
        tick_sprite.position = (self._cx, self._cy)
        tick_sprite.angle = self._heading
        self._tick_sprites.draw()

        r_label = (
            self._radius - self._label_offset if self._label_position == "inside"
            else self._radius + self._label_offset
        )
        idx = 0
        for h in range(0, 360, self._label_interval):
            x, y = self._point_at(h, r_label)
            if idx >= len(self._label_pool):
                kw: dict = dict(bold=self._label_bold, italic=self._label_italic)
                if self._label_font:
                    kw["font_name"] = self._label_font
                # A given pool slot always represents the same heading
                # value (h doesn't change frame to frame, only self._heading
                # does), so text/font_size are correct forever once set
                # here — measured reassigning them every frame anyway (the
                # previous code did) cost ~8ms of this method's ~17.7ms
                # heading-label total for only 36 labels; only updating
                # x/y/rotation below costs ~0.09ms for the same 36.
                text_val = self._label_format.format(h / 10.0)
                font_size_val = (
                    self._label_emphasize_font_size
                    if self._label_emphasize_interval and h % self._label_emphasize_interval == 0
                    else self._label_font_size
                )
                self._label_pool.append(arcade.Text(
                    text_val, 0, 0,
                    color=self._label_color,
                    font_size=font_size_val,
                    anchor_x="center",
                    anchor_y=self._label_anchor_y,
                    batch=self._heading_label_batch,
                    **kw,
                ))
            t = self._label_pool[idx]
            t.x, t.y = x, y
            # Radial orientation: baseline tangent to the circle (perpendicular
            # to the radius), with "up" pointing outward along the radius.
            # point_at()'s angle is (90 - h + heading); subtracting the 90
            # unrotated "up" gives the rotation needed to reach it. Negated
            # relative to that derivation: arcade.Text's rendered rotation
            # comes out mirrored versus a plain geometric CCW rotation once
            # it's drawn through the runtime's render pipeline (confirmed by
            # comparing against the designer's PIL preview, which needed no
            # such flip), so the sign is reversed here to compensate.
            t.rotation = h - self._heading
            idx += 1
        self._heading_label_batch.draw()

        if self._show_track:
            self._draw_track()

        if self._show_bug:
            self._draw_heading_bug()

        if self._show_marker:
            self._draw_heading_marker()

        if self._range_label_dr is not None:
            self._draw_range_label()

        if self._show_center_marker and self._center_marker_clip:
            self._draw_center_marker()

        for p in self._bearing_pointers:
            if p.visible:
                self._draw_bearing_pointer(p)

        if self._show_cdi and self._cdi_visible:
            self._draw_cdi()
            if self._deviation_bar_dr is not None:
                self._draw_deviation_bar()
            if self._dev_markers_shown:
                self._draw_deviation_markers()

    def _draw_range_label(self) -> None:
        # Fixed relative to the rose centre — like heading_marker, does not
        # rotate with heading.
        if self._range_label_text_obj is None:
            kw: dict = dict(bold=self._range_label_bold, italic=self._range_label_italic)
            if self._range_label_font:
                kw["font_name"] = self._range_label_font
            self._range_label_text_obj = arcade.Text(
                "", 0, 0,
                color=self._range_label_color,
                font_size=self._range_label_font_size,
                anchor_x=self._range_label_anchor_x,
                anchor_y=self._range_label_anchor_y,
                **kw,
            )
        t = self._range_label_text_obj
        t.text = self._range_label_format.format(self._range_label_value)
        t.anchor_x = self._range_label_anchor_x
        t.anchor_y = self._range_label_anchor_y
        t.x = self._cx + self._range_label_offset_x
        t.y = self._cy + self._range_label_offset_y
        t.draw()

    def _draw_heading_marker(self) -> None:
        # Fixed top-dead-centre, straight up from the rose centre — no
        # rotation, since this marker doesn't move; the rose rotates under it.
        cx, cy = self._cx, self._cy + self._marker_radius
        pts = [(cx + px, cy + py) for px, py in self._marker_points]
        if self._marker_filled:
            arcade.draw_polygon_filled(pts, self._marker_color)
            if self._marker_outline_color is not None:
                arcade.draw_polygon_outline(pts, self._marker_outline_color, self._marker_outline_width)
        else:
            arcade.draw_polygon_outline(pts, self._marker_color, self._marker_width)

    def _draw_center_marker(self) -> None:
        # Fixed directly at the rose centre — no radius offset, no rotation.
        pts = [(self._cx + px, self._cy + py) for px, py in self._center_marker_points]
        if self._center_marker_filled:
            arcade.draw_polygon_filled(pts, self._center_marker_color)
            if self._center_marker_outline_color is not None:
                arcade.draw_polygon_outline(pts, self._center_marker_outline_color, self._center_marker_outline_width)
        else:
            arcade.draw_polygon_outline(pts, self._center_marker_color, self._center_marker_width)

    def _draw_bearing_pointer(self, p: _BearingPointer) -> None:
        # Same positioning model as heading_bug: a polygon on the rose's own
        # circle (radius + offset), rotating with the rose, oriented by its
        # own bearing dataref rather than the rose's heading.
        self._draw_pointer_shape(
            p.angle, self._radius + p.offset, p.points, p.color, p.filled, p.width,
            p.outline_color, p.outline_width,
        )
        if p.tail_points:
            # Diametrically opposite the head — same dataref/visibility,
            # own shape/offset/styling, like an RMI needle's tail.
            self._draw_pointer_shape(
                p.angle + 180.0, self._radius + p.tail_offset, p.tail_points, p.tail_color,
                p.tail_filled, p.tail_width, p.tail_outline_color, p.tail_outline_width,
            )

    def _draw_pointer_shape(
        self,
        bearing_deg: float,
        radius: float,
        points: list[tuple[float, float]],
        color: tuple[int, int, int, int],
        filled: bool,
        width: float,
        outline_color: tuple[int, int, int, int] | None,
        outline_width: float,
    ) -> None:
        cx, cy = self._point_at(bearing_deg, radius)
        angle = math.radians(self._heading - bearing_deg)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        pts = [
            (cx + px * cos_a - py * sin_a, cy + px * sin_a + py * cos_a)
            for px, py in points
        ]
        if filled:
            arcade.draw_polygon_filled(pts, color)
            if outline_color is not None:
                arcade.draw_polygon_outline(pts, outline_color, outline_width)
        else:
            arcade.draw_polygon_outline(pts, color, width)

    def _draw_heading_bug(self) -> None:
        cx, cy = self._point_at(self._bug_heading, self._bug_radius)
        if self._bug_line_shown:
            # Drawn first, underneath the bug symbol — a radial spoke from
            # the rose centre out to the bug's own position.
            self._draw_dashed_line(
                self._cx, self._cy, cx, cy,
                self._bug_line_color, self._bug_line_width, self._bug_line_dash,
            )
        # Radial orientation, like the ticks: point_at()'s outward direction
        # at this heading is (90 - bug_heading + heading) degrees from +x:
        # rotating the bug's local +y (its unrotated "outward") to line up
        # with that direction takes (90 - bug_heading + heading) - 90, i.e.
        # (heading - bug_heading). Manual point rotation (not arcade.Text),
        # so this uses the plain geometric angle directly — the sign flip
        # needed for label rotation is a quirk of arcade.Text specifically
        # (see the label loop above), not of raw draw_polygon coordinates.
        angle = math.radians(self._heading - self._bug_heading)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        pts = [
            (cx + px * cos_a - py * sin_a, cy + px * sin_a + py * cos_a)
            for px, py in self._bug_points
        ]
        if self._bug_filled:
            arcade.draw_polygon_filled(pts, self._bug_color)
            if self._bug_outline_color is not None:
                arcade.draw_polygon_outline(pts, self._bug_outline_color, self._bug_outline_width)
        else:
            arcade.draw_polygon_outline(pts, self._bug_color, self._bug_width)

    def _draw_track(self) -> None:
        x0, y0 = self._point_at(self._track_angle, self._track_start)
        x1, y1 = self._point_at(self._track_angle, self._track_end)
        arcade.draw_line(x0, y0, x1, y1, self._track_color, self._track_width)
        if self._track_tick_position is not None:
            tx, ty = self._point_at(self._track_angle, self._track_tick_position)
            line_angle = math.radians(90.0 - self._track_angle + self._heading)
            perp = line_angle + math.pi / 2.0
            half = self._track_tick_length / 2.0
            dx, dy = half * math.cos(perp), half * math.sin(perp)
            arcade.draw_line(tx - dx, ty - dy, tx + dx, ty + dy,
                             self._track_color, self._track_width)

    def _draw_cdi(self) -> None:
        # Two independent line segments from the rose centre, head towards
        # the course angle and tail diametrically opposite — same
        # positioning model as track (point_at() handles the rose's own
        # rotation plus this angle), each with its own start/end/style,
        # optional dashing, and optional polygon symbol.
        if self._cdi_head is not None:
            self._draw_cdi_segment(self._cdi_head, self._cdi_angle)
        if self._cdi_tail is not None:
            self._draw_cdi_segment(self._cdi_tail, self._cdi_angle + 180.0)

    def _draw_cdi_segment(self, seg: _CdiSegment, bearing_deg: float) -> None:
        x0, y0 = self._point_at(bearing_deg, seg.start)
        x1, y1 = self._point_at(bearing_deg, seg.end)
        self._draw_dashed_line(x0, y0, x1, y1, seg.color, seg.width, seg.dash)
        if seg.symbol_points:
            # symbol_offset is px from the rose centre (same units as
            # start/end), unlike bearing_pointers' offset-from-circle, so no
            # `self._radius +` here — reuses _draw_pointer_shape as-is since
            # that method just takes a plain radius from the rose centre.
            self._draw_pointer_shape(
                bearing_deg, seg.symbol_offset, seg.symbol_points, seg.symbol_color,
                seg.symbol_filled, seg.symbol_width, seg.symbol_outline_color,
                seg.symbol_outline_width,
            )

    def _draw_deviation_bar(self) -> None:
        # Translates from the rose centre along the perpendicular to the CDI
        # course line (cdi_angle + 90°) by a dataref-driven px amount, but
        # its own polygon points are oriented ALONG the course line
        # (cdi_angle), like a symbol — so, unlike _draw_pointer_shape, the
        # position angle and rotation angle are different and computed
        # separately here rather than reusing that method.
        cx, cy = self._point_at(self._cdi_angle + 90.0, self._deviation_bar_value)
        angle = math.radians(self._heading - self._cdi_angle)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        pts = [
            (cx + px * cos_a - py * sin_a, cy + px * sin_a + py * cos_a)
            for px, py in self._deviation_bar_points
        ]
        if self._deviation_bar_filled:
            arcade.draw_polygon_filled(pts, self._deviation_bar_color)
            if self._deviation_bar_outline_color is not None:
                arcade.draw_polygon_outline(pts, self._deviation_bar_outline_color, self._deviation_bar_outline_width)
        else:
            arcade.draw_polygon_outline(pts, self._deviation_bar_color, self._deviation_bar_width)

    def _draw_moving_map(self) -> None:
        # Scaled to whatever range range_rings.label is currently showing —
        # but the rose's outer edge represents *double* that value, matching
        # the real EFIS convention (the displayed range is the half-range
        # ring; the rose extends out to twice it), confirmed against the
        # real Zibo ND. px_per_nm = radius / (2 * range), so a feature at
        # twice the configured range lands exactly on the rose's own
        # radius, no separate circle-clip needed. No range configured (0,
        # the unset-table-lookup default) means no defined scale, so draw
        # nothing rather than divide by zero.
        if self._range_label_value <= 0:
            return
        index = navdata.get_index()
        if index is None:
            return
        range_nm = self._range_label_value * 2.0
        px_per_nm = self._radius / range_nm

        by_type: dict[str, list[tuple[float, float, dict]]] = {}
        for entry in index.nearby(self._map_lat, self._map_lon, range_nm):
            style = self._map_styles.get(entry["type"])
            if style is None or not style.visible:
                continue
            if (
                entry["type"] == "airport" and style.icao_only
                and not navdata.looks_like_icao_ident(entry.get("ident", ""))
            ):
                continue
            bearing_deg, distance_nm = geo.bearing_distance_nm(
                self._map_lat, self._map_lon, entry["lat"], entry["lon"],
            )
            if distance_nm > range_nm:
                continue
            by_type.setdefault(entry["type"], []).append((distance_nm, bearing_deg, entry))

        # Icons are pre-baked once per style (_bake_map_icon, on first use)
        # into a normal-colors texture and a white-silhouette texture, then
        # drawn via a pooled SpriteList — Arcade only needs to update each
        # instance's small transform (position, and texture/color for the
        # single "active" entry, if any) rather than regenerating full
        # polygon/circle vertex geometry and re-uploading a VBO for every
        # visible feature every frame. Measured ~9ms/frame at 180 features
        # for the old per-frame ShapeElementList rebuild versus a handful
        # of cheap position writes here. Labels share one pyglet Batch
        # (self._map_label_batch, see its own comment) rather than each
        # calling Text.draw() individually, for the same reason.
        active_lines_to_draw: list[tuple] = []

        for type_name, style in self._map_styles.items():
            items = by_type.get(type_name, [])
            items.sort(key=lambda t: t[0])
            visible_items = items[: self._map_max_per_type]

            if style.icon_texture is None and (style.points or style.circle_radius > 0.0):
                _bake_map_icon(style)
            if style.icon_texture is not None:
                if style.icon_sprites is None:
                    style.icon_sprites = arcade.SpriteList()
                while len(style.icon_sprites) < len(visible_items):
                    sp = arcade.Sprite(style.icon_texture, scale=style.icon_scale)
                    style.icon_sprites.append(sp)
                for i in range(len(visible_items), len(style.icon_sprites)):
                    style.icon_sprites[i].visible = False

            label_idx = 0
            for i, (distance_nm, bearing_deg, entry) in enumerate(visible_items):
                cx, cy = self._point_at(bearing_deg, distance_nm * px_per_nm)

                # The "active" candidate (e.g. the tuned VOR) recolors
                # every color slot on this one entry — same icon shape,
                # just highlighted via the white-silhouette texture tinted
                # to active_color — and gets a dashed course-line radial
                # from its own position out to the rose's edge.
                is_active = bool(style.active_ident) and entry.get("ident", "") == style.active_ident

                if style.icon_texture is not None:
                    sp = style.icon_sprites[i]
                    sp.visible = True
                    # Symbols stay screen-fixed (not rotated with heading
                    # or bearing) — a map icon's "up" is always the
                    # window's own +Y direction, like north-up on a paper
                    # chart, not the heading-up convention the rest of
                    # this rose uses, so no angle to set here.
                    sp.position = (cx, cy)
                    if is_active:
                        sp.texture = style.icon_texture_active
                        sp.color = style.active_color[:3]
                        sp.alpha = style.active_color[3]
                    else:
                        sp.texture = style.icon_texture
                        sp.color = (255, 255, 255)
                        sp.alpha = 255

                if is_active and style.active_course_dataref is not None:
                    # A full radial through the VOR — both the course
                    # direction and its reciprocal — not just a one-way ray
                    # toward the rose's edge, so both the TO and FROM sides
                    # of the course are visible.
                    angle = math.radians(90.0 - style.active_course + self._heading)
                    dx, dy = math.cos(angle), math.sin(angle)
                    ex1, ey1 = _ray_circle_exit(cx, cy, dx, dy, self._cx, self._cy, self._radius)
                    ex2, ey2 = _ray_circle_exit(cx, cy, -dx, -dy, self._cx, self._cy, self._radius)
                    active_lines_to_draw.append(
                        (ex1, ey1, ex2, ey2, style.active_color, style.active_width, style.active_dash)
                    )

                if style.label:
                    if label_idx >= len(style.label_pool):
                        kw: dict = dict(bold=style.label_bold, italic=style.label_italic)
                        if style.label_font:
                            kw["font_name"] = style.label_font
                        style.label_pool.append(arcade.Text(
                            "", 0, 0,
                            color=style.label_color,
                            font_size=style.label_font_size,
                            anchor_x="left", anchor_y="center",
                            batch=self._map_label_batch,
                            **kw,
                        ))
                    t = style.label_pool[label_idx]
                    t.visible = True
                    t.text = str(entry.get("ident", ""))
                    # color/font_size are constant per-style (already set at
                    # construction above) — deliberately NOT reassigned here
                    # every frame: pyglet's text layout re-triggers a full
                    # document relayout on every property write regardless
                    # of whether the value actually changed, and profiling
                    # showed font_size alone accounting for roughly half of
                    # this method's total cost when reassigned needlessly.
                    t.x, t.y = cx + style.label_offset_x, cy + style.label_offset_y
                    label_idx += 1

            # Pooled labels beyond this frame's count stay in the batch
            # (removing/recreating them would defeat the point of pooling)
            # but must be hidden — Text.visible = False confirmed to
            # exclude a label from the batch's draw cost, unlike the old
            # per-label draw() calls where simply not calling draw() was
            # enough.
            for i in range(label_idx, len(style.label_pool)):
                style.label_pool[i].visible = False

            if style.icon_sprites is not None:
                style.icon_sprites.draw()

        # The active-VOR course line is a dashed line (immediate-mode, like
        # the CDI's own dashed segments) — at most one per feature type, so
        # batching it into a SpriteList isn't worth the complexity.
        for x0, y0, x1, y1, line_color, line_width, dash in active_lines_to_draw:
            self._draw_dashed_line(x0, y0, x1, y1, line_color, line_width, dash)
        # All styles' labels share one batch, drawn once here (after every
        # style's icons above) rather than interleaved per-feature — a
        # label always sits offset to the right of its own symbol rather
        # than overlapping it, so drawing all labels on top of all symbols
        # is visually equivalent to drawing each on top of just its own.
        self._map_label_batch.draw()

    def _draw_deviation_markers(self) -> None:
        # 4 fixed marks (2 each side) on the same perpendicular-to-course
        # axis as the deviation bar, at ±spacing and ±2*spacing from centre
        # — unlike the bar, these don't slide with a dataref, but they do
        # rotate with the CDI's own course angle like everything else here.
        angle = math.radians(self._heading - self._cdi_angle)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        for k in (-2, -1, 1, 2):
            mx, my = self._point_at(self._cdi_angle + 90.0, k * self._dev_markers_spacing)
            if self._dev_markers_shape == "tick":
                # Local endpoints (0, -half)/(0, half), rotated the same way
                # as the deviation bar's own polygon points — a tick reads
                # as a short segment along the course direction.
                half = self._dev_markers_size
                x0, y0 = mx + half * sin_a, my - half * cos_a
                x1, y1 = mx - half * sin_a, my + half * cos_a
                arcade.draw_line(x0, y0, x1, y1, self._dev_markers_color, self._dev_markers_width)
            else:
                arcade.draw_circle_outline(
                    mx, my, self._dev_markers_size, self._dev_markers_color,
                    self._dev_markers_width, num_segments=self._segments,
                )

    @staticmethod
    def _draw_dashed_line(
        x0: float, y0: float, x1: float, y1: float,
        color: tuple[int, int, int, int], width: float,
        dash: tuple[float, float] | None,
    ) -> None:
        if not dash:
            arcade.draw_line(x0, y0, x1, y1, color, width)
            return
        on, off = dash
        period = on + off
        total = math.hypot(x1 - x0, y1 - y0)
        if period <= 0 or total <= 0:
            arcade.draw_line(x0, y0, x1, y1, color, width)
            return
        ux, uy = (x1 - x0) / total, (y1 - y0) / total
        d = 0.0
        while d < total:
            seg_end = min(d + on, total)
            arcade.draw_line(x0 + ux * d, y0 + uy * d, x0 + ux * seg_end, y0 + uy * seg_end, color, width)
            d += period


def _parse_cdi_segment(seg_cfg: dict[str, Any], default_end: float) -> _CdiSegment:
    symbol_cfg = seg_cfg.get("symbol")
    symbol_kwargs: dict[str, Any] = {}
    if symbol_cfg:
        soc = symbol_cfg.get("outline_color")
        symbol_kwargs = dict(
            symbol_offset=float(symbol_cfg.get("offset", 0.0)),
            symbol_points=[tuple(p) for p in symbol_cfg["points"]],
            symbol_color=_as_color(symbol_cfg.get("color", [255, 255, 255, 255])),
            symbol_filled=bool(symbol_cfg.get("filled", True)),
            symbol_width=float(symbol_cfg.get("width", 2.0)),
            symbol_outline_color=_as_color(soc) if soc is not None else None,
            symbol_outline_width=float(symbol_cfg.get("outline_width", 1.0)),
        )
    return _CdiSegment(
        start=float(seg_cfg.get("start", 0.0)),
        end=float(seg_cfg.get("end", default_end)),
        color=_as_color(seg_cfg.get("color", [255, 255, 255, 255])),
        width=float(seg_cfg.get("width", 2.0)),
        dash=tuple(seg_cfg["dash"]) if seg_cfg.get("dash") else None,
        **symbol_kwargs,
    )


def _compass_rose_factory(
    comp: dict[str, Any],
    base_dir: Path,
    container_size: tuple[int, int] | None = None,
) -> VectorCompassRose:
    label_font, label_bold, label_italic = resolve_font_for_arcade(
        comp.get("label_font"), base_dir,
        bold=bool(comp.get("label_bold", False)),
        italic=bool(comp.get("label_italic", False)),
        explicit_file=comp.get("label_font_file"),
    )

    bg = comp.get("background_color")
    rose = VectorCompassRose(
        name=comp["name"],
        center=tuple(comp["center"]),
        radius=float(comp["radius"]),
        background_color=_as_color(bg) if bg is not None else None,
        show_line=bool(comp.get("show_line", True)),
        line_color=_as_color(comp.get("line_color")),
        line_width=float(comp.get("line_width", 2.0)),
        num_segments=int(comp.get("num_segments", 128)),
        tick5_length=float(comp.get("tick5_length", 8.0)),
        tick5_color=_as_color(comp.get("tick5_color")),
        tick5_width=float(comp.get("tick5_width", 1.0)),
        tick5_position=str(comp.get("tick5_position", "outside")),
        tick10_length=float(comp.get("tick10_length", 16.0)),
        tick10_color=_as_color(comp.get("tick10_color")),
        tick10_width=float(comp.get("tick10_width", 2.0)),
        tick10_position=str(comp.get("tick10_position", "outside")),
        label_interval=float(comp.get("label_interval", 30.0)),
        label_offset=float(comp.get("label_offset", 20.0)),
        label_position=str(comp.get("label_position", "inside")),
        label_font=label_font,
        label_font_size=float(comp.get("label_font_size", 14.0)),
        label_color=_as_color(comp.get("label_color")),
        label_format=str(comp.get("label_format", "{:02.0f}")),
        label_bold=label_bold,
        label_italic=label_italic,
        label_emphasize_interval=comp.get("label_emphasize_interval"),
        label_emphasize_font_size=comp.get("label_emphasize_font_size"),
        label_anchor_y=str(comp.get("label_anchor_y", "center")),
        viewport=tuple(comp["viewport"]) if "viewport" in comp else None,
    )

    heading_cfg = comp.get("heading")
    if heading_cfg:
        rose.set_heading_dataref(
            heading_cfg["dataref"],
            heading_cfg.get("convert_function"),
        )

    track_cfg = comp.get("track")
    if track_cfg:
        rose.set_track(
            color=_as_color(track_cfg.get("color", [0, 255, 0, 255])),
            width=float(track_cfg.get("width", 2.0)),
            start=float(track_cfg.get("start", 0.0)),
            end=float(track_cfg.get("end", comp.get("radius", 150.0))),
            tick_position=track_cfg.get("tick_position"),
            tick_length=float(track_cfg.get("tick_length", 20.0)),
            dataref=track_cfg["dataref"],
            convert_fn=track_cfg.get("convert_function"),
        )

    bug_cfg = comp.get("heading_bug")
    if bug_cfg:
        oc = bug_cfg.get("outline_color")
        line_cfg = bug_cfg.get("line") or {}
        line_color = line_cfg.get("color")
        rose.set_heading_bug(
            radius=float(bug_cfg.get("radius", comp.get("radius", 150.0))),
            points=[tuple(p) for p in bug_cfg["points"]],
            color=_as_color(bug_cfg.get("color", [255, 255, 255, 255])),
            filled=bool(bug_cfg.get("filled", True)),
            width=float(bug_cfg.get("width", 2.0)),
            outline_color=_as_color(oc) if oc is not None else None,
            outline_width=float(bug_cfg.get("outline_width", 1.0)),
            dataref=bug_cfg["dataref"],
            convert_fn=bug_cfg.get("convert_function"),
            line_color=_as_color(line_color) if line_color is not None else None,
            line_width=float(line_cfg.get("width", 2.0)),
            line_dash=tuple(line_cfg["dash"]) if line_cfg.get("dash") else None,
        )

    rings_cfg = comp.get("range_rings")
    if rings_cfg:
        # count/color/width and label are independent sub-features — a
        # range_rings block with only a label (no count) should not
        # implicitly draw a ring.
        if "count" in rings_cfg:
            rose.set_range_rings(
                count=int(rings_cfg["count"]),
                color=_as_color(rings_cfg.get("color")),
                width=float(rings_cfg.get("width", 1.0)),
                half=str(rings_cfg.get("half", "full")),
            )

        label_cfg = rings_cfg.get("label")
        if label_cfg:
            range_label_font, range_label_bold, range_label_italic = resolve_font_for_arcade(
                label_cfg.get("font"), base_dir,
                bold=bool(label_cfg.get("bold", False)),
                italic=bool(label_cfg.get("italic", False)),
                explicit_file=label_cfg.get("font_file"),
            )
            rose.set_range_label(
                dataref=label_cfg["dataref"],
                convert_fn=label_cfg.get("convert_function"),
                format_str=str(label_cfg.get("format", "{:.0f}")),
                offset=tuple(label_cfg.get("offset", [0.0, 0.0])),
                font=range_label_font,
                font_size=float(label_cfg.get("font_size", 14.0)),
                bold=range_label_bold,
                italic=range_label_italic,
                color=_as_color(label_cfg.get("color")),
                table=label_cfg.get("table"),
                anchor_x=str(label_cfg.get("anchor_x", "center")),
                anchor_y=str(label_cfg.get("anchor_y", "center")),
            )

    marker_cfg = comp.get("heading_marker")
    if marker_cfg:
        moc = marker_cfg.get("outline_color")
        rose.set_heading_marker(
            radius=float(marker_cfg.get("radius", comp.get("radius", 150.0))),
            points=[tuple(p) for p in marker_cfg["points"]],
            color=_as_color(marker_cfg.get("color", [255, 255, 255, 255])),
            filled=bool(marker_cfg.get("filled", True)),
            width=float(marker_cfg.get("width", 2.0)),
            outline_color=_as_color(moc) if moc is not None else None,
            outline_width=float(marker_cfg.get("outline_width", 1.0)),
        )

    center_marker_cfg = comp.get("center_marker")
    if center_marker_cfg:
        cmoc = center_marker_cfg.get("outline_color")
        rose.set_center_marker(
            points=[tuple(p) for p in center_marker_cfg["points"]],
            color=_as_color(center_marker_cfg.get("color", [255, 255, 255, 255])),
            filled=bool(center_marker_cfg.get("filled", True)),
            width=float(center_marker_cfg.get("width", 2.0)),
            outline_color=_as_color(cmoc) if cmoc is not None else None,
            outline_width=float(center_marker_cfg.get("outline_width", 1.0)),
            clip=bool(center_marker_cfg.get("clip", True)),
        )

    for pointer_cfg in comp.get("bearing_pointers", []):
        poc = pointer_cfg.get("outline_color")
        pvis = pointer_cfg.get("visibility")
        tail_cfg = pointer_cfg.get("tail")
        tail_kwargs: dict[str, Any] = {}
        if tail_cfg:
            toc = tail_cfg.get("outline_color")
            tail_kwargs = dict(
                tail_offset=float(tail_cfg.get("offset", 0.0)),
                tail_points=[tuple(p) for p in tail_cfg["points"]],
                tail_color=_as_color(tail_cfg.get("color", [255, 255, 255, 255])),
                tail_filled=bool(tail_cfg.get("filled", True)),
                tail_width=float(tail_cfg.get("width", 2.0)),
                tail_outline_color=_as_color(toc) if toc is not None else None,
                tail_outline_width=float(tail_cfg.get("outline_width", 1.0)),
            )
        rose.add_bearing_pointer(
            name=str(pointer_cfg.get("name", "")),
            dataref=pointer_cfg["dataref"],
            convert_fn=pointer_cfg.get("convert_function"),
            offset=float(pointer_cfg.get("offset", 0.0)),
            points=[tuple(p) for p in pointer_cfg["points"]],
            color=_as_color(pointer_cfg.get("color", [255, 255, 255, 255])),
            filled=bool(pointer_cfg.get("filled", True)),
            width=float(pointer_cfg.get("width", 2.0)),
            outline_color=_as_color(poc) if poc is not None else None,
            outline_width=float(pointer_cfg.get("outline_width", 1.0)),
            vis_dataref=pvis["dataref"] if pvis else None,
            vis_predicate=resolve_predicate_name(pvis) if pvis else None,
            **tail_kwargs,
        )

    cdi_cfg = comp.get("course_deviation_indicator")
    if cdi_cfg:
        default_end = float(comp.get("radius", 150.0))
        cdi_vis_cfg = cdi_cfg.get("visibility")
        rose.set_course_deviation_indicator(
            dataref=cdi_cfg["dataref"],
            convert_fn=cdi_cfg.get("convert_function"),
            head=_parse_cdi_segment(cdi_cfg.get("head", {}), default_end),
            tail=_parse_cdi_segment(cdi_cfg.get("tail", {}), default_end),
            vis_dataref=cdi_vis_cfg["dataref"] if cdi_vis_cfg else None,
            vis_predicate=resolve_predicate_name(cdi_vis_cfg) if cdi_vis_cfg else None,
        )

        dev_bar_cfg = cdi_cfg.get("deviation_bar")
        if dev_bar_cfg:
            dboc = dev_bar_cfg.get("outline_color")
            rose.set_deviation_bar(
                dataref=dev_bar_cfg["dataref"],
                convert_fn=dev_bar_cfg.get("convert_function"),
                points=[tuple(p) for p in dev_bar_cfg["points"]],
                color=_as_color(dev_bar_cfg.get("color", [255, 255, 255, 255])),
                filled=bool(dev_bar_cfg.get("filled", True)),
                width=float(dev_bar_cfg.get("width", 2.0)),
                outline_color=_as_color(dboc) if dboc is not None else None,
                outline_width=float(dev_bar_cfg.get("outline_width", 1.0)),
                table=dev_bar_cfg.get("table"),
            )

        markers_cfg = cdi_cfg.get("deviation_markers")
        if markers_cfg:
            rose.set_deviation_markers(
                shape=str(markers_cfg.get("shape", "circle")),
                spacing=float(markers_cfg.get("spacing", 40.0)),
                size=float(markers_cfg.get("size", 4.0)),
                width=float(markers_cfg.get("width", 2.0)),
                color=_as_color(markers_cfg.get("color", [255, 255, 255, 255])),
            )

    map_cfg = comp.get("moving_map")
    if map_cfg:
        styles: dict[str, _MapFeatureStyle] = {}
        for type_name in ("airport", "vor", "ndb", "waypoint"):
            style_cfg = map_cfg.get(type_name)
            if not style_cfg:
                continue
            label_font, label_bold, label_italic = resolve_font_for_arcade(
                style_cfg.get("label_font"), base_dir,
                bold=bool(style_cfg.get("label_bold", False)),
                italic=bool(style_cfg.get("label_italic", False)),
                explicit_file=style_cfg.get("label_font_file"),
            )
            circle_cfg = style_cfg.get("circle") or {}
            style_vis_cfg = style_cfg.get("visibility")
            active_cfg = style_cfg.get("active") or {}
            active_ident_dr = active_cfg.get("ident_dataref")
            active_ident_datarefs = (
                [f"{active_ident_dr}[{i}]" for i in range(int(active_cfg.get("ident_char_count", 1)))]
                if active_ident_dr else []
            )
            active_course_dr = active_cfg.get("course_dataref")
            active_course_fn = active_cfg.get("convert_function")
            styles[type_name] = _MapFeatureStyle(
                points=[tuple(p) for p in style_cfg.get("points", [])],
                filled=bool(style_cfg.get("filled", True)),
                color=_as_color(style_cfg.get("color", [255, 255, 255, 255])),
                outline=bool(style_cfg.get("outline", False)),
                outline_color=_as_color(style_cfg.get("outline_color", [255, 255, 255, 255])),
                outline_width=float(style_cfg.get("outline_width", 1.0)),
                label=bool(style_cfg.get("label", False)),
                label_font_size=float(style_cfg.get("label_font_size", 10.0)),
                label_color=_as_color(style_cfg.get("label_color", [255, 255, 255, 255])),
                label_font=label_font,
                label_bold=label_bold,
                label_italic=label_italic,
                label_offset=tuple(style_cfg.get("label_offset", [6.0, 0.0])),
                circle_radius=float(circle_cfg.get("radius", 0.0)),
                circle_filled=bool(circle_cfg.get("filled", True)),
                circle_color=_as_color(circle_cfg.get("color", [255, 255, 255, 255])),
                circle_outline=bool(circle_cfg.get("outline", False)),
                circle_outline_color=_as_color(circle_cfg.get("outline_color", [255, 255, 255, 255])),
                circle_outline_width=float(circle_cfg.get("outline_width", 1.0)),
                icao_only=bool(style_cfg.get("icao_only", True)),
                vis_dataref=_as_dataref(style_vis_cfg["dataref"]) if style_vis_cfg else None,
                vis_predicate=get_convert(resolve_predicate_name(style_vis_cfg)) if style_vis_cfg else None,
                active_ident_datarefs=active_ident_datarefs,
                active_color=_as_color(active_cfg.get("color", [255, 0, 0, 255])),
                active_course_dataref=_as_dataref(active_course_dr) if active_course_dr else None,
                active_course_convert=get_convert(active_course_fn) if active_course_fn else None,
                active_dash=tuple(active_cfg["dash"]) if active_cfg.get("dash") else None,
                active_width=float(active_cfg.get("width", 2.0)),
            )
        map_vis_cfg = map_cfg.get("visibility")
        rose.set_moving_map(
            gps_lat_dataref=map_cfg["gps_lat_dataref"],
            gps_lon_dataref=map_cfg["gps_lon_dataref"],
            max_per_type=int(map_cfg.get("max_per_type", 60)),
            styles=styles,
            vis_dataref=map_vis_cfg["dataref"] if map_vis_cfg else None,
            vis_predicate=resolve_predicate_name(map_vis_cfg) if map_vis_cfg else None,
        )

    if "visibility" in comp:
        v = comp["visibility"]
        rose.set_visibility(v["dataref"], resolve_predicate_name(v))

    return rose


register_component("VectorCompassRose", _compass_rose_factory)
