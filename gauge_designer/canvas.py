"""PIL-based static sprite compositor — renders an instrument YAML as a QPixmap.

Sprites are composited at their nominal positions with no rotation or translation
applied (datarefs are unavailable at design time). Visibility flags are ignored so
all components are always visible. The selected component is outlined in yellow.
"""

import io
from pathlib import Path

from PIL import Image, ImageDraw
from PySide6.QtWidgets import QWidget, QScrollArea, QLabel, QVBoxLayout
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap


class InstrumentCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: dict = {}
        self._yaml_dir: str = ""
        self._selected_name: str | None = None
        self._atlas_cache: dict[str, Image.Image] = {}

        self._img_label = QLabel()
        self._img_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        scroll = QScrollArea()
        scroll.setWidget(self._img_label)
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
        self._img_label.setPixmap(QPixmap())

    # ── Rendering ────────────────────────────────────────────────────────

    def _render(self):
        if not self._data:
            self._img_label.setPixmap(QPixmap())
            return
        pixmap = self._composite()
        self._img_label.setPixmap(pixmap)
        self._img_label.resize(pixmap.size())

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

        # Yellow outline for the selected component drawn on top
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
                    # Non-sprite: draw a crosshair at position
                    pos = comp.get("position", [w // 2, h // 2])
                    cx, cy_up = int(pos[0]), int(pos[1])
                    cy = h - cy_up
                    draw.line([(cx - 12, cy), (cx + 12, cy)], fill=(255, 220, 0, 255), width=2)
                    draw.line([(cx, cy - 12), (cx, cy + 12)], fill=(255, 220, 0, 255), width=2)
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

        # Convert from YAML centre+y-up coords to PIL top-left+y-down
        paste_x = int(round(px - cw / 2))
        paste_y = int(round((canvas_h - py) - ch / 2))

        return sprite, paste_x, paste_y
