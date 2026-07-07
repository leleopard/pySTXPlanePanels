"""PIL-based panel layout canvas.

Each instrument is drawn as a labelled, coloured rectangle at its
declared position and size. Ctrl+wheel zooms. Left-click selects.
Starts zoomed out (0.3×) since panels are typically 1500+ px wide.
"""

import io
import os
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont
from PySide6.QtWidgets import QWidget, QScrollArea, QVBoxLayout
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QPainter

from gauge_designer.ui_utils import flip_y


def _rgba(raw: list) -> tuple[int, int, int, int]:
    """Accept [r,g,b] or [r,g,b,a] in 0-255; default alpha = 255."""
    if len(raw) == 3:
        return (int(raw[0]), int(raw[1]), int(raw[2]), 255)
    return (int(raw[0]), int(raw[1]), int(raw[2]), int(raw[3]))


_PALETTE = [
    (70, 130, 190, 170),
    (70, 170, 90,  170),
    (190, 130, 50, 170),
    (150, 70, 170, 170),
    (170, 50, 70,  170),
    (50, 170, 170, 170),
    (170, 170, 50, 170),
]

def _load_bold_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf",                                     # Windows
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",             # Linux (Debian/Ubuntu)
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",     # Linux (RHEL/Fedora)
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",           # Linux (Fedora alt)
        "/Library/Fonts/Arial Bold.ttf",                                     # macOS
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",                # macOS (Ventura+)
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()

_FONT = _load_bold_font(22)


