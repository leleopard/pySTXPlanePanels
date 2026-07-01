"""Shared font file discovery and loading for gauge_core components.

Both Text and VectorTape need to call arcade.load_font() so that
project-bundled fonts (TTF/TTC in the assets/ directory) are registered
with pyglet before arcade.Text objects are created.  This module provides
auto-discovery so an explicit font_file: YAML field is not required.

TTC (font collection) handling
-------------------------------
Windows GDI only understands four standard subfamily names
(Regular / Bold / Italic / Bold Italic) matched by weight flags.
Non-standard subfamilies like "_Thin" are invisible to the flag-based
lookup.  The safe approach is to pass the **full face name** (family +
subfamily, e.g. "ST_Boeing_PFD Bold") directly as font_name so GDI
does an exact lookup rather than a weight-class guess.

resolve_font_for_arcade() does this: it picks the best TTC face via PIL
getname(), constructs the full face name, and returns it along with
bold=False/italic=False so arcade.Text never tries to resolve by flags.
"""

from __future__ import annotations

from pathlib import Path

import arcade

_LOADED: set[str] = set()

_EXTENSIONS = (".ttc", ".ttf", ".otf")   # TTC first so it wins over same-stem TTF

_BOLD_WORDS   = ("bold", "heavy", "black")
_ITALIC_WORDS = ("italic", "oblique")
_STYLE_WORDS  = _BOLD_WORDS + _ITALIC_WORDS + ("regular", "normal")


def strip_style_suffix(name: str) -> str:
    """Strip trailing style words (Bold/Italic/Regular/...) from a font name.

    pyglet's Windows backend (DirectWrite) matches loaded fonts by base
    family name plus a separate weight/italic flag — a literal family name
    like "ST_Boeing_PFD Bold" is a different (unregistered) family as far
    as DirectWrite is concerned, even though the file was loaded and a
    "ST_Boeing_PFD" + bold=True lookup would find it. Baked-in style words
    are a leftover of hand-typed names or the designer's font picker
    (QFontDialog reports "Family Style" for multi-file font families); the
    bold/italic booleans already carry that information, so the suffix is
    redundant and actively breaks the lookup.
    """
    words = name.split()
    while words and words[-1].lower() in _STYLE_WORDS:
        words.pop()
    return " ".join(words) if words else name


def _normalize(text: str) -> str:
    return text.lower().replace(" ", "").replace("_", "").replace("-", "")


def _find_font_file(
    name: str, base_dir: Path, bold: bool = False, italic: bool = False,
) -> Path | None:
    """Search base_dir and its ancestors for a font file matching name.

    A single family can be split across several plain TTF/OTF files (one
    per weight, e.g. "..._Bold.ttf" / "...-Regular.ttf") rather than faces
    within one TTC. When more than one file matches `name`, the one whose
    filename-inferred style (words after the matched name) best matches
    bold/italic is picked — otherwise the first alphabetical match would
    win regardless of the requested style.
    """
    needle = _normalize(name)
    p = base_dir.resolve()
    for _ in range(6):
        for sub in ("", "assets", "assets/fonts", "fonts"):
            d = p / sub if sub else p
            if not d.is_dir():
                continue
            candidates = [
                f for f in sorted(d.iterdir())
                if f.suffix.lower() in _EXTENSIONS
                and _normalize(f.stem).startswith(needle)
            ]
            if not candidates:
                continue
            ttc = next((f for f in candidates if f.suffix.lower() == ".ttc"), None)
            if ttc is not None:
                return ttc

            def _style_score(f: Path) -> int:
                suffix = _normalize(f.stem)[len(needle):]
                has_bold   = any(w in suffix for w in _BOLD_WORDS)
                has_italic = any(w in suffix for w in _ITALIC_WORDS)
                return (has_bold == bold) + (has_italic == italic)

            return max(candidates, key=_style_score)
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


def _best_ttc_face_name(path: Path, bold: bool, italic: bool) -> str | None:
    """Return the full face name for the best-matching face in a TTC.

    Uses PIL to enumerate faces via getname() and pick the one whose
    style flags best match bold/italic.  Returns "Family Style" (e.g.
    "ST_Boeing_PFD Bold") so pyglet/GDI can do an exact name lookup,
    bypassing the unreliable weight-flag matching for non-standard
    subfamily names like "_Thin".

    Returns None if PIL is unavailable or the file has no faces.
    """
    try:
        from PIL import ImageFont  # optional dep; not available in pure-runtime installs
    except ImportError:
        return None

    best_family: str | None = None
    best_style: str = ""
    best_score = -999
    idx = 0
    while True:
        try:
            face = ImageFont.truetype(str(path), 10, index=idx)
        except OSError:
            break
        family, style = face.getname()
        sl = style.lower()
        has_bold   = any(w in sl for w in _BOLD_WORDS)
        has_italic = any(w in sl for w in _ITALIC_WORDS)
        score = (2 if has_bold == bold else -1) + (2 if has_italic == italic else -1)
        if score > best_score:
            best_score = score
            best_family, best_style = family, style
        idx += 1

    if best_family is None:
        return None
    # Build the full face name.  Standard subfamilies ("Regular", "Normal")
    # don't need to be appended — the family name alone covers them.
    if best_style and best_style.lower() not in ("regular", "normal", ""):
        return f"{best_family} {best_style}"
    return best_family


def resolve_font_for_arcade(
    name: str | None,
    base_dir: Path,
    bold: bool = False,
    italic: bool = False,
    explicit_file: str | None = None,
) -> tuple[str | None, bool, bool]:
    """Return (font_name, bold, italic) to pass to arcade.Text.

    Loads the font file (auto-discovered or explicit) and, for TTC files,
    replaces name+bold+italic with the full face name and False+False so
    that pyglet/GDI does an exact lookup rather than weight-flag guessing.

    For plain TTF/OTF files, any trailing style words (e.g. "Bold") are
    stripped from `name` after the file is loaded so pyglet's weight-based
    lookup (name + bold/italic flags) is used instead of an exact
    "Family Style" name match.
    """
    if not name and not explicit_file:
        return name, bold, italic

    if explicit_file:
        path = (base_dir / explicit_file).resolve()
    else:
        path = _find_font_file(name, base_dir, bold=bold, italic=italic)  # type: ignore[arg-type]

    if path is None:
        return name, bold, italic

    ensure_font_loaded(path)

    if path.suffix.lower() == ".ttc":
        full_name = _best_ttc_face_name(path, bold, italic)
        if full_name:
            return full_name, False, False
        return name, bold, italic

    return strip_style_suffix(name), bold, italic
