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

import io
from pathlib import Path

from PIL import Image, ImageDraw
from PySide6.QtWidgets import QWidget, QScrollArea, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QPainter


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
        self._atlas_cache: dict[str, Image.Image] = {}
        self._hidden: set[str] = set()
        self._zoom: float = 1.0

        # drag state (stored in unzoomed canvas coordinates)
        self._drag_name: str | None = None
        self._drag_start: tuple[float, float] | None = None
        self._drag_orig: list[int] | None = None

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
        self._render()

    def set_selected(self, name: str | None):
        if self._selected_name != name:
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
        self._hidden = set()
        self._atlas_cache.clear()
        self._drag_name = None
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

        self._render()

        # keep the world-point under the cursor stationary:
        # new_scroll = cursor * (zoom_ratio - 1) + old_scroll
        zoom_ratio = self._zoom / old_zoom
        self._scroll.horizontalScrollBar().setValue(
            int(cursor_x * (zoom_ratio - 1) + h_val))
        self._scroll.verticalScrollBar().setValue(
            int(cursor_y * (zoom_ratio - 1) + v_val))

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
        pos = comp.get("position", [0, 0]) if comp else [0, 0]
        self._drag_orig = [int(pos[0]), int(pos[1])]
        self._surface.setCursor(Qt.SizeAllCursor)
        self.component_selected.emit(name)

    def _on_move(self, event):
        p = event.position()
        canvas_x = p.x() / self._zoom
        canvas_y = p.y() / self._zoom
        _w, ih = self._data.get("size", [310, 310]) if self._data else [310, 310]
        self._coord_label.setText(f"X {int(round(canvas_x))}  Y {ih - int(round(canvas_y))}")

        if not (event.buttons() & Qt.LeftButton) or not self._drag_name:
            return
        dx = canvas_x - self._drag_start[0]
        dy = canvas_y - self._drag_start[1]
        new_x = int(round(self._drag_orig[0] + dx))
        new_y = int(round(self._drag_orig[1] - dy))  # y-down → y-up
        comp = self._find_comp(self._drag_name)
        if comp is not None:
            comp["position"] = [new_x, new_y]
            self._render()

    def _on_leave(self):
        self._coord_label.setText("")

    def _on_release(self, event):
        if event.button() != Qt.LeftButton or not self._drag_name:
            return
        self._surface.setCursor(Qt.CrossCursor)
        comp = self._find_comp(self._drag_name)
        if comp is not None:
            x, y = comp.get("position", [0, 0])
            self.component_moved.emit(self._drag_name, int(x), int(y))
        self._drag_name = None
        self._drag_start = None
        self._drag_orig = None

    # ── Hit testing ───────────────────────────────────────────────────────

    def _hits_at(self, cx: int, cy: int) -> list[str]:
        """All sprites containing unzoomed canvas point (cx, cy), topmost first."""
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

        # Save scroll position — widget resize triggered by set_pixmap can reset it.
        h_bar = self._scroll.horizontalScrollBar()
        v_bar = self._scroll.verticalScrollBar()
        saved_h = h_bar.value()
        saved_v = v_bar.value()

        pixmap = self._composite()
        if self._zoom != 1.0:
            pixmap = pixmap.scaled(
                int(pixmap.width() * self._zoom),
                int(pixmap.height() * self._zoom),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        self._surface.set_pixmap(pixmap)

        # Restore only when zoom/size didn't change (i.e. the scroll area range
        # is the same). If range shrank the setValue call clamps gracefully.
        h_bar.setValue(saved_h)
        v_bar.setValue(saved_v)

    def _composite(self) -> QPixmap:
        w, h = self._data.get("size", [310, 310])
        composite = Image.new("RGBA", (w, h), (30, 30, 30, 255))

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
            except Exception:
                continue

        if self._selected_name:
            draw = ImageDraw.Draw(composite)
            for comp in self._data.get("components", []):
                if comp.get("name") != self._selected_name:
                    continue
                ctype = comp.get("type")
                if ctype == "ImagePanel":
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
                elif ctype in ("SpriteSheet", "ScrollingTape"):
                    rect = self._viewport_rect_pil(comp, h)
                    if rect is not None:
                        rx, ry, rw, rh = rect
                        draw.rectangle(
                            [rx, ry, rx + rw - 1, ry + rh - 1],
                            outline=(255, 220, 0, 255),
                            width=2,
                        )
                    else:
                        pos = comp.get("position", [w // 2, h // 2])
                        cx_p, cy_up = int(pos[0]), int(pos[1])
                        cy_p = h - cy_up
                        draw.line([(cx_p - 12, cy_p), (cx_p + 12, cy_p)],
                                  fill=(255, 220, 0, 255), width=2)
                        draw.line([(cx_p, cy_p - 12), (cx_p, cy_p + 12)],
                                  fill=(255, 220, 0, 255), width=2)
                else:
                    pos = comp.get("position", [w // 2, h // 2])
                    cx_p, cy_up = int(pos[0]), int(pos[1])
                    cy_p = h - cy_up
                    draw.line([(cx_p - 12, cy_p), (cx_p + 12, cy_p)],
                              fill=(255, 220, 0, 255), width=2)
                    draw.line([(cx_p, cy_p - 12), (cx_p, cy_p + 12)],
                              fill=(255, 220, 0, 255), width=2)
                break

        buf = io.BytesIO()
        composite.save(buf, format="PNG")
        pixmap = QPixmap()
        pixmap.loadFromData(buf.getvalue())
        return pixmap

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
