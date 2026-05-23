"""Structured form for editing instrument components.

Supports three image-based component types whose visible sections adapt
to the selected type:

  ImagePanel    — atlas sub-region sprite with optional rotation,
                  translation, viewport clip, visibility.
  SpriteSheet   — frame-indexed sprite grid with animation dataref,
                  viewport clip, visibility.
  ScrollingTape — continuously scrolling texture strip with scroll
                  dataref, viewport clip, visibility.
  Text          — label / dataref readout (no texture section).
"""

import os
from pathlib import Path

import gauge_core.convert as _convert_reg  # noqa: F401 — registers convert functions
import gauge_core.component as _component_reg  # noqa: F401
from gauge_core.registry import known_converts
from gauge_designer.ui_utils import flip_y, is_y_down
from PySide6.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
    QPushButton, QCheckBox, QDialog, QColorDialog,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView,
    QFileDialog,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor


class _NoScrollComboBox(QComboBox):
    """QComboBox that ignores mouse-wheel events to prevent accidental changes."""
    def wheelEvent(self, event):
        event.ignore()


class _ColorButton(QPushButton):
    """Button showing the current RGBA color; opens QColorDialog on click."""
    color_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rgba = (255, 255, 255, 255)
        self.setFixedHeight(24)
        self.clicked.connect(self._pick)
        self._refresh()

    def set_rgba(self, raw) -> None:
        if raw is None:
            self._rgba = (255, 255, 255, 255)
        elif len(raw) == 3:
            self._rgba = (int(raw[0]), int(raw[1]), int(raw[2]), 255)
        else:
            self._rgba = tuple(int(v) for v in raw[:4])
        self._refresh()

    def get_rgba(self) -> tuple:
        return self._rgba

    def _refresh(self) -> None:
        r, g, b, a = self._rgba
        luma = r * 299 + g * 587 + b * 114
        fg = "#000" if luma > 128000 else "#fff"
        self.setText(f"  #{r:02X}{g:02X}{b:02X}   α {a}")
        self.setStyleSheet(
            f"background-color: rgb({r},{g},{b}); color: {fg};"
            f"border: 1px solid #888; text-align: left; padding: 2px;"
        )

    def _pick(self) -> None:
        r, g, b, a = self._rgba
        c = QColorDialog.getColor(
            QColor(r, g, b, a), self, "Pick Color",
            QColorDialog.ShowAlphaChannel,
        )
        if c.isValid():
            self._rgba = (c.red(), c.green(), c.blue(), c.alpha())
            self._refresh()
            self.color_changed.emit()


# ── Registry data ─────────────────────────────────────────────────────────────

_NONE = "(none)"

# Derived from the live registry — adding a function to convert.py is enough.
_PREDICATE_PREFIXES = ("true_if_", "nav_gsflg_")

def _build_func_lists() -> tuple[list[str], list[str]]:
    all_fns = known_converts()
    predicates = [n for n in all_fns if any(n.startswith(p) for p in _PREDICATE_PREFIXES)]
    values = [_NONE] + [n for n in all_fns if n not in predicates]
    return values, predicates

_VALUE_FUNCS, _PREDICATES = _build_func_lists()

_COMP_TYPES = ["ImagePanel", "SpriteSheet", "ScrollingTape", "Text",
               "Line", "Arc", "FilledRect", "Polygon", "VectorTape"]


def _coerce_num(text: str):
    t = text.strip()
    try:
        return int(t) if ("." not in t and "e" not in t.lower()) else float(t)
    except ValueError:
        return 0


# ── Table editor ─────────────────────────────────────────────────────────────

class _TableEditor(QWidget):
    changed = Signal()

    def __init__(self, *headers, parent=None):
        super().__init__(parent)
        n = max(2, len(headers))
        self._tbl = QTableWidget(0, n)
        self._tbl.setHorizontalHeaderLabels(list(headers) if headers else ["Col 0", "Col 1"])
        self._tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl.setFixedHeight(110)
        self._tbl.itemChanged.connect(lambda: self.changed.emit())

        add = QPushButton("+"); add.setFixedWidth(26); add.clicked.connect(self._add)
        rm  = QPushButton("−"); rm.setFixedWidth(26);  rm.clicked.connect(self._rm)
        btns = QHBoxLayout()
        btns.setContentsMargins(0, 0, 0, 0); btns.setSpacing(2)
        btns.addWidget(add); btns.addWidget(rm); btns.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(2)
        layout.addWidget(self._tbl); layout.addLayout(btns)

    def load(self, data: list):
        self._tbl.blockSignals(True)
        self._tbl.setRowCount(0)
        n = self._tbl.columnCount()
        for row in data:
            if isinstance(row, (list, tuple)) and len(row) >= min(2, n):
                r = self._tbl.rowCount()
                self._tbl.insertRow(r)
                for c in range(min(n, len(row))):
                    self._tbl.setItem(r, c, QTableWidgetItem(str(row[c])))
        self._tbl.blockSignals(False)

    def get_data(self) -> list:
        out = []
        n = self._tbl.columnCount()
        for r in range(self._tbl.rowCount()):
            items = [self._tbl.item(r, c) for c in range(n)]
            if all(items):
                out.append([_coerce_num(item.text()) for item in items])
        return out

    def _add(self):
        self._tbl.blockSignals(True)
        r = self._tbl.rowCount()
        self._tbl.insertRow(r)
        for c in range(self._tbl.columnCount()):
            self._tbl.setItem(r, c, QTableWidgetItem("0"))
        self._tbl.blockSignals(False)
        self.changed.emit()

    def _rm(self):
        r = self._tbl.currentRow()
        if r >= 0:
            self._tbl.removeRow(r)
            self.changed.emit()


# ── Collapsible section ───────────────────────────────────────────────────────

class _Section(QWidget):
    toggled = Signal(bool)

    def __init__(self, title: str, optional: bool = False, parent=None):
        super().__init__(parent)
        self._optional = optional

        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 8, 0, 2)
        hdr.setSpacing(4)

        if optional:
            self._chk = QCheckBox()
            self._chk.toggled.connect(self._on_toggled)
            hdr.addWidget(self._chk)

        lbl = QLabel(title)
        f = lbl.font(); f.setBold(True); lbl.setFont(f)
        hdr.addWidget(lbl)

        sep = QWidget(); sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #555;")
        hdr.addWidget(sep, stretch=1)

        self._body = QWidget()
        self._form = QFormLayout(self._body)
        self._form.setContentsMargins(12, 2, 0, 4)
        self._form.setHorizontalSpacing(8)
        self._form.setVerticalSpacing(4)
        if optional:
            self._body.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        layout.addLayout(hdr)
        layout.addWidget(self._body)

    def row(self, label: str, widget: QWidget) -> QWidget:
        self._form.addRow(label, widget)
        return widget

    def row_pair(self, label: str, w1: QWidget, w2: QWidget):
        box = QWidget()
        hl = QHBoxLayout(box)
        hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(4)
        hl.addWidget(w1); hl.addWidget(w2)
        self._form.addRow(label, box)

    def row_widget(self, widget: QWidget) -> QWidget:
        self._form.addRow(widget)
        return widget

    @property
    def active(self) -> bool:
        return self._chk.isChecked() if self._optional else True

    def set_active(self, on: bool):
        if self._optional:
            self._chk.blockSignals(True)
            self._chk.setChecked(on)
            self._chk.blockSignals(False)
            self._body.setVisible(on)

    def show_body(self, visible: bool):
        self._body.setVisible(visible)

    def _on_toggled(self, on: bool):
        self._body.setVisible(on)
        self.toggled.emit(on)


