"""Shared font file discovery and loading for gauge_core components.

Both Text and VectorTape need to call arcade.load_font() so that
project-bundled fonts (TTF/TTC in the assets/ directory) are registered
with pyglet before arcade.Text objects are created.  This module provides
auto-discovery so an explicit font_file: YAML field is not required.
"""

from __future__ import annotations

from pathlib import Path

import arcade

_LOADED: set[str] = set()

_EXTENSIONS = (".ttc", ".ttf", ".otf")   # TTC first so it wins over same-stem TTF


def _find_font_file(name: str, base_dir: Path) -> Path | None:
    """Search base_dir and its ancestors for a font file matching name."""
    needle = name.lower().replace(" ", "").replace("_", "").replace("-", "")
    p = base_dir.resolve()
    for _ in range(6):
        for sub in ("", "assets", "assets/fonts", "fonts"):
            d = p / sub if sub else p
            if not d.is_dir():
                continue
            # TTC before TTF/OTF so a collection with bold/thin wins over a
            # single-face TTF with the same stem.
            files = sorted(d.iterdir(),
                           key=lambda f: (0 if f.suffix.lower() == ".ttc" else 1, f.name))
            for f in files:
                if f.suffix.lower() not in _EXTENSIONS:
                    continue
                stem = f.stem.lower().replace(" ", "").replace("_", "").replace("-", "")
                if stem == needle or stem.startswith(needle):
                    return f
        parent = p.parent
        if parent == p:
            break
        p = parent
    return None


def ensure_font_loaded(path: Path) -> None:
    """Register a font file with pyglet (no-op if already registered)."""
    key = str(path.resolve())
    if key not in _LOADED:
        arcade.load_font(key)
        _LOADED.add(key)


def auto_load_font(
    name: str | None,
    base_dir: Path,
    explicit_file: str | None = None,
) -> None:
    """Locate and load a project-bundled font for use by arcade.Text.

    If explicit_file is provided it is resolved relative to base_dir and
    loaded directly.  Otherwise the font file is located automatically by
    scanning base_dir and its ancestors for a file whose stem matches name.
    Safe to call even when no matching file exists (silently skipped).
    """
    if explicit_file:
        ensure_font_loaded((base_dir / explicit_file).resolve())
        return
    if not name:
        return
    path = _find_font_file(name, base_dir)
    if path is not None:
        ensure_font_loaded(path)
