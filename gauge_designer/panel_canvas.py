"""PIL-based panel layout canvas.

Each instrument is drawn as a labelled, coloured rectangle at its
declared position and size. Ctrl+wheel zooms. Left-click selects.
Starts zoomed out (0.3×) since panels are typically 1500+ px wide.
"""

import io
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont
from PySide6.QtWidgets import QWidget, QScrollArea, QVBoxLayout
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QPainter


_PALETTE = [
    (70, 130, 190, 170),
    (70, 170, 90,  170),
    (190, 130, 50, 170),
    (150, 70, 170, 170),
    (170, 50, 70,  170),
    (50, 170, 170, 170),
    (170, 170, 50, 170),
]

try:
    _FONT = ImageFont.load_default(size=11)
except TypeError:
    _FONT = ImageFont.load_default()


class _Surface(QWidget):
    def __init__(self, canvas: "PanelCanvas", parent=None):
        super().__init__(parent)
        self._canvas = canvas
        self._pixmap = QPixmap()

    def set_pixmap(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self.resize(pixmap.size() if not pixmap.isNull() else self.size())
        self.update()

    def paintEvent(self, _event):
        if not self._pixmap.isNull():
            QPainter(self).drawPixmap(0, 0, self._pixmap)

    def mousePressEvent(self, event):
        self._canvas._on_press(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            self._canvas._on_wheel(event)
        else:
            event.ignore()


class PanelCanvas(QWidget):
    instrument_selected = Signal(int)  # index into instruments list

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
            ix, iy = entry.get("position", [0, 0])
            iw, ih = self._inst_size(entry.get("file", ""))
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
        canvas = Image.new("RGBA", (pw, ph), (25, 25, 25, 255))
        draw = ImageDraw.Draw(canvas)

        for i, entry in enumerate(self._data.get("instruments", [])):
            ix, iy = entry.get("position", [0, 0])
            iw, ih = self._inst_size(entry.get("file", ""))
            left = ix
            top = ph - iy - ih
            right = left + iw - 1
            bottom = top + ih - 1
            is_sel = (i == self._selected_idx)

            fill = _PALETTE[i % len(_PALETTE)]
            outline = (255, 220, 0, 255) if is_sel else (160, 160, 160, 200)
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
