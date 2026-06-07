"""Modal texture-region editor.

Displays the full texture with:
- Semi-transparent overlay everywhere except the selected clip region
- Optional grid overlay (configurable X/Y spacing)
- Ctrl+wheel to zoom (mirrored in zoom spinbox)
- Crosshair cursor with live texture-coordinate readout
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QScrollArea, QWidget, QDialogButtonBox,
)
from gauge_designer.ui_utils import QSpinBox
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPainter, QPixmap, QColor, QPen


class _TextureView(QWidget):
    """Custom widget that renders the texture with clip overlay and grid."""

    mouse_pos_changed = Signal(int, int)  # texture-space x, y; (-1,-1) on leave
    zoom_changed = Signal(float)          # new zoom factor

    def __init__(self, pixmap: QPixmap,
                 orig_x: QSpinBox, orig_y: QSpinBox,
                 clip_w: QSpinBox, clip_h: QSpinBox,
                 grid_x: QSpinBox, grid_y: QSpinBox,
                 scroll_area=None,
                 parent=None):
        super().__init__(parent)
        self._pixmap = pixmap
        self._orig_x = orig_x
        self._orig_y = orig_y
        self._clip_w = clip_w
        self._clip_h = clip_h
        self._grid_x = grid_x
        self._grid_y = grid_y
        self._scroll_area = scroll_area
        self._zoom = 0.5
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)
        self._update_size()

    # ── Public ────────────────────────────────────────────────────────────

    def set_zoom(self, zoom: float):
        self._zoom = max(0.05, min(8.0, zoom))
        self._update_size()
        self.update()
        self.zoom_changed.emit(self._zoom)

    def refresh(self):
        self.update()

    # ── Internal ──────────────────────────────────────────────────────────

    def _update_size(self):
        if self._pixmap.isNull():
            self.setFixedSize(400, 400)
        else:
            self.setFixedSize(
                max(1, int(self._pixmap.width()  * self._zoom)),
                max(1, int(self._pixmap.height() * self._zoom)),
            )

    def mouseMoveEvent(self, event):
        if not self._pixmap.isNull():
            tx = int(event.position().x() / self._zoom)
            ty = int(event.position().y() / self._zoom)
            self.mouse_pos_changed.emit(tx, ty)
        event.ignore()

    def leaveEvent(self, event):
        self.mouse_pos_changed.emit(-1, -1)
        event.ignore()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
            old_zoom = self._zoom
            cx = event.position().x()
            cy = event.position().y()
            sa = self._scroll_area
            h_val = sa.horizontalScrollBar().value() if sa else 0
            v_val = sa.verticalScrollBar().value()   if sa else 0
            self.set_zoom(self._zoom * factor)
            if sa and self._zoom != old_zoom:
                zoom_ratio = self._zoom / old_zoom
                new_h = int(cx * (zoom_ratio - 1) + h_val)
                new_v = int(cy * (zoom_ratio - 1) + v_val)
                QTimer.singleShot(0, lambda: (
                    sa.horizontalScrollBar().setValue(new_h),
                    sa.verticalScrollBar().setValue(new_v),
                ))
            event.accept()
        else:
            event.ignore()

    def paintEvent(self, _event):
        if self._pixmap.isNull():
            return
        z  = self._zoom
        iw = self._pixmap.width()
        ih = self._pixmap.height()
        sw = int(iw * z)
        sh = int(ih * z)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, z < 1.0)

        # Texture
        painter.drawPixmap(0, 0, sw, sh, self._pixmap)

        # Clip region in screen coordinates
        ox = int(self._orig_x.value() * z)
        oy = int(self._orig_y.value() * z)
        cw = int(self._clip_w.value() * z)
        ch = int(self._clip_h.value() * z)

        # Overlay as four rectangles surrounding the clip region
        ov = QColor(0, 0, 0, 150)
        if oy > 0:
            painter.fillRect(0, 0, sw, oy, ov)
        bot = oy + ch
        if bot < sh:
            painter.fillRect(0, bot, sw, sh - bot, ov)
        if ox > 0:
            painter.fillRect(0, oy, ox, ch, ov)
        right = ox + cw
        if right < sw:
            painter.fillRect(right, oy, sw - right, ch, ov)

        # Clip region border
        painter.setPen(QPen(QColor(255, 220, 0), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(ox, oy, max(cw - 1, 0), max(ch - 1, 0))

        # Grid
        gx = self._grid_x.value()
        gy = self._grid_y.value()
        if gx > 0 or gy > 0:
            painter.setPen(QPen(QColor(210, 210, 210, 120), 1))
            if gx > 0:
                x = 0.0
                while x <= iw:
                    xi = int(x * z)
                    painter.drawLine(xi, 0, xi, sh)
                    x += gx
            if gy > 0:
                y = 0.0
                while y <= ih:
                    yi = int(y * z)
                    painter.drawLine(0, yi, sw, yi)
                    y += gy

        painter.end()


class TextureEditorDialog(QDialog):
    def __init__(self, texture_path: str,
                 clip_w: int, clip_h: int,
                 origin_x: int, origin_y: int,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Texture Editor")
        self.setModal(True)
        self.resize(1000, 750)

        pixmap = QPixmap()
        if texture_path and Path(texture_path).is_file():
            pixmap.load(texture_path)

        def _sb(lo: int = 0, hi: int = 4096, val: int = 0) -> QSpinBox:
            s = QSpinBox()
            s.setRange(lo, hi)
            s.setValue(val)
            s.setFixedWidth(90)
            return s

        # ── Spinboxes ──────────────────────────────────────────────────────
        self._orig_x = _sb(val=origin_x)
        self._orig_y = _sb(val=origin_y)
        self._clip_w = _sb(lo=1, val=clip_w)
        self._clip_h = _sb(lo=1, val=clip_h)
        self._grid_x = _sb(lo=0, hi=2048, val=100)
        self._grid_y = _sb(lo=0, hi=2048, val=100)

        self._zoom_sb = QSpinBox()
        self._zoom_sb.setRange(5, 800)
        self._zoom_sb.setSuffix(" %")
        self._zoom_sb.setValue(50)
        self._zoom_sb.setFixedWidth(90)
        self._zoom_sb.setSingleStep(5)

        # ── Controls grid ──────────────────────────────────────────────────
        #   Col:  0           1           2     3           4(stretch)  5         6           7     8
        #   Row0: Origin X:  [orig_x]    Y:   [orig_y]                Grid X:  [grid_x]    Y:   [grid_y]
        #   Row1: Clip W:    [clip_w]    H:   [clip_h]                Zoom:    [zoom_sb]
        grid = QGridLayout()
        grid.setSpacing(6)
        grid.setColumnStretch(4, 1)  # gap between left and right groups

        grid.addWidget(QLabel("Origin X:"), 0, 0)
        grid.addWidget(self._orig_x,        0, 1)
        grid.addWidget(QLabel("Y:"),        0, 2)
        grid.addWidget(self._orig_y,        0, 3)

        grid.addWidget(QLabel("Clip W:"),   1, 0)
        grid.addWidget(self._clip_w,        1, 1)
        grid.addWidget(QLabel("H:"),        1, 2)
        grid.addWidget(self._clip_h,        1, 3)

        grid.addWidget(QLabel("Grid X:"),   0, 5)
        grid.addWidget(self._grid_x,        0, 6)
        grid.addWidget(QLabel("Y:"),        0, 7)
        grid.addWidget(self._grid_y,        0, 8)

        grid.addWidget(QLabel("Zoom:"),     1, 5)
        grid.addWidget(self._zoom_sb,       1, 6)

        # ── Texture view ───────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setAlignment(Qt.AlignCenter)

        self._view = _TextureView(
            pixmap,
            self._orig_x, self._orig_y,
            self._clip_w, self._clip_h,
            self._grid_x, self._grid_y,
            scroll_area=scroll,
        )
        scroll.setWidget(self._view)

        for sb in (self._orig_x, self._orig_y,
                   self._clip_w, self._clip_h,
                   self._grid_x, self._grid_y):
            sb.valueChanged.connect(self._view.refresh)

        self._view.zoom_changed.connect(self._on_zoom_changed)
        self._zoom_sb.valueChanged.connect(self._on_zoom_spinbox)

        if not pixmap.isNull():
            fit = min(1.0, 580 / max(pixmap.height(), 1))
            self._view.set_zoom(fit)  # emits zoom_changed → updates _zoom_sb

        # ── Coordinate label ───────────────────────────────────────────────
        self._coord_label = QLabel("X: —   Y: —")
        self._view.mouse_pos_changed.connect(self._on_mouse_pos)

        # ── Buttons ────────────────────────────────────────────────────────
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        # ── Layout ─────────────────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addLayout(grid)
        layout.addWidget(scroll, 1)
        layout.addWidget(self._coord_label)
        layout.addWidget(btns)

    def _on_zoom_changed(self, zoom: float):
        self._zoom_sb.blockSignals(True)
        self._zoom_sb.setValue(round(zoom * 100))
        self._zoom_sb.blockSignals(False)

    def _on_zoom_spinbox(self, value: int):
        self._view.zoom_changed.disconnect(self._on_zoom_changed)
        self._view.set_zoom(value / 100.0)
        self._view.zoom_changed.connect(self._on_zoom_changed)

    def _on_mouse_pos(self, x: int, y: int):
        if x < 0:
            self._coord_label.setText("X: —   Y: —")
        else:
            self._coord_label.setText(f"X: {x}   Y: {y}")

    def get_values(self) -> tuple[int, int, int, int]:
        """Returns (clip_w, clip_h, origin_x, origin_y)."""
        return (
            self._clip_w.value(), self._clip_h.value(),
            self._orig_x.value(), self._orig_y.value(),
        )
