"""PIL-based sprite compositor with click-to-select and drag-to-reposition.

Sprites are composited at their nominal positions with no rotation or translation
applied. Visibility flags are ignored so all components are always visible.
The selected component is outlined in yellow.

Interaction:
  - Left-click a sprite  → selects it (component_selected signal)
  - Left-drag a sprite   → repositions it live; component_moved emitted on release
  - Click empty space    → no action
"""

import io
from pathlib import Path

from PIL import Image, ImageDraw
from PySide6.QtWidgets import QWidget, QScrollArea, QVBoxLayout
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QPainter


class _CanvasSurface(QWidget):
    """Inner widget that owns the pixmap and handles mouse events."""

    def __init__(self, canvas: "InstrumentCanvas", parent=None):
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

    def mouseMoveEvent(self, event):
        self._canvas._on_move(event)

    def mouseReleaseEvent(self, event):
        self._canvas._on_release(event)


class InstrumentCanvas(QWidget):
    component_selected = Signal(str)        # name of clicked component
    component_moved = Signal(str, int, int)  # name, new_x, new_y  (on drag release)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: dict = {}
        self._yaml_dir: str = ""
        self._selected_name: str | None = None
        self._atlas_cache: dict[str, Image.Image] = {}

        # drag state
        self._drag_name: str | None = None
        self._drag_start: tuple[float, float] | None = None
        self._drag_orig: list[int] | None = None

        self._surface = _CanvasSurface(self)

        scroll = QScrollArea()
        scroll.setWidget(self._surface)
        scroll.setWidgetResizable(False)
        scroll.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    # ── Public API ───────────────────────────────────────────────────────

    def load(self, data: dict, yaml_dir: str):
        self._data = data
        self._yaml_dir = yaml_dir
        self._atlas_cache.clear()
        self._render()

    def set_selected(self, name: str | None):
        if self._selected_name != name:
            self._selected_name = name
            self._render()

    def refresh(self):
        self._render()

    def clear(self):
        self._data = {}
        self._selected_name = None
        self._atlas_cache.clear()
        self._drag_name = None
        self._surface.set_pixmap(QPixmap())

    # ── Mouse handling ────────────────────────────────────────────────────

    def _on_press(self, event):
        if event.button() != Qt.LeftButton:
            return
        cx, cy = event.position().x(), event.position().y()
        hits = self._hits_at(int(cx), int(cy))
        if not hits:
            self._drag_name = None
            return
        # If the current selection is already the topmost hit, cycle downward
        if self._selected_name in hits:
            idx = hits.index(self._selected_name)
            name = hits[(idx + 1) % len(hits)]
        else:
            name = hits[0]  # topmost
        self._drag_name = name
        self._drag_start = (cx, cy)
        comp = self._find_comp(name)
        pos = comp.get("position", [0, 0]) if comp else [0, 0]
        self._drag_orig = [int(pos[0]), int(pos[1])]
        self._surface.setCursor(Qt.SizeAllCursor)
        self.component_selected.emit(name)

    def _on_move(self, event):
        if not (event.buttons() & Qt.LeftButton) or not self._drag_name:
            return
        p = event.position()
        dx = p.x() - self._drag_start[0]
        dy = p.y() - self._drag_start[1]
        new_x = int(round(self._drag_orig[0] + dx))
        new_y = int(round(self._drag_orig[1] - dy))  # canvas y-down → YAML y-up
        comp = self._find_comp(self._drag_name)
        if comp is not None:
            comp["position"] = [new_x, new_y]
            self._render()  # live preview during drag

    def _on_release(self, event):
        if event.button() != Qt.LeftButton or not self._drag_name:
            return
        self._surface.unsetCursor()
        comp = self._find_comp(self._drag_name)
        if comp is not None:
            x, y = comp.get("position", [0, 0])
            self.component_moved.emit(self._drag_name, int(x), int(y))
        self._drag_name = None
        self._drag_start = None
        self._drag_orig = None

    # ── Hit testing ───────────────────────────────────────────────────────

    def _hits_at(self, cx: int, cy: int) -> list[str]:
        """All sprites containing canvas point (cx, cy), topmost first."""
        w, h = self._data.get("size", [310, 310])
        result = []
        for comp in reversed(self._data.get("components", [])):  # topmost first
            if comp.get("type") != "ImagePanel":
                continue
            try:
                _sprite, px, py = self._crop_sprite(comp, w, h)
                cw, ch = comp.get("cliprect", [100, 100])
                if px <= cx < px + cw and py <= cy < py + ch:
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
        self._surface.set_pixmap(self._composite())

    def _composite(self) -> QPixmap:
        w, h = self._data.get("size", [310, 310])
        composite = Image.new("RGBA", (w, h), (30, 30, 30, 255))

        for comp in self._data.get("components", []):
            if comp.get("type") != "ImagePanel":
                continue
            try:
                sprite, px, py = self._crop_sprite(comp, w, h)
                composite.paste(sprite, (px, py), sprite)
            except Exception:
                continue

        if self._selected_name:
            draw = ImageDraw.Draw(composite)
            for comp in self._data.get("components", []):
                if comp.get("name") != self._selected_name:
                    continue
                if comp.get("type") == "ImagePanel":
                    try:
                        sprite, px, py = self._crop_sprite(comp, w, h)
                        cw, ch = sprite.size
                        draw.rectangle(
                            [px, py, px + cw - 1, py + ch - 1],
                            outline=(255, 220, 0, 255),
                            width=2,
                        )
                    except Exception:
                        pass
                else:
                    pos = comp.get("position", [w // 2, h // 2])
                    cx_p, cy_up = int(pos[0]), int(pos[1])
                    cy_p = h - cy_up
                    draw.line([(cx_p - 12, cy_p), (cx_p + 12, cy_p)], fill=(255, 220, 0, 255), width=2)
                    draw.line([(cx_p, cy_p - 12), (cx_p, cy_p + 12)], fill=(255, 220, 0, 255), width=2)
                break

        buf = io.BytesIO()
        composite.save(buf, format="PNG")
        pixmap = QPixmap()
        pixmap.loadFromData(buf.getvalue())
        return pixmap

    def _crop_sprite(self, comp: dict, canvas_w: int, canvas_h: int):
        tex_rel = comp.get("texture", "")
        tex_path = str((Path(self._yaml_dir) / tex_rel).resolve())
        if tex_path not in self._atlas_cache:
            self._atlas_cache[tex_path] = Image.open(tex_path).convert("RGBA")
        atlas = self._atlas_cache[tex_path]

        ox, oy = comp.get("origin", [0, 0])
        cw, ch = comp.get("cliprect", [100, 100])
        px, py = comp.get("position", [0, 0])

        sprite = atlas.crop((ox, oy, ox + cw, oy + ch))
        paste_x = int(round(px - cw / 2))
        paste_y = int(round((canvas_h - py) - ch / 2))

        return sprite, paste_x, paste_y
