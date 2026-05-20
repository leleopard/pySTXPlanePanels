"""Shared full-texture loader and cache.

ImagePanel crops sub-regions from a PIL Image atlas (see component.py).
SpriteSheet and ScrollingTape need the full texture loaded as an
arcade.Texture so the sprite can be repositioned at runtime.  This module
provides a single cache so the same file is never decoded twice regardless
of how many components reference it.
"""

from __future__ import annotations

from pathlib import Path

import arcade
from PIL import Image

_CACHE: dict[str, arcade.Texture] = {}


def load_full_texture(path: Path) -> arcade.Texture:
    """Return a cached arcade.Texture for the full image at *path*."""
    key = str(path)
    if key not in _CACHE:
        img = Image.open(path).convert("RGBA")
        _CACHE[key] = arcade.Texture(img, hash=key)
    return _CACHE[key]
