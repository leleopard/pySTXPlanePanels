"""PIL-based sprite compositor with click-to-select, drag-to-reposition,
and Ctrl+wheel zoom.

Sprites are composited at their nominal positions with no rotation or
translation applied.  Visibility flags are respected (hidden set).
The selected component is outlined in yellow.

Interaction:
  - Left-click a sprite       → selects it (component_selected signal)
  - Left-click cycling        → repeated clicks on overlapping sprites cycle
  - Left-drag a sprite        → repositions it live; component_moved on release
  - Ctrl + mouse-wheel        → zoom in/out (point under cursor stays fixed)
"""

import copy
import io
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtGui import QFontDatabase, QPixmap, QPainter
from PySide6.QtWidgets import QWidget, QScrollArea, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, Signal, QTimer

from gauge_core.emphasize import split_at_place
from gauge_core.lookup import lookup_piecewise
from gauge_core.needle_gauge import _parse_spacing_row as _ng_pad_spacing_row
from gauge_designer.ui_utils import is_y_down


def _rgba(raw) -> tuple:
    """YAML color list → (r, g, b, a) tuple."""
    if raw is None:
        return (200, 200, 200, 255)
    if len(raw) == 3:
        return (int(raw[0]), int(raw[1]), int(raw[2]), 255)
    return tuple(int(v) for v in raw[:4])


_PIL_FONT_CACHE: dict[tuple, ImageFont.FreeTypeFont] = {}
# Extra font directories populated from the loaded instrument's location.
# _pil_font searches these in addition to C:/Windows/Fonts so project-bundled
# fonts (e.g. assets/ST_Boeing_PFD.ttf) are found without system installation.
_EXTRA_FONT_DIRS: list[Path] = []

_BOLD_MARKERS   = ("bold", "bd", "heavy", "black", "b")
_ITALIC_MARKERS = ("italic", "oblique", "it", "i")


_QT_FONTS_REGISTERED: set[str] = set()


def _register_font_dirs(yaml_dir: str) -> None:
    """Populate _EXTRA_FONT_DIRS and register project fonts with QFontDatabase.

    Scanning upward from yaml_dir finds asset directories.  Each font file
    found is registered with Qt so it appears in QFontDialog without needing
    to be installed system-wide.
    """
    global _EXTRA_FONT_DIRS
    dirs: list[Path] = []
    p = Path(yaml_dir).resolve()
    for _ in range(6):
        for sub in ("assets", "assets/fonts", "fonts"):
            d = p / sub
            if d.is_dir() and d not in dirs:
                dirs.append(d)
        parent = p.parent
        if parent == p:
            break
        p = parent
    if dirs != _EXTRA_FONT_DIRS:
        _EXTRA_FONT_DIRS = dirs
        _PIL_FONT_CACHE.clear()
    # Register every discovered font file with Qt so QFontDialog lists them.
    for d in dirs:
        for f in sorted(d.iterdir()):
            if f.suffix.lower() in (".ttf", ".otf", ".ttc"):
                key = str(f.resolve())
                if key not in _QT_FONTS_REGISTERED:
                    QFontDatabase.addApplicationFont(key)
                    _QT_FONTS_REGISTERED.add(key)


def _best_ttc_face(path: Path, px_size: int, bold: bool, italic: bool
                   ) -> "ImageFont.FreeTypeFont | None":
    """Return the best-matching face from a TTC collection for the requested style.

    Enumerates all faces using PIL's getname() (family, style) and picks the
    one whose style flags best match the bold/italic request.
    """
    best: "ImageFont.FreeTypeFont | None" = None
    best_score = -999
    idx = 0
    while True:
        try:
            face = ImageFont.truetype(str(path), px_size, index=idx)
        except OSError:
            break
        _, style = face.getname()
        style_l = style.lower()
        has_bold   = any(m in style_l for m in ("bold", "heavy", "black"))
        has_italic = any(m in style_l for m in ("italic", "oblique"))
        score = (2 if has_bold == bold else -1) + (2 if has_italic == italic else -1)
        if score > best_score:
            best_score = score
            best = face
        idx += 1
    return best


def _pil_font(name: str | None, size: int, *,
              bold: bool = False, italic: bool = False) -> ImageFont.ImageFont:
    """Load a PIL font by family name and style, falling back to the default bitmap font.

    `size` is in points (matching Arcade/pyglet convention).  PIL's truetype()
    takes pixels, so we convert assuming a standard 96 DPI display:
        px = round(points * 96 / 72)

    TTC (collection) files are supported: all faces are enumerated and the
    one whose internal style flags best match bold/italic is selected.
    """
    key = (name or "", size, bold, italic)
    if key in _PIL_FONT_CACHE:
        return _PIL_FONT_CACHE[key]
    # Convert Arcade/pyglet points to PIL pixels (96 DPI, 72 pt/inch).
    px_size = max(1, int(round(size * 96 / 72)))
    font = None
    if name:
        needle = name.lower().replace(" ", "")
        search_dirs = [Path("C:/Windows/Fonts")] + _EXTRA_FONT_DIRS
        candidates: list[tuple[Path, bool, bool]] = []
        seen: set[Path] = set()
        for fonts_dir in search_dirs:
            if not fonts_dir.is_dir():
                continue
            for f in sorted(fonts_dir.iterdir()):
                if f.suffix.lower() not in (".ttf", ".otf", ".ttc") or f in seen:
                    continue
                seen.add(f)
                stem = f.stem.lower().replace(" ", "").replace("-", "")
                if needle not in stem:
                    continue
                if f.suffix.lower() == ".ttc":
                    # TTC: treat as a pseudo-candidate; bold/italic resolved
                    # by face enumeration below, not by filename suffix.
                    candidates.append((f, None, None))  # type: ignore[arg-type]
                else:
                    suffix = stem[stem.index(needle) + len(needle):]
                    is_bold   = any(m in suffix for m in _BOLD_MARKERS)   if suffix else False
                    is_italic = any(m in suffix for m in _ITALIC_MARKERS) if suffix else False
                    candidates.append((f, is_bold, is_italic))
        if candidates:
            # TTCs go first so the correct face wins over a plain .ttf fallback.
            candidates.sort(key=lambda t: (
                0 if t[0].suffix.lower() == ".ttc" else
                (t[1] != bold) * 2 + (t[2] != italic)  # type: ignore[operator]
            ))
            for f, fb, fi in candidates:
                try:
                    if f.suffix.lower() == ".ttc":
                        font = _best_ttc_face(f, px_size, bold, italic)
                    else:
                        font = ImageFont.truetype(str(f), px_size)
                    if font is not None:
                        break
                except Exception:
                    continue
    if font is None:
        try:
            font = ImageFont.load_default(size=px_size)
        except TypeError:
            font = ImageFont.load_default()
    _PIL_FONT_CACHE[key] = font
    return font


class _CanvasSurface(QWidget):
    """Inner widget that owns the scaled pixmap and forwards input to InstrumentCanvas."""

    def __init__(self, canvas: "InstrumentCanvas", parent=None):
        super().__init__(parent)
        self._canvas = canvas
        self._pixmap = QPixmap()
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)

    def set_pixmap(self, pixmap: QPixmap):
        self._pixmap = pixmap
        new_size = pixmap.size() if not pixmap.isNull() else self.size()
        if new_size != self.size():
            self.resize(new_size)
        self.update()

    def paintEvent(self, _event):
        if not self._pixmap.isNull():
            QPainter(self).drawPixmap(0, 0, self._pixmap)

    def mousePressEvent(self, event):
        self._canvas._on_press(event)

    def mouseMoveEvent(self, event):
        self._canvas._on_move(event)

    def mouseReleaseEvent(self, event):
        self._canvas._on_release(event)

    def leaveEvent(self, event):
        self._canvas._on_leave()
        super().leaveEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            self._canvas._on_wheel(event)
        else:
            event.ignore()  # let QScrollArea handle plain scroll