class _Surface(QWidget):
    def __init__(self, canvas: "PanelCanvas", parent=None):
        super().__init__(parent)
        self._canvas = canvas
        self._pixmap = QPixmap()
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)

    def set_pixmap(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self.resize(pixmap.size() if not pixmap.isNull() else self.size())
        self.update()

    def paintEvent(self, _event):
        if not self._pixmap.isNull():
            QPainter(self).drawPixmap(0, 0, self._pixmap)

    def mousePressEvent(self, event):
        self._canvas._on_press(event)

    def mouseMoveEvent(self, event):
        self._canvas._on_mouse_move(event)

    def leaveEvent(self, event):
        self._canvas._on_mouse_leave()
        super().leaveEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            self._canvas._on_wheel(event)
        else:
            event.ignore()


class PanelCanvas(QWidget):
    instrument_selected = Signal(int)   # index into instruments list
    mouse_moved = Signal(int, int)      # panel-space x, y (y-up)
    mouse_left = Signal()
    zoom_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: dict = {}
        self._yaml_dir: str = ""
        self._selected_idx: int = -1
        self._zoom: float = 0.3  # panels are large; start zoomed out
        self._size_cache: dict[str, tuple[int, int]] = {}

        self._surface = _Surface(self)
        self._scroll = QScrollArea()
        self._scroll.setWidget(self._surface)
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._scroll)

    # ── Public API ────────────────────────────────────────────────────────

    def load(self, data: dict, yaml_dir: str):
        self._data = data
        self._yaml_dir = yaml_dir
        self._size_cache.clear()
        self._render()

    def set_selected(self, idx: int):
        if self._selected_idx != idx:
            self._selected_idx = idx
            self._render()

    def refresh(self):
        self._render()

    def set_size(self, w: int, h: int):
        if self._data:
            self._data["size"] = [w, h]
            self._render()

    def clear(self):
        self._data = {}
        self._selected_idx = -1
        self._size_cache.clear()
        self._surface.set_pixmap(QPixmap())

    def set_zoom(self, z: float):
        self._zoom = max(0.05, min(4.0, z))
        self._render()

    def set_background_color(self, r: int, g: int, b: int):
        if self._data:
            self._data["background_color"] = [round(r / 255, 4), round(g / 255, 4), round(b / 255, 4)]
            self._render()

    def inst_size(self, file_rel: str, scale: float = 1.0) -> tuple[int, int]:
        """Return the rendered (width, height) of an instrument, using cache."""
        w, h = self._inst_size(file_rel)
        return (int(round(w * scale)), int(round(h * scale)))

    # ── Mouse tracking ────────────────────────────────────────────────────

    def _on_mouse_move(self, event):
        if not self._data:
            return
        _pw, ph = self._data.get("size", [1540, 920])
        px = event.position().x() / self._zoom
        py = event.position().y() / self._zoom
        # py is y-down from canvas top; convert to y-up then apply display convention
        self.mouse_moved.emit(int(px), flip_y(int(ph - py), ph))

    def _on_mouse_leave(self):
        self.mouse_left.emit()

    # ── Instrument size lookup ────────────────────────────────────────────

    def _inst_size(self, file_rel: str) -> tuple[int, int]:
        try:
            path = str((Path(self._yaml_dir) / file_rel).resolve())
            if path in self._size_cache:
                return self._size_cache[path]
            with open(path, encoding="utf-8") as f:
                d = yaml.safe_load(f)
            sz = (int(d["size"][0]), int(d["size"][1]))
            self._size_cache[path] = sz
            return sz
        except Exception:
            return (310, 310)

    # ── Zoom ─────────────────────────────────────────────────────────────

    def _on_wheel(self, event):
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1.0 / 1.15
        old_zoom = self._zoom
        self._zoom = max(0.05, min(4.0, self._zoom * factor))
        if self._zoom == old_zoom:
            event.accept()
            return
        cx = event.position().x()
        cy = event.position().y()
        hv = self._scroll.horizontalScrollBar().value()
        vv = self._scroll.verticalScrollBar().value()
        self._render()
        ratio = self._zoom / old_zoom
        self._scroll.horizontalScrollBar().setValue(int(cx * (ratio - 1) + hv))
        self._scroll.verticalScrollBar().setValue(int(cy * (ratio - 1) + vv))
        self.zoom_changed.emit(self._zoom)
        event.accept()

    # ── Hit testing ───────────────────────────────────────────────────────

    def _on_press(self, event):
        if event.button() != Qt.LeftButton:
            return
        cx = event.position().x() / self._zoom
        cy = event.position().y() / self._zoom
        pw, ph = self._data.get("size", [1540, 920])
        hit = -1
        for i, entry in enumerate(self._data.get("instruments", [])):
            if "grid" in entry:
                g = entry["grid"]
                gx, gy = g.get("position", [0, 0])
                gw = g.get("columns", 1) * g.get("cell_width", 310)
                gh = g.get("rows", 1) * g.get("cell_height", 310)
                left, top = gx, ph - gy - gh
                if left <= cx < left + gw and top <= cy < top + gh:
                    hit = i
            elif "container" in entry:
                c = entry["container"]
                ccx, ccy = c.get("position", [0, 0])
                cw, ch = c.get("size", [300, 300])
                left, top = ccx, ph - ccy - ch
                if left <= cx < left + cw and top <= cy < top + ch:
                    hit = i
            else:
                ix, iy = entry.get("position", [0, 0])
                iw, ih = self._inst_size(entry.get("file", ""))
                scale = float(entry.get("scale", 1.0))
                iw = int(round(iw * scale))
                ih = int(round(ih * scale))
                left = ix
                top = ph - iy - ih  # y-up → y-down
                if left <= cx < left + iw and top <= cy < top + ih:
                    hit = i        # take last hit (topmost in draw order)
        if hit != self._selected_idx:
            self._selected_idx = hit
            self._render()
        if hit >= 0:
            self.instrument_selected.emit(hit)

    # ── Rendering ────────────────────────────────────────────────────────

    def _render(self):
        if not self._data:
            self._surface.set_pixmap(QPixmap())
            return
        pixmap = self._composite()
        if self._zoom != 1.0:
            pixmap = pixmap.scaled(
                int(pixmap.width() * self._zoom),
                int(pixmap.height() * self._zoom),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        self._surface.set_pixmap(pixmap)

    def _composite(self) -> QPixmap:
        pw, ph = self._data.get("size", [1540, 920])
        bg = self._data.get("background_color", [0.05, 0.05, 0.05])
        try:
            bg_rgb = (int(round(bg[0] * 255)), int(round(bg[1] * 255)), int(round(bg[2] * 255)), 255)
        except (TypeError, IndexError, ValueError):
            bg_rgb = (13, 13, 13, 255)
        canvas = Image.new("RGBA", (pw, ph), bg_rgb)
        draw = ImageDraw.Draw(canvas)

        for i, entry in enumerate(self._data.get("instruments", [])):
            is_sel = (i == self._selected_idx)
            sel_outline = (255, 220, 0, 255)
            def_outline = (160, 160, 160, 200)

            if "grid" in entry:
                g = entry["grid"]
                gx, gy = g.get("position", [0, 0])
                cols = g.get("columns", 1)
                rows = g.get("rows", 1)
                cw = g.get("cell_width", 310)
                ch = g.get("cell_height", 310)
                gw = cols * cw
                gh = rows * ch
                gl = gx
                gt = ph - gy - gh
                gr = gl + gw - 1
                gb = gt + gh - 1

                draw.rectangle([gl, gt, gr, gb], fill=(30, 30, 60, 120),
                               outline=sel_outline if is_sel else (100, 120, 200, 180),
                               width=3 if is_sel else 1)

                for c in range(1, cols):
                    x = gl + c * cw
                    draw.line([(x, gt), (x, gb)], fill=(80, 100, 160, 160), width=1)
                for r in range(1, rows):
                    y = gt + r * ch
                    draw.line([(gl, y), (gr, y)], fill=(80, 100, 160, 160), width=1)

                grid_name = g.get("name", "")
                label = f"[{grid_name}]" if grid_name else "[Grid]"
                draw.text((gl + 5, gt + 5), label, fill=(160, 190, 255, 220), font=_FONT)

                for j, inst_entry in enumerate(g.get("instruments", [])):
                    col = j % cols
                    row = j // cols
                    if "container" in inst_entry:
                        c_cfg = inst_entry["container"]
                        cw_, ch_ = c_cfg.get("size", [200, 200])
                        cl = int(gx + col * cw + (cw - cw_) / 2)
                        ct = int(ph - gy - (rows - row) * ch + (ch - ch_) / 2)
                        self._draw_container_box(
                            draw, c_cfg, cl, ct, int(cw_), int(ch_),
                            False, sel_outline, def_outline,
                        )
                        continue
                    iw, ih = self._inst_size(inst_entry.get("file", ""))
                    sc = float(inst_entry.get("scale", 1.0))
                    iw = int(round(iw * sc))
                    ih = int(round(ih * sc))
                    il = int(gx + col * cw + (cw - iw) / 2)
                    it = int(ph - gy - (rows - row) * ch + (ch - ih) / 2)
                    ir = il + iw - 1
                    ib = it + ih - 1
                    # Color follows the instrument (file-based), not the cell
                    # position — so swapping instruments produces a visible change.
                    fill = _PALETTE[abs(hash(inst_entry.get("file", str(j)))) % len(_PALETTE)]
                    draw.rectangle([il, it, ir, ib], fill=fill)
                    draw.rectangle([il, it, ir, ib], outline=(180, 180, 180, 180), width=1)
                    inst_label = Path(inst_entry.get("file", "?")).stem
                    draw.text((il + 5, it + 5), inst_label, fill=(255, 255, 255, 230), font=_FONT)
            elif "container" in entry:
                c = entry["container"]
                ccx, ccy = c.get("position", [0, 0])
                cw, ch = c.get("size", [300, 300])
                cl = int(ccx)
                ct = int(ph - ccy - ch)
                self._draw_container_box(
                    draw, c, cl, ct, int(cw), int(ch), is_sel, sel_outline, def_outline,
                )
            else:
                ix, iy = entry.get("position", [0, 0])
                iw, ih = self._inst_size(entry.get("file", ""))
                scale = float(entry.get("scale", 1.0))
                iw = int(round(iw * scale))
                ih = int(round(ih * scale))
                left = ix
                top = ph - iy - ih
                right = left + iw - 1
                bottom = top + ih - 1

                fill = _PALETTE[abs(hash(entry.get("file", str(i)))) % len(_PALETTE)]
                outline = sel_outline if is_sel else def_outline
                lw = 3 if is_sel else 1

                draw.rectangle([left, top, right, bottom], fill=fill)
                draw.rectangle([left, top, right, bottom], outline=outline, width=lw)

                label = Path(entry.get("file", "?")).stem
                draw.text((left + 5, top + 5), label, fill=(255, 255, 255, 230), font=_FONT)

        buf = io.BytesIO()
        canvas.save(buf, format="PNG")
        pixmap = QPixmap()
        pixmap.loadFromData(buf.getvalue())
        return pixmap

    def _draw_container_box(
        self, draw: ImageDraw.ImageDraw, c_cfg: dict,
        left: int, top: int, w: int, h: int,
        is_sel: bool, sel_outline: tuple, def_outline: tuple,
    ) -> None:
        """Draw a container's box + its children, given the box's already-
        resolved PIL (top, left) and size — shared by the top-level branch
        and the grid-cell branch (a grid cell may itself be a container).
        """
        right, bottom = left + w - 1, top + h - 1
        bg = c_cfg.get("background_color")
        # Real runtime color when set (what-you-see-is-what-you-get, unlike
        # Grid's arbitrary designer-only tint) — else a violet tint distinct
        # from Grid's blue so an unconfigured container still reads as one.
        fill = _rgba(bg) if bg is not None else (60, 30, 70, 120)
        draw.rectangle([left, top, right, bottom], fill=fill,
                       outline=sel_outline if is_sel else def_outline,
                       width=3 if is_sel else 1)

        name = c_cfg.get("name", "")
        label = f"[{name}]" if name else "[Container]"
        draw.text((left + 5, top + 5), label, fill=(230, 190, 255, 220), font=_FONT)

        for inst_entry in c_cfg.get("instruments", []):
            ix, iy = inst_entry.get("position", [0, 0])
            iw, ih = self._inst_size(inst_entry.get("file", ""))
            sc = float(inst_entry.get("scale", 1.0))
            iw = int(round(iw * sc))
            ih = int(round(ih * sc))
            il = int(left + ix)
            it = int(top + h - iy - ih)
            ir = il + iw - 1
            ib = it + ih - 1
            cfill = _PALETTE[abs(hash(inst_entry.get("file", "?"))) % len(_PALETTE)]
            draw.rectangle([il, it, ir, ib], fill=cfill)
            draw.rectangle([il, it, ir, ib], outline=(180, 180, 180, 180), width=1)
            inst_label = Path(inst_entry.get("file", "?")).stem
            draw.text((il + 5, it + 5), inst_label, fill=(255, 255, 255, 230), font=_FONT)
