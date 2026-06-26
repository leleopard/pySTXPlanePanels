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
from PySide6.QtWidgets import QWidget, QScrollArea, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPixmap, QPainter

from gauge_designer.ui_utils import is_y_down


def _rgba(raw) -> tuple:
    """YAML color list → (r, g, b, a) tuple."""
    if raw is None:
        return (200, 200, 200, 255)
    if len(raw) == 3:
        return (int(raw[0]), int(raw[1]), int(raw[2]), 255)
    return tuple(int(v) for v in raw[:4])


_PIL_FONT_CACHE: dict[tuple, ImageFont.FreeTypeFont] = {}

_BOLD_MARKERS   = ("bold", "bd", "heavy", "black", "b")
_ITALIC_MARKERS = ("italic", "oblique", "it", "i")

def _pil_font(name: str | None, size: int, *,
              bold: bool = False, italic: bool = False) -> ImageFont.ImageFont:
    """Load a PIL font by family name and style, falling back to the default bitmap font."""
    key = (name or "", size, bold, italic)
    if key in _PIL_FONT_CACHE:
        return _PIL_FONT_CACHE[key]
    font = None
    if name:
        fonts_dir = Path("C:/Windows/Fonts")
        if fonts_dir.exists():
            needle = name.lower().replace(" ", "")
            candidates: list[tuple[Path, bool, bool]] = []
            for f in sorted(fonts_dir.iterdir()):
                if f.suffix.lower() not in (".ttf", ".otf"):
                    continue
                stem = f.stem.lower().replace(" ", "").replace("-", "")
                if needle not in stem:
                    continue
                # Everything after the family name needle is the style suffix
                suffix = stem[stem.index(needle) + len(needle):]
                is_bold   = any(m in suffix for m in _BOLD_MARKERS)   if suffix else False
                is_italic = any(m in suffix for m in _ITALIC_MARKERS) if suffix else False
                candidates.append((f, is_bold, is_italic))
            if candidates:
                # Sort by match quality: exact bold/italic match scores 0
                candidates.sort(key=lambda t: (t[1] != bold) * 2 + (t[2] != italic))
                for f, _, _ in candidates:
                    try:
                        font = ImageFont.truetype(str(f), size)
                        break
                    except Exception:
                        continue
    if font is None:
        try:
            font = ImageFont.load_default(size=size)
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
            ref = comp.get("start", [0, 0])
        elif ctype == "Arc":
            ref = comp.get("center", [0, 0])
        elif ctype == "Polygon":
            pts = comp.get("points", [])
            ref = pts[0] if pts else [0, 0]
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
                os_ = orig.get("start", [0, 0]); oe = orig.get("end", [0, 0])
                comp["start"] = [int(round(os_[0] + dx_yaml)), int(round(os_[1] + dy_yaml))]
                comp["end"]   = [int(round(oe[0]  + dx_yaml)), int(round(oe[1]  + dy_yaml))]
            elif ctype == "Polygon":
                comp["points"] = [[int(round(p[0] + dx_yaml)), int(round(p[1] + dy_yaml))]
                                  for p in orig.get("points", [])]
            elif ctype == "Arc":
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
                ref = comp.get("start", [0, 0])
            elif ctype == "Arc":
                ref = comp.get("center", [0, 0])
            elif ctype == "Polygon":
                pts = comp.get("points", [[0, 0]])
                ref = pts[0] if pts else [0, 0]
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
                    s = comp.get("start", [0, 0]); e = comp.get("end", [0, 0])
                    x1, y1 = int(s[0]), h - int(s[1])
                    x2, y2 = int(e[0]), h - int(e[1])
                    pad = 8
                    if (min(x1, x2) - pad <= cx <= max(x1, x2) + pad and
                            min(y1, y2) - pad <= cy <= max(y1, y2) + pad):
                        result.append(comp.get("name"))
                elif ctype == "Arc":
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
                    pts = comp.get("points", [])
                    if pts:
                        xs = [int(p[0]) for p in pts]
                        ys = [h - int(p[1]) for p in pts]
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
                elif ctype == "RotaryEncoder":
                    self._render_rotary_encoder(comp, composite, draw, h)
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
                    s = comp.get("start", [0, 0]); e = comp.get("end", [0, 0])
                    lw = max(3, int(float(comp.get("width", 1.0))) + 2)
                    draw.line([(int(s[0]), h - int(s[1])), (int(e[0]), h - int(e[1]))],
                              fill=SEL, width=lw)
                elif ctype == "Arc":
                    ctr = comp.get("center", [0, 0])
                    r = int(round(float(comp.get("radius", 50))))
                    cx_p, cy_p = int(ctr[0]), h - int(ctr[1])
                    bbox = [cx_p - r, cy_p - r, cx_p + r, cy_p + r]
                    sa, ea = float(comp.get("start_angle", 0)), float(comp.get("end_angle", 360))
                    draw.arc(bbox, -ea, -sa, fill=SEL, width=4)
                elif ctype in ("FilledRect", "RotaryEncoder"):
                    pos = comp.get("position", [0, 0]); sz = comp.get("size", [100, 100])
                    cx_p, cy_p = int(pos[0]), h - int(pos[1])
                    hw, hh = int(sz[0]) // 2, int(sz[1]) // 2
                    draw.rectangle([cx_p - hw, cy_p - hh, cx_p + hw, cy_p + hh],
                                   outline=SEL, width=2)
                elif ctype == "Polygon":
                    pts = [(int(p[0]), h - int(p[1])) for p in comp.get("points", [])]
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

    def _render_line(self, comp: dict, draw: ImageDraw.ImageDraw, canvas_h: int) -> None:
        s = comp.get("start", [0, 0]); e = comp.get("end", [0, 0])
        color = _rgba(comp.get("color"))
        width = max(1, int(round(float(comp.get("width", 1.0)))))
        draw.line([(int(s[0]), canvas_h - int(s[1])), (int(e[0]), canvas_h - int(e[1]))],
                  fill=color, width=width)

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

    @staticmethod
    def _crosshair(draw: ImageDraw.ImageDraw, cx: int, cy: int) -> None:
        """1px yellow crosshair, 20px long (10px each arm)."""
        c = (255, 220, 0, 255)
        draw.line([(cx - 10, cy), (cx + 10, cy)], fill=c, width=1)
        draw.line([(cx, cy - 10), (cx, cy + 10)], fill=c, width=1)

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
        pts = [(int(p[0]), canvas_h - int(p[1])) for p in pts_raw]
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

        # Crosshair on the selected point
        if (comp.get("name") == self._selected_name
                and 0 <= self._selected_point_idx < len(pts)):
            px, py = pts[self._selected_point_idx]
            self._crosshair(draw, px, py)

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

        # Component position in PIL coords — anchor point for value=0
        pos = comp.get("position", [vx + vw / 2, vy_bottom + vh / 2])
        cy_pil = canvas_h - pos[1]   # y-axis anchor (PIL)
        cx_pil = pos[0]              # x-axis anchor

        if axis == "y":
            spine_x = int(vx) if tick_side == "left" else int(vx + vw)
            tick_dir = 1 if tick_side == "left" else -1
            # Bands
            for band in comp.get("bands", []):
                bc = _rgba(band.get("color"))
                bw = float(band.get("width", 8))
                bside = band.get("side") or tick_side
                bx = int(vx) if bside == "left" else int(vx + vw - bw)
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
                toff     = int(td.get("offset", 0))
                tc_col   = _rgba(td["color"]) if td.get("color") else tc
                x0 = spine_x + tick_dir * toff
                x1 = spine_x + tick_dir * (toff + int(length))
                v = math.floor((-half_range - interval) / interval) * interval
                while v <= half_range + interval + interval * 0.001:
                    y = int(cy_pil - v * ppu)
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
                by = int(py_top) if bside == "top" else int(py_top + vh - bh)
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
                toff     = int(td.get("offset", 0))
                tc_col   = _rgba(td["color"]) if td.get("color") else tc
                y0 = spine_y + tick_dir * toff
                y1 = spine_y + tick_dir * (toff + int(length))
                v = math.floor((-half_range - interval) / interval) * interval
                while v <= half_range + interval + interval * 0.001:
                    x = int(cx_pil + v * ppu)
                    if int(vx) <= x <= int(vx + vw):
                        draw.line([(x, y0), (x, y1)], fill=tc_col, width=tw)
                    v += interval

        # Labels
        labels = comp.get("labels") or {}
        label_interval = float(labels.get("interval", 0))
        if label_interval > 0:
            label_offset = float(labels.get("offset", 8))
            label_color  = _rgba(labels.get("color", [255, 255, 255, 255]))
            label_fmt    = labels.get("format", "{:.0f}")
            wrap         = comp.get("wrap")
            font_size    = max(8, int(float(labels.get("font_size", 18))))
            font         = _pil_font(labels.get("font"), font_size,
                                     bold=bool(labels.get("bold", False)),
                                     italic=bool(labels.get("italic", False)))

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
                    pil_anchor = "rm"
                else:
                    lx = spine_x + int(label_offset)
                    pil_anchor = "lm"
                lx_clip = lx - int(vx)  # x in clip_img coords
                half_range = vh / 2 / ppu
                v = math.floor((-half_range - label_interval) / label_interval) * label_interval
                v_max = half_range + label_interval
                while v <= v_max + label_interval * 0.001:
                    y_local = int(cy_pil - v * ppu) - int(py_top)
                    if -font_size <= y_local <= clip_h + font_size:
                        display = v % wrap if wrap else v
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
                    pil_anchor = "mb"
                else:
                    ly_base = spine_y + int(label_offset)
                    pil_anchor = "mt"
                ly_clip = ly_base - int(py_top)  # y in clip_img coords
                half_range = vw / 2 / ppu
                v = math.floor((-half_range - label_interval) / label_interval) * label_interval
                v_max = half_range + label_interval
                while v <= v_max + label_interval * 0.001:
                    x_local = int(cx_pil + v * ppu) - int(vx)
                    if -font_size <= x_local <= clip_w + font_size:
                        display = v % wrap if wrap else v
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
            # 0° reference mark — inward from arc top (larger y in PIL = toward centre)
            arc_ref_shape   = str(comp.get("arc_ref_shape", "tick"))
            arc_ref_h       = int(float(comp.get("arc_ref_height", 10.0)))
            arc_ref_w       = int(float(comp.get("arc_ref_width", 10.0)))
            arc_ref_filled  = bool(comp.get("arc_ref_filled", True))
            arc_ref_line_w  = max(1, int(float(comp.get("arc_ref_line_width", 2.0))))
            arc_top_y = int(arc_cy_c - arc_r_i)  # PIL top of arc (min y = outer edge)
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

        # Aircraft reference (fixed wing stubs + centre dot)
        if comp.get("show_reference", True):
            stub = 30; gap = 6
            cd.line([(int(cx_c) - stub - gap, int(cy_c)),
                     (int(cx_c) - gap, int(cy_c))], fill=ptr_c, width=3)
            cd.line([(int(cx_c) + gap, int(cy_c)),
                     (int(cx_c) + stub + gap, int(cy_c))], fill=ptr_c, width=3)
            cd.ellipse([int(cx_c) - 4, int(cy_c) - 4,
                        int(cx_c) + 4, int(cy_c) + 4], fill=ptr_c)

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