class InstrumentCanvas(QWidget):
    component_selected = Signal(str)        # name of clicked component
    component_moved = Signal(str, int, int)  # name, new_x, new_y  (on drag release)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: dict = {}
        self._yaml_dir: str = ""
        self._selected_name: str | None = None
        self._selected_point_idx: int = -1
        self._atlas_cache: dict[str, Image.Image] = {}
        self._hidden: set[str] = set()
        self._zoom: float = 1.0
        self._deferred_scroll: tuple[int, int] | None = None

        # drag state (stored in unzoomed canvas coordinates)
        self._drag_name: str | None = None
        self._drag_start: tuple[float, float] | None = None
        self._drag_orig: list[int] | None = None
        self._drag_orig_comp: dict | None = None  # deep copy of original comp for non-position types

        self._surface = _CanvasSurface(self)

        self._scroll = QScrollArea()
        self._scroll.setWidget(self._surface)
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignCenter)

        self._coord_label = QLabel("")
        self._coord_label.setAlignment(Qt.AlignLeft)
        self._coord_label.setStyleSheet("font-size: 11px; color: #aaa; padding: 1px 4px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._scroll)
        layout.addWidget(self._coord_label)

    # ── Public API ───────────────────────────────────────────────────────

    def load(self, data: dict, yaml_dir: str):
        self._data = data
        self._yaml_dir = yaml_dir
        self._atlas_cache.clear()
        self._hidden = set()   # reset so no stale names from previous instrument bleed through
        _register_font_dirs(yaml_dir)
        self._render()

    def set_selected_point(self, idx: int):
        self._selected_point_idx = idx
        self._render()

    def set_selected(self, name: str | None):
        if self._selected_name != name:
            self._selected_point_idx = -1   # reset when switching component
            self._selected_name = name
            self._render()

    def force_selected(self, name: str | None):
        """Set selected name and re-render unconditionally (needed after renames)."""
        self._selected_name = name
        self._render()

    def set_hidden(self, hidden: set[str]):
        self._hidden = hidden
        self._render()

    def refresh(self):
        self._render()

    def set_size(self, w: int, h: int):
        if self._data:
            self._data["size"] = [w, h]
            self._render()

    def clear(self):
        self._data = {}
        self._selected_name = None
        self._selected_point_idx = -1
        self._hidden = set()
        self._atlas_cache.clear()
        self._drag_name = None
        self._drag_orig_comp = None
        self._surface.set_pixmap(QPixmap())

    # ── Zoom ─────────────────────────────────────────────────────────────

    def _on_wheel(self, event):
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1.0 / 1.15
        old_zoom = self._zoom
        self._zoom = max(0.2, min(4.0, self._zoom * factor))

        if self._zoom == old_zoom:
            event.accept()
            return

        # cursor position in surface (zoomed) coordinates
        cursor_x = event.position().x()
        cursor_y = event.position().y()
        h_val = self._scroll.horizontalScrollBar().value()
        v_val = self._scroll.verticalScrollBar().value()

        self._render()  # sets _deferred_scroll to pre-zoom values

        # Compute zoom-corrected scroll and override _deferred_scroll so the
        # timer queued by _render() applies these values instead of the pre-zoom ones.
        zoom_ratio = self._zoom / old_zoom
        new_h = int(cursor_x * (zoom_ratio - 1) + h_val)
        new_v = int(cursor_y * (zoom_ratio - 1) + v_val)
        self._deferred_scroll = (new_h, new_v)
        self._apply_deferred_scroll()

        event.accept()

    # ── Mouse handling ────────────────────────────────────────────────────

    def _on_press(self, event):
        if event.button() != Qt.LeftButton:
            return
        # convert from zoomed surface coords to unzoomed canvas coords
        cx = event.position().x() / self._zoom
        cy = event.position().y() / self._zoom
        hits = self._hits_at(int(cx), int(cy))
        if not hits:
            self._drag_name = None
            return
        if self._selected_name in hits:
            idx = hits.index(self._selected_name)
            name = hits[(idx + 1) % len(hits)]
        else:
            name = hits[0]  # topmost
        self._drag_name = name
        self._drag_start = (cx, cy)
        comp = self._find_comp(name)
        self._drag_orig_comp = copy.deepcopy(comp) if comp else None
        # Reference anchor in y-up coords for each type
        ctype = comp.get("type", "") if comp else ""
        if ctype == "Line":
            ref = self._line_pts(comp)[0]
        elif ctype in ("Arc", "VectorCompassRose"):
            ref = comp.get("center", [0, 0])
        elif ctype == "Polygon":
            ref = comp.get("origin", [0, 0])
        elif ctype == "AttitudeIndicator":
            vp = comp.get("viewport", [0, 0, 200, 200])
            ref = [int(vp[0]), int(vp[1])]
        else:
            ref = comp.get("position", [0, 0]) if comp else [0, 0]
        self._drag_orig = [int(ref[0]), int(ref[1])]
        self._surface.setCursor(Qt.SizeAllCursor)
        self.component_selected.emit(name)

    def _on_move(self, event):
        p = event.position()
        canvas_x = p.x() / self._zoom
        canvas_y = p.y() / self._zoom
        _w, ih = self._data.get("size", [310, 310]) if self._data else [310, 310]
        # Show coordinate in the user's selected convention
        y_coord = int(round(canvas_y)) if is_y_down() else ih - int(round(canvas_y))
        self._coord_label.setText(f"X {int(round(canvas_x))}  Y {y_coord}")

        if not (event.buttons() & Qt.LeftButton) or not self._drag_name:
            return
        dx = canvas_x - self._drag_start[0]
        dy = canvas_y - self._drag_start[1]
        dx_yaml = dx
        dy_yaml = -dy  # canvas y-down → y-up
        comp = self._find_comp(self._drag_name)
        orig = self._drag_orig_comp
        if comp is not None and orig is not None:
            ctype = comp.get("type", "")
            if ctype == "Line":
                # Whole-line drag: every point shifts by the same delta.
                # Individual point editing happens via the properties form's
                # points table, not by dragging on the canvas.
                new_pts = [[int(round(x + dx_yaml)), int(round(y + dy_yaml))]
                           for x, y in self._line_pts(orig)]
                if "points" in orig:
                    comp["points"] = new_pts
                else:
                    comp["start"], comp["end"] = new_pts[0], new_pts[1]
            elif ctype == "Polygon":
                oo = orig.get("origin", [0, 0])
                comp["origin"] = [int(round(oo[0] + dx_yaml)), int(round(oo[1] + dy_yaml))]
            elif ctype in ("Arc", "VectorCompassRose"):
                oc = orig.get("center", [0, 0])
                comp["center"] = [int(round(oc[0] + dx_yaml)), int(round(oc[1] + dy_yaml))]
            elif ctype == "AttitudeIndicator":
                ovp = orig.get("viewport", [0, 0, 200, 200])
                comp["viewport"] = [
                    int(round(ovp[0] + dx_yaml)),
                    int(round(ovp[1] + dy_yaml)),
                    int(ovp[2]), int(ovp[3])
                ]
            else:
                op = orig.get("position", [0, 0])
                comp["position"] = [int(round(op[0] + dx_yaml)), int(round(op[1] + dy_yaml))]
            self._render()

    def _on_leave(self):
        self._coord_label.setText("")

    def _on_release(self, event):
        if event.button() != Qt.LeftButton or not self._drag_name:
            return
        self._surface.setCursor(Qt.CrossCursor)
        comp = self._find_comp(self._drag_name)
        if comp is not None:
            ctype = comp.get("type", "")
            if ctype == "Line":
                ref = self._line_pts(comp)[0]
            elif ctype in ("Arc", "VectorCompassRose"):
                ref = comp.get("center", [0, 0])
            elif ctype == "Polygon":
                ref = comp.get("origin", [0, 0])
            elif ctype == "AttitudeIndicator":
                vp = comp.get("viewport", [0, 0, 200, 200])
                ref = [int(vp[0]), int(vp[1])]
            else:
                ref = comp.get("position", [0, 0])
            self.component_moved.emit(self._drag_name, int(ref[0]), int(ref[1]))
        self._drag_name = None
        self._drag_start = None
        self._drag_orig = None
        self._drag_orig_comp = None

    # ── Hit testing ───────────────────────────────────────────────────────

    def _hits_at(self, cx: int, cy: int) -> list[str]:
        """All components containing unzoomed canvas point (cx, cy), topmost first."""
        w, h = self._data.get("size", [310, 310])
        result = []
        for comp in reversed(self._data.get("components", [])):  # topmost first
            if comp.get("name") in self._hidden:
                continue
            ctype = comp.get("type")
            try:
                if ctype == "ImagePanel":
                    sprite, px, py = self._crop_sprite(comp, w, h)
                    cw, ch = sprite.size
                    if px <= cx < px + cw and py <= cy < py + ch:
                        result.append(comp.get("name"))
                elif ctype in ("SpriteSheet", "ScrollingTape"):
                    rect = self._viewport_rect_pil(comp, h)
                    if rect is not None:
                        rx, ry, rw, rh = rect
                        if rx <= cx < rx + rw and ry <= cy < ry + rh:
                            result.append(comp.get("name"))
                elif ctype == "Line":
                    pts = self._line_pts(comp)
                    xs = [int(x) for x, _y in pts]
                    ys = [h - int(y) for _x, y in pts]
                    pad = 8
                    if (min(xs) - pad <= cx <= max(xs) + pad and
                            min(ys) - pad <= cy <= max(ys) + pad):
                        result.append(comp.get("name"))
                elif ctype in ("Arc", "VectorCompassRose"):
                    ctr = comp.get("center", [0, 0])
                    r = int(round(float(comp.get("radius", 50)))) + 8
                    ax, ay = int(ctr[0]), h - int(ctr[1])
                    if (ax - r) <= cx <= (ax + r) and (ay - r) <= cy <= (ay + r):
                        result.append(comp.get("name"))
                elif ctype in ("FilledRect", "RotaryEncoder"):
                    pos = comp.get("position", [0, 0]); sz = comp.get("size", [100, 100])
                    fx, fy = int(pos[0]), h - int(pos[1])
                    hw, hh = int(sz[0]) // 2, int(sz[1]) // 2
                    if (fx - hw) <= cx <= (fx + hw) and (fy - hh) <= cy <= (fy + hh):
                        result.append(comp.get("name"))
                elif ctype == "Polygon":
                    orig_xy = comp.get("origin", [0, 0])
                    pts = comp.get("points", [])
                    if pts:
                        xs = [int(orig_xy[0] + p[0]) for p in pts]
                        ys = [h - int(orig_xy[1] + p[1]) for p in pts]
                        pad = 4
                        if (min(xs) - pad <= cx <= max(xs) + pad and
                                min(ys) - pad <= cy <= max(ys) + pad):
                            result.append(comp.get("name"))
                elif ctype == "Vector":
                    pos = comp.get("position", [0, 0])
                    ox_p = int(pos[0]); oy_p = h - int(pos[1])
                    dir_cfg = comp.get("direction", 0.0)
                    dir_deg = float(dir_cfg) if not isinstance(dir_cfg, dict) else 0.0
                    len_cfg = comp.get("length", 50.0)
                    length = float(len_cfg) if not isinstance(len_cfg, dict) else 50.0
                    dir_rad = math.radians(dir_deg)
                    ex_p = int(round(ox_p + length * math.cos(dir_rad)))
                    ey_p = int(round(oy_p - length * math.sin(dir_rad)))
                    pad = 8
                    if (min(ox_p, ex_p) - pad <= cx <= max(ox_p, ex_p) + pad and
                            min(oy_p, ey_p) - pad <= cy <= max(oy_p, ey_p) + pad):
                        result.append(comp.get("name"))
                elif ctype in ("VectorTape", "AttitudeIndicator"):
                    rect = self._viewport_rect_pil(comp, h)
                    if rect is not None:
                        rx, ry, rw, rh = rect
                        if rx <= cx < rx + rw and ry <= cy < ry + rh:
                            result.append(comp.get("name"))
            except Exception:
                continue
        return result

    def _find_comp(self, name: str) -> dict | None:
        for comp in self._data.get("components", []):
            if comp.get("name") == name:
                return comp
        return None

    # ── Rendering ────────────────────────────────────────────────────────

    def _render(self):
        if not self._data:
            self._surface.set_pixmap(QPixmap())
            return

        # Capture the intended scroll position before any resize resets it.
        # _on_wheel overrides _deferred_scroll with zoom-corrected values after
        # calling _render(), so the timer always applies the latest intention.
        self._deferred_scroll = (
            self._scroll.horizontalScrollBar().value(),
            self._scroll.verticalScrollBar().value(),
        )

        pixmap = self._composite()
        if self._zoom != 1.0:
            pixmap = pixmap.scaled(
                int(pixmap.width() * self._zoom),
                int(pixmap.height() * self._zoom),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        self._surface.set_pixmap(pixmap)

        # Restore immediately (handles sync resets) and also after Qt settles
        # (handles async layout events queued by the widget resize).
        self._apply_deferred_scroll()
        QTimer.singleShot(0, self._apply_deferred_scroll)

    def _apply_deferred_scroll(self) -> None:
        if self._deferred_scroll is not None:
            h, v = self._deferred_scroll
            self._scroll.horizontalScrollBar().setValue(h)
            self._scroll.verticalScrollBar().setValue(v)

    def _composite(self) -> QPixmap:
        w, h = self._data.get("size", [310, 310])
        composite = Image.new("RGBA", (w, h), (30, 30, 30, 255))
        draw = ImageDraw.Draw(composite)

        for comp in self._data.get("components", []):
            if comp.get("name") in self._hidden:
                continue
            ctype = comp.get("type")
            try:
                if ctype == "ImagePanel":
                    sprite, px, py = self._crop_sprite(comp, w, h)
                    composite.paste(sprite, (px, py), sprite)
                elif ctype == "SpriteSheet":
                    self._render_spritesheet(comp, composite, w, h)
                elif ctype == "ScrollingTape":
                    self._render_scrolltape(comp, composite, w, h)
                elif ctype == "Line":
                    self._render_line(comp, draw, h)
                elif ctype == "Arc":
                    self._render_arc(comp, draw, h)
                elif ctype == "FilledRect":
                    self._render_filledrect(comp, composite, draw, h)
                elif ctype == "Polygon":
                    self._render_polygon(comp, draw, h)
                elif ctype == "Vector":
                    self._render_vector(comp, draw, h)
                elif ctype == "VectorTape":
                    self._render_vectortape(comp, composite, draw, w, h)
                elif ctype == "AttitudeIndicator":
                    self._render_ai(comp, composite, draw, w, h)
                elif ctype == "VectorCompassRose":
                    self._render_compassrose(comp, composite, draw, h)
                elif ctype == "RotaryEncoder":
                    self._render_rotary_encoder(comp, composite, draw, h)
                elif ctype == "NeedleGauge":
                    self._render_needlegauge(comp, composite, draw, h)
                elif ctype == "Text":
                    self._render_text(comp, draw, h)
            except Exception:
                continue

        SEL = (255, 220, 0, 255)
        if self._selected_name:
            for comp in self._data.get("components", []):
                if comp.get("name") != self._selected_name:
                    continue
                ctype = comp.get("type")
                if ctype == "ImagePanel":
                    try:
                        sprite, px, py = self._crop_sprite(comp, w, h)
                        cw, ch = sprite.size
                        draw.rectangle([px, py, px + cw - 1, py + ch - 1],
                                       outline=SEL, width=2)
                    except Exception:
                        pass
                elif ctype in ("SpriteSheet", "ScrollingTape", "VectorTape", "AttitudeIndicator"):
                    rect = self._viewport_rect_pil(comp, h)
                    if rect is not None:
                        rx, ry, rw, rh = rect
                        draw.rectangle([rx, ry, rx + rw - 1, ry + rh - 1],
                                       outline=SEL, width=2)
                    else:
                        self._draw_crosshair(draw, comp.get("position", [w//2, h//2]), h, SEL)
                elif ctype == "Line":
                    pts = self._line_pts(comp)
                    lw = max(3, int(float(comp.get("width", 1.0))) + 2)
                    poly = [(int(x), h - int(y)) for x, y in pts]
                    draw.line(poly, fill=SEL, width=lw)
                elif ctype == "Arc":
                    ctr = comp.get("center", [0, 0])
                    r = int(round(float(comp.get("radius", 50))))
                    cx_p, cy_p = int(ctr[0]), h - int(ctr[1])
                    bbox = [cx_p - r, cy_p - r, cx_p + r, cy_p + r]
                    sa, ea = float(comp.get("start_angle", 0)), float(comp.get("end_angle", 360))
                    draw.arc(bbox, -ea, -sa, fill=SEL, width=4)
                elif ctype == "VectorCompassRose":
                    ctr = comp.get("center", [0, 0])
                    r = int(round(float(comp.get("radius", 50))))
                    cx_p, cy_p = int(ctr[0]), h - int(ctr[1])
                    draw.ellipse([cx_p - r, cy_p - r, cx_p + r, cy_p + r], outline=SEL, width=3)
                elif ctype == "NeedleGauge":
                    ctr = comp.get("center", [0, 0])
                    cx_p, cy_p = int(ctr[0]), h - int(ctr[1])
                    if str(comp.get("gradation_type", "circular")) == "linear":
                        lin = comp.get("linear") or {}
                        table = lin.get("spacing_table", [])
                        half = max((abs(p[1]) for p in table), default=50)
                        vertical = str(lin.get("orientation", "vertical")) == "vertical"
                        if vertical:
                            draw.rectangle([cx_p - 40, cy_p - int(half) - 10,
                                           cx_p + 40, cy_p + int(half) + 10], outline=SEL, width=2)
                        else:
                            draw.rectangle([cx_p - int(half) - 10, cy_p - 40,
                                           cx_p + int(half) + 10, cy_p + 40], outline=SEL, width=2)
                    else:
                        r = int(round(float(comp.get("radius", 50))))
                        draw.ellipse([cx_p - r, cy_p - r, cx_p + r, cy_p + r], outline=SEL, width=3)
                elif ctype in ("FilledRect", "RotaryEncoder"):
                    pos = comp.get("position", [0, 0]); sz = comp.get("size", [100, 100])
                    cx_p, cy_p = int(pos[0]), h - int(pos[1])
                    hw, hh = int(sz[0]) // 2, int(sz[1]) // 2
                    draw.rectangle([cx_p - hw, cy_p - hh, cx_p + hw, cy_p + hh],
                                   outline=SEL, width=2)
                elif ctype == "Polygon":
                    orig_xy = comp.get("origin", [0, 0])
                    pts = [(int(orig_xy[0] + p[0]), h - int(orig_xy[1] + p[1]))
                           for p in comp.get("points", [])]
                    if len(pts) >= 2:
                        draw.polygon(pts, outline=SEL)
                elif ctype == "Vector":
                    pos = comp.get("position", [0, 0])
                    ox_p = int(pos[0]); oy_p = h - int(pos[1])
                    dir_cfg = comp.get("direction", 0.0)
                    dir_deg = float(dir_cfg) if not isinstance(dir_cfg, dict) else 0.0
                    len_cfg = comp.get("length", 50.0)
                    length = float(len_cfg) if not isinstance(len_cfg, dict) else 50.0
                    dir_rad = math.radians(dir_deg)
                    ex_p = int(round(ox_p + length * math.cos(dir_rad)))
                    ey_p = int(round(oy_p - length * math.sin(dir_rad)))
                    lw = max(3, int(float(comp.get("width", 1.0))) + 2)
                    draw.line([(ox_p, oy_p), (ex_p, ey_p)], fill=SEL, width=lw)
                elif ctype == "Text":
                    pos = comp.get("position", [0, 0])
                    self._draw_crosshair(draw, pos, h, SEL)
                else:
                    self._draw_crosshair(draw, comp.get("position", [w//2, h//2]), h, SEL)
                break

        buf = io.BytesIO()
        composite.save(buf, format="PNG")
        pixmap = QPixmap()
        pixmap.loadFromData(buf.getvalue())
        return pixmap

    def _draw_crosshair(self, draw: ImageDraw.ImageDraw,
                        pos, canvas_h: int, color) -> None:
        cx_p, cy_p = int(pos[0]), canvas_h - int(pos[1])
        draw.line([(cx_p - 12, cy_p), (cx_p + 12, cy_p)], fill=color, width=2)
        draw.line([(cx_p, cy_p - 12), (cx_p, cy_p + 12)], fill=color, width=2)

    @staticmethod
    def _line_pts(comp: dict) -> list[list[float]]:
        """Points for a Line component: explicit points: list if present
        (2+, drawn as a connected polyline), else the legacy start/end pair."""
        pts = comp.get("points")
        if pts:
            return [[float(p[0]), float(p[1])] for p in pts]
        return [list(comp.get("start", [0, 0])), list(comp.get("end", [0, 0]))]

    def _render_line(self, comp: dict, draw: ImageDraw.ImageDraw, canvas_h: int) -> None:
        pts = self._line_pts(comp)
        color = _rgba(comp.get("color"))
        width = max(1, int(round(float(comp.get("width", 1.0)))))
        poly = [(int(x), canvas_h - int(y)) for x, y in pts]
        draw.line(poly, fill=color, width=width)

    def _render_arc(self, comp: dict, draw: ImageDraw.ImageDraw, canvas_h: int) -> None:
        ctr = comp.get("center", [0, 0])
        r = int(round(float(comp.get("radius", 50))))
        cx_p, cy_p = int(ctr[0]), canvas_h - int(ctr[1])
        bbox = [cx_p - r, cy_p - r, cx_p + r, cy_p + r]
        sa = float(comp.get("start_angle", 0))
        ea = float(comp.get("end_angle", 360))
        color = _rgba(comp.get("color"))
        width = max(1, int(round(float(comp.get("width", 1.0)))))
        # Arcade uses CCW angles in y-up space; PIL uses CW angles in y-down space.
        # Flipping y negates all angles, so swap and negate: pil_start=-ea, pil_end=-sa.
        draw.arc(bbox, -ea, -sa, fill=color, width=width)

    def _render_needlegauge(self, comp: dict, composite: Image.Image,
                            draw: ImageDraw.ImageDraw, canvas_h: int) -> None:
        ctr = comp.get("center", [0, 0])
        cx_p, cy_p = float(ctr[0]), canvas_h - float(ctr[1])
        grad = str(comp.get("gradation_type", "circular"))

        if grad == "linear":
            self._render_needlegauge_linear(comp, draw, cx_p, cy_p)
        else:
            r = float(comp.get("radius", 100.0))
            # NeedleGauge's own clock convention (0°=up, CW+), NOT the
            # standalone Arc component's math convention above. Converting
            # straight to PIL's angle: pil = clock_angle - 90. PIL (like
            # Arcade's draw_arc_outline) silently draws the wrong short-way
            # arc — or nothing — unless the first angle is numerically
            # smaller than the second (confirmed empirically); an outline
            # has no directionality, so sorting is always safe.
            sa = float(comp.get("start_angle", -130.0))
            ea = float(comp.get("end_angle", 130.0))
            acolor = _rgba(comp.get("arc_color") or comp.get("color"))
            awidth = max(1, int(round(float(comp.get("arc_width", 2.0)))))
            bbox = [cx_p - r, cy_p - r, cx_p + r, cy_p + r]
            p1, p2 = sa - 90.0, ea - 90.0
            draw.arc(bbox, min(p1, p2), max(p1, p2), fill=acolor, width=awidth)

        # Needle — no live dataref value in the static preview, so use a
        # representative mid-scale angle when dataref-driven.
        angle_cfg = comp.get("needle_angle", -130.0)
        if isinstance(angle_cfg, dict):
            table = angle_cfg.get("table") or [[0, 0]]
            angles = [row[1] for row in table]
            angle = (min(angles) + max(angles)) / 2.0
        else:
            angle = float(angle_cfg)
        length = float(comp.get("needle_length", 150.0))
        ncolor = _rgba(comp.get("needle_color") or comp.get("color"))
        nwidth = max(1, int(round(float(comp.get("needle_width", 2.0)))))
        angle_rad = math.radians(angle)
        # 0°=up, CW+ (this component's clock convention): direction is
        # (sin, cos); PIL y is flipped vs. Arcade, so negate the cos term.
        ex = cx_p + length * math.sin(angle_rad)
        ey = cy_p - length * math.cos(angle_rad)

        nv = comp.get("needle_viewport")
        if nv:
            # Same "draw fully, clip after" approach as _render_compassrose's
            # viewport handling — matches the runtime's GL scissor without
            # hand-clipping the line geometry. nv is [dx, dy, w, h] relative
            # to `center` (not cx_p/cy_p, which are already PIL-flipped).
            layer = Image.new("RGBA", composite.size, (0, 0, 0, 0))
            ImageDraw.Draw(layer).line([(cx_p, cy_p), (ex, ey)], fill=ncolor, width=nwidth)
            off_x, off_y, nvw, nvh = nv
            abs_x, abs_y = float(ctr[0]) + off_x, float(ctr[1]) + off_y
            rx, ry = int(abs_x), int(canvas_h - abs_y - nvh)
            rw, rh = int(nvw), int(nvh)
            cropped = layer.crop((rx, ry, rx + rw, ry + rh))
            composite.alpha_composite(cropped, (rx, ry))
            # Reference outline for the clip box itself — always shown (not
            # gated by selection) so offset/size can be tuned without having
            # to keep re-selecting the component.
            draw.rectangle([rx, ry, rx + rw - 1, ry + rh - 1],
                           outline=(0, 200, 255, 220), width=1)
        else:
            draw.line([(cx_p, cy_p), (ex, ey)], fill=ncolor, width=nwidth)

    def _render_needlegauge_linear(self, comp: dict, draw: ImageDraw.ImageDraw,
                                   cx_p: float, cy_p: float) -> None:
        """One spacing_table row = one fully-styled tick — no interval-based
        generation, no interpolation. See gauge_core/needle_gauge.py."""
        lin = comp.get("linear") or {}
        table = [_ng_pad_spacing_row(p) for p in lin.get("spacing_table", [])]
        if not table:
            return
        vertical = str(lin.get("orientation", "vertical")) == "vertical"
        side = str(lin.get("tick_side", "left"))
        tick_color = _rgba(lin.get("tick_color"))

        # Tape's own centre line, possibly shifted away from the needle's
        # pivot (cx_p, cy_p); y is negated (Arcade y-up -> PIL y-down).
        off_x, off_y = lin.get("offset", [0.0, 0.0])
        tx_p = cx_p + float(off_x)
        ty_p = cy_p - float(off_y)

        rect_bg = lin.get("background_color")
        rect_line = lin.get("line_color")
        if rect_bg is not None or rect_line is not None:
            rw, rh = lin.get("size", [0.0, 0.0])
            rw, rh = float(rw), float(rh)
            bbox = [tx_p - rw / 2, ty_p - rh / 2, tx_p + rw / 2, ty_p + rh / 2]
            if rect_bg is not None:
                draw.rectangle(bbox, fill=_rgba(rect_bg))
            if rect_line is not None:
                lw = max(1, int(round(float(lin.get("line_width", 1.0)))))
                draw.rectangle(bbox, outline=_rgba(rect_line), width=lw)

        for value, off, length, width, _show_label, _font_size, _label_offset in table:
            width = max(1, int(round(width)))
            if vertical:
                x0, x1 = (tx_p - length, tx_p) if side == "left" else (tx_p, tx_p + length)
                y = ty_p - off
                draw.line([(x0, y), (x1, y)], fill=tick_color, width=width)
            else:
                y0, y1 = (ty_p - length, ty_p) if side == "top" else (ty_p, ty_p + length)
                x = tx_p + off
                draw.line([(x, y0), (x, y1)], fill=tick_color, width=width)

        labels = lin.get("labels")
        if labels:
            fmt = labels.get("format") or "{:.0f}"
            lfont = labels.get("font")
            bold = bool(labels.get("bold", False))
            italic = bool(labels.get("italic", False))
            lcolor = _rgba(labels.get("color"))
            for value, off, _length, _width, show_label, font_size, label_offset in table:
                if not show_label:
                    continue
                text = fmt.format(value)
                font = _pil_font(lfont, max(8, int(font_size)), bold=bold, italic=italic)
                if vertical:
                    ly = ty_p - off
                    if side == "left":
                        draw.text((tx_p - label_offset, ly), text, fill=lcolor, font=font, anchor="rm")
                    else:
                        draw.text((tx_p + label_offset, ly), text, fill=lcolor, font=font, anchor="lm")
                else:
                    lx = tx_p + off
                    if side == "top":
                        draw.text((lx, ty_p - label_offset), text, fill=lcolor, font=font, anchor="mb")
                    else:
                        draw.text((lx, ty_p + label_offset), text, fill=lcolor, font=font, anchor="mt")

        target = lin.get("target")
        if target:
            # No live dataref value in the static preview — use the middle
            # value of this component's OWN spacing_table (the same table
            # the runtime interpolates against) as a representative position.
            values = [row[0] for row in table]
            mid_value = (min(values) + max(values)) / 2.0
            pairs = sorted(([row[0], row[1]] for row in table), key=lambda p: p[0])
            off = lookup_piecewise(pairs, mid_value)
            length = float(target.get("length", 20.0))
            width = max(1, int(round(float(target.get("width", 2.0)))))
            tcolor = _rgba(target.get("color"))
            if vertical:
                x0, x1 = (tx_p - length, tx_p) if side == "left" else (tx_p, tx_p + length)
                y = ty_p - off
                draw.line([(x0, y), (x1, y)], fill=tcolor, width=width)
            else:
                y0, y1 = (ty_p - length, ty_p) if side == "top" else (ty_p, ty_p + length)
                x = tx_p + off
                draw.line([(x, y0), (x, y1)], fill=tcolor, width=width)

    @staticmethod
    def _crosshair(draw: ImageDraw.ImageDraw, cx: int, cy: int) -> None:
        """1px yellow crosshair, 20px long (10px each arm)."""
        c = (255, 220, 0, 255)
        draw.line([(cx - 10, cy), (cx + 10, cy)], fill=c, width=1)
        draw.line([(cx, cy - 10), (cx, cy + 10)], fill=c, width=1)

    @staticmethod
    def _point_crosshair(draw: ImageDraw.ImageDraw, cx: int, cy: int) -> None:
        """Cyan circled crosshair, 16px arms — deliberately distinct from
        the origin's thin yellow crosshair so the two markers can't be
        confused, marking whichever point is selected in a Points table."""
        c = (0, 220, 255, 255)
        draw.line([(cx - 8, cy), (cx + 8, cy)], fill=c, width=2)
        draw.line([(cx, cy - 8), (cx, cy + 8)], fill=c, width=2)
        draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], outline=c, width=2)

    @staticmethod
    def _paste_rotated_text(composite: Image.Image, text: str, font, color,
                            x: float, y: float, rotation_deg: float,
                            anchor_y: str = "m") -> None:
        """Draw `text` anchored at (x, y), rotated `rotation_deg` (same sign
        convention as Arcade: positive = counter-clockwise as viewed).
        PIL has no rotated-text draw call, so render to a transparent tile
        with the requested anchor point placed at the tile's own centre —
        drawn generously oversized so the glyph never clips regardless of
        anchor — then rotate (which pivots on the tile centre, i.e. the
        anchor point) and alpha-paste onto `composite` centred at (x, y).
        `anchor_y` is a PIL vertical anchor code: "a" (top/ascender),
        "m" (middle), "s" (baseline), "d" (bottom/descender).
        """
        bbox = font.getbbox(text)
        pad = max(8, font.size)
        tw = (bbox[2] - bbox[0]) + pad * 2
        th = font.size * 4
        tile = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        cx, cy = tw / 2, th / 2
        ImageDraw.Draw(tile).text((cx, cy), text, fill=color, font=font, anchor="m" + anchor_y)
        rotated = tile.rotate(rotation_deg, expand=True, resample=Image.BICUBIC)
        px = int(round(x - rotated.width / 2))
        py = int(round(y - rotated.height / 2))
        composite.paste(rotated, (px, py), rotated)

    def _render_compassrose(self, comp: dict, composite: Image.Image,
                            draw: ImageDraw.ImageDraw, canvas_h: int) -> None:
        """Static preview at heading=0 — matches the runtime's neutral orientation.

        Mirrors the runtime's optional scissor clip (viewport): with one
        configured, render onto a transparent layer first and paste back only
        the cropped viewport rect, the same "draw fully, clip after" approach
        the runtime's GL scissor achieves — avoids hand-clipping every element
        (circle, ticks, rotated labels, track line) against the rect.
        """
        vp = comp.get("viewport")
        if vp:
            layer = Image.new("RGBA", composite.size, (0, 0, 0, 0))
            ldraw = ImageDraw.Draw(layer)
            self._render_compassrose_unclipped(comp, layer, ldraw, canvas_h)
            vx, vy, vw, vh = self._viewport_rect_pil(comp, canvas_h)
            cropped = layer.crop((vx, vy, vx + vw, vy + vh))
            composite.alpha_composite(cropped, (vx, vy))
            # Drawn last, outside the clipped layer, only when the marker
            # has opted out of clipping — the clipped case is handled
            # inside _render_compassrose_unclipped() instead, matching the
            # runtime's scissor-block structure in vector_compass_rose.py.
            center_cfg = comp.get("center_marker")
            if center_cfg and center_cfg.get("points") and not bool(center_cfg.get("clip", True)):
                self._draw_compassrose_center_marker(comp, draw, canvas_h)
        else:
            self._render_compassrose_unclipped(comp, composite, draw, canvas_h)

    def _render_compassrose_unclipped(self, comp: dict, composite: Image.Image,
                                      draw: ImageDraw.ImageDraw, canvas_h: int) -> None:
        ctr = comp.get("center", [0, 0])
        r = float(comp.get("radius", 100))
        cx_p, cy_p = float(ctr[0]), canvas_h - float(ctr[1])

        def point_at(heading_deg: float, radius: float) -> tuple[float, float]:
            angle = math.radians(90.0 - heading_deg)
            # PIL y is flipped relative to Arcade's y-up: subtract, not add.
            return cx_p + radius * math.cos(angle), cy_p - radius * math.sin(angle)

        bg = comp.get("background_color")
        if bg is not None:
            draw.ellipse([cx_p - r, cy_p - r, cx_p + r, cy_p + r], fill=_rgba(bg))

        map_cfg = comp.get("moving_map")
        if map_cfg:
            # No live GPS position or generated nav data cache in the
            # designer — a few fixed placeholder positions around the
            # centre show each configured type's styling without
            # implying real data, same "representative, not data-driven"
            # spirit as other no-live-value previews in this file.
            self._draw_compassrose_map_placeholders(map_cfg, point_at, draw)

        if comp.get("show_line", True):
            line_w = max(1, int(round(float(comp.get("line_width", 2.0)))))
            draw.ellipse([cx_p - r, cy_p - r, cx_p + r, cy_p + r],
                         outline=_rgba(comp.get("line_color")), width=line_w)

        rings = comp.get("range_rings")
        if rings:
            # count/color/width and label are independent — a range_rings
            # block with only a label (no count) should not implicitly
            # draw a ring.
            if "count" in rings:
                ring_count = max(1, min(10, int(rings["count"])))
                ring_color = _rgba(rings.get("color"))
                ring_w = max(1, int(round(float(rings.get("width", 1.0)))))
                ring_half = rings.get("half", "full")
                spacing = r / ring_count
                for k in range(1, ring_count + 1):
                    rk = k * spacing
                    bbox = [cx_p - rk, cy_p - rk, cx_p + rk, cy_p + rk]
                    if ring_half == "top":
                        # PIL angles run clockwise from 3 o'clock in image
                        # (y-down) space, so — unlike arcade's CCW/y-up
                        # convention — the top half is 180-360, not 0-180.
                        draw.arc(bbox, 180, 360, fill=ring_color, width=ring_w)
                    elif ring_half == "bottom":
                        draw.arc(bbox, 0, 180, fill=ring_color, width=ring_w)
                    else:
                        draw.ellipse(bbox, outline=ring_color, width=ring_w)

            range_label = rings.get("label")
            if range_label:
                rl_off = range_label.get("offset", [0.0, 0.0])
                rl_x = cx_p + float(rl_off[0])
                rl_y = cy_p - float(rl_off[1])  # PIL y-down vs. Arcade y-up
                rl_size = max(8, int(float(range_label.get("font_size", 14.0))))
                rl_font = _pil_font(range_label.get("font"), rl_size,
                                    bold=bool(range_label.get("bold", False)),
                                    italic=bool(range_label.get("italic", False)))
                rl_text = str(range_label.get("format", "{:.0f}")).format(0.0)
                rl_anchor_x = {"left": "l", "center": "m", "right": "r"}.get(
                    range_label.get("anchor_x", "center"), "m")
                rl_anchor_y = {"baseline": "s", "center": "m", "top": "a", "bottom": "d"}.get(
                    range_label.get("anchor_y", "center"), "m")
                draw.text((rl_x, rl_y), rl_text, fill=_rgba(range_label.get("color")),
                         font=rl_font, anchor=rl_anchor_x + rl_anchor_y)

        tick5_len  = float(comp.get("tick5_length", 8.0))
        tick5_col  = _rgba(comp.get("tick5_color"))
        tick5_w    = max(1, int(round(float(comp.get("tick5_width", 1.0)))))
        tick5_pos  = comp.get("tick5_position", "outside")
        tick10_len = float(comp.get("tick10_length", 16.0))
        tick10_col = _rgba(comp.get("tick10_color"))
        tick10_w   = max(1, int(round(float(comp.get("tick10_width", 2.0)))))
        tick10_pos = comp.get("tick10_position", "outside")

        for h_deg in range(0, 360, 5):
            is_major = (h_deg % 10) == 0
            length   = tick10_len if is_major else tick5_len
            position = tick10_pos if is_major else tick5_pos
            color    = tick10_col if is_major else tick5_col
            width    = tick10_w if is_major else tick5_w
            r0, r1 = (r - length, r) if position == "inside" else (r, r + length)
            x0, y0 = point_at(h_deg, r0)
            x1, y1 = point_at(h_deg, r1)
            draw.line([(x0, y0), (x1, y1)], fill=color, width=width)

        label_interval = max(1, int(float(comp.get("label_interval", 30))))
        label_offset   = float(comp.get("label_offset", 20.0))
        label_position = comp.get("label_position", "inside")
        label_fmt      = comp.get("label_format", "{:02.0f}")
        label_bold = bool(comp.get("label_bold", False))
        label_italic = bool(comp.get("label_italic", False))
        font_size = max(8, int(float(comp.get("label_font_size", 14))))
        font = _pil_font(comp.get("label_font"), font_size, bold=label_bold, italic=label_italic)
        emphasize_interval = comp.get("label_emphasize_interval")
        emphasize_font = None
        if emphasize_interval:
            emphasize_interval = int(float(emphasize_interval))
            emphasize_size = max(8, int(float(comp.get("label_emphasize_font_size") or font_size)))
            emphasize_font = _pil_font(comp.get("label_font"), emphasize_size,
                                       bold=label_bold, italic=label_italic)
        label_color = _rgba(comp.get("label_color"))
        anchor_y_pil = {"baseline": "s", "center": "m", "top": "a", "bottom": "d"}.get(
            comp.get("label_anchor_y", "center"), "m")
        r_label = (r - label_offset) if label_position == "inside" else (r + label_offset)
        for h_deg in range(0, 360, label_interval):
            x, y = point_at(h_deg, r_label)
            text = label_fmt.format(h_deg / 10.0)
            use_font = (
                emphasize_font if emphasize_interval and h_deg % emphasize_interval == 0 else font
            )
            # Radial orientation: baseline tangent to the circle (perpendicular
            # to the radius), "up" pointing outward. Static preview → heading=0,
            # matching the runtime's -h rotation with heading folded in.
            self._paste_rotated_text(composite, text, use_font, label_color, x, y, -h_deg,
                                     anchor_y=anchor_y_pil)

        track_cfg = comp.get("track")
        if track_cfg:
            # No live dataref value in the static preview — show a
            # representative angle so position/length/tick are visible.
            track_angle = 10.0
            tcolor = _rgba(track_cfg.get("color", [0, 255, 0, 255]))
            twidth = max(1, int(round(float(track_cfg.get("width", 2.0)))))
            tstart = float(track_cfg.get("start", 0.0))
            tend = float(track_cfg.get("end", r))
            x0, y0 = point_at(track_angle, tstart)
            x1, y1 = point_at(track_angle, tend)
            draw.line([(x0, y0), (x1, y1)], fill=tcolor, width=twidth)
            tick_pos = track_cfg.get("tick_position")
            if tick_pos is not None:
                tick_len = float(track_cfg.get("tick_length", 20.0))
                tx, ty = point_at(track_angle, float(tick_pos))
                line_angle = math.radians(90.0 - track_angle)  # heading=0 for static preview
                perp = line_angle + math.pi / 2.0
                half = tick_len / 2.0
                # point_at() subtracts the sin term (PIL y is flipped vs. Arcade);
                # match that convention for this offset too.
                dx, dy = half * math.cos(perp), half * math.sin(perp)
                draw.line([(tx - dx, ty + dy), (tx + dx, ty - dy)], fill=tcolor, width=twidth)

        bug_cfg = comp.get("heading_bug")
        if bug_cfg and bug_cfg.get("points"):
            # No live dataref value in the static preview — show a
            # representative angle so position/orientation are visible.
            bug_heading = 20.0
            bug_radius = float(bug_cfg.get("radius", comp.get("radius", r)))
            bcx, bcy = point_at(bug_heading, bug_radius)
            # Rotate the bug's local points the same way point_at() derives
            # position (heading=0 for the static preview, so the runtime's
            # `heading - bug_heading` reduces to `-bug_heading`); PIL y is
            # flipped vs. Arcade, so negate the rotated Y offset only (same
            # rule the track tick above uses for its perpendicular offset).
            angle = math.radians(-bug_heading)
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            bug_pts = []
            for px, py in bug_cfg["points"]:
                rx = px * cos_a - py * sin_a
                ry = px * sin_a + py * cos_a
                bug_pts.append((bcx + rx, bcy - ry))
            bcolor = _rgba(bug_cfg.get("color"))
            if bool(bug_cfg.get("filled", True)):
                draw.polygon(bug_pts, fill=bcolor)
                boc = bug_cfg.get("outline_color")
                if boc is not None:
                    bow = max(1, int(round(float(bug_cfg.get("outline_width", 1.0)))))
                    draw.polygon(bug_pts, outline=_rgba(boc), width=bow)
            else:
                bwidth = max(1, int(round(float(bug_cfg.get("width", 1.0)))))
                draw.line(bug_pts + [bug_pts[0]], fill=bcolor, width=bwidth)

        marker_cfg = comp.get("heading_marker")
        if marker_cfg and marker_cfg.get("points"):
            # Fixed top-dead-centre, heading=0 for the static preview — no
            # rotation (the marker never turns). Points are y-up like the
            # rest of the schema; negate only the Y offset to match PIL's
            # y-down space (same rule used above for the bug/track offsets).
            marker_radius = float(marker_cfg.get("radius", comp.get("radius", r)))
            mcx, mcy = point_at(0.0, marker_radius)
            marker_pts = [(mcx + px, mcy - py) for px, py in marker_cfg["points"]]
            mcolor = _rgba(marker_cfg.get("color"))
            if bool(marker_cfg.get("filled", True)):
                draw.polygon(marker_pts, fill=mcolor)
                moc = marker_cfg.get("outline_color")
                if moc is not None:
                    mow = max(1, int(round(float(marker_cfg.get("outline_width", 1.0)))))
                    draw.polygon(marker_pts, outline=_rgba(moc), width=mow)
            else:
                mwidth = max(1, int(round(float(marker_cfg.get("width", 1.0)))))
                draw.line(marker_pts + [marker_pts[0]], fill=mcolor, width=mwidth)

        center_cfg = comp.get("center_marker")
        if center_cfg and center_cfg.get("points") and (
            comp.get("viewport") is None or bool(center_cfg.get("clip", True))
        ):
            self._draw_compassrose_center_marker(comp, draw, canvas_h)

        # Representative angles, one per pointer, staggered so multiple
        # pointers don't overlap in the static preview (no live dataref
        # value here, unlike heading_bug which only ever has one) — kept
        # close to top-dead-centre (like heading_bug's own 20° and
        # heading_marker's 0°) rather than spread across a wide arc, since a
        # wide-radius rose puts far-from-vertical angles well outside the
        # instrument's own canvas bounds (e.g. radius=400 at 60° can land
        # 340+px off-centre horizontally), making the pointer invisible in
        # the preview even though it renders fine at runtime. `preview_angle`
        # overrides this per-pointer when the user has set one explicitly —
        # designer-only, no effect on the running panel.
        for idx, pointer_cfg in enumerate(comp.get("bearing_pointers") or []):
            if not pointer_cfg.get("points"):
                continue
            if "preview_angle" in pointer_cfg:
                p_angle = float(pointer_cfg["preview_angle"])
            else:
                step = 10.0 + 20.0 * (idx // 2)
                p_angle = -step if idx % 2 == 0 else step
            self._draw_compassrose_pointer_shape(
                point_at, draw, p_angle, r + float(pointer_cfg.get("offset", 0.0)),
                pointer_cfg["points"], pointer_cfg.get("color"),
                bool(pointer_cfg.get("filled", True)), pointer_cfg.get("width", 1.0),
                pointer_cfg.get("outline_color"), pointer_cfg.get("outline_width", 1.0),
            )
            tail_cfg = pointer_cfg.get("tail")
            if tail_cfg and tail_cfg.get("points"):
                # Diametrically opposite the head, same representative angle
                # + 180°, sharing the head's preview_angle.
                self._draw_compassrose_pointer_shape(
                    point_at, draw, p_angle + 180.0, r + float(tail_cfg.get("offset", 0.0)),
                    tail_cfg["points"], tail_cfg.get("color"),
                    bool(tail_cfg.get("filled", True)), tail_cfg.get("width", 1.0),
                    tail_cfg.get("outline_color"), tail_cfg.get("outline_width", 1.0),
                )

        cdi_cfg = comp.get("course_deviation_indicator")
        if cdi_cfg:
            # 0° (straight up) default for the static preview — no live
            # dataref value here, and head/tail start/end are typically
            # small relative to the rose radius (near the centre), so unlike
            # bearing_pointers there's little risk of landing off-canvas
            # regardless of angle; 0° just matches heading_marker's own
            # simplest-case convention. `preview_angle` overrides this when
            # the user has set one explicitly — designer-only, no effect on
            # the running panel.
            cdi_angle = float(cdi_cfg.get("preview_angle", 0.0))
            self._draw_compassrose_cdi_segment(point_at, draw, cdi_angle, cdi_cfg.get("head") or {}, r)
            self._draw_compassrose_cdi_segment(point_at, draw, cdi_angle + 180.0, cdi_cfg.get("tail") or {}, r)

            devbar_cfg = cdi_cfg.get("deviation_bar")
            if devbar_cfg and devbar_cfg.get("points"):
                # No live dataref value here either — a representative
                # translation (a third of the rose radius, by default) shows
                # the bar visibly off-centre for layout purposes, same
                # spirit as heading_bug/track's own representative-angle
                # previews. `preview_deviation` overrides this when the user
                # has set one explicitly — designer-only, no effect on the
                # running panel.
                preview_px = float(devbar_cfg.get("preview_deviation", r / 3.0))
                self._draw_compassrose_deviation_bar(
                    point_at, draw, cdi_angle, preview_px, devbar_cfg,
                )

            markers_cfg = cdi_cfg.get("deviation_markers")
            if markers_cfg:
                self._draw_compassrose_deviation_markers(point_at, draw, cdi_angle, markers_cfg)

    def _draw_compassrose_deviation_markers(
        self, point_at, draw: ImageDraw.ImageDraw, cdi_angle: float, markers_cfg: dict,
    ) -> None:
        spacing = float(markers_cfg.get("spacing", 40.0))
        size = float(markers_cfg.get("size", 4.0))
        width = max(1, int(round(float(markers_cfg.get("width", 2.0)))))
        color = _rgba(markers_cfg.get("color"))
        shape = markers_cfg.get("shape", "circle")
        angle = math.radians(-cdi_angle)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        for k in (-2, -1, 1, 2):
            mx, my = point_at(cdi_angle + 90.0, k * spacing)
            if shape == "tick":
                x0, y0 = mx + size * sin_a, my + size * cos_a
                x1, y1 = mx - size * sin_a, my - size * cos_a
                draw.line([(x0, y0), (x1, y1)], fill=color, width=width)
            else:
                draw.ellipse([mx - size, my - size, mx + size, my + size], outline=color, width=width)

    def _draw_compassrose_deviation_bar(
        self, point_at, draw: ImageDraw.ImageDraw, cdi_angle: float,
        deviation_px: float, devbar_cfg: dict,
    ) -> None:
        # Translates perpendicular to the course line (cdi_angle + 90°) but
        # its own points are oriented ALONG the course line (cdi_angle) —
        # same decoupled position/rotation angle as the runtime's
        # _draw_deviation_bar(), so this can't reuse
        # _draw_compassrose_pointer_shape (which assumes both angles match).
        pcx, pcy = point_at(cdi_angle + 90.0, deviation_px)
        angle = math.radians(-cdi_angle)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        pts = []
        for px, py in devbar_cfg["points"]:
            rx = px * cos_a - py * sin_a
            ry = px * sin_a + py * cos_a
            pts.append((pcx + rx, pcy - ry))
        color = _rgba(devbar_cfg.get("color"))
        if bool(devbar_cfg.get("filled", True)):
            draw.polygon(pts, fill=color)
            oc = devbar_cfg.get("outline_color")
            if oc is not None:
                ow = max(1, int(round(float(devbar_cfg.get("outline_width", 1.0)))))
                draw.polygon(pts, outline=_rgba(oc), width=ow)
        else:
            width = max(1, int(round(float(devbar_cfg.get("width", 1.0)))))
            draw.line(pts + [pts[0]], fill=color, width=width)

    def _draw_compassrose_cdi_segment(
        self, point_at, draw: ImageDraw.ImageDraw, bearing_deg: float,
        seg_cfg: dict, default_radius: float,
    ) -> None:
        start = float(seg_cfg.get("start", 0.0))
        end = float(seg_cfg.get("end", default_radius))
        x0, y0 = point_at(bearing_deg, start)
        x1, y1 = point_at(bearing_deg, end)
        color = _rgba(seg_cfg.get("color"))
        width = max(1, int(round(float(seg_cfg.get("width", 2.0)))))
        dash = seg_cfg.get("dash")
        drew_dashed = False
        if dash:
            on, off = float(dash[0]), float(dash[1])
            period = on + off
            total = math.hypot(x1 - x0, y1 - y0)
            if period > 0 and total > 0:
                ux, uy = (x1 - x0) / total, (y1 - y0) / total
                d = 0.0
                while d < total:
                    seg_end = min(d + on, total)
                    draw.line([(x0 + ux * d, y0 + uy * d), (x0 + ux * seg_end, y0 + uy * seg_end)],
                              fill=color, width=width)
                    d += period
                drew_dashed = True
        if not drew_dashed:
            draw.line([(x0, y0), (x1, y1)], fill=color, width=width)
        symbol_cfg = seg_cfg.get("symbol")
        if symbol_cfg and symbol_cfg.get("points"):
            # symbol_offset is px from the rose centre (same units as
            # start/end), unlike bearing_pointers' offset-from-circle, so
            # pass it straight through as the radius argument.
            self._draw_compassrose_pointer_shape(
                point_at, draw, bearing_deg, float(symbol_cfg.get("offset", 0.0)),
                symbol_cfg["points"], symbol_cfg.get("color"),
                bool(symbol_cfg.get("filled", True)), symbol_cfg.get("width", 1.0),
                symbol_cfg.get("outline_color"), symbol_cfg.get("outline_width", 1.0),
            )

    def _draw_compassrose_map_placeholders(self, map_cfg: dict, point_at, draw: ImageDraw.ImageDraw) -> None:
        # One representative position per configured type, spread around
        # the centre so they don't overlap — no live GPS position or
        # generated nav data cache in the designer, so this only previews
        # each type's own styling, not real placement.
        for type_name, bearing_deg, placeholder_ident in (
            ("airport", 45.0, "APT"), ("vor", 135.0, "VOR"), ("ndb", 225.0, "NDB"),
            ("waypoint", 315.0, "WPT"),
        ):
            style_cfg = map_cfg.get(type_name)
            circle_cfg = (style_cfg or {}).get("circle")
            if not style_cfg or (not style_cfg.get("points") and not circle_cfg):
                continue
            radius = 40.0
            # Fill and outline are independent — either, both, or neither
            # can be enabled, each with its own color (outline also its
            # own width). Same convention for the circle and the polygon.
            if circle_cfg and circle_cfg.get("radius"):
                cx, cy = point_at(bearing_deg, radius)
                r = float(circle_cfg["radius"])
                bbox = (cx - r, cy - r, cx + r, cy + r)
                if bool(circle_cfg.get("filled", True)):
                    draw.ellipse(bbox, fill=_rgba(circle_cfg.get("color")))
                if circle_cfg.get("outline"):
                    ow = max(1, int(round(float(circle_cfg.get("outline_width", 1.0)))))
                    draw.ellipse(bbox, outline=_rgba(circle_cfg.get("outline_color")), width=ow)
            if style_cfg.get("points"):
                self._draw_compassrose_map_symbol_shape(
                    point_at, draw, bearing_deg, radius,
                    style_cfg["points"],
                    bool(style_cfg.get("filled", True)), style_cfg.get("color"),
                    bool(style_cfg.get("outline", False)),
                    style_cfg.get("outline_color"), style_cfg.get("outline_width", 1.0),
                )
            if style_cfg.get("label"):
                lx, ly = point_at(bearing_deg, radius)
                loff = style_cfg.get("label_offset", [6.0, 0.0])
                lx += float(loff[0]); ly -= float(loff[1])  # PIL y-down vs. Arcade y-up
                size = max(6, int(float(style_cfg.get("label_font_size", 10.0))))
                font = _pil_font(style_cfg.get("label_font"), size)
                draw.text((lx, ly), placeholder_ident,
                          fill=_rgba(style_cfg.get("label_color", [255, 255, 255, 255])),
                          font=font, anchor="lm")

    def _draw_compassrose_map_symbol_shape(
        self, point_at, draw: ImageDraw.ImageDraw, bearing_deg: float, radius: float,
        points: list, filled: bool, color, outline: bool, outline_color, outline_width,
    ) -> None:
        # Map symbols are screen-fixed (unlike bearing_pointers' radial
        # needles) — heading=0 in the static preview, so screen-fixed means
        # no rotation at all here; bearing_deg is only used for placement
        # via point_at(), matching the runtime's own decoupling of symbol
        # position from symbol rotation. Fill and outline are independent.
        pcx, pcy = point_at(bearing_deg, radius)
        pts = [(pcx + px, pcy - py) for px, py in points]
        if filled:
            draw.polygon(pts, fill=_rgba(color))
        if outline:
            ow = max(1, int(round(float(outline_width))))
            draw.polygon(pts, outline=_rgba(outline_color), width=ow)

    def _draw_compassrose_pointer_shape(
        self, point_at, draw: ImageDraw.ImageDraw, bearing_deg: float, radius: float,
        points: list, color, filled: bool, width, outline_color, outline_width,
    ) -> None:
        # Shared by bearing_pointers' head and tail — same derivation as
        # heading_bug's own preview block: heading=0 for the static preview,
        # so the runtime's `heading - angle` reduces to `-angle`.
        pcx, pcy = point_at(bearing_deg, radius)
        angle = math.radians(-bearing_deg)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        pts = []
        for px, py in points:
            rx = px * cos_a - py * sin_a
            ry = px * sin_a + py * cos_a
            pts.append((pcx + rx, pcy - ry))
        rgba = _rgba(color)
        if filled:
            draw.polygon(pts, fill=rgba)
            if outline_color is not None:
                ow = max(1, int(round(float(outline_width))))
                draw.polygon(pts, outline=_rgba(outline_color), width=ow)
        else:
            lw = max(1, int(round(float(width))))
            draw.line(pts + [pts[0]], fill=rgba, width=lw)

    def _draw_compassrose_center_marker(self, comp: dict, draw: ImageDraw.ImageDraw,
                                         canvas_h: int) -> None:
        center_cfg = comp["center_marker"]
        ctr = comp.get("center", [0, 0])
        cx_p, cy_p = float(ctr[0]), canvas_h - float(ctr[1])
        # Fixed directly at the rose centre — no radius offset, no rotation.
        # Points are y-up like the rest of the schema; negate only the Y
        # offset to match PIL's y-down space (same rule used for the bug/
        # heading-marker offsets above).
        pts = [(cx_p + px, cy_p - py) for px, py in center_cfg["points"]]
        color = _rgba(center_cfg.get("color"))
        if bool(center_cfg.get("filled", True)):
            draw.polygon(pts, fill=color)
            oc = center_cfg.get("outline_color")
            if oc is not None:
                ow = max(1, int(round(float(center_cfg.get("outline_width", 1.0)))))
                draw.polygon(pts, outline=_rgba(oc), width=ow)
        else:
            width = max(1, int(round(float(center_cfg.get("width", 1.0)))))
            draw.line(pts + [pts[0]], fill=color, width=width)

    def _render_filledrect(self, comp: dict, composite: Image.Image,
                           draw: ImageDraw.ImageDraw, canvas_h: int) -> None:
        pos = comp.get("position", [0, 0]); sz = comp.get("size", [100, 100])
        cx_p, cy_p = int(pos[0]), canvas_h - int(pos[1])
        hw, hh = int(sz[0]) // 2, int(sz[1]) // 2
        bbox = [cx_p - hw, cy_p - hh, cx_p + hw, cy_p + hh]
        # Draw on a transparent layer and alpha_composite onto the background so
        # that fill colors with alpha < 255 (including alpha=0) composite correctly
        # instead of punching holes through to the Qt widget background.
        layer = Image.new("RGBA", composite.size, (0, 0, 0, 0))
        ldraw = ImageDraw.Draw(layer)
        ldraw.rectangle(bbox, fill=_rgba(comp.get("color")))
        oc = comp.get("outline_color")
        if oc is not None:
            ow = max(1, int(round(float(comp.get("outline_width", 1.0)))))
            ldraw.rectangle(bbox, outline=_rgba(oc), width=ow)
        composite.alpha_composite(layer)
        self._crosshair(draw, cx_p, cy_p)

    def _render_polygon(self, comp: dict, draw: ImageDraw.ImageDraw, canvas_h: int) -> None:
        pts_raw = comp.get("points", [])
        if len(pts_raw) < 2:
            return
        orig_xy = comp.get("origin", [0, 0])
        ox, oy = int(orig_xy[0]), int(orig_xy[1])
        pts = [(ox + int(p[0]), canvas_h - (oy + int(p[1]))) for p in pts_raw]
        color = _rgba(comp.get("color"))
        if comp.get("filled", True):
            draw.polygon(pts, fill=color)
            oc = comp.get("outline_color")
            if oc is not None:
                ow = max(1, int(round(float(comp.get("outline_width", 1.0)))))
                draw.polygon(pts, outline=_rgba(oc), width=ow)
        else:
            width = max(1, int(round(float(comp.get("width", 1.0)))))
            draw.line(pts + [pts[0]], fill=color, width=width)

        # Crosshair on origin
        self._crosshair(draw, ox, canvas_h - oy)

        # Crosshair on whichever point is selected in the Points table
        # (only while this Polygon is the selected component) — distinct
        # style from the origin's crosshair above.
        if comp.get("name") == self._selected_name and 0 <= self._selected_point_idx < len(pts):
            px, py = pts[self._selected_point_idx]
            self._point_crosshair(draw, px, py)

    def _render_rotary_encoder(self, comp: dict, composite: Image.Image,
                               draw: ImageDraw.ImageDraw, canvas_h: int) -> None:
        """Render background + face textures (if set), then overlay markers."""
        pos = comp.get("position", [0, 0])
        sz  = comp.get("size", [60, 60])
        cx_p = int(pos[0]); cy_p = canvas_h - int(pos[1])
        tw, th = int(sz[0]), int(sz[1])
        hw, hh = tw // 2, th // 2
        x0, y0 = cx_p - hw, cy_p - hh
        x1, y1 = cx_p + hw, cy_p + hh

        # Background texture — fills component size
        bg_tex = comp.get("background_texture", "")
        if bg_tex:
            try:
                atlas = self._load_atlas(bg_tex)
                ox, oy = comp.get("background_origin", [0, 0])
                cw, ch = comp.get("background_cliprect", [tw, th])
                region = atlas.crop((ox, oy, ox + cw, oy + ch)).resize(
                    (tw, th), Image.LANCZOS
                )
                composite.paste(region, (x0, y0), region)
            except Exception:
                pass

        # Face texture — may have its own size and centre offset
        face_tex = comp.get("face_texture", "")
        face_off = comp.get("face_offset", [0, 0])
        fox, foy = int(face_off[0]), int(face_off[1])
        face_sz  = comp.get("face_size", sz)
        fw, fh   = int(face_sz[0]), int(face_sz[1])
        # face_offset is y-up; convert to PIL (y-down) by negating y component
        face_cx_p = cx_p + fox
        face_cy_p = cy_p - foy
        if face_tex:
            try:
                atlas = self._load_atlas(face_tex)
                ox, oy = comp.get("face_origin", [0, 0])
                cw, ch = comp.get("face_cliprect", [fw, fh])
                region = atlas.crop((ox, oy, ox + cw, oy + ch)).resize(
                    (fw, fh), Image.LANCZOS
                )
                composite.paste(region, (face_cx_p - fw // 2, face_cy_p - fh // 2), region)
            except Exception as _exc:
                print(f"[canvas RotaryEncoder face] {_exc}", flush=True)

        # Face bounding box (light-blue dashed) — shows face_size in canvas
        if face_tex:
            FACE_BOX = (80, 180, 255, 160)
            fx0 = face_cx_p - fw // 2; fy0 = face_cy_p - fh // 2
            fx1 = fx0 + fw;            fy1 = fy0 + fh
            dash2, gap2 = 4, 3
            for seg_x in range(fx0, fx1, dash2 + gap2):
                x_end = min(seg_x + dash2, fx1)
                draw.line([(seg_x, fy0), (x_end, fy0)], fill=FACE_BOX, width=1)
                draw.line([(seg_x, fy1), (x_end, fy1)], fill=FACE_BOX, width=1)
            for seg_y in range(fy0, fy1, dash2 + gap2):
                y_end = min(seg_y + dash2, fy1)
                draw.line([(fx0, seg_y), (fx0, y_end)], fill=FACE_BOX, width=1)
                draw.line([(fx1, seg_y), (fx1, y_end)], fill=FACE_BOX, width=1)
        # Dashed outline overlay (component bounding box — always shown)
        DASH = (100, 180, 100, 180)
        dash, gap = 6, 4
        for seg_x in range(x0, x1, dash + gap):
            x_end = min(seg_x + dash, x1)
            draw.line([(seg_x, y0), (x_end, y0)], fill=DASH, width=1)
            draw.line([(seg_x, y1), (x_end, y1)], fill=DASH, width=1)
        for seg_y in range(y0, y1, dash + gap):
            y_end = min(seg_y + dash, y1)
            draw.line([(x0, seg_y), (x0, y_end)], fill=DASH, width=1)
            draw.line([(x1, seg_y), (x1, y_end)], fill=DASH, width=1)

        # Centre divider (shows left/right tap halves)
        draw.line([(cx_p, y0 + 2), (cx_p, y1 - 2)],
                  fill=(100, 180, 100, 100), width=1)

        # Label when no textures are set
        if not bg_tex and not face_tex:
            font = ImageFont.load_default()
            label = "ROT"
            try:
                bbox = draw.textbbox((0, 0), label, font=font)
                tw2 = bbox[2] - bbox[0]; th2 = bbox[3] - bbox[1]
            except Exception:
                tw2, th2 = len(label) * 6, 10
            draw.text((cx_p - tw2 // 2, cy_p - th2 // 2), label,
                      fill=(100, 180, 100, 160), font=font)

        # Component centre crosshair (yellow)
        self._crosshair(draw, cx_p, cy_p)

        # Face centre cross (white) — shows where the face texture is anchored
        if face_tex:
            FACE_C = (255, 255, 255, 210)
            arm = 8
            draw.line([(face_cx_p - arm, face_cy_p), (face_cx_p + arm, face_cy_p)],
                      fill=FACE_C, width=1)
            draw.line([(face_cx_p, face_cy_p - arm), (face_cx_p, face_cy_p + arm)],
                      fill=FACE_C, width=1)

        # Rotation centre marker (cyan) — only when non-zero offset
        face_rc = comp.get("face_rotation_center", [0, 0])
        rcx, rcy = int(face_rc[0]), int(face_rc[1])
        if rcx != 0 or rcy != 0:
            rc_cx_p = cx_p + rcx
            rc_cy_p = cy_p - rcy
            ROT_C = (0, 200, 255, 210)
            arm = 6
            draw.line([(rc_cx_p - arm, rc_cy_p), (rc_cx_p + arm, rc_cy_p)],
                      fill=ROT_C, width=1)
            draw.line([(rc_cx_p, rc_cy_p - arm), (rc_cx_p, rc_cy_p + arm)],
                      fill=ROT_C, width=1)
            draw.ellipse([rc_cx_p - 4, rc_cy_p - 4, rc_cx_p + 4, rc_cy_p + 4],
                         outline=ROT_C, width=1)

    def _render_vector(self, comp: dict, draw: ImageDraw.ImageDraw, canvas_h: int) -> None:
        pos = comp.get("position", [0, 0])
        ox_p = int(pos[0]); oy_p = canvas_h - int(pos[1])
        dir_cfg = comp.get("direction", 0.0)
        dir_deg = float(dir_cfg) if not isinstance(dir_cfg, dict) else 0.0
        len_cfg = comp.get("length", 50.0)
        length = float(len_cfg) if not isinstance(len_cfg, dict) else 50.0
        if length == 0:
            return
        dir_rad = math.radians(dir_deg)
        sign = 1.0 if length >= 0 else -1.0
        # Absolute tip position in PIL space (y-axis inverted vs Arcade)
        ex_p = ox_p + length * math.cos(dir_rad)
        ey_p = oy_p - length * math.sin(dir_rad)
        color = _rgba(comp.get("color"))
        width = max(1, int(round(float(comp.get("width", 1.0)))))
        cap = comp.get("cap", "none")
        _cap_w = float(comp.get("cap_width", 10.0))
        _cap_h = float(comp.get("cap_height", _cap_w / 2.0))
        if comp.get("hide_if_less_than_cap", False) and abs(length) < _cap_h:
            return
        # Shaft endpoint: shorten by cap height for triangle so total length is preserved
        if cap == "triangle":
            shaft_len = length - sign * _cap_h
            sx_p = ox_p + shaft_len * math.cos(dir_rad)
            sy_p = oy_p - shaft_len * math.sin(dir_rad)
        else:
            sx_p, sy_p = ex_p, ey_p
        draw.line([(ox_p, oy_p), (int(round(sx_p)), int(round(sy_p)))], fill=color, width=width)
        if cap != "none":
            half_w = _cap_w / 2.0
            cap_filled = comp.get("cap_filled", True)
            # PIL y-down: backward unit vector accounts for sign of length
            bx_p = -sign * math.cos(dir_rad)
            by_p =  sign * math.sin(dir_rad)   # PIL y-down: flipped vs Arcade
            # Perpendicular unit vector (symmetric cap — sign cancels)
            px_p = -math.sin(dir_rad)
            py_p = -math.cos(dir_rad)           # PIL y-down
            if cap == "triangle":
                p1 = (ex_p + bx_p * _cap_h + px_p * half_w,
                      ey_p + by_p * _cap_h + py_p * half_w)
                p2 = (ex_p + bx_p * _cap_h - px_p * half_w,
                      ey_p + by_p * _cap_h - py_p * half_w)
                pts = [
                    (int(round(ex_p)), int(round(ey_p))),
                    (int(round(p1[0])), int(round(p1[1]))),
                    (int(round(p2[0])), int(round(p2[1]))),
                ]
                if cap_filled:
                    draw.polygon(pts, fill=color)
                else:
                    draw.polygon(pts, outline=color)
            elif cap == "bar":
                draw.line([
                    (int(round(ex_p + px_p * half_w)), int(round(ey_p + py_p * half_w))),
                    (int(round(ex_p - px_p * half_w)), int(round(ey_p - py_p * half_w))),
                ], fill=color, width=width)

    def _render_text(self, comp: dict, draw: ImageDraw.ImageDraw, canvas_h: int) -> None:
        pos   = comp.get("position", [0, 0])
        cx_p  = int(pos[0])
        cy_p  = canvas_h - int(pos[1])
        color = _rgba(comp.get("color"))
        size  = max(8, int(float(comp.get("font_size", 12.0))))
        bold   = bool(comp.get("bold", False))
        italic = bool(comp.get("italic", False))
        font  = _pil_font(comp.get("font_name"), size, bold=bold, italic=italic)
        anchor_x = comp.get("anchor_x", "left")
        anchor_y = comp.get("anchor_y", "baseline")
        pil_x = {"left": "l", "center": "m", "right": "r"}.get(anchor_x, "l")
        pil_y = {"baseline": "s", "center": "m", "top": "a", "bottom": "d"}.get(anchor_y, "s")

        emphasize_place = comp.get("emphasize_place")
        if emphasize_place and (comp.get("dataref") or comp.get("text_format")):
            # No live dataref value in the static preview — show a
            # representative sample so the split is visible at design time.
            hi_size = max(8, int(float(comp.get("emphasize_font_size") or size)))
            hi_font = _pil_font(comp.get("font_name"), hi_size, bold=bold, italic=italic)
            sample = (10 ** int(emphasize_place)) * 12.345
            hi_text, lo_text = split_at_place(sample, emphasize_place)
            hi_w = draw.textlength(hi_text, font=hi_font)
            lo_w = draw.textlength(lo_text, font=font)
            total = hi_w + lo_w
            start = {"r": cx_p - total, "m": cx_p - total / 2}.get(pil_x, cx_p)
            try:
                draw.text((start, cy_p), hi_text, fill=color, font=hi_font, anchor="l" + pil_y)
                draw.text((start + hi_w, cy_p), lo_text, fill=color, font=font, anchor="l" + pil_y)
            except TypeError:
                draw.text((start, cy_p), hi_text, fill=color, font=hi_font)
                draw.text((start + hi_w, cy_p), lo_text, fill=color, font=font)
        else:
            char_count = comp.get("char_count")
            if char_count:
                # No live dataref value in the static preview — a run of
                # "?" the configured length previews the text's footprint
                # (useful for layout) without implying a specific value.
                text = "?" * max(1, int(char_count))
            else:
                text = comp.get("text") or comp.get("text_format") or comp.get("dataref") or "?"
            try:
                draw.text((cx_p, cy_p), str(text), fill=color, font=font, anchor=pil_x + pil_y)
            except TypeError:
                draw.text((cx_p, cy_p), str(text), fill=color, font=font)
        self._crosshair(draw, cx_p, cy_p)

    def _render_vectortape(self, comp: dict, composite: Image.Image,
                           draw: ImageDraw.ImageDraw, canvas_w: int, canvas_h: int) -> None:
        vp = comp.get("viewport")
        if not vp:
            return
        vx, vy_bottom, vw, vh = (float(v) for v in vp)
        py_top = canvas_h - vy_bottom - vh  # PIL y-down

        # Tape background — only drawn when bg_color is explicitly set (matches runtime)
        bg_raw = comp.get("bg_color")
        if bg_raw is not None:
            bg = [int(vx), int(py_top), int(vx + vw), int(py_top + vh)]
            draw.rectangle(bg, fill=_rgba(bg_raw))

        axis = comp.get("scroll_axis", "y")
        tick_side = comp.get("tick_side", "left")
        tc = _rgba(comp.get("tick_color"))
        ppu = float(comp.get("pixels_per_unit", 5.0))
        ticks = comp.get("ticks", [])

        # Anchor = viewport centre (matches runtime behaviour)
        cy_pil = canvas_h - vy_bottom - vh / 2
        cx_pil = vx + vw / 2

        if axis == "y":
            spine_x = int(vx) if tick_side == "left" else int(vx + vw)
            tick_dir = 1 if tick_side == "left" else -1
            # Bands
            for band in comp.get("bands", []):
                bc = _rgba(band.get("color"))
                bw = float(band.get("width", 8))
                bside = band.get("side") or tick_side
                boff = float(band.get("offset", 0))
                bx = int(vx + boff) if bside == "left" else int(vx + vw - bw - boff)
                dash = int(band.get("dash", 0))
                if dash > 0:
                    y, on = int(py_top), True
                    while y < int(py_top + vh):
                        seg = min(y + dash, int(py_top + vh))
                        if on:
                            draw.rectangle([bx, y, int(bx + bw) - 1, seg - 1], fill=bc)
                        y, on = seg, not on
                else:
                    draw.rectangle([bx, int(py_top), int(bx + bw), int(py_top + vh)], fill=bc)
            # Spine line
            if ticks:
                draw.line([(spine_x, int(py_top)), (spine_x, int(py_top + vh))],
                          fill=tc, width=1)
            # Tick marks — anchored to pos[1] so they align with labels
            half_range = vh / 2 / ppu
            for td in ticks:
                interval = float(td["interval"])
                length   = float(td.get("length", 15))
                tw       = max(1, int(td.get("width", 2)))
                x_off    = int(td.get("x_offset", 0))
                y_off    = int(td.get("y_offset", 0))
                tc_col   = _rgba(td["color"]) if td.get("color") else tc
                x0 = spine_x + tick_dir * x_off
                x1 = spine_x + tick_dir * (x_off + int(length))
                v = math.floor((-half_range - interval) / interval) * interval
                while v <= half_range + interval + interval * 0.001:
                    # PIL y is flipped relative to Arcade's y-up; subtract
                    # y_off so positive values nudge the tick up, matching
                    # the runtime (gauge_core/vector_tape.py).
                    y = int(cy_pil - v * ppu - y_off)
                    if int(py_top) <= y <= int(py_top + vh):
                        draw.line([(x0, y), (x1, y)], fill=tc_col, width=tw)
                    v += interval
        else:
            spine_y = int(py_top) if tick_side == "top" else int(py_top + vh)
            tick_dir = 1 if tick_side != "top" else -1
            for band in comp.get("bands", []):
                bc = _rgba(band.get("color"))
                bh = float(band.get("width", 8))
                bside = band.get("side") or tick_side
                boff = float(band.get("offset", 0))
                by = int(py_top + boff) if bside == "top" else int(py_top + vh - bh - boff)
                dash = int(band.get("dash", 0))
                if dash > 0:
                    x, on = int(vx), True
                    while x < int(vx + vw):
                        seg = min(x + dash, int(vx + vw))
                        if on:
                            draw.rectangle([x, by, seg - 1, int(by + bh) - 1], fill=bc)
                        x, on = seg, not on
                else:
                    draw.rectangle([int(vx), by, int(vx + vw), int(by + bh)], fill=bc)
            if ticks:
                draw.line([(int(vx), spine_y), (int(vx + vw), spine_y)], fill=tc, width=1)
            half_range = vw / 2 / ppu
            for td in ticks:
                interval = float(td["interval"])
                length   = float(td.get("length", 15))
                tw       = max(1, int(td.get("width", 2)))
                x_off    = int(td.get("x_offset", 0))
                y_off    = int(td.get("y_offset", 0))
                tc_col   = _rgba(td["color"]) if td.get("color") else tc
                y0 = spine_y + tick_dir * y_off
                y1 = spine_y + tick_dir * (y_off + int(length))
                v = math.floor((-half_range - interval) / interval) * interval
                while v <= half_range + interval + interval * 0.001:
                    x = int(cx_pil + v * ppu + x_off)
                    if int(vx) <= x <= int(vx + vw):
                        draw.line([(x, y0), (x, y1)], fill=tc_col, width=tw)
                    v += interval

        # Bugs — shown at their static value; dataref bugs shown at value 0 (unknown in preview)
        for bug in comp.get("bugs", []):
            val_cfg = bug.get("value", 0.0)
            bug_val = float(val_cfg) if not isinstance(val_cfg, dict) else 0.0
            bc = _rgba(bug.get("color", [255, 200, 0, 255]))
            bug_filled = bool(bug.get("filled", True))
            bug_lw = max(1, int(round(float(bug.get("width", 2.0)))))
            pts_raw = bug.get("points", [])
            if len(pts_raw) < 3:
                continue
            if axis == "y":
                sp_x = int(vx) if tick_side == "left" else int(vx + vw)
                anchor_y = int(round(cy_pil - bug_val * ppu))
                anchor_y = max(int(py_top), min(int(py_top + vh), anchor_y))
                pts = [(int(round(sp_x + p[0])), int(round(anchor_y - p[1])))
                       for p in pts_raw]
            else:
                sp_y = int(py_top) if tick_side == "top" else int(py_top + vh)
                anchor_x = int(round(cx_pil + bug_val * ppu))
                anchor_x = max(int(vx), min(int(vx + vw), anchor_x))
                pts = [(int(round(anchor_x + p[0])), int(round(sp_y - p[1])))
                       for p in pts_raw]
            if bug_filled:
                draw.polygon(pts, fill=bc)
            else:
                draw.polygon(pts, outline=bc, width=bug_lw)

        # Labels
        labels = comp.get("labels") or {}
        label_interval = float(labels.get("interval", 0))
        if label_interval > 0:
            label_offset = float(labels.get("offset", 8))
            label_color  = _rgba(labels.get("color", [255, 255, 255, 255]))
            label_fmt    = labels.get("format", "{:.0f}")
            wrap         = comp.get("wrap")
            font_size    = max(8, int(float(labels.get("font_size", 18))))
            lbl_bold     = bool(labels.get("bold", False))
            lbl_italic   = bool(labels.get("italic", False))
            font         = _pil_font(labels.get("font"), font_size, bold=lbl_bold, italic=lbl_italic)
            emphasize_place = labels.get("emphasize_place")
            hi_font = None
            if emphasize_place:
                hi_size = max(8, int(float(labels.get("emphasize_font_size") or font_size)))
                hi_font = _pil_font(labels.get("font"), hi_size, bold=lbl_bold, italic=lbl_italic)

            # Sub-image exactly the size of the viewport — matches the OpenGL
            # scissor rectangle used at runtime, clipping in both axes.
            clip_w = max(1, int(vw))
            clip_h = max(1, int(vh))
            clip_img = Image.new("RGBA", (clip_w, clip_h), (0, 0, 0, 0))
            ldraw = ImageDraw.Draw(clip_img)

            if axis == "y":
                label_side = labels.get("side") or tick_side
                spine_x = int(vx) if tick_side == "left" else int(vx + vw)
                if label_side == "left":
                    lx = spine_x - int(label_offset)
                    default_justify = "r"
                else:
                    lx = spine_x + int(label_offset)
                    default_justify = "l"
                justify = {"left": "l", "center": "m", "right": "r"}.get(labels.get("justify"), default_justify)
                pil_anchor = justify + "m"
                lx_clip = lx - int(vx)  # x in clip_img coords
                half_range = vh / 2 / ppu
                v = math.floor((-half_range - label_interval) / label_interval) * label_interval
                v_max = half_range + label_interval
                while v <= v_max + label_interval * 0.001:
                    y_local = int(cy_pil - v * ppu) - int(py_top)
                    if -font_size <= y_local <= clip_h + font_size:
                        display = v % wrap if wrap else v
                        if emphasize_place:
                            hi_text, lo_text = split_at_place(display, emphasize_place)
                            hi_w = ldraw.textlength(hi_text, font=hi_font)
                            lo_w = ldraw.textlength(lo_text, font=font)
                            total = hi_w + lo_w
                            start = {"r": lx_clip - total, "m": lx_clip - total / 2}.get(justify, lx_clip)
                            try:
                                ldraw.text((start, y_local), hi_text, fill=label_color,
                                           font=hi_font, anchor="lm")
                                ldraw.text((start + hi_w, y_local), lo_text, fill=label_color,
                                           font=font, anchor="lm")
                            except TypeError:
                                ldraw.text((start, y_local), hi_text, fill=label_color, font=hi_font)
                                ldraw.text((start + hi_w, y_local), lo_text, fill=label_color, font=font)
                        else:
                            text = label_fmt.format(display)
                            try:
                                ldraw.text((lx_clip, y_local), text, fill=label_color,
                                           font=font, anchor=pil_anchor)
                            except TypeError:
                                ldraw.text((lx_clip, y_local), text, fill=label_color,
                                           font=font)
                    v += label_interval
                composite.paste(clip_img, (int(vx), int(py_top)), mask=clip_img)
            else:
                label_side = labels.get("side") or tick_side
                spine_y = int(py_top) if tick_side == "top" else int(py_top + vh)
                if label_side == "top":
                    ly_base = spine_y - int(label_offset)
                    default_justify = "b"
                else:
                    ly_base = spine_y + int(label_offset)
                    default_justify = "t"
                justify = {"top": "t", "center": "m", "bottom": "b"}.get(labels.get("justify"), default_justify)
                pil_anchor = "m" + justify
                ly_clip = ly_base - int(py_top)  # y in clip_img coords
                half_range = vw / 2 / ppu
                v = math.floor((-half_range - label_interval) / label_interval) * label_interval
                v_max = half_range + label_interval
                while v <= v_max + label_interval * 0.001:
                    x_local = int(cx_pil + v * ppu) - int(vx)
                    if -font_size <= x_local <= clip_w + font_size:
                        display = v % wrap if wrap else v
                        if emphasize_place:
                            hi_text, lo_text = split_at_place(display, emphasize_place)
                            hi_w = ldraw.textlength(hi_text, font=hi_font)
                            lo_w = ldraw.textlength(lo_text, font=font)
                            start = x_local - (hi_w + lo_w) / 2  # always centered on the tick
                            try:
                                ldraw.text((start, ly_clip), hi_text, fill=label_color,
                                           font=hi_font, anchor="l" + justify)
                                ldraw.text((start + hi_w, ly_clip), lo_text, fill=label_color,
                                           font=font, anchor="l" + justify)
                            except TypeError:
                                ldraw.text((start, ly_clip), hi_text, fill=label_color, font=hi_font)
                                ldraw.text((start + hi_w, ly_clip), lo_text, fill=label_color, font=font)
                        else:
                            text = label_fmt.format(display)
                            try:
                                ldraw.text((x_local, ly_clip), text, fill=label_color,
                                           font=font, anchor=pil_anchor)
                            except TypeError:
                                ldraw.text((x_local, ly_clip), text, fill=label_color,
                                           font=font)
                    v += label_interval
                composite.paste(clip_img, (int(vx), int(py_top)), mask=clip_img)

        # Viewport border
        draw.rectangle([int(vx), int(py_top), int(vx + vw - 1), int(py_top + vh - 1)],
                       outline=(80, 80, 150, 255), width=1)

        # Position marker (where current value sits)
        mx, my = int(cx_pil), int(cy_pil)
        draw.line([(mx - 8, my), (mx + 8, my)], fill=(255, 200, 0, 255), width=1)
        draw.line([(mx, my - 8), (mx, my + 8)], fill=(255, 200, 0, 255), width=1)

    def _render_ai(self, comp: dict, composite: Image.Image,
                   draw: ImageDraw.ImageDraw, canvas_w: int, canvas_h: int) -> None:
        vp = comp.get("viewport")
        if not vp:
            return
        vx, vy_bottom, vw, vh = (float(v) for v in vp)
        py_top = canvas_h - vy_bottom - vh  # PIL top edge (y-down)

        sky_c = _rgba(comp.get("sky_color",    [0, 100, 180]))
        gnd_c = _rgba(comp.get("ground_color", [100, 60, 10]))
        hor_c = _rgba(comp.get("horizon_color"))
        ldr_c = _rgba(comp.get("ladder_color"))
        arc_c = _rgba(comp.get("bank_arc_color"))
        ptr_c = _rgba(comp.get("roll_pointer_color"))
        hor_w = max(1, int(float(comp.get("horizon_width", 3))))
        ldr_w = max(1, int(float(comp.get("ladder_width", 2))))
        arc_w = max(1, int(float(comp.get("bank_arc_width", 2))))
        ppu   = float(comp.get("pixels_per_degree", 8.0))
        arc_r_raw = float(comp.get("bank_arc_radius", 0.0))
        arc_r = arc_r_raw if arc_r_raw > 0 else 0.45 * min(vw, vh)
        arc_y_offset = float(comp.get("bank_arc_y_offset", 0.0))
        show_arc_line  = bool(comp.get("show_arc_line",  comp.get("show_bank_arc", True)))
        show_arc_ticks = bool(comp.get("show_arc_ticks", comp.get("show_bank_arc", True)))
        _ptr_sz     = float(comp.get("roll_pointer_size", 12.0))
        ptr_h       = float(comp.get("roll_pointer_height", _ptr_sz))
        ptr_w       = float(comp.get("roll_pointer_width",  _ptr_sz))
        ptr_filled  = bool(comp.get("roll_pointer_filled", True))
        ptr_inward  = bool(comp.get("roll_pointer_inward", True))
        ptr_line_w  = max(1, int(float(comp.get("roll_pointer_line_width", 2.0))))
        ptr_y_off   = float(comp.get("roll_pointer_y_offset", 0.0))
        font_sz = max(8, int(comp.get("label_font_size", 14)))
        font  = _pil_font(comp.get("ladder_font_name") or None, font_sz,
                          bold=bool(comp.get("ladder_bold", False)),
                          italic=bool(comp.get("ladder_italic", False)))

        clip_w = max(1, int(vw))
        clip_h = max(1, int(vh))
        ci = Image.new("RGBA", (clip_w, clip_h), (0, 0, 0, 0))
        cd = ImageDraw.Draw(ci)

        cx_c = clip_w / 2.0
        cy_c = clip_h / 2.0

        # Sky / ground background (static preview, bank=0, pitch=0)
        cd.rectangle([0, 0, clip_w - 1, int(cy_c)], fill=sky_c)
        cd.rectangle([0, int(cy_c), clip_w - 1, clip_h - 1], fill=gnd_c)

        # Pitch ladder
        half_vw = vw / 2.0
        ladder_step = float(comp.get("ladder_step", 5.0))
        hw_4 = half_vw * float(comp.get("ladder_hw_4", 0.40))
        hw_2 = half_vw * float(comp.get("ladder_hw_2", 0.31))
        hw_1 = half_vw * float(comp.get("ladder_hw_1", 0.22))
        n_steps = round(90.0 / ladder_step)
        for i in range(-n_steps, n_steps + 1):
            if i == 0:
                continue
            p_deg = i * ladder_step
            ly = int(cy_c - p_deg * ppu)  # positive pitch → above centre (PIL y-down)
            if ly < 0 or ly >= clip_h:
                continue
            abs_i = abs(i)
            if abs_i % 4 == 0:
                hw, lw, labeled = hw_4, hor_w, True
            elif abs_i % 2 == 0:
                hw, lw, labeled = hw_2, ldr_w, False
            else:
                hw, lw, labeled = hw_1, ldr_w, False
            x0, x1 = int(cx_c - hw), int(cx_c + hw)
            cd.line([(x0, ly), (x1, ly)], fill=ldr_c, width=lw)
            if labeled:
                label = str(abs(round(p_deg)))
                gap = 6
                try:
                    cd.text((x1 + gap, ly), label, fill=ldr_c, font=font, anchor="lm")
                    cd.text((x0 - gap, ly), label, fill=ldr_c, font=font, anchor="rm")
                except TypeError:
                    cd.text((x1 + gap, ly), label, fill=ldr_c, font=font)

        # Horizon line
        cd.line([(0, int(cy_c)), (clip_w - 1, int(cy_c))], fill=hor_c, width=hor_w)

        # arc_cy_c: centre for the arc/ticks/pointer in PIL clip-image coords.
        # Positive bank_arc_y_offset = up in Arcade = lower y in PIL (y-down).
        arc_cy_c = cy_c - arc_y_offset
        arc_r_i  = int(arc_r)

        show_arc_bg = bool(comp.get("show_arc_bg", False))
        if show_arc_bg:
            raw_bg = comp.get("arc_bg_color")
            bg_c = _rgba(raw_bg) if raw_bg is not None else sky_c
            arc_bg_inset = float(comp.get("arc_bg_inset", 0.0))
            r_bg = max(0.0, arc_r_i - arc_bg_inset)
            # Polygon: arc contour (left→top→right) then viewport top corners.
            # PIL angles 210°→330° CW pass through 270° (top) — same ±60° arc.
            n = 64
            bg_pts = []
            for i in range(n + 1):
                theta = math.radians(210.0 + 120.0 * i / n)
                bg_pts.append((cx_c + r_bg * math.cos(theta),
                                arc_cy_c + r_bg * math.sin(theta)))
            bg_pts += [(clip_w - 1, 0), (0, 0)]
            cd.polygon(bg_pts, fill=bg_c)

        if show_arc_line:
            # Upper portion ±60° from vertical.
            # PIL arc CW from 210° to 330° passes through 270° (top) ✓
            bbox = [int(cx_c - arc_r_i), int(arc_cy_c - arc_r_i),
                    int(cx_c + arc_r_i), int(arc_cy_c + arc_r_i)]
            cd.arc(bbox, 210, 330, fill=arc_c, width=arc_w)

        # 0° reference mark — drawn whenever bank arc is visible (line or ticks)
        arc_ref_shape   = str(comp.get("arc_ref_shape", "tick"))
        arc_ref_h       = int(float(comp.get("arc_ref_height", 10.0)))
        arc_ref_w       = int(float(comp.get("arc_ref_width", 10.0)))
        arc_ref_filled  = bool(comp.get("arc_ref_filled", True))
        arc_ref_line_w  = max(1, int(float(comp.get("arc_ref_line_width", 2.0))))
        arc_ref_offset  = float(comp.get("arc_ref_offset", 0.0))
        arc_top_y = int(arc_cy_c - arc_r_i - arc_ref_offset)  # offset: +outward = smaller y in PIL
        if arc_ref_shape == "arrow":
            arrow_pts = [
                (int(cx_c), arc_top_y + arc_ref_h),        # tip (inward = larger y)
                (int(cx_c) - arc_ref_w // 2, arc_top_y),   # base left
                (int(cx_c) + arc_ref_w // 2, arc_top_y),   # base right
            ]
            if arc_ref_filled:
                cd.polygon(arrow_pts, fill=arc_c)
            else:
                cd.polygon(arrow_pts, outline=arc_c, width=arc_ref_line_w)
        else:
            cd.line([(int(cx_c), arc_top_y), (int(cx_c), arc_top_y + arc_ref_h)],
                    fill=arc_c, width=arc_w + 1)

        if show_arc_ticks:
            _tick_lens = {
                10: float(comp.get("bank_tick_10", 6.0)),
                20: float(comp.get("bank_tick_20", 6.0)),
                30: float(comp.get("bank_tick_30", 10.0)),
                45: float(comp.get("bank_tick_45", 6.0)),
                60: float(comp.get("bank_tick_60", 6.0)),
            }
            ticks_inward = bool(comp.get("ticks_inward", True))
            # Tick marks — same formula as runtime, y-flipped for PIL
            for a in [10, 20, 30, 45, 60]:
                for sign in (-1, 1):
                    ba_rad = math.radians(sign * a)
                    tick_len = _tick_lens[a]
                    if ticks_inward:
                        ox = int(cx_c     + arc_r * math.sin(ba_rad))
                        oy = int(arc_cy_c - arc_r * math.cos(ba_rad))
                        ix = int(cx_c     + (arc_r - tick_len) * math.sin(ba_rad))
                        iy = int(arc_cy_c - (arc_r - tick_len) * math.cos(ba_rad))
                    else:
                        ix = int(cx_c     + arc_r * math.sin(ba_rad))
                        iy = int(arc_cy_c - arc_r * math.cos(ba_rad))
                        ox = int(cx_c     + (arc_r + tick_len) * math.sin(ba_rad))
                        oy = int(arc_cy_c - (arc_r + tick_len) * math.cos(ba_rad))
                    cd.line([(ix, iy), (ox, oy)], fill=arc_c, width=arc_w)

        # Slip indicator (static preview: bank=0, slip=0 — centred at top of arc)
        if comp.get("show_slip", False):
            slip_c_raw  = comp.get("slip_color")
            slip_c      = _rgba(slip_c_raw) if slip_c_raw else _rgba(None)
            slip_w_f    = float(comp.get("slip_width",  20.0))
            slip_h_f    = float(comp.get("slip_height",  8.0))
            slip_fld    = bool(comp.get("slip_filled", True))
            slip_lw     = max(1, int(float(comp.get("slip_line_width", 2.0))))
            slip_off    = float(comp.get("slip_offset", 0.0))
            s_cx  = int(cx_c)
            s_cy  = int(arc_cy_c - arc_r_i - slip_off)
            s_hw  = int(slip_w_f / 2)
            s_hh  = int(slip_h_f / 2)
            s_box = [s_cx - s_hw, s_cy - s_hh, s_cx + s_hw, s_cy + s_hh]
            if slip_fld:
                cd.rectangle(s_box, fill=slip_c)
            else:
                cd.rectangle(s_box, outline=slip_c, width=slip_lw)

        # Roll pointer at bank=0: triangle at the top of the arc.
        # PIL y-down: inward (toward centre) → tip_y > base_y; outward → tip_y < base_y.
        ptr_base_y = int(arc_cy_c - arc_r_i - ptr_y_off)
        tip_offset = int(ptr_h)
        ptr_tip_y  = ptr_base_y + tip_offset if ptr_inward else ptr_base_y - tip_offset
        half_ptr   = int(ptr_w * 0.5)
        ptr_pts = [
            (int(cx_c), ptr_tip_y),
            (int(cx_c) - half_ptr, ptr_base_y),
            (int(cx_c) + half_ptr, ptr_base_y),
        ]
        if ptr_filled:
            cd.polygon(ptr_pts, fill=ptr_c)
        else:
            cd.polygon(ptr_pts, outline=ptr_c, width=ptr_line_w)

        # PIL y is down, AI coords are y-up, so negate y when converting points.
        # Legacy stubs/dot only when NEITHER polygon is configured.
        _bug_pts_raw  = comp.get("centre_bug_points", [])
        _wing_pts_raw = comp.get("wing_points", [])

        # Wing bars — below FD bars
        if comp.get("show_reference", True):
            if _wing_pts_raw:
                wing_fill_c = _rgba(comp.get("wing_fill_color", [0, 0, 0]))
                wing_out_c  = _rgba(comp.get("wing_outline_color", [255, 255, 255]))
                wing_out_w  = max(1, int(float(comp.get("wing_outline_width", 2.0))))
                for sign in (1, -1):
                    w_pts = [(int(cx_c + sign * p[0]), int(cy_c - p[1])) for p in _wing_pts_raw]
                    if comp.get("wing_filled", True):
                        cd.polygon(w_pts, fill=wing_fill_c, outline=wing_out_c, width=wing_out_w)
                    else:
                        cd.polygon(w_pts, outline=wing_out_c, width=wing_out_w)
            elif not _bug_pts_raw:
                stub = 30; gap = 6
                cd.line([(int(cx_c) - stub - gap, int(cy_c)),
                         (int(cx_c) - gap, int(cy_c))], fill=ptr_c, width=3)
                cd.line([(int(cx_c) + gap, int(cy_c)),
                         (int(cx_c) + stub + gap, int(cy_c))], fill=ptr_c, width=3)

        # Flight director — static preview at zero deflection (bars centred)
        if comp.get("show_fd_h_bar", False):
            fd_h_c   = _rgba(comp.get("fd_h_color", [255, 200, 0]))
            fd_h_len = int(float(comp.get("fd_h_length", 200.0)))
            fd_h_w   = max(1, int(float(comp.get("fd_h_width", 3.0))))
            half_h   = fd_h_len // 2
            cd.line([(int(cx_c) - half_h, int(cy_c)),
                     (int(cx_c) + half_h, int(cy_c))],
                    fill=fd_h_c, width=fd_h_w)
        if comp.get("show_fd_v_bar", False):
            fd_v_c   = _rgba(comp.get("fd_v_color", [255, 200, 0]))
            fd_v_len = int(float(comp.get("fd_v_length", 200.0)))
            fd_v_w   = max(1, int(float(comp.get("fd_v_width", 3.0))))
            half_v   = fd_v_len // 2
            cd.line([(int(cx_c), int(cy_c) - half_v),
                     (int(cx_c), int(cy_c) + half_v)],
                    fill=fd_v_c, width=fd_v_w)

        # Centre bug — above FD bars
        if comp.get("show_reference", True):
            if _bug_pts_raw:
                bug_fill_c = _rgba(comp.get("centre_bug_fill_color", [0, 0, 0]))
                bug_out_c  = _rgba(comp.get("centre_bug_outline_color", [255, 255, 255]))
                bug_out_w  = max(1, int(float(comp.get("centre_bug_outline_width", 2.0))))
                bug_pts = [(int(cx_c + p[0]), int(cy_c - p[1])) for p in _bug_pts_raw]
                if comp.get("centre_bug_filled", True):
                    cd.polygon(bug_pts, fill=bug_fill_c, outline=bug_out_c, width=bug_out_w)
                else:
                    cd.polygon(bug_pts, outline=bug_out_c, width=bug_out_w)
            elif not _wing_pts_raw:
                cd.ellipse([int(cx_c) - 4, int(cy_c) - 4,
                            int(cx_c) + 4, int(cy_c) + 4], fill=ptr_c)

        corner_radius = float(comp.get("corner_radius", 0.0))
        if corner_radius > 0:
            cr = max(1, min(int(corner_radius), clip_w // 2, clip_h // 2))
            mask = Image.new("L", (clip_w, clip_h), 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                [0, 0, clip_w - 1, clip_h - 1], radius=cr, fill=255
            )
            ci.putalpha(mask)

        composite.paste(ci, (int(vx), int(py_top)), mask=ci)
        draw.rectangle([int(vx), int(py_top), int(vx + vw - 1), int(py_top + vh - 1)],
                       outline=(80, 80, 150, 255), width=1)

    def _viewport_rect_pil(self, comp: dict, canvas_h: int) -> tuple[int, int, int, int] | None:
        """Return (x, y, w, h) in PIL (y-down) coords for the component's viewport."""
        vp = comp.get("viewport")
        if not vp:
            return None
        vx, vy, vw, vh = vp
        return (int(vx), int(canvas_h - vy - vh), int(vw), int(vh))

    def _load_atlas(self, tex_rel: str) -> Image.Image:
        tex_path = str((Path(self._yaml_dir) / tex_rel).resolve())
        if tex_path not in self._atlas_cache:
            self._atlas_cache[tex_path] = Image.open(tex_path).convert("RGBA")
        return self._atlas_cache[tex_path]

    def _render_spritesheet(self, comp: dict, composite: Image.Image,
                            canvas_w: int, canvas_h: int) -> None:
        atlas = self._load_atlas(comp.get("texture", ""))
        frame_w = int(comp.get("frame_width", 100))
        frame_h = int(comp.get("frame_height", 100))
        stride_x = int(comp.get("stride_x", frame_w))
        stride_y = int(comp.get("stride_y", frame_h))
        columns  = int(comp.get("columns", 1))
        total    = columns * int(comp.get("rows", 1))

        # Use the table's first output as the initial frame (matches runtime at min value).
        anim  = comp.get("animation", {})
        table = anim.get("table", [])
        frame = float(table[0][1]) if table else 0.0
        int_frame = max(0, min(total - 1, int(frame)))
        col = int_frame % columns
        row = int_frame // columns
        crop_x = col * stride_x
        crop_y = row * stride_y

        pos = comp.get("position", [canvas_w // 2, canvas_h // 2])
        pos_x, pos_y = float(pos[0]), float(pos[1])

        # The active frame's centre always aligns with position, regardless of which
        # frame is shown.  The canvas paste position is therefore always the same.
        f_left = int(round(pos_x - frame_w / 2))
        f_top  = int(round(canvas_h - pos_y - frame_h / 2))

        rect = self._viewport_rect_pil(comp, canvas_h)
        if rect is not None:
            vx, vy, vw, vh = rect
            ix1, iy1 = max(f_left, vx), max(f_top, vy)
            ix2, iy2 = min(f_left + frame_w, vx + vw), min(f_top + frame_h, vy + vh)
            if ix2 > ix1 and iy2 > iy1:
                ax1 = crop_x + (ix1 - f_left)
                ay1 = crop_y + (iy1 - f_top)
                visible = atlas.crop((ax1, ay1, ax1 + (ix2 - ix1), ay1 + (iy2 - iy1)))
                composite.paste(visible, (ix1, iy1), visible)
        else:
            frame_img = atlas.crop((crop_x, crop_y,
                                    min(crop_x + frame_w, atlas.width),
                                    min(crop_y + frame_h, atlas.height)))
            composite.paste(frame_img, (f_left, f_top), frame_img)

    def _render_scrolltape(self, comp: dict, composite: Image.Image,
                           canvas_w: int, canvas_h: int) -> None:
        atlas = self._load_atlas(comp.get("texture", ""))
        axis  = comp.get("scroll_axis", "y")

        pos = comp.get("position", [canvas_w // 2, canvas_h // 2])
        pos_x, pos_y = float(pos[0]), float(pos[1])

        # Use the table's first output as the initial scroll offset (matches runtime
        # at the minimum input value, so the preview digit agrees with the test harness
        # when its spinbox is at the table minimum).
        scroll    = comp.get("scroll", {})
        table     = scroll.get("table", [])
        offset_px = float(table[0][1]) if table else 0.0

        # Derive atlas top-left in PIL (y-down) coords.
        # Runtime: at offset O, row O (or column O) is centred at position.
        #   y-axis: row 0 is at Arcade y = pos_y + O  → PIL y = canvas_h - pos_y - O
        #   x-axis: col 0 is at Arcade x = pos_x - O  → PIL x = pos_x - O
        if axis == "y":
            t_left = int(round(pos_x - atlas.width / 2))
            t_top  = int(round(canvas_h - pos_y - offset_px))
        else:
            t_left = int(round(pos_x - offset_px))
            t_top  = int(round(canvas_h - pos_y - atlas.height / 2))

        rect = self._viewport_rect_pil(comp, canvas_h)
        if rect is not None:
            vx, vy, vw, vh = rect
            ix1, iy1 = max(t_left, vx), max(t_top, vy)
            ix2, iy2 = min(t_left + atlas.width, vx + vw), min(t_top + atlas.height, vy + vh)
            if ix2 > ix1 and iy2 > iy1:
                strip = atlas.crop((ix1 - t_left, iy1 - t_top, ix2 - t_left, iy2 - t_top))
                composite.paste(strip, (ix1, iy1), strip)
        else:
            patch_w = min(100, atlas.width)
            patch_h = min(100, atlas.height)
            patch = atlas.crop((0, 0, patch_w, patch_h))
            paste_x = int(round(pos_x - patch_w / 2))
            paste_y = int(round((canvas_h - pos_y) - patch_h / 2))
            composite.paste(patch, (paste_x, paste_y), patch)

    def _crop_sprite(self, comp: dict, canvas_w: int, canvas_h: int):
        atlas = self._load_atlas(comp.get("texture", ""))

        ox, oy = comp.get("origin", [0, 0])
        cw, ch = comp.get("cliprect", [100, 100])
        px, py = comp.get("position", [0, 0])

        sprite = atlas.crop((ox, oy, ox + cw, oy + ch))

        if comp.get("resize_to_container"):
            if comp.get("maintain_proportions", True):
                scale = min(canvas_w / cw, canvas_h / ch)
                new_w = max(1, int(round(cw * scale)))
                new_h = max(1, int(round(ch * scale)))
            else:
                new_w, new_h = canvas_w, canvas_h
            sprite = sprite.resize((new_w, new_h), Image.LANCZOS)
            cw, ch = new_w, new_h

        paste_x = int(round(px - cw / 2))
        paste_y = int(round((canvas_h - py) - ch / 2))

        return sprite, paste_x, paste_y