def _sb(lo: int = -4096, hi: int = 4096) -> QSpinBox:
    s = QSpinBox(); s.setRange(lo, hi); s.setMinimumWidth(64); return s


def _pair_box(w1: QWidget, w2: QWidget, sep: str = "×") -> QWidget:
    box = QWidget()
    hl = QHBoxLayout(box)
    hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(4)
    hl.addWidget(w1); hl.addWidget(QLabel(sep)); hl.addWidget(w2); hl.addStretch()
    return box


# ── Main form ─────────────────────────────────────────────────────────────────

class PropertiesForm(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._yaml_dir: str = ""
        self._ref_height: int = 310
        self._extra: dict = {}
        self._loading = False

        body = QWidget()
        self._vbox = QVBoxLayout(body)
        self._vbox.setContentsMargins(6, 4, 6, 4)
        self._vbox.setSpacing(0)

        self._mk_component()
        self._mk_position()
        self._mk_texture()
        self._mk_spritesheet()
        self._mk_scrolltape()
        self._mk_line_sec()
        self._mk_arc_sec()
        self._mk_filledrect_sec()
        self._mk_polygon_sec()
        self._mk_vectortape_sec()
        self._mk_rotation()
        self._mk_translation()
        self._mk_animation()
        self._mk_viewport()
        self._mk_visibility()
        self._vbox.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(body)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def set_yaml_dir(self, d: str):
        self._yaml_dir = d

    def set_ref_height(self, h: int):
        self._ref_height = h

    # ── Section builders ──────────────────────────────────────────────────

    def _mk_component(self):
        s = _Section("Component")
        self._name = QLineEdit()
        self._name.editingFinished.connect(self._emit)
        s.row("Name", self._name)

        self._type = _NoScrollComboBox()
        self._type.addItems(_COMP_TYPES)
        self._type.currentTextChanged.connect(self._on_type_changed)
        self._type.currentTextChanged.connect(self._emit)
        s.row("Type", self._type)
        self._vbox.addWidget(s)

    def _mk_position(self):
        self._pos_sec = _Section("Position")
        self._px = _sb(); self._py = _sb()
        for w in (self._px, self._py):
            w.valueChanged.connect(self._emit)
        self._pos_sec.row_pair("X  /  Y", self._px, self._py)
        self._vbox.addWidget(self._pos_sec)

    def _mk_texture(self):
        self._tex_sec = _Section("Texture")

        # File row — shared by all image-based types
        tex_row = QWidget()
        hl = QHBoxLayout(tex_row)
        hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(4)
        self._tex_edit_btn = QPushButton("Edit"); self._tex_edit_btn.setFixedWidth(38)
        self._tex_edit_btn.setToolTip("Open texture editor (ImagePanel only)")
        self._tex_edit_btn.setEnabled(False)
        self._tex_edit_btn.clicked.connect(self._open_texture_editor)
        hl.addWidget(self._tex_edit_btn)
        self._tex = QLineEdit()
        self._tex.editingFinished.connect(self._emit)
        self._tex.textChanged.connect(
            lambda t: self._tex_edit_btn.setEnabled(
                bool(t.strip()) and self._type.currentText() == "ImagePanel"
            )
        )
        hl.addWidget(self._tex)
        btn = QPushButton("…"); btn.setFixedWidth(26)
        btn.clicked.connect(self._browse_tex)
        hl.addWidget(btn)
        self._tex_sec.row("File", tex_row)

        # Atlas detail — ImagePanel-only fields in a toggleable container
        self._atlas_detail = QWidget()
        ad = QFormLayout(self._atlas_detail)
        ad.setContentsMargins(0, 0, 0, 0)
        ad.setHorizontalSpacing(8)
        ad.setVerticalSpacing(4)

        self._clip_w = _sb(0, 4096); self._clip_h = _sb(0, 4096)
        for w in (self._clip_w, self._clip_h):
            w.valueChanged.connect(self._emit)
        ad.addRow("Clip W  /  H", _pair_box(self._clip_w, self._clip_h))

        self._orig_x = _sb(0, 4096); self._orig_y = _sb(0, 4096)
        for w in (self._orig_x, self._orig_y):
            w.valueChanged.connect(self._emit)
        ad.addRow("Origin X  /  Y", _pair_box(self._orig_x, self._orig_y))

        self._resize_chk = QCheckBox("Fit to gauge size")
        self._resize_chk.toggled.connect(self._on_resize_toggled)
        self._resize_chk.toggled.connect(self._emit)
        ad.addRow(self._resize_chk)

        self._prop_chk = QCheckBox("Maintain proportions")
        self._prop_chk.setChecked(True)
        self._prop_chk.setEnabled(False)
        self._prop_chk.toggled.connect(self._emit)
        ad.addRow(self._prop_chk)

        self._tex_sec.row_widget(self._atlas_detail)
        self._vbox.addWidget(self._tex_sec)

    def _mk_spritesheet(self):
        """Grid layout parameters — SpriteSheet only."""
        self._ss_sec = _Section("Sprite grid")
        self._ss_sec.setVisible(False)

        self._ss_cols = QSpinBox(); self._ss_cols.setRange(1, 999); self._ss_cols.setMinimumWidth(64)
        self._ss_rows_sb = QSpinBox(); self._ss_rows_sb.setRange(1, 999); self._ss_rows_sb.setMinimumWidth(64)
        for w in (self._ss_cols, self._ss_rows_sb):
            w.valueChanged.connect(self._emit)
        cr_box = QWidget(); crl = QHBoxLayout(cr_box)
        crl.setContentsMargins(0, 0, 0, 0); crl.setSpacing(4)
        crl.addWidget(self._ss_cols); crl.addWidget(QLabel("cols"))
        crl.addWidget(self._ss_rows_sb); crl.addWidget(QLabel("rows"))
        crl.addStretch()
        self._ss_sec.row("Grid size", cr_box)

        self._ss_fw = _sb(1, 4096); self._ss_fh = _sb(1, 4096)
        for w in (self._ss_fw, self._ss_fh):
            w.valueChanged.connect(self._emit)
        self._ss_sec.row("Frame W  ×  H", _pair_box(self._ss_fw, self._ss_fh))

        # Stride: 0 = special value meaning "same as frame size"
        self._ss_sx = _sb(0, 4096); self._ss_sx.setSpecialValueText("= frame W")
        self._ss_sy = _sb(0, 4096); self._ss_sy.setSpecialValueText("= frame H")
        for w in (self._ss_sx, self._ss_sy):
            w.valueChanged.connect(self._emit)
        self._ss_sec.row("Stride X  ×  Y", _pair_box(self._ss_sx, self._ss_sy))
        hint = QLabel("Stride overrides frame size when atlas has inter-frame gaps.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #999; font-size: 10px;")
        self._ss_sec.row_widget(hint)

        self._ss_smooth = QCheckBox("Smooth  (sub-frame X interpolation for fluid animation)")
        self._ss_smooth.setChecked(True)
        self._ss_smooth.toggled.connect(self._emit)
        self._ss_sec.row_widget(self._ss_smooth)

        self._vbox.addWidget(self._ss_sec)

    def _mk_scrolltape(self):
        """Scroll axis — ScrollingTape only."""
        self._st_sec = _Section("Scroll tape")
        self._st_sec.setVisible(False)

        self._st_axis = _NoScrollComboBox()
        self._st_axis.addItems(["y  (vertical)", "x  (horizontal)"])
        self._st_axis.currentTextChanged.connect(self._emit)
        self._st_sec.row("Scroll axis", self._st_axis)

        self._vbox.addWidget(self._st_sec)

    def _mk_line_sec(self):
        self._line_sec = _Section("Line")
        self._line_sec.setVisible(False)

        self._line_x1 = _sb(); self._line_y1 = _sb()
        for w in (self._line_x1, self._line_y1):
            w.valueChanged.connect(self._emit)
        self._line_sec.row_pair("Start X  /  Y", self._line_x1, self._line_y1)

        self._line_x2 = _sb(); self._line_y2 = _sb()
        for w in (self._line_x2, self._line_y2):
            w.valueChanged.connect(self._emit)
        self._line_sec.row_pair("End X  /  Y", self._line_x2, self._line_y2)

        self._line_color = _ColorButton()
        self._line_color.color_changed.connect(self._emit)
        self._line_sec.row("Color", self._line_color)

        self._line_width = QDoubleSpinBox()
        self._line_width.setRange(0.5, 50.0); self._line_width.setDecimals(1)
        self._line_width.setValue(1.0)
        self._line_width.valueChanged.connect(self._emit)
        self._line_sec.row("Width px", self._line_width)

        self._vbox.addWidget(self._line_sec)

    def _mk_arc_sec(self):
        self._arc_sec = _Section("Arc")
        self._arc_sec.setVisible(False)

        self._arc_cx = _sb(); self._arc_cy = _sb()
        for w in (self._arc_cx, self._arc_cy):
            w.valueChanged.connect(self._emit)
        self._arc_sec.row_pair("Center X  /  Y", self._arc_cx, self._arc_cy)

        self._arc_radius = QDoubleSpinBox()
        self._arc_radius.setRange(0.0, 4096.0); self._arc_radius.setDecimals(1)
        self._arc_radius.valueChanged.connect(self._emit)
        self._arc_sec.row("Radius", self._arc_radius)

        self._arc_start = QDoubleSpinBox()
        self._arc_start.setRange(-360.0, 360.0); self._arc_start.setDecimals(1)
        self._arc_start.valueChanged.connect(self._emit)
        self._arc_sec.row("Start angle °", self._arc_start)

        self._arc_end = QDoubleSpinBox()
        self._arc_end.setRange(-360.0, 360.0); self._arc_end.setDecimals(1)
        self._arc_end.setValue(360.0)
        self._arc_end.valueChanged.connect(self._emit)
        self._arc_sec.row("End angle °", self._arc_end)

        self._arc_color = _ColorButton()
        self._arc_color.color_changed.connect(self._emit)
        self._arc_sec.row("Color", self._arc_color)

        self._arc_width = QDoubleSpinBox()
        self._arc_width.setRange(0.5, 50.0); self._arc_width.setDecimals(1)
        self._arc_width.setValue(1.0)
        self._arc_width.valueChanged.connect(self._emit)
        self._arc_sec.row("Width px", self._arc_width)

        self._arc_tilt = QDoubleSpinBox()
        self._arc_tilt.setRange(-360.0, 360.0); self._arc_tilt.setDecimals(1)
        self._arc_tilt.valueChanged.connect(self._emit)
        self._arc_sec.row("Tilt °", self._arc_tilt)

        self._arc_segs = QSpinBox()
        self._arc_segs.setRange(8, 256); self._arc_segs.setValue(64)
        self._arc_segs.valueChanged.connect(self._emit)
        self._arc_sec.row("Segments", self._arc_segs)

        self._vbox.addWidget(self._arc_sec)

    def _mk_filledrect_sec(self):
        self._frt_sec = _Section("Rectangle")
        self._frt_sec.setVisible(False)

        self._frt_w = _sb(0, 4096); self._frt_h = _sb(0, 4096)
        for w in (self._frt_w, self._frt_h):
            w.valueChanged.connect(self._emit)
        self._frt_sec.row_pair("Width  ×  Height", self._frt_w, self._frt_h)

        self._frt_color = _ColorButton()
        self._frt_color.color_changed.connect(self._emit)
        self._frt_sec.row("Fill color", self._frt_color)

        self._frt_outline_chk = QCheckBox("Outline")
        self._frt_outline_chk.toggled.connect(self._on_frt_outline_toggled)
        self._frt_outline_chk.toggled.connect(self._emit)
        self._frt_sec.row_widget(self._frt_outline_chk)

        self._frt_outline_color = _ColorButton()
        self._frt_outline_color.set_rgba((255, 255, 255, 255))
        self._frt_outline_color.setEnabled(False)
        self._frt_outline_color.color_changed.connect(self._emit)
        self._frt_sec.row("Outline color", self._frt_outline_color)

        self._frt_outline_width = QDoubleSpinBox()
        self._frt_outline_width.setRange(0.5, 50.0); self._frt_outline_width.setDecimals(1)
        self._frt_outline_width.setValue(1.0)
        self._frt_outline_width.setEnabled(False)
        self._frt_outline_width.valueChanged.connect(self._emit)
        self._frt_sec.row("Outline width", self._frt_outline_width)

        self._vbox.addWidget(self._frt_sec)

    def _mk_polygon_sec(self):
        self._poly_sec = _Section("Polygon")
        self._poly_sec.setVisible(False)

        self._poly_pts = _TableEditor("X", "Y")
        self._poly_pts.changed.connect(self._emit)
        self._poly_sec.row("Points", self._poly_pts)

        self._poly_color = _ColorButton()
        self._poly_color.color_changed.connect(self._emit)
        self._poly_sec.row("Fill color", self._poly_color)

        self._poly_filled = QCheckBox("Filled")
        self._poly_filled.setChecked(True)
        self._poly_filled.toggled.connect(self._on_poly_filled_toggled)
        self._poly_filled.toggled.connect(self._emit)
        self._poly_sec.row_widget(self._poly_filled)

        # Unfilled-only: outline width (primary color is the outline color)
        self._poly_width = QDoubleSpinBox()
        self._poly_width.setRange(0.5, 50.0); self._poly_width.setDecimals(1)
        self._poly_width.setValue(1.0)
        self._poly_width.setEnabled(False)  # shown only when not filled
        self._poly_width.valueChanged.connect(self._emit)
        self._poly_sec.row("Outline width", self._poly_width)

        # Filled + outline overlay
        self._poly_outline_chk = QCheckBox("Add outline")
        self._poly_outline_chk.toggled.connect(self._on_poly_outline_toggled)
        self._poly_outline_chk.toggled.connect(self._emit)
        self._poly_sec.row_widget(self._poly_outline_chk)

        self._poly_outline_color = _ColorButton()
        self._poly_outline_color.set_rgba((255, 255, 255, 255))
        self._poly_outline_color.setEnabled(False)
        self._poly_outline_color.color_changed.connect(self._emit)
        self._poly_sec.row("Outline color", self._poly_outline_color)

        self._poly_outline_width = QDoubleSpinBox()
        self._poly_outline_width.setRange(0.5, 50.0); self._poly_outline_width.setDecimals(1)
        self._poly_outline_width.setValue(1.0)
        self._poly_outline_width.setEnabled(False)
        self._poly_outline_width.valueChanged.connect(self._emit)
        self._poly_sec.row("Outline width ", self._poly_outline_width)

        self._vbox.addWidget(self._poly_sec)

    def _mk_vectortape_sec(self):
        self._vt_sec = _Section("Vector Tape")
        self._vt_sec.setVisible(False)
        self._vt_labels_cache: dict = {}   # preserves interval/color/format/offset

        self._vt_axis = _NoScrollComboBox()
        self._vt_axis.addItems(["y  (vertical)", "x  (horizontal)"])
        self._vt_axis.currentTextChanged.connect(self._emit)
        self._vt_sec.row("Scroll axis", self._vt_axis)

        self._vt_ppu = QDoubleSpinBox()
        self._vt_ppu.setRange(0.1, 100.0); self._vt_ppu.setDecimals(2)
        self._vt_ppu.setValue(5.0)
        self._vt_ppu.valueChanged.connect(self._emit)
        self._vt_sec.row("Pixels / unit", self._vt_ppu)

        self._vt_tick_side = _NoScrollComboBox()
        self._vt_tick_side.addItems(["left", "right", "top", "bottom"])
        self._vt_tick_side.currentTextChanged.connect(self._emit)
        self._vt_sec.row("Tick side", self._vt_tick_side)

        self._vt_tick_color = _ColorButton()
        self._vt_tick_color.color_changed.connect(self._emit)
        self._vt_sec.row("Tick color", self._vt_tick_color)

        self._vt_ticks = _TableEditor("Interval", "Length", "Width")
        self._vt_ticks.changed.connect(self._emit)
        self._vt_sec.row("Ticks", self._vt_ticks)

        self._vt_label_interval = QDoubleSpinBox()
        self._vt_label_interval.setRange(0.0, 9999.0); self._vt_label_interval.setDecimals(1)
        self._vt_label_interval.setSpecialValueText("(none)")
        self._vt_label_interval.valueChanged.connect(self._emit)
        self._vt_sec.row("Label interval", self._vt_label_interval)

        self._vt_label_offset = QDoubleSpinBox()
        self._vt_label_offset.setRange(0.0, 200.0); self._vt_label_offset.setDecimals(1)
        self._vt_label_offset.setValue(8.0)
        self._vt_label_offset.valueChanged.connect(self._emit)
        self._vt_sec.row("Label offset px", self._vt_label_offset)

        self._vt_label_side = _NoScrollComboBox()
        self._vt_label_side.addItems(["(same as tick side)", "left", "right", "top", "bottom"])
        self._vt_label_side.currentTextChanged.connect(self._emit)
        self._vt_sec.row("Label side", self._vt_label_side)

        self._vt_label_font_size = QDoubleSpinBox()
        self._vt_label_font_size.setRange(4.0, 120.0); self._vt_label_font_size.setDecimals(1)
        self._vt_label_font_size.setValue(18.0)
        self._vt_label_font_size.valueChanged.connect(self._emit)
        self._vt_sec.row("Label size px", self._vt_label_font_size)

        self._vt_label_font = QLineEdit()
        self._vt_label_font.setPlaceholderText("e.g. Arial  (blank = default)")
        self._vt_label_font.editingFinished.connect(self._emit)
        self._vt_sec.row("Label font", self._vt_label_font)

        hint = QLabel("Ticks, label interval/color/format and bands are preserved as-is from YAML.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #999; font-size: 10px;")
        self._vt_sec.row_widget(hint)

        self._vbox.addWidget(self._vt_sec)

    def _mk_rotation(self):
        self._rot_sec = _Section("Rotation", optional=True)
        self._rot_sec.toggled.connect(self._emit)

        self._rot_dr = QLineEdit(); self._rot_dr.editingFinished.connect(self._emit)
        self._rot_sec.row("Dataref", self._dr_field(self._rot_dr))

        self._rot_fn = _NoScrollComboBox(); self._rot_fn.addItems(_VALUE_FUNCS)
        self._rot_fn.currentTextChanged.connect(self._emit)
        self._rot_sec.row("Convert fn", self._rot_fn)

        self._rot_cx = _sb(); self._rot_cy = _sb()
        for w in (self._rot_cx, self._rot_cy):
            w.valueChanged.connect(self._emit)
        self._rot_sec.row_pair("Pivot X  /  Y", self._rot_cx, self._rot_cy)

        self._rot_tbl = _TableEditor("Input value", "Angle °")
        self._rot_tbl.changed.connect(self._emit)
        self._rot_sec.row("Table", self._rot_tbl)

        self._vbox.addWidget(self._rot_sec)

    def _mk_translation(self):
        self._tr_sec = _Section("Translation", optional=True)
        self._tr_sec.toggled.connect(self._emit)

        self._tr_dr = QLineEdit(); self._tr_dr.editingFinished.connect(self._emit)
        self._tr_sec.row("Dataref", self._dr_field(self._tr_dr))

        self._tr_fn = _NoScrollComboBox(); self._tr_fn.addItems(_VALUE_FUNCS)
        self._tr_fn.currentTextChanged.connect(self._emit)
        self._tr_sec.row("Convert fn", self._tr_fn)

        angle_box = QWidget()
        ahl = QHBoxLayout(angle_box)
        ahl.setContentsMargins(0, 0, 0, 0); ahl.setSpacing(6)
        self._tr_fixed = QCheckBox("Fixed")
        self._tr_fixed.toggled.connect(self._on_tr_fixed)
        self._tr_fixed.toggled.connect(self._emit)
        ahl.addWidget(self._tr_fixed)
        self._tr_angle = QDoubleSpinBox()
        self._tr_angle.setRange(-360.0, 360.0); self._tr_angle.setDecimals(1)
        self._tr_angle.setEnabled(False)
        self._tr_angle.valueChanged.connect(self._emit)
        ahl.addWidget(self._tr_angle)
        self._tr_sec.row("Angle °", angle_box)

        self._tr_add = QDoubleSpinBox()
        self._tr_add.setRange(-360.0, 360.0); self._tr_add.setDecimals(1)
        self._tr_add.valueChanged.connect(self._emit)
        self._tr_sec.row("Add to rotation °", self._tr_add)

        self._tr_tbl = _TableEditor("Input value", "Pixels")
        self._tr_tbl.changed.connect(self._emit)
        self._tr_sec.row("Table", self._tr_tbl)

        self._vbox.addWidget(self._tr_sec)

    def _mk_animation(self):
        """Shared animation/scroll block — SpriteSheet and ScrollingTape."""
        self._anim_sec = _Section("Animation")
        self._anim_sec.setVisible(False)

        self._anim_dr = QLineEdit(); self._anim_dr.editingFinished.connect(self._emit)
        self._anim_sec.row("Dataref", self._dr_field(self._anim_dr))

        self._anim_fn = _NoScrollComboBox(); self._anim_fn.addItems(_VALUE_FUNCS)
        self._anim_fn.currentTextChanged.connect(self._emit)
        self._anim_sec.row("Convert fn", self._anim_fn)

        self._anim_tbl = _TableEditor("Input value", "Output")
        self._anim_tbl.changed.connect(self._emit)
        self._anim_sec.row("Table", self._anim_tbl)

        self._vbox.addWidget(self._anim_sec)

    def _mk_viewport(self):
        self._vp_sec = _Section("Viewport clip", optional=True)
        self._vp_sec.toggled.connect(self._emit)

        self._vp_x = _sb(0, 4096); self._vp_y = _sb(0, 4096)
        for w in (self._vp_x, self._vp_y):
            w.valueChanged.connect(self._emit)
        y_label = "X  /  Y top" if is_y_down() else "X  /  Y bottom"
        self._vp_sec.row_pair(y_label, self._vp_x, self._vp_y)

        self._vp_w = _sb(0, 4096); self._vp_h = _sb(0, 4096)
        for w in (self._vp_w, self._vp_h):
            w.valueChanged.connect(self._emit)
        self._vp_sec.row_pair("W  /  H", self._vp_w, self._vp_h)

        self._vbox.addWidget(self._vp_sec)

    def _mk_visibility(self):
        self._vis_sec = _Section("Visibility", optional=True)
        self._vis_sec.toggled.connect(self._emit)

        self._vis_dr = QLineEdit(); self._vis_dr.editingFinished.connect(self._emit)
        self._vis_sec.row("Dataref", self._dr_field(self._vis_dr))

        self._vis_pred = _NoScrollComboBox(); self._vis_pred.addItems(_PREDICATES)
        self._vis_pred.currentTextChanged.connect(self._emit)
        self._vis_sec.row("Predicate", self._vis_pred)

        self._vbox.addWidget(self._vis_sec)

    # ── Public API ────────────────────────────────────────────────────────

    def load(self, comp: dict):
        self._loading = True
        known = {
            "name", "type", "position",
            # ImagePanel
            "texture", "cliprect", "origin",
            "resize_to_container", "maintain_proportions",
            "rotation", "translation",
            # SpriteSheet
            "columns", "rows", "frame_width", "frame_height",
            "stride_x", "stride_y", "smooth", "animation",
            # ScrollingTape
            "scroll_axis", "scroll",
            # Line
            "start", "end",
            # Arc
            "center", "radius", "start_angle", "end_angle",
            "tilt_angle", "num_segments",
            # FilledRect
            "size",
            # Polygon
            "points", "filled",
            # shared across vector types
            "color", "width",
            "outline_color", "outline_width",
            # VectorTape (bands are stored in _extra; ticks + labels handled by form)
            "pixels_per_unit", "tick_side", "tick_color", "ticks", "labels",
            # shared across all
            "viewport", "visibility",
        }
        self._extra = {k: v for k, v in comp.items() if k not in known}

        self._name.setText(str(comp.get("name", "")))
        ct = str(comp.get("type", "ImagePanel"))
        idx = self._type.findText(ct)
        self._type.setCurrentIndex(max(idx, 0))
        self._on_type_changed(ct)  # explicit: index may not have changed

        pos = comp.get("position", [0, 0])
        self._px.setValue(int(pos[0]))
        self._py.setValue(flip_y(int(pos[1]), self._ref_height))

        # Texture file (all image-based types)
        self._tex.setText(str(comp.get("texture", "")))

        # ImagePanel atlas detail
        cr = comp.get("cliprect", [0, 0])
        self._clip_w.setValue(int(cr[0])); self._clip_h.setValue(int(cr[1]))
        orig = comp.get("origin", [0, 0])
        self._orig_x.setValue(int(orig[0])); self._orig_y.setValue(int(orig[1]))
        resize = bool(comp.get("resize_to_container", False))
        self._resize_chk.blockSignals(True)
        self._resize_chk.setChecked(resize)
        self._resize_chk.blockSignals(False)
        self._prop_chk.setEnabled(resize)
        self._prop_chk.setChecked(bool(comp.get("maintain_proportions", True)))

        # SpriteSheet grid params
        self._ss_cols.setValue(int(comp.get("columns", 1)))
        self._ss_rows_sb.setValue(int(comp.get("rows", 1)))
        self._ss_fw.setValue(max(1, int(comp.get("frame_width", 1))))
        self._ss_fh.setValue(max(1, int(comp.get("frame_height", 1))))
        self._ss_sx.setValue(int(comp.get("stride_x", 0)))
        self._ss_sy.setValue(int(comp.get("stride_y", 0)))
        self._ss_smooth.setChecked(bool(comp.get("smooth", True)))

        # ScrollingTape axis
        axis = str(comp.get("scroll_axis", "y"))
        self._st_axis.setCurrentIndex(0 if axis == "y" else 1)

        # Line
        start = comp.get("start", [0, 0])
        self._line_x1.setValue(int(start[0]))
        self._line_y1.setValue(flip_y(int(start[1]), self._ref_height))
        end = comp.get("end", [0, 0])
        self._line_x2.setValue(int(end[0]))
        self._line_y2.setValue(flip_y(int(end[1]), self._ref_height))
        self._line_color.set_rgba(comp.get("color"))
        self._line_width.setValue(float(comp.get("width", 1.0)))

        # Arc
        ctr = comp.get("center", [0, 0])
        self._arc_cx.setValue(int(ctr[0]))
        self._arc_cy.setValue(flip_y(int(ctr[1]), self._ref_height))
        self._arc_radius.setValue(float(comp.get("radius", 50.0)))
        self._arc_start.setValue(float(comp.get("start_angle", 0.0)))
        self._arc_end.setValue(float(comp.get("end_angle", 360.0)))
        self._arc_color.set_rgba(comp.get("color"))
        self._arc_width.setValue(float(comp.get("width", 1.0)))
        self._arc_tilt.setValue(float(comp.get("tilt_angle", 0.0)))
        self._arc_segs.setValue(int(comp.get("num_segments", 64)))

        # FilledRect
        sz = comp.get("size", [100, 100])
        self._frt_w.setValue(int(sz[0])); self._frt_h.setValue(int(sz[1]))
        self._frt_color.set_rgba(comp.get("color"))
        frt_oc = comp.get("outline_color")
        self._frt_outline_chk.blockSignals(True)
        self._frt_outline_chk.setChecked(frt_oc is not None)
        self._frt_outline_chk.blockSignals(False)
        self._frt_outline_color.setEnabled(frt_oc is not None)
        self._frt_outline_color.set_rgba(frt_oc if frt_oc is not None else (255, 255, 255, 255))
        self._frt_outline_width.setEnabled(frt_oc is not None)
        self._frt_outline_width.setValue(float(comp.get("outline_width", 1.0)))

        # Polygon
        pts = comp.get("points", [])
        self._poly_pts.load([[p[0], p[1]] for p in pts])
        self._poly_color.set_rgba(comp.get("color"))
        filled = bool(comp.get("filled", True))
        self._poly_filled.blockSignals(True)
        self._poly_filled.setChecked(filled)
        self._poly_filled.blockSignals(False)
        self._poly_width.setEnabled(not filled)
        self._poly_width.setValue(float(comp.get("width", 1.0)))
        poly_oc = comp.get("outline_color")
        has_poly_outline = poly_oc is not None and filled
        self._poly_outline_chk.blockSignals(True)
        self._poly_outline_chk.setChecked(has_poly_outline)
        self._poly_outline_chk.blockSignals(False)
        self._poly_outline_chk.setVisible(filled)
        self._poly_outline_color.setEnabled(has_poly_outline)
        self._poly_outline_color.setVisible(filled)
        self._poly_outline_color.set_rgba(poly_oc if poly_oc is not None else (255, 255, 255, 255))
        self._poly_outline_width.setEnabled(has_poly_outline)
        self._poly_outline_width.setVisible(filled)
        self._poly_outline_width.setValue(float(comp.get("outline_width", 1.0)))

        # VectorTape
        self._vt_axis.setCurrentIndex(0 if str(comp.get("scroll_axis", "y")) == "y" else 1)
        self._vt_ppu.setValue(float(comp.get("pixels_per_unit", 5.0)))
        ts = str(comp.get("tick_side", "left"))
        self._vt_tick_side.setCurrentIndex(max(self._vt_tick_side.findText(ts), 0))
        self._vt_tick_color.set_rgba(comp.get("tick_color"))
        ticks = comp.get("ticks") or []
        self._vt_ticks.load(
            [[td["interval"], td.get("length", 15), td.get("width", 2)] for td in ticks]
        )
        lbl = comp.get("labels") or {}
        self._vt_labels_cache = {k: v for k, v in lbl.items()
                                 if k not in ("interval", "font_size", "font", "side", "offset")}
        self._vt_label_interval.setValue(float(lbl.get("interval", 0.0)))
        self._vt_label_offset.setValue(float(lbl.get("offset", 8.0)))
        ls = str(lbl.get("side", "")) if lbl.get("side") else ""
        self._vt_label_side.setCurrentIndex(
            max(self._vt_label_side.findText(ls), 0) if ls else 0
        )
        self._vt_label_font_size.setValue(float(lbl.get("font_size", 18.0)))
        self._vt_label_font.setText(str(lbl.get("font", "")))

        # ImagePanel rotation
        rot = comp.get("rotation")
        self._rot_sec.set_active(rot is not None)
        if rot:
            self._rot_dr.setText(str(rot.get("dataref", "")))
            self._rot_fn.setCurrentIndex(
                max(self._rot_fn.findText(rot.get("convert_function") or _NONE), 0))
            rc = rot.get("rotation_center", [0, 0])
            self._rot_cx.setValue(int(rc[0])); self._rot_cy.setValue(int(rc[1]))
            self._rot_tbl.load(rot.get("table", []))
        else:
            self._rot_dr.clear(); self._rot_fn.setCurrentIndex(0)
            self._rot_cx.setValue(0); self._rot_cy.setValue(0)
            self._rot_tbl.load([])

        # ImagePanel translation
        tr = comp.get("translation")
        self._tr_sec.set_active(tr is not None)
        if tr:
            self._tr_dr.setText(str(tr.get("dataref", "")))
            self._tr_fn.setCurrentIndex(
                max(self._tr_fn.findText(tr.get("convert_function") or _NONE), 0))
            fa = tr.get("translation_angle")
            self._tr_fixed.setChecked(fa is not None)
            self._tr_angle.setValue(float(fa) if fa is not None else 0.0)
            self._tr_angle.setEnabled(fa is not None)
            self._tr_add.setValue(float(tr.get("add_angle_to_rotation", 0.0)))
            self._tr_tbl.load(tr.get("table", []))
        else:
            self._tr_dr.clear(); self._tr_fn.setCurrentIndex(0)
            self._tr_fixed.setChecked(False)
            self._tr_angle.setValue(0.0); self._tr_angle.setEnabled(False)
            self._tr_add.setValue(0.0); self._tr_tbl.load([])

        # SpriteSheet animation / ScrollingTape scroll — same widget, different YAML key
        anim = comp.get("animation") or comp.get("scroll")
        if anim:
            self._anim_dr.setText(str(anim.get("dataref", "")))
            self._anim_fn.setCurrentIndex(
                max(self._anim_fn.findText(anim.get("convert_function") or _NONE), 0))
            self._anim_tbl.load(anim.get("table", []))
        else:
            self._anim_dr.clear()
            self._anim_fn.setCurrentIndex(0)
            self._anim_tbl.load([])

        # Viewport (shared)
        vp = comp.get("viewport")
        self._vp_sec.set_active(vp is not None)
        if vp:
            self._vp_x.setValue(int(vp[0]))
            self._vp_w.setValue(int(vp[2]))
            self._vp_h.setValue(int(vp[3]))
            # vp[1] is the bottom edge (y-up YAML).  In y-down mode display the top edge.
            vy_display = (self._ref_height - int(vp[1]) - int(vp[3])) if is_y_down() else int(vp[1])
            self._vp_y.setValue(vy_display)
        else:
            self._vp_x.setValue(0); self._vp_y.setValue(0)
            self._vp_w.setValue(0); self._vp_h.setValue(0)

        # Visibility (shared)
        vis = comp.get("visibility")
        self._vis_sec.set_active(vis is not None)
        if vis:
            self._vis_dr.setText(str(vis.get("dataref", "")))
            self._vis_pred.setCurrentIndex(
                max(self._vis_pred.findText(str(vis.get("predicate", ""))), 0))
        else:
            self._vis_dr.clear()
            if self._vis_pred.count():
                self._vis_pred.setCurrentIndex(0)

        self._loading = False

    def get_data(self) -> dict:
        data: dict = {}
        data["name"] = self._name.text().strip()
        ct = self._type.currentText()
        data["type"] = ct

        # Position only for types that use a single centre point
        if ct not in ("Line", "Arc", "Polygon"):
            data["position"] = [self._px.value(), flip_y(self._py.value(), self._ref_height)]

        if ct == "Line":
            data["start"] = [self._line_x1.value(), flip_y(self._line_y1.value(), self._ref_height)]
            data["end"]   = [self._line_x2.value(), flip_y(self._line_y2.value(), self._ref_height)]
            data["color"] = list(self._line_color.get_rgba())
            w = self._line_width.value()
            if w != 1.0:
                data["width"] = w

        elif ct == "Arc":
            data["center"]      = [self._arc_cx.value(), flip_y(self._arc_cy.value(), self._ref_height)]
            data["radius"]      = self._arc_radius.value()
            data["start_angle"] = self._arc_start.value()
            data["end_angle"]   = self._arc_end.value()
            data["color"]       = list(self._arc_color.get_rgba())
            w = self._arc_width.value()
            if w != 1.0:
                data["width"] = w
            t = self._arc_tilt.value()
            if t != 0.0:
                data["tilt_angle"] = t
            s = self._arc_segs.value()
            if s != 64:
                data["num_segments"] = s

        elif ct == "FilledRect":
            data["size"]  = [self._frt_w.value(), self._frt_h.value()]
            data["color"] = list(self._frt_color.get_rgba())
            if self._frt_outline_chk.isChecked():
                data["outline_color"] = list(self._frt_outline_color.get_rgba())
                data["outline_width"] = self._frt_outline_width.value()

        elif ct == "Polygon":
            data["points"] = [[row[0], row[1]] for row in self._poly_pts.get_data()]
            data["color"]  = list(self._poly_color.get_rgba())
            if not self._poly_filled.isChecked():
                data["filled"] = False
                data["width"]  = self._poly_width.value()
            elif self._poly_outline_chk.isChecked():
                data["outline_color"] = list(self._poly_outline_color.get_rgba())
                data["outline_width"] = self._poly_outline_width.value()

        elif ct == "ImagePanel":
            data["texture"] = self._tex.text().strip()
            data["origin"]  = [self._orig_x.value(), self._orig_y.value()]
            data["cliprect"] = [self._clip_w.value(), self._clip_h.value()]
            if self._resize_chk.isChecked():
                data["resize_to_container"] = True
                if not self._prop_chk.isChecked():
                    data["maintain_proportions"] = False

            if self._rot_sec.active:
                rot: dict = {"dataref": self._rot_dr.text().strip()}
                cf = self._rot_fn.currentText()
                if cf != _NONE:
                    rot["convert_function"] = cf
                rc = [self._rot_cx.value(), self._rot_cy.value()]
                if rc != [0, 0]:
                    rot["rotation_center"] = rc
                rot["table"] = self._rot_tbl.get_data()
                data["rotation"] = rot

            if self._tr_sec.active:
                tr: dict = {"dataref": self._tr_dr.text().strip()}
                cf = self._tr_fn.currentText()
                if cf != _NONE:
                    tr["convert_function"] = cf
                if self._tr_fixed.isChecked():
                    tr["translation_angle"] = self._tr_angle.value()
                add = self._tr_add.value()
                if add != 0.0:
                    tr["add_angle_to_rotation"] = add
                tr["table"] = self._tr_tbl.get_data()
                data["translation"] = tr

        elif ct == "SpriteSheet":
            data["texture"] = self._tex.text().strip()
            data["columns"] = self._ss_cols.value()
            data["rows"] = self._ss_rows_sb.value()
            data["frame_width"] = self._ss_fw.value()
            data["frame_height"] = self._ss_fh.value()
            if self._ss_sx.value() > 0:
                data["stride_x"] = self._ss_sx.value()
            if self._ss_sy.value() > 0:
                data["stride_y"] = self._ss_sy.value()
            if not self._ss_smooth.isChecked():
                data["smooth"] = False
            anim_dr = self._anim_dr.text().strip()
            anim_tbl = self._anim_tbl.get_data()
            if anim_dr or anim_tbl:
                anim: dict = {"dataref": anim_dr, "table": anim_tbl}
                cf = self._anim_fn.currentText()
                if cf != _NONE:
                    anim["convert_function"] = cf
                data["animation"] = anim

        elif ct == "ScrollingTape":
            data["texture"] = self._tex.text().strip()
            data["scroll_axis"] = "y" if self._st_axis.currentIndex() == 0 else "x"
            anim_dr = self._anim_dr.text().strip()
            anim_tbl = self._anim_tbl.get_data()
            if anim_dr or anim_tbl:
                scroll: dict = {"dataref": anim_dr, "table": anim_tbl}
                cf = self._anim_fn.currentText()
                if cf != _NONE:
                    scroll["convert_function"] = cf
                data["scroll"] = scroll

        elif ct == "VectorTape":
            data["scroll_axis"] = "y" if self._vt_axis.currentIndex() == 0 else "x"
            data["pixels_per_unit"] = self._vt_ppu.value()
            data["tick_side"] = self._vt_tick_side.currentText()
            data["tick_color"] = list(self._vt_tick_color.get_rgba())
            anim_dr = self._anim_dr.text().strip()
            anim_tbl = self._anim_tbl.get_data()
            if anim_dr or anim_tbl:
                vt_scroll: dict = {"dataref": anim_dr, "table": anim_tbl}
                cf = self._anim_fn.currentText()
                if cf != _NONE:
                    vt_scroll["convert_function"] = cf
                data["scroll"] = vt_scroll
            # Ticks list
            ticks_raw = self._vt_ticks.get_data()
            if ticks_raw:
                data["ticks"] = [
                    {"interval": r[0], "length": r[1], "width": r[2]}
                    for r in ticks_raw
                ]
            # Labels dict: cache preserves color/format/offset;
            # form controls interval, font_size, font, and side.
            lbl_dict = dict(self._vt_labels_cache)
            lbl_interval = self._vt_label_interval.value()
            if lbl_interval > 0:
                lbl_dict["interval"] = lbl_interval
            else:
                lbl_dict.pop("interval", None)
            lbl_dict["font_size"] = self._vt_label_font_size.value()
            lbl_dict["offset"] = self._vt_label_offset.value()
            fn = self._vt_label_font.text().strip()
            if fn:
                lbl_dict["font"] = fn
            else:
                lbl_dict.pop("font", None)
            ls = self._vt_label_side.currentText()
            if ls != "(same as tick side)":
                lbl_dict["side"] = ls
            else:
                lbl_dict.pop("side", None)
            if lbl_dict:
                data["labels"] = lbl_dict

        if self._vp_sec.active:
            vh = self._vp_h.value()
            vy_display = self._vp_y.value()
            # Convert display Y back to y-up bottom edge for the YAML.
            vy_yaml = (self._ref_height - vy_display - vh) if is_y_down() else vy_display
            data["viewport"] = [self._vp_x.value(), vy_yaml, self._vp_w.value(), vh]

        if self._vis_sec.active:
            data["visibility"] = {
                "dataref":   self._vis_dr.text().strip(),
                "predicate": self._vis_pred.currentText(),
            }

        data.update(self._extra)
        return data

    def clear(self):
        self._loading = True
        self._name.clear()
        self._type.setCurrentIndex(0)
        self._on_type_changed("ImagePanel")  # explicit: index may not have changed
        self._px.setValue(0); self._py.setValue(0)
        self._tex.clear()
        self._clip_w.setValue(0); self._clip_h.setValue(0)
        self._orig_x.setValue(0); self._orig_y.setValue(0)
        self._resize_chk.setChecked(False)
        self._prop_chk.setChecked(True); self._prop_chk.setEnabled(False)
        self._ss_cols.setValue(1); self._ss_rows_sb.setValue(1)
        self._ss_fw.setValue(1); self._ss_fh.setValue(1)
        self._ss_sx.setValue(0); self._ss_sy.setValue(0)
        self._ss_smooth.setChecked(True)
        self._st_axis.setCurrentIndex(0)
        self._rot_sec.set_active(False)
        self._tr_sec.set_active(False)
        self._anim_dr.clear(); self._anim_fn.setCurrentIndex(0); self._anim_tbl.load([])
        self._vp_sec.set_active(False)
        self._vis_sec.set_active(False)
        # Vector primitives
        self._line_x1.setValue(0); self._line_y1.setValue(0)
        self._line_x2.setValue(0); self._line_y2.setValue(0)
        self._line_color.set_rgba(None); self._line_width.setValue(1.0)
        self._arc_cx.setValue(0); self._arc_cy.setValue(0)
        self._arc_radius.setValue(50.0)
        self._arc_start.setValue(0.0); self._arc_end.setValue(360.0)
        self._arc_color.set_rgba(None); self._arc_width.setValue(1.0)
        self._arc_tilt.setValue(0.0); self._arc_segs.setValue(64)
        self._frt_w.setValue(100); self._frt_h.setValue(100)
        self._frt_color.set_rgba(None)
        self._frt_outline_chk.setChecked(False)
        self._frt_outline_color.set_rgba(None); self._frt_outline_width.setValue(1.0)
        self._poly_pts.load([])
        self._poly_color.set_rgba(None)
        self._poly_filled.setChecked(True); self._poly_width.setValue(1.0)
        self._poly_outline_chk.setChecked(False)
        self._poly_outline_color.set_rgba(None); self._poly_outline_width.setValue(1.0)
        self._vt_axis.setCurrentIndex(0)
        self._vt_ppu.setValue(5.0)
        self._vt_tick_side.setCurrentIndex(0)
        self._vt_tick_color.set_rgba(None)
        self._vt_ticks.load([])
        self._vt_labels_cache = {}
        self._vt_label_interval.setValue(0.0)
        self._vt_label_offset.setValue(8.0)
        self._vt_label_side.setCurrentIndex(0)
        self._vt_label_font_size.setValue(18.0)
        self._vt_label_font.clear()
        self._extra = {}
        self._loading = False

    # ── Internal ──────────────────────────────────────────────────────────

    def _emit(self):
        if not self._loading:
            self.changed.emit()

    def _on_type_changed(self, ct: str):
        is_ip  = ct == "ImagePanel"
        is_ss  = ct == "SpriteSheet"
        is_st  = ct == "ScrollingTape"
        is_img = is_ip or is_ss or is_st
        is_line = ct == "Line"
        is_arc  = ct == "Arc"
        is_frt  = ct == "FilledRect"
        is_poly = ct == "Polygon"
        is_vt   = ct == "VectorTape"

        # Position: hide for types that define geometry without a single centre point
        self._pos_sec.setVisible(not is_line and not is_arc and not is_poly)

        # Texture section visible for image types; atlas detail only for ImagePanel
        self._tex_sec.setVisible(is_img)
        self._atlas_detail.setVisible(is_ip)
        self._tex_edit_btn.setVisible(is_ip)

        # Type-specific sections
        self._ss_sec.setVisible(is_ss)
        self._st_sec.setVisible(is_st)
        self._line_sec.setVisible(is_line)
        self._arc_sec.setVisible(is_arc)
        self._frt_sec.setVisible(is_frt)
        self._poly_sec.setVisible(is_poly)
        self._vt_sec.setVisible(is_vt)

        # Rotation and Translation: ImagePanel only
        self._rot_sec.setVisible(is_ip)
        self._tr_sec.setVisible(is_ip)

        # Animation: SpriteSheet, ScrollingTape, and VectorTape (scroll dataref)
        self._anim_sec.setVisible(is_ss or is_st or is_vt)

        # Viewport clip: image types and VectorTape (always required for tape)
        self._vp_sec.setVisible(is_img or is_vt)
        if is_vt:
            self._vp_sec.set_active(True)

    def _on_frt_outline_toggled(self, on: bool):
        self._frt_outline_color.setEnabled(on)
        self._frt_outline_width.setEnabled(on)

    def _on_poly_filled_toggled(self, filled: bool):
        self._poly_width.setEnabled(not filled)
        # Outline overlay only makes sense when filled; unfilled IS an outline
        self._poly_outline_chk.setVisible(filled)
        self._poly_outline_color.setVisible(filled)
        self._poly_outline_width.setVisible(filled)
        if not filled:
            self._poly_outline_chk.blockSignals(True)
            self._poly_outline_chk.setChecked(False)
            self._poly_outline_chk.blockSignals(False)

    def _on_poly_outline_toggled(self, on: bool):
        self._poly_outline_color.setEnabled(on)
        self._poly_outline_width.setEnabled(on)

    def _on_resize_toggled(self, on: bool):
        self._prop_chk.setEnabled(on)
        if not on:
            self._prop_chk.setChecked(True)

    def _on_tr_fixed(self, on: bool):
        self._tr_angle.setEnabled(on)

    def _dr_field(self, lineedit: QLineEdit) -> QWidget:
        box = QWidget()
        hl = QHBoxLayout(box)
        hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(2)
        hl.addWidget(lineedit)
        btn = QPushButton("…"); btn.setFixedWidth(26)
        btn.setToolTip("Browse X-Plane datarefs")
        btn.clicked.connect(lambda: self._pick_dataref(lineedit))
        hl.addWidget(btn)
        return box

    def _pick_dataref(self, lineedit: QLineEdit) -> None:
        from gauge_designer.dataref_picker import DatarefPickerDialog
        dlg = DatarefPickerDialog(current=lineedit.text().strip(), parent=self)
        if dlg.exec() == QDialog.Accepted:
            dr = dlg.selected_dataref()
            if dr:
                lineedit.setText(dr)
                self._emit()

    def _open_texture_editor(self):
        tex_rel = self._tex.text().strip()
        if not tex_rel:
            return
        tex_abs = str((Path(self._yaml_dir) / tex_rel).resolve()) if self._yaml_dir else tex_rel
        from gauge_designer.texture_editor import TextureEditorDialog
        dlg = TextureEditorDialog(
            texture_path=tex_abs,
            clip_w=self._clip_w.value(),
            clip_h=self._clip_h.value(),
            origin_x=self._orig_x.value(),
            origin_y=self._orig_y.value(),
            parent=self,
        )
        if dlg.exec() == QDialog.Accepted:
            cw, ch, ox, oy = dlg.get_values()
            self._loading = True
            self._clip_w.setValue(cw); self._clip_h.setValue(ch)
            self._orig_x.setValue(ox); self._orig_y.setValue(oy)
            self._loading = False
            self._emit()

    def _browse_tex(self):
        start = self._yaml_dir
        if self._tex.text() and self._yaml_dir:
            try:
                start = str((Path(self._yaml_dir) / self._tex.text()).resolve())
            except Exception:
                pass
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Texture", start, "Images (*.png *.jpg *.bmp)"
        )
        if not path:
            return
        if self._yaml_dir:
            rel = os.path.relpath(path, self._yaml_dir).replace("\\", "/")
            self._tex.setText(rel)
        else:
            self._tex.setText(path)
        self._emit()
