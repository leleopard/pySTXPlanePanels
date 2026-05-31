"""Standalone circular gauge test — SSAA with two-pass downsampling.

Arc from -220° to 40°, radius 100px, centred in a 600×600 window.
Numpad +/-  : ±0.1°   |   Up/Down arrows : ±1°
Angle convention: 0° = right, CCW positive.

AA strategy: render at 4× into an offscreen FBO, then downsample in two
GL_LINEAR blit passes (4× → 2× → 1×).  Each pass is a 2:1 ratio, which
GL_LINEAR handles perfectly — it averages an exact 2×2 source block per
output pixel.  The two passes together give 16-sample coverage per final
pixel, equivalent quality to 16× MSAA without any driver configuration.

A direct 3× → 1× blit with GL_LINEAR is poor because it samples a 2×2
region out of a 3×3 source area (≈44% coverage).  Power-of-2 two-pass
avoids that waste entirely.
"""
import math
import arcade
from arcade.shape_list import (
    ShapeElementList,
    create_line,
    create_line_strip,
    create_ellipse_filled,
)
from pyglet.gl import (
    glBindFramebuffer, glBlitFramebuffer,
    GL_READ_FRAMEBUFFER, GL_DRAW_FRAMEBUFFER,
    GL_COLOR_BUFFER_BIT, GL_LINEAR,
)
from pyglet.math import Mat4

WIDTH         = 600
HEIGHT        = 600
CX            = WIDTH  / 2
CY            = HEIGHT / 2
ARC_RADIUS    = 100.0
ARC_START     = -220.0
ARC_END       =   40.0
ARC_WIDTH     =   3.0
NEEDLE_LENGTH =  90.0
NEEDLE_WIDTH  =   2.5
ARC_SEGMENTS  =  64
SSAA          =   4        # render at 4×; two-pass blit: 4× → 2× → 1×


def _arc_points(cx, cy, r, a0, a1, n):
    return [
        (cx + r * math.cos(math.radians(a0 + i / n * (a1 - a0))),
         cy + r * math.sin(math.radians(a0 + i / n * (a1 - a0))))
        for i in range(n + 1)
    ]


class GaugeWindow(arcade.Window):
    def __init__(self):
        # Keep screen FBO non-MSAA so GL_LINEAR blits to it are valid.
        super().__init__(WIDTH, HEIGHT, "Circular Gauge Test — SSAA 4× two-pass",
                         antialiasing=False)
        self.background_color = arcade.color.BLACK
        self._angle = ARC_START
        self._last_angle: float | None = None

        ctx = self.ctx
        # Full-resolution FBO at SSAA× (e.g. 2400×2400 for 600×600 window).
        sw, sh = WIDTH * SSAA, HEIGHT * SSAA
        self._ssaa_tex = ctx.texture((sw, sh), components=4)
        self._ssaa_fbo = ctx.framebuffer(color_attachments=[self._ssaa_tex])

        # Half-resolution intermediate FBO (e.g. 1200×1200).
        mw, mh = WIDTH * (SSAA // 2), HEIGHT * (SSAA // 2)
        self._mid_tex = ctx.texture((mw, mh), components=4)
        self._mid_fbo = ctx.framebuffer(color_attachments=[self._mid_tex])

        self._ssaa_size = (sw, sh)
        self._mid_size  = (mw, mh)

        # Static shapes — built once.
        self._static: ShapeElementList = ShapeElementList()
        self._static.append(create_line_strip(
            _arc_points(CX, CY, ARC_RADIUS, ARC_START, ARC_END, ARC_SEGMENTS),
            arcade.color.WHITE, ARC_WIDTH,
        ))
        self._static.append(create_ellipse_filled(CX, CY, 4, 4, arcade.color.WHITE))

        # Needle — rebuilt only when angle changes.
        self._needle: ShapeElementList | None = None

    def _build_needle(self):
        rad = math.radians(self._angle)
        n = ShapeElementList()
        n.append(create_line(
            CX, CY,
            CX + NEEDLE_LENGTH * math.cos(rad),
            CY + NEEDLE_LENGTH * math.sin(rad),
            arcade.color.WHITE, NEEDLE_WIDTH,
        ))
        self._needle = n
        self._last_angle = self._angle

    def _step(self, d: float):
        self._angle = max(ARC_START, min(ARC_END, self._angle + d))

    def on_key_press(self, key, _mods):
        if key == arcade.key.NUM_ADD:
            self._step(0.1)
        elif key == arcade.key.NUM_SUBTRACT:
            self._step(-0.1)
        elif key == arcade.key.UP:
            self._step(1.0)
        elif key == arcade.key.DOWN:
            self._step(-1.0)
        elif key == arcade.key.ESCAPE:
            self.close()

    def on_draw(self):
        sw, sh = self._ssaa_size
        mw, mh = self._mid_size
        ctx = self.ctx

        # ── Phase 1: render geometry into 4× FBO ──────────────────────────
        saved_proj = ctx.projection_matrix
        self._ssaa_fbo.use()
        self._ssaa_fbo.viewport = (0, 0, sw, sh)
        self._ssaa_fbo.clear(color=(0.0, 0.0, 0.0, 1.0))
        ctx.projection_matrix = Mat4.orthogonal_projection(
            0, WIDTH, 0, HEIGHT, -100.0, 100.0
        )

        if self._last_angle != self._angle:
            self._build_needle()
        self._static.draw()
        if self._needle:
            self._needle.draw()

        # ── Phase 2: 4× → 2× (perfect 2:1 GL_LINEAR downsample) ──────────
        glBindFramebuffer(GL_READ_FRAMEBUFFER, self._ssaa_fbo.glo)
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, self._mid_fbo.glo)
        glBlitFramebuffer(
            0, 0, sw, sh,
            0, 0, mw, mh,
            GL_COLOR_BUFFER_BIT, GL_LINEAR,
        )

        # ── Phase 3: 2× → 1× (perfect 2:1 GL_LINEAR downsample) ──────────
        ctx.screen.use()
        ctx.projection_matrix = saved_proj
        glBindFramebuffer(GL_READ_FRAMEBUFFER, self._mid_fbo.glo)
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, ctx.screen.glo)
        glBlitFramebuffer(
            0, 0, mw, mh,
            0, 0, WIDTH, HEIGHT,
            GL_COLOR_BUFFER_BIT, GL_LINEAR,
        )
        glBindFramebuffer(GL_READ_FRAMEBUFFER, ctx.screen.glo)


if __name__ == "__main__":
    GaugeWindow()
    arcade.run()
