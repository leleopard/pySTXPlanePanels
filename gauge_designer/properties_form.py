"""Structured form for editing an ImagePanel component."""

import os
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
    QPushButton, QCheckBox, QDialog,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView,
    QFileDialog,
)
from PySide6.QtCore import Qt, Signal


class _NoScrollComboBox(QComboBox):
    """QComboBox that ignores mouse-wheel events to prevent accidental changes."""

    def wheelEvent(self, event):
        event.ignore()

# ── Registry data ─────────────────────────────────────────────────────────────

_NONE = "(none)"

_VALUE_FUNCS = [
    _NONE,
    "identity",
    "return100s", "return1000s", "return10000s",
    "convert_in_to_mb",
    "divideby100",
    "add_compass_heading_to_value",
    "calculate_turn_rate",
    "return_alt_hundreds",
    "convert_lbs_to_gallons",
    "convert_suction",
]

_PREDICATES = [
    "true_if_zero",
    "true_if_over_zero",
    "true_if_equals_1", "true_if_equals_2", "true_if_equals_3",
    "true_if_equals_4", "true_if_equals_5",
    "true_if_over_1", "true_if_over_2",
    "nav_gsflg_visible",
]

_COMP_TYPES = ["ImagePanel", "Text"]


def _coerce_num(text: str):
    t = text.strip()
    try:
        return int(t) if ("." not in t and "e" not in t.lower()) else float(t)
    except ValueError:
        return 0


# ── Table editor ─────────────────────────────────────────────────────────────

class _TableEditor(QWidget):
    changed = Signal()

    def __init__(self, col0="Input value", col1="Output", parent=None):
        super().__init__(parent)
        self._tbl = QTableWidget(0, 2)
        self._tbl.setHorizontalHeaderLabels([col0, col1])
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
        for row in data:
            if isinstance(row, (list, tuple)) and len(row) >= 2:
                r = self._tbl.rowCount()
                self._tbl.insertRow(r)
                self._tbl.setItem(r, 0, QTableWidgetItem(str(row[0])))
                self._tbl.setItem(r, 1, QTableWidgetItem(str(row[1])))
        self._tbl.blockSignals(False)

    def get_data(self) -> list:
        out = []
        for r in range(self._tbl.rowCount()):
            i0, i1 = self._tbl.item(r, 0), self._tbl.item(r, 1)
            if i0 and i1:
                out.append([_coerce_num(i0.text()), _coerce_num(i1.text())])
        return out

    def _add(self):
        self._tbl.blockSignals(True)
        r = self._tbl.rowCount(); self._tbl.insertRow(r)
        self._tbl.setItem(r, 0, QTableWidgetItem("0"))
        self._tbl.setItem(r, 1, QTableWidgetItem("0"))
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
        """Full-width row spanning both label and field columns."""
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


def _sb(lo=-4096, hi=4096) -> QSpinBox:
    s = QSpinBox(); s.setRange(lo, hi); s.setMinimumWidth(64); return s


# ── Main form ─────────────────────────────────────────────────────────────────

