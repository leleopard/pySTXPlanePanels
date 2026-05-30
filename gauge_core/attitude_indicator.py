"""AttitudeIndicator component — glass-cockpit ADI with pitch ladder.

Renders:
  - Sky / ground background (rotated with bank)
  - Pitch ladder: lines + labels, translated by pitch, rotated by bank
  - Bank arc scale: fixed arc with tick marks at ±10/20/30/45/60°
  - Roll pointer: triangle that moves with the current bank angle
  - Aircraft reference: fixed wing-stub lines and centre dot
  - All clipped to a configurable viewport rectangle

Coordinate conventions
----------------------
  - ``viewport`` uses the same ``[x, y_bottom, width, height]`` convention as
    ``VectorTape`` (Arcade y-up, bottom-left origin).
  - Positive pitch  = nose up → horizon bar moves below centre.
  - Positive bank   = right bank → background rotates clockwise.
  - Pitch ladder lines at pitch angle ``p`` are labelled with ``|p|``; their
    position relative to centre is ``(p - aircraft_pitch) * pixels_per_degree``.

YAML schema
-----------
    - type: AttitudeIndicator
      name: ai
      viewport: [50, 100, 300, 300]         # [x, y_bottom, w, h]
      pitch_dataref: sim/cockpit2/gauges/indicators/pitch_deg
      roll_dataref:  sim/cockpit2/gauges/indicators/roll_deg
      pixels_per_degree: 8.0
      sky_color:          [0, 100, 180, 255]
      ground_color:       [100, 60,  10, 255]
      horizon_color:      [255, 255, 255]
      horizon_width:      3
      ladder_color:       [255, 255, 255]
      ladder_width:       2
      label_font_size:    14
      bank_arc_color:     [255, 255, 255]
      bank_arc_width:     2
      bank_arc_radius:    0     # 0 → auto: 0.45 * min(viewport_w, viewport_h)
      roll_pointer_color: [255, 255, 255]
      roll_pointer_size:  12    # half-base of the roll-pointer triangle (px)
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

import arcade

from gauge_core.lookup import lookup_piecewise
from gauge_core.registry import get_convert, register_component
from gauge_core.vector_primitives import _VecBase, _as_color, _as_dataref


_BANK_TICKS   = [10, 20, 30, 45, 60]  # drawn on both sides (± each)
_LADDER_RANGE = 90   # draw ladder from -90° to +90°
_SSAA         = 3    # supersample factor — render 3× larger, blit down with bilinear

# Minimal shader: draw a resolve texture onto a viewport-sized quad.
# Uses arcade's WindowBlock UBO (binding 0) so projection is always current.
_BLIT_VS = """
#version 330
uniform WindowBlock {
    mat4 projection;
    mat4 view;
} window;
uniform vec4 u_vp;   // (vx, vy, vw, vh) in world space
in vec2 in_uv;       // static quad UVs: (0,0)–(1,1)
out vec2 v_uv;
void main() {
    vec2 world = u_vp.xy + in_uv * u_vp.zw;
    gl_Position = window.projection * window.view * vec4(world, 0.0, 1.0);
    v_uv = in_uv;
}
"""

_BLIT_FS = """
#version 330
uniform sampler2D tex;
in vec2 v_uv;
out vec4 frag_color;
void main() {
    frag_color = texture(tex, v_uv);
}
"""


def _rot(x: float, y: float, cos_b: float, sin_b: float,
         cx: float, cy: float) -> tuple[float, float]:
    """Rotate (x, y) around origin by the given cos/sin, then offset to (cx, cy)."""
    return cx + x * cos_b - y * sin_b, cy + x * sin_b + y * cos_b


class AttitudeIndicator(_VecBase):
    """Glass-cockpit attitude indicator with pitch ladder."""

    def __init__(
        self,
        name: str,
        viewport: tuple[float, float, float, float],
        ppu: float = 8.0,
        sky_color: tuple = (0, 100, 180, 255),
        ground_color: tuple = (100, 60, 10, 255),
        horizon_color: tuple = (255, 255, 255, 255),
        horizon_width: float = 3.0,
        ladder_color: tuple = (255, 255, 255, 255),
        ladder_width: float = 2.0,
        label_font_size: int = 14,
        bank_arc_color: tuple = (255, 255, 255, 255),
        bank_arc_width: float = 2.0,
        bank_arc_radius: float = 0.0,
        roll_pointer_color: tuple = (255, 255, 255, 255),
        roll_pointer_size: float = 12.0,
        ladder_step: float = 5.0,
        ladder_hw_4: float = 0.40,
        ladder_hw_2: float = 0.31,
        ladder_hw_1: float = 0.22,
        ladder_font_name: str = "",
        ladder_bold: bool = False,
        ladder_italic: bool = False,
        smoothing: float = 0.0,
    ) -> None:
        self.name = name
        self._vx = float(viewport[0])
        self._vy = float(viewport[1])
        self._vw = float(viewport[2])
        self._vh = float(viewport[3])
        self._ppu         = float(ppu)
        self._sky_color   = sky_color
        self._gnd_color   = ground_color
        self._hor_color   = horizon_color
        self._hor_width   = float(horizon_width)
        self._ldr_color   = ladder_color
        self._ldr_width   = float(ladder_width)
        self._font_size   = int(label_font_size)
        self._arc_color   = bank_arc_color
        self._arc_width   = float(bank_arc_width)
        self._arc_r       = float(bank_arc_radius)
        self._ptr_color   = roll_pointer_color
        self._ptr_size    = float(roll_pointer_size)
        self._ladder_step = float(ladder_step)
        self._ladder_hw_4 = float(ladder_hw_4)
        self._ladder_hw_2 = float(ladder_hw_2)
        self._ladder_hw_1 = float(ladder_hw_1)
        self._ladder_font  = str(ladder_font_name)
        self._ladder_bold  = bool(ladder_bold)
        self._ladder_italic = bool(ladder_italic)
        # Clamp to [0, 0.99]: 0 = no smoothing, higher = heavier EMA low-pass.
        self._smooth = max(0.0, min(0.99, float(smoothing)))
        # Reusable Text objects — grown lazily on first draw, never recreated.
        self._lbl_pool_r: list[arcade.Text] = []   # right side, anchor_x="left"
        self._lbl_pool_l: list[arcade.Text] = []   # left  side, anchor_x="right"
        # SSAA offscreen FBO — lazy-created on first draw, recreated if size changes.
        self._ssaa_fbo: Any | None = None
        self._ssaa_tex: Any | None = None
        self._ssaa_dim: tuple[int, int] = (0, 0)
        # 1× resolve FBO: receives GL_LINEAR blit from SSAA FBO (both non-MSAA
        # so GL_LINEAR is valid), then drawn to ctx.screen via shader quad.
        self._res_fbo:  Any | None = None
        self._res_tex:  Any | None = None
        self._res_dim:  tuple[int, int] = (0, 0)
        self._blit_prog: Any | None = None  # textured-quad program
        self._blit_vao:  Any | None = None  # static (0,0)–(1,1) UV quad
        self._pitch: float = 0.0
        self._bank:  float = 0.0
        self._pitch_dr:   Any | None      = None
        self._pitch_conv: Callable | None = None
        self._bank_dr:    Any | None      = None
        self._bank_conv:  Callable | None = None
        self._init_visibility()

    # ── dataref wiring ──────────────────────────────────────────────────────

    def set_pitch_dataref(self, dataref: Any,
                          convert_fn: str | None = None) -> None:
        self._pitch_dr = _as_dataref(dataref)
        if convert_fn:
            self._pitch_conv = get_convert(convert_fn)

    def set_roll_dataref(self, dataref: Any,
                         convert_fn: str | None = None) -> None:
        self._bank_dr = _as_dataref(dataref)
        if convert_fn:
            self._bank_conv = get_convert(convert_fn)

    # ── panel composition ───────────────────────────────────────────────────

    def apply_scale(self, scale: float) -> None:
        self._vx *= scale;  self._vy *= scale
        self._vw *= scale;  self._vh *= scale
        self._ppu       *= scale
        self._arc_r     *= scale
        self._ptr_size  *= scale
        self._hor_width *= scale
        self._ldr_width *= scale
        self._arc_width *= scale
        self._font_size  = max(6, int(self._font_size * scale))

    def apply_offset(self, dx: float, dy: float) -> None:
        self._vx += dx;  self._vy += dy

    # ── per-frame update ────────────────────────────────────────────────────

    def update(self, get_data: Callable[[Any], float]) -> None:
        self._update_visibility(get_data)
        alpha = 1.0 - self._smooth
        if self._pitch_dr is not None:
            raw = float(get_data(self._pitch_dr))
            if self._pitch_conv is not None:
                raw = float(self._pitch_conv(raw, get_data))
            self._pitch = raw if self._smooth == 0.0 else self._pitch + alpha * (raw - self._pitch)
        if self._bank_dr is not None:
            raw = float(get_data(self._bank_dr))
            if self._bank_conv is not None:
                raw = float(self._bank_conv(raw, get_data))
            self._bank = raw if self._smooth == 0.0 else self._bank + alpha * (raw - self._bank)

    # ── draw ────────────────────────────────────────────────────────────────

    def draw(self) -> None:
        if not self._visible:
            return
        vx, vy, vw, vh = self._vx, self._vy, self._vw, self._vh
        cx = vx + vw / 2.0
        cy = vy + vh / 2.0

        # Positive bank = right bank = CCW rotation of AI background.
        bank_rad = math.radians(self._bank)
        cos_b = math.cos(bank_rad)
        sin_b = math.sin(bank_rad)

        # y-offset in AI space where the natural horizon (pitch=0 line) sits.
        # Positive pitch → nose up → horizon sinks below centre → negative y offset.
        pitch_y = -self._pitch * self._ppu

        arc_r = self._arc_r if self._arc_r > 0 else 0.45 * min(vw, vh)

        ctx = arcade.get_window().ctx

        # ── Lazy-create / resize SSAA FBO (3×) and resolve FBO (1×) ─────────────
        ssaa_w = int(vw * _SSAA)
        ssaa_h = int(vh * _SSAA)
        out_w  = int(vw)
        out_h  = int(vh)
        if self._ssaa_fbo is None or self._ssaa_dim != (ssaa_w, ssaa_h):
            if self._ssaa_tex is not None:
                self._ssaa_fbo.release()
                self._ssaa_tex.release()
            self._ssaa_tex = ctx.texture((ssaa_w, ssaa_h), components=4)
            self._ssaa_fbo = ctx.framebuffer(color_attachments=[self._ssaa_tex])
            self._ssaa_dim = (ssaa_w, ssaa_h)
        if self._res_fbo is None or self._res_dim != (out_w, out_h):
            if self._res_tex is not None:
                self._res_fbo.release()
                self._res_tex.release()
            self._res_tex = ctx.texture((out_w, out_h), components=4)
            self._res_fbo = ctx.framebuffer(color_attachments=[self._res_tex])
            self._res_dim = (out_w, out_h)

        # ── Lazy-create blit shader + static UV quad (shared forever) ─────────
        if self._blit_prog is None:
            self._blit_prog = ctx.program(vertex_shader=_BLIT_VS,
                                          fragment_shader=_BLIT_FS)
            self._blit_prog["tex"] = 0  # sampler → texture unit 0
        if self._blit_vao is None:
            import array as _arr
            from arcade.gl import BufferDescription
            buf = ctx.buffer(data=_arr.array("f",
                             [0.0, 0.0,  1.0, 0.0,  0.0, 1.0,  1.0, 1.0]).tobytes())
            self._blit_vao = ctx.geometry(
                [BufferDescription(buf, "2f", ["in_uv"])],
                mode=ctx.TRIANGLE_STRIP,
            )

        # ── Phase 1: all geometry → SSAA FBO ─────────────────────────────────
        from pyglet.math import Mat4
        # Save projection before clobbering it — DefaultProjector.use() has an
        # early-exit that skips restoring projection_matrix when the viewport
        # hasn't changed, so we must restore explicitly.
        saved_proj = ctx.projection_matrix
        self._ssaa_fbo.use()
        self._ssaa_fbo.viewport = (0, 0, ssaa_w, ssaa_h)
        self._ssaa_fbo.clear(color=(0, 0, 0, 0))
        ctx.projection_matrix = Mat4.orthogonal_projection(
            vx, vx + vw, vy, vy + vh, -100.0, 100.0
        )

        self._draw_background(cx, cy, pitch_y, cos_b, sin_b, vw, vh)
        self._draw_ladder(cx, cy, pitch_y, cos_b, sin_b, vw, labels=False)
        self._draw_horizon(cx, cy, pitch_y, cos_b, sin_b)
        self._draw_bank_arc(cx, cy, arc_r)
        self._draw_roll_pointer(cx, cy, arc_r)
        self._draw_reference(cx, cy)

        # ── Blit SSAA (3×) → resolve FBO (1×) via GL_LINEAR ──────────────────
        # Both FBOs are non-MSAA: GL_LINEAR is valid here.
        # Direct blit to ctx.screen (MSAA) with GL_LINEAR is NOT valid per spec
        # (drivers silently fall back to GL_NEAREST, giving zero AA benefit).
        from pyglet.gl import (
            glBindFramebuffer, glBlitFramebuffer,
            GL_READ_FRAMEBUFFER, GL_DRAW_FRAMEBUFFER,
            GL_COLOR_BUFFER_BIT, GL_LINEAR,
        )
        glBindFramebuffer(GL_READ_FRAMEBUFFER, self._ssaa_fbo.glo)
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, self._res_fbo.glo)
        glBlitFramebuffer(0, 0, ssaa_w, ssaa_h, 0, 0, out_w, out_h,
                          GL_COLOR_BUFFER_BIT, GL_LINEAR)

        # ── Draw resolve texture → ctx.screen via shader quad ─────────────────
        # Using a shader quad (not glBlitFramebuffer) so the draw goes through
        # the normal pipeline and the MSAA screen samples it correctly.
        ctx.screen.use()
        ctx.projection_matrix = saved_proj  # direct restore; camera.use() early-exits
        self._blit_prog["u_vp"] = (vx, vy, float(vw), float(vh))
        self._res_tex.use(0)
        ctx.disable(ctx.BLEND)
        self._blit_vao.render(self._blit_prog)
        ctx.enable(ctx.BLEND)

        # ── Phase 2: text labels at native resolution ─────────────────────────
        # arcade.Text uses pyglet's own projection — must render at screen res.
        ctx.scissor = (int(vx), int(vy), int(vw), int(vh))
        try:
            self._draw_ladder(cx, cy, pitch_y, cos_b, sin_b, vw, lines=False)
        finally:
            ctx.scissor = None

    # ── sub-draw helpers ─────────────────────────────────────────────────────

    def _draw_background(self, cx, cy, pitch_y, cos_b, sin_b, vw, vh) -> None:
        big = (vw + vh) * 2
        sky_pts = [
            _rot(-big, pitch_y,       cos_b, sin_b, cx, cy),
            _rot( big, pitch_y,       cos_b, sin_b, cx, cy),
            _rot( big, pitch_y + big, cos_b, sin_b, cx, cy),
            _rot(-big, pitch_y + big, cos_b, sin_b, cx, cy),
        ]
        gnd_pts = [
            _rot(-big, pitch_y - big, cos_b, sin_b, cx, cy),
            _rot( big, pitch_y - big, cos_b, sin_b, cx, cy),
            _rot( big, pitch_y,       cos_b, sin_b, cx, cy),
            _rot(-big, pitch_y,       cos_b, sin_b, cx, cy),
        ]
        arcade.draw_polygon_filled(sky_pts, self._sky_color)
        arcade.draw_polygon_filled(gnd_pts, self._gnd_color)

    def _draw_horizon(self, cx, cy, pitch_y, cos_b, sin_b) -> None:
        big = 20000.0
        x1, y1 = _rot(-big, pitch_y, cos_b, sin_b, cx, cy)
        x2, y2 = _rot( big, pitch_y, cos_b, sin_b, cx, cy)
        arcade.draw_line(x1, y1, x2, y2, self._hor_color, self._hor_width)

    def _draw_ladder(
        self, cx, cy, pitch_y, cos_b, sin_b, vw,
        *, lines: bool = True, labels: bool = True,
    ) -> None:
        half_vw = vw / 2.0
        hw_4 = half_vw * self._ladder_hw_4
        hw_2 = half_vw * self._ladder_hw_2
        hw_1 = half_vw * self._ladder_hw_1

        n_steps = round(_LADDER_RANGE / self._ladder_step)
        lbl_idx = 0
        for i in range(-n_steps, n_steps + 1):
            if i == 0:
                continue  # horizon is drawn separately
            p = i * self._ladder_step
            y_ai  = pitch_y + p * self._ppu
            abs_i = abs(i)
            if abs_i % 4 == 0:
                hw, lw, labeled = hw_4, self._hor_width, True
            elif abs_i % 2 == 0:
                hw, lw, labeled = hw_2, self._ldr_width, False
            else:
                hw, lw, labeled = hw_1, self._ldr_width, False

            if lines:
                x1, y1 = _rot(-hw, y_ai, cos_b, sin_b, cx, cy)
                x2, y2 = _rot( hw, y_ai, cos_b, sin_b, cx, cy)
                arcade.draw_line(x1, y1, x2, y2, self._ldr_color, lw)

            if labeled:
                if labels:
                    label_text = str(abs(round(p)))
                    gap   = 6
                    lx_r, ly_r = _rot( hw + gap, y_ai, cos_b, sin_b, cx, cy)
                    lx_l, ly_l = _rot(-(hw + gap), y_ai, cos_b, sin_b, cx, cy)
                    rot  = -self._bank  # arcade Text.rotation is CW positive; bank is CCW positive

                    if lbl_idx >= len(self._lbl_pool_r):
                        fkw: dict = {"bold": self._ladder_bold, "italic": self._ladder_italic}
                        if self._ladder_font:
                            fkw["font_name"] = self._ladder_font
                        self._lbl_pool_r.append(arcade.Text(
                            "", 0.0, 0.0, color=self._ldr_color,
                            font_size=self._font_size, anchor_x="left", anchor_y="center",
                            **fkw,
                        ))
                        self._lbl_pool_l.append(arcade.Text(
                            "", 0.0, 0.0, color=self._ldr_color,
                            font_size=self._font_size, anchor_x="right", anchor_y="center",
                            **fkw,
                        ))

                    tr = self._lbl_pool_r[lbl_idx]
                    tr.text = label_text
                    tr.x = lx_r;  tr.y = ly_r;  tr.rotation = rot
                    tr.draw()

                    tl = self._lbl_pool_l[lbl_idx]
                    tl.text = label_text
                    tl.x = lx_l;  tl.y = ly_l;  tl.rotation = rot
                    tl.draw()

                lbl_idx += 1

    def _draw_bank_arc(self, cx, cy, arc_r) -> None:
        # Arc spans ±60° from vertical (upper portion of circle).
        # Arcade angle convention: 0=right, CCW positive.
        # Our ±60° bank arc runs from arcade-angle 30° (upper-right, +60° bank)
        # to 150° (upper-left, -60° bank).
        arcade.draw_arc_outline(
            cx, cy,
            arc_r * 2, arc_r * 2,
            self._arc_color,
            30.0, 150.0,
            self._arc_width,
            num_segments=64,
        )
        # 0° reference mark at top
        arcade.draw_line(cx, cy + arc_r - 10,
                         cx, cy + arc_r,
                         self._arc_color, self._arc_width + 1)
        # Tick marks at ±10/20/30/45/60°
        for a in _BANK_TICKS:
            for sign in (-1, 1):
                ba_rad = math.radians(sign * a)
                ox = cx + arc_r * math.sin(ba_rad)
                oy = cy + arc_r * math.cos(ba_rad)
                tick_len = 10.0 if a == 30 else 6.0
                ix = cx + (arc_r - tick_len) * math.sin(ba_rad)
                iy = cy + (arc_r - tick_len) * math.cos(ba_rad)
                arcade.draw_line(ix, iy, ox, oy,
                                 self._arc_color, self._arc_width)

    def _draw_roll_pointer(self, cx, cy, arc_r) -> None:
        # Triangle at the current bank position on the arc, tip pointing inward.
        bank_rad = math.radians(-self._bank)
        ux =  math.sin(bank_rad)   # outward radial unit vector
        uy =  math.cos(bank_rad)
        px_v = -uy                 # perpendicular (CCW from outward)
        py_v =  ux
        bx = cx + arc_r * ux      # base centre on arc
        by = cy + arc_r * uy
        s  = self._ptr_size
        tip = (bx - ux * s,          by - uy * s)
        p1  = (bx + px_v * s * 0.5,  by + py_v * s * 0.5)
        p2  = (bx - px_v * s * 0.5,  by - py_v * s * 0.5)
        arcade.draw_polygon_filled([tip, p1, p2], self._ptr_color)

    def _draw_reference(self, cx, cy) -> None:
        # Fixed aircraft reference: two horizontal wing stubs + centre dot.
        stub = 30.0
        gap  =  6.0
        arcade.draw_line(cx - stub - gap, cy, cx - gap, cy, self._ptr_color, 3)
        arcade.draw_line(cx + gap, cy, cx + stub + gap, cy, self._ptr_color, 3)
        arcade.draw_circle_filled(cx, cy, 4, self._ptr_color)


# ── Factory + registration ────────────────────────────────────────────────────

def _ai_factory(
    comp: dict[str, Any],
    base_dir: Path,
    container_size: tuple[int, int] | None = None,
) -> AttitudeIndicator:
    ai = AttitudeIndicator(
        name=comp["name"],
        viewport=tuple(comp["viewport"]),
        ppu=float(comp.get("pixels_per_degree", 8.0)),
        sky_color=_as_color(comp.get("sky_color",   [0, 100, 180])),
        ground_color=_as_color(comp.get("ground_color", [100, 60, 10])),
        horizon_color=_as_color(comp.get("horizon_color")),
        horizon_width=float(comp.get("horizon_width", 3.0)),
        ladder_color=_as_color(comp.get("ladder_color")),
        ladder_width=float(comp.get("ladder_width", 2.0)),
        label_font_size=int(comp.get("label_font_size", 14)),
        bank_arc_color=_as_color(comp.get("bank_arc_color")),
        bank_arc_width=float(comp.get("bank_arc_width", 2.0)),
        bank_arc_radius=float(comp.get("bank_arc_radius", 0.0)),
        roll_pointer_color=_as_color(comp.get("roll_pointer_color")),
        roll_pointer_size=float(comp.get("roll_pointer_size", 12.0)),
        ladder_step=float(comp.get("ladder_step", 5.0)),
        ladder_hw_4=float(comp.get("ladder_hw_4", 0.40)),
        ladder_hw_2=float(comp.get("ladder_hw_2", 0.31)),
        ladder_hw_1=float(comp.get("ladder_hw_1", 0.22)),
        ladder_font_name=str(comp.get("ladder_font_name", "")),
        ladder_bold=bool(comp.get("ladder_bold", False)),
        ladder_italic=bool(comp.get("ladder_italic", False)),
        smoothing=float(comp.get("smoothing", 0.0)),
    )
    if "pitch_dataref" in comp:
        ai.set_pitch_dataref(comp["pitch_dataref"],
                             comp.get("pitch_convert_function"))
    if "roll_dataref" in comp:
        ai.set_roll_dataref(comp["roll_dataref"],
                            comp.get("roll_convert_function"))
    if "visibility" in comp:
        v = comp["visibility"]
        ai.set_visibility(v["dataref"], v["predicate"])
    return ai


register_component("AttitudeIndicator", _ai_factory)
