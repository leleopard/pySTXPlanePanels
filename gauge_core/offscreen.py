"""Headless offscreen rendering.

Rasterises a panel or instrument into a PIL image with no visible window,
at a caller-supplied set of dataref values. This is what lets rendering be
checked automatically — by the regression suite's golden-image tier, or by
anything else that wants a picture of a gauge without a human looking at a
screen.

Two things make the output reproducible enough to diff against a committed
baseline:

- Rendering goes into an explicitly created framebuffer object, never the
  window's default framebuffer. A hidden window's default framebuffer is
  not reliably readable (on Windows it reads back all-black), and it is
  double-buffered, so what a pixel grab returns depends on where in the
  swap cycle it happened.
- Antialiasing, when asked for, is done by rendering large and downsampling
  in PIL rather than through the GL blit chain the live window uses. GL
  downsampling is driver-dependent and would make baselines machine
  specific; PIL's resampling is identical everywhere.

The GL context is created once and reused across renders — context creation
dominates the cost of a single frame, so a suite rendering 40 cases wants
one context, not 40.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

import arcade
from PIL import Image
from pyglet.math import Mat4

from gauge_core.panel import Panel
from gauge_core.runner import draw_panel, load_panel_or_instrument

# Size of the throwaway host window. The panel is rendered into an FBO of
# its own dimensions, so this only has to be a valid window, not a useful
# one — it never becomes visible.
_HOST_WINDOW_SIZE = (64, 64)

_host_window: arcade.Window | None = None


def _get_host_window() -> arcade.Window:
    """Return the shared hidden window that owns the GL context."""
    global _host_window
    if _host_window is None:
        _host_window = arcade.Window(
            *_HOST_WINDOW_SIZE,
            title="gauge_core offscreen",
            visible=False,
        )
    _host_window.switch_to()
    return _host_window


def close_host_window() -> None:
    """Tear down the shared GL context. Safe to call when none was created."""
    global _host_window
    if _host_window is not None:
        try:
            _host_window.close()
        finally:
            _host_window = None


def values_source(
    values: Mapping[str, float] | None = None,
    default: float = 0.0,
) -> Callable[[Any], float]:
    """Build a get_data callable backed by a plain dict of dataref values.

    Datarefs reach components either as strings or, for indexed array
    refs, as tuples — the loader converts YAML lists to tuples. Both are
    looked up by their string form, matching how MockDataSource keys its
    own table, so a case file can name either kind as an ordinary string.
    """
    table = dict(values or {})

    def get_data(dataref: Any) -> float:
        if dataref in table:
            return float(table[dataref])
        return float(table.get(str(dataref), default))

    return get_data


def render_panel(
    panel: Panel,
    values: Mapping[str, float] | None = None,
    supersample: int = 1,
    default_value: float = 0.0,
    warmup: int = 0,
) -> Image.Image:
    """Render *panel* offscreen and return it as an RGBA PIL image.

    `values` maps dataref name to the value the gauge should read; anything
    not listed reads `default_value`. `supersample` >1 renders at that
    multiple and downsamples for antialiasing.

    `warmup` renders and discards that many frames first. The very first
    frame drawn after components are constructed can differ from every
    later one by a level or two on antialiased edges, because arcade packs
    textures into its shared atlas lazily as they are first drawn. The
    difference is far below anything a tolerance-based comparison would
    flag, so this defaults to off; the golden-image tier turns it on since
    it costs one frame and removes the variance entirely.
    """
    if supersample < 1:
        raise ValueError(f"supersample must be >= 1, got {supersample}")
    if warmup < 0:
        raise ValueError(f"warmup must be >= 0, got {warmup}")

    for _ in range(warmup):
        render_panel(
            panel,
            values=values,
            supersample=supersample,
            default_value=default_value,
            warmup=0,
        )

    window = _get_host_window()
    ctx = window.ctx

    width, height = int(panel.size[0]), int(panel.size[1])
    # Don't ask the driver for a texture bigger than it supports — a large
    # panel at supersample=4 can exceed the limit on low-end GPUs (the Pi 5
    # caps out at 4096), and a silent driver failure is worse than just
    # rendering with less antialiasing than was requested.
    max_texture = ctx.info.MAX_TEXTURE_SIZE
    factor = supersample
    while factor > 1 and (width * factor > max_texture or height * factor > max_texture):
        factor //= 2

    fb_width, fb_height = width * factor, height * factor

    background = panel.background_color or (0, 0, 0)
    background_normalized = (
        background[0] / 255.0,
        background[1] / 255.0,
        background[2] / 255.0,
        1.0,
    )

    texture = ctx.texture((fb_width, fb_height), components=4)
    framebuffer = ctx.framebuffer(color_attachments=[texture])

    # Components that clip themselves (ImagePanel, NeedleGauge, SpriteSheet,
    # ScrollingTape, AttitudeIndicator) convert their viewport rectangle from
    # logical panel coords into framebuffer pixels using the ratio between
    # the active viewport and the window's `_panel_size` — the same attribute
    # PanelWindow sets. Without it they would scale against the host window's
    # own dimensions, which have nothing to do with the panel, and clip
    # everything away.
    saved_panel_size = getattr(window, "_panel_size", None)
    window._panel_size = (width, height)

    saved_projection = ctx.projection_matrix
    try:
        framebuffer.use()
        framebuffer.viewport = (0, 0, fb_width, fb_height)
        framebuffer.clear(color_normalized=background_normalized)
        # Project panel coordinates across the whole FBO regardless of the
        # supersample factor, so components draw at their logical sizes and
        # only the sample density changes.
        ctx.projection_matrix = Mat4.orthogonal_projection(
            0, width, 0, height, -100.0, 100.0
        )

        draw_panel(panel, values_source(values, default_value), is_test_mode=False)

        raw = framebuffer.read(components=4)
    finally:
        ctx.projection_matrix = saved_projection
        ctx.screen.use()
        framebuffer.delete()
        texture.delete()
        if saved_panel_size is None:
            del window._panel_size
        else:
            window._panel_size = saved_panel_size

    # GL's origin is bottom-left, PIL's is top-left.
    image = Image.frombytes("RGBA", (fb_width, fb_height), bytes(raw)).transpose(
        Image.FLIP_TOP_BOTTOM
    )
    if factor > 1:
        image = image.resize((width, height), Image.LANCZOS)
    return image


def render_yaml(
    yaml_path: str | Path,
    values: Mapping[str, float] | None = None,
    supersample: int = 1,
    default_value: float = 0.0,
    warmup: int = 0,
) -> Image.Image:
    """Load a panel or instrument YAML and render it offscreen."""
    panel = load_panel_or_instrument(yaml_path)
    return render_panel(
        panel,
        values=values,
        supersample=supersample,
        default_value=default_value,
        warmup=warmup,
    )