class PropertiesForm(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._yaml_dir: str = ""
        self._extra: dict = {}
        self._loading = False

        body = QWidget()
        self._vbox = QVBoxLayout(body)
        self._vbox.setContentsMargins(6, 4, 6, 4)
        self._vbox.setSpacing(0)

        self._mk_component()
        self._mk_position()
        self._mk_texture()
        self._mk_rotation()
        self._mk_translation()
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
        s = _Section("Position")
        self._px = _sb(); self._py = _sb()
        for w in (self._px, self._py):
            w.valueChanged.connect(self._emit)
        s.row_pair("X  /  Y", self._px, self._py)
        self._vbox.addWidget(s)

    def _mk_texture(self):
        self._tex_sec = _Section("Texture")

        tex_row = QWidget()
        hl = QHBoxLayout(tex_row)
        hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(4)
        self._tex_edit_btn = QPushButton("Edit"); self._tex_edit_btn.setFixedWidth(38)
        self._tex_edit_btn.setToolTip("Open texture editor")
        self._tex_edit_btn.setEnabled(False)
        self._tex_edit_btn.clicked.connect(self._open_texture_editor)
        hl.addWidget(self._tex_edit_btn)
        self._tex = QLineEdit()
        self._tex.editingFinished.connect(self._emit)
        self._tex.textChanged.connect(
            lambda t: self._tex_edit_btn.setEnabled(bool(t.strip()))
        )
        hl.addWidget(self._tex)
        btn = QPushButton("…"); btn.setFixedWidth(26)
        btn.clicked.connect(self._browse_tex)
        hl.addWidget(btn)
        self._tex_sec.row("File", tex_row)

        self._clip_w = _sb(0, 4096); self._clip_h = _sb(0, 4096)
        for w in (self._clip_w, self._clip_h):
            w.valueChanged.connect(self._emit)
        self._tex_sec.row_pair("Clip W  /  H", self._clip_w, self._clip_h)

        self._orig_x = _sb(0, 4096); self._orig_y = _sb(0, 4096)
        for w in (self._orig_x, self._orig_y):
            w.valueChanged.connect(self._emit)
        self._tex_sec.row_pair("Origin X  /  Y", self._orig_x, self._orig_y)

        self._resize_chk = QCheckBox("Fit to gauge size")
        self._resize_chk.toggled.connect(self._on_resize_toggled)
        self._resize_chk.toggled.connect(self._emit)
        self._tex_sec.row_widget(self._resize_chk)

        self._prop_chk = QCheckBox("Maintain proportions")
        self._prop_chk.setChecked(True)
        self._prop_chk.setEnabled(False)
        self._prop_chk.toggled.connect(self._emit)
        self._tex_sec.row_widget(self._prop_chk)

        self._vbox.addWidget(self._tex_sec)

    def _mk_rotation(self):
        self._rot_sec = _Section("Rotation", optional=True)
        self._rot_sec.toggled.connect(self._emit)

        self._rot_dr = QLineEdit(); self._rot_dr.editingFinished.connect(self._emit)
        self._rot_sec.row("Dataref", self._rot_dr)

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
        self._tr_sec.row("Dataref", self._tr_dr)

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

    def _mk_visibility(self):
        self._vis_sec = _Section("Visibility", optional=True)
        self._vis_sec.toggled.connect(self._emit)

        self._vis_dr = QLineEdit(); self._vis_dr.editingFinished.connect(self._emit)
        self._vis_sec.row("Dataref", self._vis_dr)

        self._vis_pred = _NoScrollComboBox(); self._vis_pred.addItems(_PREDICATES)
        self._vis_pred.currentTextChanged.connect(self._emit)
        self._vis_sec.row("Predicate", self._vis_pred)

        self._vbox.addWidget(self._vis_sec)

    # ── Public API ────────────────────────────────────────────────────────

    def load(self, comp: dict):
        self._loading = True
        known = {"name", "type", "position", "texture", "cliprect", "origin",
                 "rotation", "translation", "visibility",
                 "resize_to_container", "maintain_proportions"}
        self._extra = {k: v for k, v in comp.items() if k not in known}

        self._name.setText(str(comp.get("name", "")))
        ct = str(comp.get("type", "ImagePanel"))
        self._type.setCurrentIndex(max(self._type.findText(ct), 0))
        self._tex_sec.show_body(ct == "ImagePanel")

        pos = comp.get("position", [0, 0])
        self._px.setValue(int(pos[0])); self._py.setValue(int(pos[1]))

        self._tex.setText(str(comp.get("texture", "")))
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
        data["type"] = self._type.currentText()
        data["position"] = [self._px.value(), self._py.value()]

        if data["type"] == "ImagePanel":
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

        if self._vis_sec.active:
            data["visibility"] = {
                "dataref":   self._vis_dr.text().strip(),
                "predicate": self._vis_pred.currentText(),
            }

        data.update(self._extra)
        return data

    def clear(self):
        self._loading = True
        self._name.clear(); self._type.setCurrentIndex(0)
        self._px.setValue(0); self._py.setValue(0)
        self._tex.clear()
        self._clip_w.setValue(0); self._clip_h.setValue(0)
        self._orig_x.setValue(0); self._orig_y.setValue(0)
        self._resize_chk.setChecked(False)
        self._prop_chk.setChecked(True)
        self._prop_chk.setEnabled(False)
        self._rot_sec.set_active(False)
        self._tr_sec.set_active(False)
        self._vis_sec.set_active(False)
        self._extra = {}
        self._loading = False

    # ── Internal ──────────────────────────────────────────────────────────

    def _emit(self):
        if not self._loading:
            self.changed.emit()

    def _on_type_changed(self, ct: str):
        self._tex_sec.show_body(ct == "ImagePanel")

    def _on_resize_toggled(self, on: bool):
        self._prop_chk.setEnabled(on)
        if not on:
            self._prop_chk.setChecked(True)

    def _on_tr_fixed(self, on: bool):
        self._tr_angle.setEnabled(on)

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
