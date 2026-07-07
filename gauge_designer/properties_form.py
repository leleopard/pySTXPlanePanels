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
from gauge_designer.ui_utils import flip_y, is_y_down, QSpinBox, QDoubleSpinBox
from PySide6.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QComboBox,
    QPushButton, QCheckBox, QDialog, QColorDialog, QFontDialog,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView,
    QFileDialog, QListWidget, QListWidgetItem, QStackedWidget, QFrame,
    QGroupBox, QDialogButtonBox,
)
from PySide6.QtCore import Qt, Signal, QSize, QSettings
from PySide6.QtGui import QColor, QIcon, QPixmap


class _NoScrollComboBox(QComboBox):
    """QComboBox that ignores mouse-wheel events to prevent accidental changes."""
    def wheelEvent(self, event):
        event.ignore()


_CUSTOM_COLOR_SLOTS = 16  # QColorDialog's fixed custom-color palette size


class _ColorButton(QPushButton):
    """Button showing the current RGBA color as a small swatch icon (not as
    the button's own background — that fights the OS theme and makes the
    hex/alpha text hard to read against light or saturated colors); opens
    QColorDialog on click.

    QColorDialog's "custom colors" row is a static, in-memory, per-process
    palette — Qt doesn't persist it across app restarts on its own. This
    class loads it from QSettings the first time any color button is used,
    and saves it back after every pick so custom swatches survive a restart.

    The dialog's own "Add to Custom Colors" button always targets slot 0
    (it's a fresh dialog instance on every pick, so whatever internal
    next-slot pointer Qt/the OS keeps resets each time) — clicking it
    repeatedly just clobbers slot 0 instead of filling the palette left to
    right. `_reslot_custom_colors()` detects that overwrite after the
    dialog closes, restores the clobbered slot, and re-homes the new color
    into our own tracked next-empty slot instead.
    """
    color_changed = Signal()
    _custom_colors_loaded = False
    _next_custom_slot = 0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rgba = (255, 255, 255, 255)
        self.setFixedHeight(24)
        self.setIconSize(QSize(16, 16))
        self.clicked.connect(self._pick)
        _ColorButton._load_custom_colors()
        self._refresh()

    @classmethod
    def _load_custom_colors(cls) -> None:
        if cls._custom_colors_loaded:
            return
        cls._custom_colors_loaded = True
        settings = QSettings()
        for i in range(_CUSTOM_COLOR_SLOTS):
            raw = settings.value(f"colorPicker/customColor{i}", "")
            if raw:
                color = QColor(raw)
                if color.isValid():
                    QColorDialog.setCustomColor(i, color)
        cls._next_custom_slot = int(settings.value("colorPicker/nextCustomSlot", 0))

    @classmethod
    def _save_custom_colors(cls) -> None:
        settings = QSettings()
        for i in range(_CUSTOM_COLOR_SLOTS):
            settings.setValue(f"colorPicker/customColor{i}",
                              QColorDialog.customColor(i).name(QColor.HexArgb))
        settings.setValue("colorPicker/nextCustomSlot", cls._next_custom_slot)

    @classmethod
    def _reslot_custom_colors(cls, before: list) -> None:
        # Two passes so restoring a clobbered slot can never be mistaken,
        # on a later loop step, for a second native-dialog change (a write
        # into next_custom_slot would otherwise get re-read as "changed"
        # if the loop reaches that slot before this call returns).
        after = [QColorDialog.customColor(i) for i in range(len(before))]
        added = [after[i] for i in range(len(before)) if after[i] != before[i]]
        for i, prev in enumerate(before):
            if after[i] != prev:
                QColorDialog.setCustomColor(i, prev)
        for new_color in added:
            QColorDialog.setCustomColor(cls._next_custom_slot, new_color)
            cls._next_custom_slot = (cls._next_custom_slot + 1) % _CUSTOM_COLOR_SLOTS

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
        pixmap = QPixmap(16, 16)
        pixmap.fill(QColor(r, g, b, a))
        self.setIcon(QIcon(pixmap))
        self.setText(f"  #{r:02X}{g:02X}{b:02X}   α {a}")
        self.setStyleSheet("text-align: left; padding: 2px;")

    def _pick(self) -> None:
        r, g, b, a = self._rgba
        before = [QColorDialog.customColor(i) for i in range(_CUSTOM_COLOR_SLOTS)]
        c = QColorDialog.getColor(
            QColor(r, g, b, a), self, "Pick Color",
            QColorDialog.ShowAlphaChannel,
        )
        self._reslot_custom_colors(before)
        self._save_custom_colors()
        if c.isValid():
            self._rgba = (c.red(), c.green(), c.blue(), c.alpha())
            self._refresh()
            self.color_changed.emit()


# ── Registry data ─────────────────────────────────────────────────────────────

_NONE = "(none)"

# Shared tooltip for any field accepting a Python str.format() mini-language
# spec, e.g. VectorTape label format and Text's custom format override.
_FORMAT_SPEC_TOOLTIP = (
    "Python format-spec syntax: {:<width><.precision><type>}\n"
    "\n"
    "  {:.0f}    -> 123        (no decimals)\n"
    "  {:.1f}    -> 123.4      (1 decimal place)\n"
    "  {:02.0f}  -> 03         (zero-padded to 2 digits)\n"
    "  {:5.0f}   -> \"  123\"    (right-aligned, padded to width 5)\n"
    "  {:+.0f}   -> +123       (always show sign)\n"
    "\n"
    "Leave blank to use the default."
)

# Derived from the live registry — adding a function to convert.py is enough.
_PREDICATE_PREFIXES = ("true_if_", "nav_gsflg_")

def _build_func_lists() -> tuple[list[str], list[str]]:
    all_fns = known_converts()
    predicates = [n for n in all_fns if any(n.startswith(p) for p in _PREDICATE_PREFIXES)]
    values = [_NONE] + [n for n in all_fns if n not in predicates]
    return values, predicates

_VALUE_FUNCS, _PREDICATES = _build_func_lists()


def _pts_to_str(pts: list) -> str:
    """Convert [[x,y],...] list to 'x1,y1  x2,y2  ...' string for display."""
    if not pts:
        return ""
    return "  ".join(f"{p[0]},{p[1]}" for p in pts)


def _str_to_pts(s: str) -> list:
    """Parse 'x1,y1  x2,y2  ...' string back to [[x,y],...] list."""
    pts = []
    for tok in s.strip().split():
        parts = tok.split(",")
        if len(parts) == 2:
            try:
                pts.append([float(parts[0]), float(parts[1])])
            except ValueError:
                pass
    return pts


_COMP_TYPES = ["ImagePanel", "SpriteSheet", "ScrollingTape", "Text",
               "Line", "Arc", "FilledRect", "Polygon", "VectorTape", "Vector",
               "AttitudeIndicator", "NeedleGauge", "VectorCompassRose",
               "RotaryEncoder"]


def _coerce_num(text: str):
    t = text.strip()
    try:
        return int(t) if ("." not in t and "e" not in t.lower()) else float(t)
    except ValueError:
        return 0


# ── Table editor ─────────────────────────────────────────────────────────────

class _TableEditor(QWidget):
    """Generic N-column numeric table.

    By default cells are plain text (parsed via _coerce_num). Pass
    use_spinboxes=True for QDoubleSpinBox cells instead — safer numeric
    entry (no stray text, scroll/arrow increments), used where every column
    in the table is purely numeric (e.g. a value->pixel breakpoint table).
    """
    changed = Signal()

    def __init__(self, *headers, parent=None, use_spinboxes: bool = False,
                 decimals: int = 2, value_range: tuple = (-99999.0, 99999.0)):
        super().__init__(parent)
        self._use_spinboxes = use_spinboxes
        self._decimals = decimals
        self._value_range = value_range
        n = max(2, len(headers))
        self._tbl = QTableWidget(0, n)
        self._tbl.setHorizontalHeaderLabels(list(headers) if headers else ["Col 0", "Col 1"])
        self._tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl.setFixedHeight(110)
        if not use_spinboxes:
            self._tbl.itemChanged.connect(lambda: self.changed.emit())

        add = QPushButton("+");  add.setFixedWidth(26); add.clicked.connect(self._add)
        rm  = QPushButton("−");  rm.setFixedWidth(26);  rm.clicked.connect(self._rm)
        up  = QPushButton("↑");  up.setFixedWidth(26);  up.clicked.connect(self._move_up)
        dn  = QPushButton("↓");  dn.setFixedWidth(26);  dn.clicked.connect(self._move_dn)
        btns = QHBoxLayout()
        btns.setContentsMargins(0, 0, 0, 0); btns.setSpacing(2)
        btns.addWidget(add); btns.addWidget(rm); btns.addWidget(up); btns.addWidget(dn)
        btns.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(2)
        layout.addWidget(self._tbl); layout.addLayout(btns)

    def _make_spin(self, value=0.0) -> QDoubleSpinBox:
        sb = QDoubleSpinBox()
        sb.setRange(*self._value_range)
        sb.setDecimals(self._decimals)
        sb.setValue(float(value))          # set before connecting: no spurious emit
        sb.valueChanged.connect(lambda: self.changed.emit())
        return sb

    def load(self, data: list):
        self._tbl.blockSignals(True)
        self._tbl.setRowCount(0)
        n = self._tbl.columnCount()
        for row in data:
            if isinstance(row, (list, tuple)) and len(row) >= min(2, n):
                r = self._tbl.rowCount()
                self._tbl.insertRow(r)
                for c in range(min(n, len(row))):
                    if self._use_spinboxes:
                        self._tbl.setCellWidget(r, c, self._make_spin(row[c]))
                    else:
                        self._tbl.setItem(r, c, QTableWidgetItem(str(row[c])))
        self._tbl.blockSignals(False)

    def get_data(self) -> list:
        out = []
        n = self._tbl.columnCount()
        for r in range(self._tbl.rowCount()):
            if self._use_spinboxes:
                widgets = [self._tbl.cellWidget(r, c) for c in range(n)]
                if all(widgets):
                    out.append([w.value() for w in widgets])
            else:
                items = [self._tbl.item(r, c) for c in range(n)]
                if all(items):
                    out.append([_coerce_num(item.text()) for item in items])
        return out

    def _add(self):
        self._tbl.blockSignals(True)
        r = self._tbl.rowCount()
        self._tbl.insertRow(r)
        for c in range(self._tbl.columnCount()):
            if self._use_spinboxes:
                self._tbl.setCellWidget(r, c, self._make_spin(0.0))
            else:
                self._tbl.setItem(r, c, QTableWidgetItem("0"))
        self._tbl.blockSignals(False)
        self.changed.emit()

    def _rm(self):
        r = self._tbl.currentRow()
        if r >= 0:
            self._tbl.removeRow(r)
            self.changed.emit()

    def _swap_rows(self, r_a: int, r_b: int) -> None:
        n = self._tbl.columnCount()
        self._tbl.blockSignals(True)
        for c in range(n):
            if self._use_spinboxes:
                wa, wb = self._tbl.cellWidget(r_a, c), self._tbl.cellWidget(r_b, c)
                va = wa.value() if wa else 0.0
                vb = wb.value() if wb else 0.0
                self._tbl.setCellWidget(r_a, c, self._make_spin(vb))
                self._tbl.setCellWidget(r_b, c, self._make_spin(va))
            else:
                a = self._tbl.item(r_a, c)
                b = self._tbl.item(r_b, c)
                text_a = a.text() if a else ""
                text_b = b.text() if b else ""
                self._tbl.setItem(r_a, c, QTableWidgetItem(text_b))
                self._tbl.setItem(r_b, c, QTableWidgetItem(text_a))
        self._tbl.blockSignals(False)
        self.changed.emit()

    def _move_up(self):
        r = self._tbl.currentRow()
        if r > 0:
            self._swap_rows(r, r - 1)
            self._tbl.setCurrentCell(r - 1, self._tbl.currentColumn())

    def _move_dn(self):
        r = self._tbl.currentRow()
        if 0 <= r < self._tbl.rowCount() - 1:
            self._swap_rows(r, r + 1)
            self._tbl.setCurrentCell(r + 1, self._tbl.currentColumn())


# ── Polygon points table (spinbox cells) ─────────────────────────────────────

class _PointsTableEditor(QWidget):
    """X/Y points table whose cells are QSpinBox widgets (no accidental wheel edits,
    direct numeric input without needing to parse text)."""
    changed        = Signal()
    point_selected = Signal(int)   # row index of selected point, or -1

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tbl = QTableWidget(0, 2)
        self._tbl.setHorizontalHeaderLabels(["X", "Y"])
        self._tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl.setFixedHeight(130)
        self._tbl.itemSelectionChanged.connect(self._on_selection_changed)

        add = QPushButton("+"); add.setFixedWidth(26); add.clicked.connect(self._add)
        rm  = QPushButton("−"); rm.setFixedWidth(26);  rm.clicked.connect(self._rm)
        btns = QHBoxLayout()
        btns.setContentsMargins(0, 0, 0, 0); btns.setSpacing(2)
        btns.addWidget(add); btns.addWidget(rm); btns.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(2)
        layout.addWidget(self._tbl)
        layout.addLayout(btns)

    def _make_spin(self, value: int = 0) -> QSpinBox:
        sb = QSpinBox()
        sb.setRange(-9999, 9999)
        sb.setValue(int(round(value)))
        sb.valueChanged.connect(self.changed)
        return sb

    def load(self, data: list):
        self._tbl.setRowCount(0)
        for row in data:
            if isinstance(row, (list, tuple)) and len(row) >= 2:
                r = self._tbl.rowCount()
                self._tbl.insertRow(r)
                self._tbl.setCellWidget(r, 0, self._make_spin(row[0]))
                self._tbl.setCellWidget(r, 1, self._make_spin(row[1]))

    def get_data(self) -> list:
        out = []
        for r in range(self._tbl.rowCount()):
            sx = self._tbl.cellWidget(r, 0)
            sy = self._tbl.cellWidget(r, 1)
            if sx and sy:
                out.append([sx.value(), sy.value()])
        return out

    def _add(self):
        r = self._tbl.rowCount()
        self._tbl.insertRow(r)
        self._tbl.setCellWidget(r, 0, self._make_spin(0))
        self._tbl.setCellWidget(r, 1, self._make_spin(0))
        self.changed.emit()

    def _rm(self):
        r = self._tbl.currentRow()
        if r >= 0:
            self._tbl.removeRow(r)
            self.changed.emit()

    def _on_selection_changed(self):
        rows = self._tbl.selectedIndexes()
        self.point_selected.emit(rows[0].row() if rows else -1)


# ── Band endpoint editor ─────────────────────────────────────────────────────

class _BandEndpointWidget(QWidget):
    """Compact single-row endpoint editor: static spinbox or dataref + table dialog."""
    changed = Signal()

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._table_data: list = []   # kept in memory; edited via dialog

        self._mode = _NoScrollComboBox()
        self._mode.addItems(["Static", "Dataref"])
        self._mode.setFixedWidth(72)
        self._mode.currentIndexChanged.connect(self._on_mode_changed)

        # Static controls
        self._static_spin = QDoubleSpinBox()
        self._static_spin.setRange(-99999.0, 99999.0)
        self._static_spin.setDecimals(2)
        self._static_spin.valueChanged.connect(self.changed)

        static_w = QWidget()
        sl = QHBoxLayout(static_w)
        sl.setContentsMargins(0, 0, 0, 0); sl.setSpacing(2)
        sl.addWidget(self._static_spin)

        # Dataref controls (all on one line)
        self._dr_edit = QLineEdit()
        self._dr_edit.setPlaceholderText("dataref path")
        self._dr_edit.editingFinished.connect(self.changed)
        self._dr_btn = QPushButton("…")
        self._dr_btn.setFixedWidth(26)
        self._dr_btn.setToolTip("Pick dataref")
        self._dr_btn.clicked.connect(self._pick_dr)
        self._fn_combo = _NoScrollComboBox()
        self._fn_combo.addItems(_VALUE_FUNCS)
        self._fn_combo.setToolTip("Convert function")
        self._fn_combo.currentTextChanged.connect(self.changed)
        self._tbl_btn = QPushButton("Table…")
        self._tbl_btn.setFixedWidth(58)
        self._tbl_btn.setToolTip("Edit calibration table")
        self._tbl_btn.clicked.connect(self._edit_table)

        dr_w = QWidget()
        dl = QHBoxLayout(dr_w)
        dl.setContentsMargins(0, 0, 0, 0); dl.setSpacing(2)
        dl.addWidget(self._dr_edit, 1)
        dl.addWidget(self._dr_btn)
        dl.addWidget(self._fn_combo)
        dl.addWidget(self._tbl_btn)

        self._stack = QStackedWidget()
        self._stack.addWidget(static_w)
        self._stack.addWidget(dr_w)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0); row.setSpacing(4)
        row.addWidget(QLabel(label))
        row.addWidget(self._mode)
        row.addWidget(self._stack, 1)

    def _on_mode_changed(self, idx: int):
        self._stack.setCurrentIndex(idx)
        self.changed.emit()

    def _pick_dr(self):
        from gauge_designer.dataref_picker import DatarefPickerDialog
        dlg = DatarefPickerDialog(current=self._dr_edit.text().strip(), parent=self)
        if dlg.exec() == QDialog.Accepted and dlg.selected_dataref():
            self._dr_edit.setText(dlg.selected_dataref())
            self.changed.emit()

    def _edit_table(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Calibration table")
        dlg.resize(300, 220)
        tbl = _TableEditor("Input", "Output")
        tbl.load(self._table_data)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay = QVBoxLayout(dlg)
        lay.addWidget(tbl, 1)
        lay.addWidget(btns)
        if dlg.exec() == QDialog.Accepted:
            self._table_data = tbl.get_data()
            self.changed.emit()

    def load(self, raw):
        if isinstance(raw, dict):
            self._mode.blockSignals(True)
            self._mode.setCurrentIndex(1)
            self._stack.setCurrentIndex(1)
            self._mode.blockSignals(False)
            self._dr_edit.setText(str(raw.get("dataref", "")))
            self._table_data = raw.get("table", [])
            fn = raw.get("convert_function") or _NONE
            self._fn_combo.setCurrentIndex(max(self._fn_combo.findText(fn), 0))
        else:
            self._mode.blockSignals(True)
            self._mode.setCurrentIndex(0)
            self._stack.setCurrentIndex(0)
            self._mode.blockSignals(False)
            try:
                self._static_spin.setValue(float(raw))
            except (TypeError, ValueError):
                self._static_spin.setValue(0.0)

    def get_data(self):
        if self._mode.currentIndex() == 0:
            return self._static_spin.value()
        result: dict = {
            "dataref": self._dr_edit.text().strip(),
            "table": self._table_data,
        }
        fn = self._fn_combo.currentText()
        if fn != _NONE:
            result["convert_function"] = fn
        return result


# ── Band list editor ──────────────────────────────────────────────────────────

class _BandsEditor(QWidget):
    """Edits the full list of VectorTape bands."""
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bands: list[dict] = []   # raw band dicts, parallel to list rows
        self._loading = False

        # List
        self._list = QListWidget()
        self._list.setFixedHeight(90)
        self._list.currentRowChanged.connect(self._on_row_changed)

        # List toolbar
        add_btn = QPushButton("+"); add_btn.setFixedWidth(26)
        add_btn.setToolTip("Add band"); add_btn.clicked.connect(self._add)
        rm_btn  = QPushButton("−"); rm_btn.setFixedWidth(26)
        rm_btn.setToolTip("Remove band"); rm_btn.clicked.connect(self._remove)
        list_bar = QHBoxLayout()
        list_bar.setContentsMargins(0, 0, 0, 0); list_bar.setSpacing(2)
        list_bar.addWidget(add_btn); list_bar.addWidget(rm_btn)
        list_bar.addStretch()

        # Edit panel (shown when a band is selected)
        self._edit_panel = QFrame()
        self._edit_panel.setFrameShape(QFrame.StyledPanel)
        self._edit_panel.setVisible(False)
        ep_layout = QVBoxLayout(self._edit_panel)
        ep_layout.setContentsMargins(6, 6, 6, 6)
        ep_layout.setSpacing(4)

        self._ep_min = _BandEndpointWidget("Min:")
        self._ep_max = _BandEndpointWidget("Max:")
        self._ep_min.changed.connect(self._on_endpoint_changed)
        self._ep_max.changed.connect(self._on_endpoint_changed)

        color_row = QHBoxLayout()
        color_row.setContentsMargins(0, 0, 0, 0)
        color_row.addWidget(QLabel("Color:"))
        self._ep_color = _ColorButton()
        self._ep_color.color_changed.connect(self._on_endpoint_changed)
        color_row.addWidget(self._ep_color, 1)

        width_row = QHBoxLayout()
        width_row.setContentsMargins(0, 0, 0, 0)
        width_row.addWidget(QLabel("Width px:"))
        self._ep_width = QDoubleSpinBox()
        self._ep_width.setRange(1.0, 200.0); self._ep_width.setDecimals(1)
        self._ep_width.setValue(8.0)
        self._ep_width.valueChanged.connect(self._on_endpoint_changed)
        width_row.addWidget(self._ep_width)
        width_row.addWidget(QLabel("Side:"))
        self._ep_side = _NoScrollComboBox()
        self._ep_side.addItems(["left", "right", "top", "bottom"])
        self._ep_side.currentTextChanged.connect(self._on_endpoint_changed)
        width_row.addWidget(self._ep_side)
        width_row.addWidget(QLabel("Offset px:"))
        self._ep_offset = QDoubleSpinBox()
        self._ep_offset.setRange(0.0, 500.0); self._ep_offset.setDecimals(1)
        self._ep_offset.setToolTip("Gap between the spine and the band's edge — same direction ticks use.")
        self._ep_offset.valueChanged.connect(self._on_endpoint_changed)
        width_row.addWidget(self._ep_offset)
        width_row.addStretch()

        dash_row = QHBoxLayout()
        dash_row.setContentsMargins(0, 0, 0, 0); dash_row.setSpacing(4)
        self._ep_dash_chk = QCheckBox("Dashed")
        self._ep_dash_chk.toggled.connect(lambda on: self._ep_dash_len.setEnabled(on))
        self._ep_dash_chk.toggled.connect(self._on_endpoint_changed)
        self._ep_dash_len = QDoubleSpinBox()
        self._ep_dash_len.setRange(1.0, 500.0); self._ep_dash_len.setDecimals(1)
        self._ep_dash_len.setValue(5.0); self._ep_dash_len.setEnabled(False)
        self._ep_dash_len.setSuffix(" px")
        self._ep_dash_len.valueChanged.connect(self._on_endpoint_changed)
        dash_row.addWidget(self._ep_dash_chk)
        dash_row.addWidget(self._ep_dash_len)
        dash_row.addStretch()

        ep_layout.addWidget(self._ep_min)
        ep_layout.addWidget(self._ep_max)
        ep_layout.addLayout(color_row)
        ep_layout.addLayout(width_row)
        ep_layout.addLayout(dash_row)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self._list)
        layout.addLayout(list_bar)
        layout.addWidget(self._edit_panel)

    def _band_label(self, band: dict) -> str:
        def _ep_str(v):
            if isinstance(v, dict):
                dr = v.get("dataref", "?")
                return f"DR:{dr.split('/')[-1]}"
            return str(v)
        lo = _ep_str(band["range"][0])
        hi = _ep_str(band["range"][1])
        dash_str = f" dash={band['dash']}" if band.get("dash") else ""
        return f"{lo} → {hi}   (w={band.get('width', 8)}{dash_str})"

    def _refresh_list(self):
        self._list.blockSignals(True)
        current = self._list.currentRow()
        self._list.clear()
        for band in self._bands:
            item = QListWidgetItem(self._band_label(band))
            c = band.get("color", [255, 255, 255, 255])
            item.setForeground(QColor(int(c[0]), int(c[1]), int(c[2])))
            self._list.addItem(item)
        self._list.setCurrentRow(current)
        self._list.blockSignals(False)

    def _on_row_changed(self, row: int):
        if row < 0 or row >= len(self._bands):
            self._edit_panel.setVisible(False)
            return
        self._loading = True
        band = self._bands[row]
        self._ep_min.load(band["range"][0])
        self._ep_max.load(band["range"][1])
        self._ep_color.set_rgba(band.get("color"))
        self._ep_width.setValue(float(band.get("width", 8.0)))
        side = band.get("side") or "left"
        self._ep_side.setCurrentText(side)
        self._ep_offset.setValue(float(band.get("offset", 0.0)))
        dash = band.get("dash")
        self._ep_dash_chk.blockSignals(True)
        self._ep_dash_chk.setChecked(dash is not None)
        self._ep_dash_chk.blockSignals(False)
        self._ep_dash_len.setEnabled(dash is not None)
        self._ep_dash_len.setValue(float(dash) if dash is not None else 5.0)
        self._edit_panel.setVisible(True)
        self._loading = False

    def _on_endpoint_changed(self):
        if self._loading:
            return
        row = self._list.currentRow()
        if row < 0 or row >= len(self._bands):
            return
        self._bands[row]["range"] = [self._ep_min.get_data(), self._ep_max.get_data()]
        self._bands[row]["color"] = list(self._ep_color.get_rgba())
        self._bands[row]["width"] = self._ep_width.value()
        self._bands[row]["side"] = self._ep_side.currentText()
        if self._ep_offset.value() != 0:
            self._bands[row]["offset"] = self._ep_offset.value()
        else:
            self._bands[row].pop("offset", None)
        if self._ep_dash_chk.isChecked():
            self._bands[row]["dash"] = self._ep_dash_len.value()
        else:
            self._bands[row].pop("dash", None)
        self._refresh_list()
        self.changed.emit()

    def _add(self):
        self._bands.append({"range": [0.0, 100.0], "color": [255, 255, 255, 180], "width": 8.0, "side": "left"})
        self._refresh_list()
        self._list.setCurrentRow(len(self._bands) - 1)
        self.changed.emit()

    def _remove(self):
        row = self._list.currentRow()
        if row < 0:
            return
        self._bands.pop(row)
        self._refresh_list()
        self.changed.emit()

    def load(self, bands: list):
        self._loading = True
        self._bands = []
        for b in bands:
            entry = {
                "range": list(b.get("range", [0.0, 100.0])),
                "color": b.get("color", [255, 255, 255, 180]),
                "width": float(b.get("width", 8.0)),
                "side": b.get("side") or "left",
            }
            if b.get("offset"):
                entry["offset"] = float(b["offset"])
            if b.get("dash") is not None:
                entry["dash"] = float(b["dash"])
            self._bands.append(entry)
        self._refresh_list()
        self._edit_panel.setVisible(False)
        self._loading = False

    def get_data(self) -> list:
        result = []
        for b in self._bands:
            entry = {"range": list(b["range"]), "color": list(b["color"]),
                     "width": b["width"], "side": b.get("side", "left")}
            if b.get("offset"):
                entry["offset"] = b["offset"]
            if b.get("dash") is not None:
                entry["dash"] = b["dash"]
            result.append(entry)
        return result


# ── Bug list editor ───────────────────────────────────────────────────────────

class _BugsEditor(QWidget):
    """Edits the list of VectorTape bug markers."""
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bugs: list[dict] = []
        self._loading = False

        self._list = QListWidget()
        self._list.setFixedHeight(80)
        self._list.currentRowChanged.connect(self._on_row_changed)

        add_btn = QPushButton("+"); add_btn.setFixedWidth(26)
        add_btn.setToolTip("Add bug"); add_btn.clicked.connect(self._add)
        rm_btn = QPushButton("−"); rm_btn.setFixedWidth(26)
        rm_btn.setToolTip("Remove bug"); rm_btn.clicked.connect(self._remove)
        list_bar = QHBoxLayout()
        list_bar.setContentsMargins(0, 0, 0, 0); list_bar.setSpacing(2)
        list_bar.addWidget(add_btn); list_bar.addWidget(rm_btn); list_bar.addStretch()

        self._edit_panel = QFrame()
        self._edit_panel.setFrameShape(QFrame.StyledPanel)
        self._edit_panel.setVisible(False)
        ep = QVBoxLayout(self._edit_panel)
        ep.setContentsMargins(6, 6, 6, 6); ep.setSpacing(4)

        self._bug_value = _BandEndpointWidget("Value:")
        self._bug_value.changed.connect(self._on_field_changed)
        ep.addWidget(self._bug_value)

        color_row = QHBoxLayout()
        color_row.setContentsMargins(0, 0, 0, 0); color_row.setSpacing(6)
        color_row.addWidget(QLabel("Color:"))
        self._bug_color = _ColorButton()
        self._bug_color.color_changed.connect(self._on_field_changed)
        color_row.addWidget(self._bug_color, 1)
        ep.addLayout(color_row)

        style_row = QHBoxLayout()
        style_row.setContentsMargins(0, 0, 0, 0); style_row.setSpacing(8)
        self._bug_filled = QCheckBox("Filled")
        self._bug_filled.setChecked(True)
        self._bug_filled.toggled.connect(lambda on: self._bug_width.setEnabled(not on))
        self._bug_filled.toggled.connect(self._on_field_changed)
        self._bug_width = QDoubleSpinBox()
        self._bug_width.setRange(1.0, 20.0); self._bug_width.setDecimals(1)
        self._bug_width.setValue(2.0); self._bug_width.setEnabled(False)
        self._bug_width.setPrefix("w: "); self._bug_width.setSuffix(" px")
        self._bug_width.valueChanged.connect(self._on_field_changed)
        style_row.addWidget(self._bug_filled)
        style_row.addWidget(self._bug_width)
        style_row.addStretch()
        ep.addLayout(style_row)

        ep.addWidget(QLabel("Points relative to spine anchor (Arcade y-up):"))
        self._bug_points = _PointsTableEditor()
        self._bug_points.changed.connect(self._on_field_changed)
        ep.addWidget(self._bug_points)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(2)
        layout.addWidget(self._list)
        layout.addLayout(list_bar)
        layout.addWidget(self._edit_panel)

    def _bug_label(self, bug: dict) -> str:
        val = bug.get("value", 0.0)
        val_str = f"DR:{str(val.get('dataref','?')).split('/')[-1]}" \
            if isinstance(val, dict) else str(float(val))
        pts = len(bug.get("points", []))
        style = "filled" if bug.get("filled", True) else "outline"
        return f"{val_str}   ({pts} pts, {style})"

    def _refresh_list(self):
        self._list.blockSignals(True)
        current = self._list.currentRow()
        self._list.clear()
        for bug in self._bugs:
            item = QListWidgetItem(self._bug_label(bug))
            c = bug.get("color", [255, 200, 0, 255])
            item.setForeground(QColor(int(c[0]), int(c[1]), int(c[2])))
            self._list.addItem(item)
        self._list.setCurrentRow(current)
        self._list.blockSignals(False)

    def _on_row_changed(self, row: int):
        if row < 0 or row >= len(self._bugs):
            self._edit_panel.setVisible(False)
            return
        self._loading = True
        bug = self._bugs[row]
        self._bug_value.load(bug.get("value", 0.0))
        self._bug_color.set_rgba(bug.get("color"))
        filled = bool(bug.get("filled", True))
        self._bug_filled.setChecked(filled)
        self._bug_width.setEnabled(not filled)
        self._bug_width.setValue(float(bug.get("width", 2.0)))
        self._bug_points.load(bug.get("points", []))
        self._edit_panel.setVisible(True)
        self._loading = False

    def _on_field_changed(self):
        if self._loading:
            return
        row = self._list.currentRow()
        if row < 0 or row >= len(self._bugs):
            return
        self._bugs[row]["value"] = self._bug_value.get_data()
        self._bugs[row]["color"] = list(self._bug_color.get_rgba())
        self._bugs[row]["filled"] = self._bug_filled.isChecked()
        self._bugs[row]["width"] = self._bug_width.value()
        self._bugs[row]["points"] = self._bug_points.get_data()
        self._refresh_list()
        self.changed.emit()

    def _add(self):
        self._bugs.append({
            "value": 0.0,
            "color": [255, 200, 0, 255],
            "filled": True,
            "width": 2.0,
            "points": [[0, 0], [10, 5], [10, -5]],
        })
        self._refresh_list()
        self._list.setCurrentRow(len(self._bugs) - 1)
        self.changed.emit()

    def _remove(self):
        row = self._list.currentRow()
        if row < 0:
            return
        self._bugs.pop(row)
        self._refresh_list()
        self.changed.emit()

    def load(self, bugs: list):
        self._loading = True
        self._bugs = []
        for b in bugs:
            self._bugs.append({
                "value": b.get("value", 0.0),
                "color": b.get("color", [255, 200, 0, 255]),
                "filled": bool(b.get("filled", True)),
                "width": float(b.get("width", 2.0)),
                "points": [list(p) for p in b.get("points", [])],
            })
        self._refresh_list()
        self._edit_panel.setVisible(False)
        self._loading = False

    def get_data(self) -> list:
        result = []
        for b in self._bugs:
            entry: dict = {
                "value": b["value"],
                "color": list(b["color"]),
                "points": [list(p) for p in b["points"]],
            }
            if not b.get("filled", True):
                entry["filled"] = False
                entry["width"] = b["width"]
            result.append(entry)
        return result


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


class _SubSection(QWidget):
    """Collapsible sub-group for nesting inside a _Section body."""

    def __init__(self, title: str, collapsed: bool = False, parent=None):
        super().__init__(parent)
        self._title = title
        self._collapsed = collapsed

        self._hdr = QPushButton()
        self._hdr.setFlat(True)
        self._hdr.setStyleSheet(
            "QPushButton { text-align: left; font-weight: bold; "
            "color: black; padding: 3px 0 1px 0; border: none; }"
            "QPushButton:hover { color: #333; }"
        )
        self._hdr.clicked.connect(self._toggle)
        self._update_btn()

        self._body = QWidget()
        self._form = QFormLayout(self._body)
        self._form.setContentsMargins(8, 2, 0, 4)
        self._form.setHorizontalSpacing(8)
        self._form.setVerticalSpacing(4)
        self._body.setVisible(not collapsed)

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 2, 0, 0)
        vbox.setSpacing(0)
        vbox.addWidget(self._hdr)
        vbox.addWidget(self._body)

    def _update_btn(self):
        arrow = "▸" if self._collapsed else "▾"
        self._hdr.setText(f"  {arrow}  {self._title}")

    def _toggle(self):
        self._collapsed = not self._collapsed
        self._body.setVisible(not self._collapsed)
        self._update_btn()

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


def _sb(lo: int = -4096, hi: int = 4096) -> QSpinBox:
    s = QSpinBox(); s.setRange(lo, hi); s.setMinimumWidth(64); return s


def _pair_box(w1: QWidget, w2: QWidget, sep: str = "×") -> QWidget:
    box = QWidget()
    hl = QHBoxLayout(box)
    hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(4)
    hl.addWidget(w1); hl.addWidget(QLabel(sep)); hl.addWidget(w2); hl.addStretch()
    return box


def _sep_label(text: str) -> QLabel:
    """Thin horizontal separator label used as a sub-section divider."""
    lbl = QLabel(text)
    lbl.setStyleSheet("color: #aaa; font-size: 10px; margin-top: 4px;")
    return lbl


# ── Main form ─────────────────────────────────────────────────────────────────

class PropertiesForm(QWidget):
    changed        = Signal()
    point_selected = Signal(int)   # polygon point row, or -1

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
        self._mk_text_sec()
        self._mk_line_sec()
        self._mk_arc_sec()
        self._mk_filledrect_sec()
        self._mk_polygon_sec()
        self._mk_vector_sec()
        self._mk_vectortape_sec()
        self._mk_ai_sec()
        self._mk_needlegauge_sec()
        self._mk_compassrose_sec()
        self._mk_rotary_encoder_sec()
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
        btn.clicked.connect(lambda: self._browse_tex())
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

        self._ss_smooth = QCheckBox("Smooth  (sub-frame interpolation for fluid animation)")
        self._ss_smooth.setChecked(True)
        self._ss_smooth.toggled.connect(self._emit)
        self._ss_sec.row_widget(self._ss_smooth)

        self._ss_ppu = QDoubleSpinBox()
        self._ss_ppu.setRange(0.0, 100000.0)
        self._ss_ppu.setDecimals(2)
        self._ss_ppu.setSingleStep(1.0)
        self._ss_ppu.setValue(0.0)
        self._ss_ppu.setSpecialValueText("= frame width")
        self._ss_ppu.setToolTip(
            "Pixels per unit: atlas pixels shifted per unit of the fractional frame value.\n"
            "shift = (frame_value − floor(frame_value)) × pixels_per_unit.\n"
            "0 (special value) = default, equals frame width (fast, one full frame per step).\n"
            "Smaller values give subtle sub-frame motion (e.g. 5 px/unit for a slow compass)."
        )
        self._ss_ppu.valueChanged.connect(self._emit)

        self._ss_shift_dir = QComboBox()
        self._ss_shift_dir.addItem("→  Right", "right")
        self._ss_shift_dir.addItem("←  Left",  "left")
        self._ss_shift_dir.setToolTip(
            "Direction the atlas slides as the fractional value increases.\n"
            "Right: content appears to scroll right (default).\n"
            "Left:  content appears to scroll left (e.g. compass heading increasing)."
        )
        self._ss_shift_dir.currentIndexChanged.connect(self._emit)

        self._ss_sec.row("Pixels / unit", _pair_box(self._ss_ppu, self._ss_shift_dir, ""))

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

    def _mk_text_sec(self):
        self._txt_sec = _Section("Text")
        self._txt_sec.setVisible(False)

        # Mode: Static text or Dataref-driven
        self._txt_mode = _NoScrollComboBox()
        self._txt_mode.addItems(["Static", "Dataref"])
        self._txt_mode.currentIndexChanged.connect(self._on_txt_mode_changed)
        self._txt_mode.currentIndexChanged.connect(self._emit)
        self._txt_sec.row("Mode", self._txt_mode)

        # Stacked pages: [0] Static, [1] Dataref
        self._txt_stack = QStackedWidget()

        # Page 0 — static text
        static_page = QWidget()
        sp_form = QFormLayout(static_page)
        sp_form.setContentsMargins(0, 2, 0, 2)
        sp_form.setHorizontalSpacing(8)
        sp_form.setVerticalSpacing(4)
        self._txt_static = QLineEdit()
        self._txt_static.setPlaceholderText("label text")
        self._txt_static.editingFinished.connect(self._emit)
        sp_form.addRow("Text", self._txt_static)

        # Page 1 — dataref-driven
        dr_page = QWidget()
        dp_form = QFormLayout(dr_page)
        dp_form.setContentsMargins(0, 2, 0, 2)
        dp_form.setHorizontalSpacing(8)
        dp_form.setVerticalSpacing(4)

        self._txt_dr = QLineEdit()
        self._txt_dr.editingFinished.connect(self._emit)
        dp_form.addRow("Dataref", self._dr_field(self._txt_dr))

        self._txt_fn = _NoScrollComboBox()
        self._txt_fn.addItems(_VALUE_FUNCS)
        self._txt_fn.currentTextChanged.connect(self._emit)
        dp_form.addRow("Convert fn", self._txt_fn)

        self._txt_decimals = QSpinBox()
        self._txt_decimals.setRange(0, 6)
        self._txt_decimals.setValue(1)
        self._txt_decimals.setMinimumWidth(50)
        self._txt_decimals.valueChanged.connect(self._update_txt_format)
        self._txt_decimals.valueChanged.connect(self._emit)
        dp_form.addRow("Decimal places", self._txt_decimals)

        self._txt_width = QSpinBox()
        self._txt_width.setRange(0, 20)
        self._txt_width.setValue(0)
        self._txt_width.setSpecialValueText("auto")
        self._txt_width.setMinimumWidth(50)
        self._txt_width.valueChanged.connect(self._update_txt_format)
        self._txt_width.valueChanged.connect(self._emit)
        dp_form.addRow("Min width", self._txt_width)

        self._txt_zerofill = QCheckBox("Zero fill")
        self._txt_zerofill.toggled.connect(self._update_txt_format)
        self._txt_zerofill.toggled.connect(self._emit)
        dp_form.addRow(self._txt_zerofill)

        fmt_w = QWidget()
        fmt_hl = QHBoxLayout(fmt_w)
        fmt_hl.setContentsMargins(0, 0, 0, 0)
        fmt_hl.setSpacing(4)
        self._txt_fmt_preview = QLabel("{:.1f}")
        self._txt_fmt_preview.setStyleSheet("font-family: monospace; color: #aaa;")
        fmt_hl.addWidget(self._txt_fmt_preview)
        fmt_hl.addStretch()
        dp_form.addRow("Format string", fmt_w)

        self._txt_fmt_custom = QLineEdit()
        self._txt_fmt_custom.setPlaceholderText("Override, e.g.  {:05.0f}  (blank = auto)")
        self._txt_fmt_custom.setToolTip(_FORMAT_SPEC_TOOLTIP)
        self._txt_fmt_custom.editingFinished.connect(self._on_txt_fmt_custom_changed)
        self._txt_fmt_custom.editingFinished.connect(self._emit)
        dp_form.addRow("Custom fmt", self._txt_fmt_custom)

        self._txt_emphasize_place = QDoubleSpinBox()
        self._txt_emphasize_place.setRange(0.0, 8.0)
        self._txt_emphasize_place.setDecimals(0)
        self._txt_emphasize_place.setSpecialValueText("(none)")
        self._txt_emphasize_place.setToolTip(
            "Number of trailing digits to keep at the regular font size — the\n"
            "leading digits above them render at Emphasize font size instead.\n"
            "E.g. 3 keeps \"000\" small and makes the leading \"30\" in \"30,000\"\n"
            "big. (none) disables the split; the value renders as one\n"
            "uniform-size run."
        )
        self._txt_emphasize_place.valueChanged.connect(self._emit)
        dp_form.addRow("Emphasize place", self._txt_emphasize_place)

        self._txt_emphasize_size = QDoubleSpinBox()
        self._txt_emphasize_size.setRange(4.0, 200.0); self._txt_emphasize_size.setDecimals(1)
        self._txt_emphasize_size.setValue(12.0)
        self._txt_emphasize_size.setToolTip(
            "Font size for the leading (emphasized) digits — everything except\n"
            "the last Emphasize place digits. Only used when Emphasize place is set."
        )
        self._txt_emphasize_size.valueChanged.connect(self._emit)
        dp_form.addRow("Emphasize font size", self._txt_emphasize_size)

        self._txt_stack.addWidget(static_page)
        self._txt_stack.addWidget(dr_page)
        self._txt_sec.row_widget(self._txt_stack)

        # Font row (always visible)
        self._txt_font_name = QLineEdit()
        self._txt_font_name.setPlaceholderText("Arial  (blank = default)")
        self._txt_font_name.editingFinished.connect(self._emit)
        _txt_font_btn = QPushButton("…")
        _txt_font_btn.setFixedWidth(28)
        _txt_font_btn.setToolTip("Choose font")
        _txt_font_btn.clicked.connect(self._pick_txt_font)
        _txt_font_row = QWidget()
        _txt_font_hl = QHBoxLayout(_txt_font_row)
        _txt_font_hl.setContentsMargins(0, 0, 0, 0)
        _txt_font_hl.setSpacing(4)
        _txt_font_hl.addWidget(self._txt_font_name)
        _txt_font_hl.addWidget(_txt_font_btn)
        self._txt_sec.row("Font", _txt_font_row)

        self._txt_font_size = QDoubleSpinBox()
        self._txt_font_size.setRange(4.0, 200.0)
        self._txt_font_size.setDecimals(1)
        self._txt_font_size.setValue(12.0)
        self._txt_font_size.valueChanged.connect(self._emit)
        self._txt_sec.row("Font size", self._txt_font_size)

        _style_row = QWidget()
        _style_hl = QHBoxLayout(_style_row)
        _style_hl.setContentsMargins(0, 0, 0, 0)
        _style_hl.setSpacing(12)
        self._txt_bold = QCheckBox("Bold")
        self._txt_bold.toggled.connect(self._emit)
        self._txt_italic = QCheckBox("Italic")
        self._txt_italic.toggled.connect(self._emit)
        _style_hl.addWidget(self._txt_bold)
        _style_hl.addWidget(self._txt_italic)
        _style_hl.addStretch()
        self._txt_sec.row("Style", _style_row)

        self._txt_color = _ColorButton()
        self._txt_color.color_changed.connect(self._emit)
        self._txt_sec.row("Color", self._txt_color)

        self._txt_anchor_x = _NoScrollComboBox()
        self._txt_anchor_x.addItems(["left", "center", "right"])
        self._txt_anchor_x.currentTextChanged.connect(self._emit)
        self._txt_sec.row("Anchor X", self._txt_anchor_x)

        self._txt_anchor_y = _NoScrollComboBox()
        self._txt_anchor_y.addItems(["baseline", "center", "top", "bottom"])
        self._txt_anchor_y.currentTextChanged.connect(self._emit)
        self._txt_sec.row("Anchor Y", self._txt_anchor_y)

        self._vbox.addWidget(self._txt_sec)

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

        self._poly_ox = _sb(); self._poly_oy = _sb()
        for w in (self._poly_ox, self._poly_oy):
            w.valueChanged.connect(self._emit)
        y_label = "Origin X  /  Y top" if is_y_down() else "Origin X  /  Y"
        self._poly_sec.row_pair(y_label, self._poly_ox, self._poly_oy)

        self._poly_pts = _PointsTableEditor()
        self._poly_pts.changed.connect(self._emit)
        self._poly_pts.point_selected.connect(self.point_selected)
        self._poly_sec.row("Points (relative to origin)", self._poly_pts)

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

    def _mk_vector_sec(self):
        self._vec_sec = _Section("Vector")
        self._vec_sec.setVisible(False)

        # Direction: static angle or dataref-driven (reuse _BandEndpointWidget)
        self._vec_dir = _BandEndpointWidget("Direction °")
        self._vec_dir.changed.connect(self._emit)
        self._vec_sec.row_widget(self._vec_dir)

        # Length: static pixels or dataref-driven
        self._vec_len = _BandEndpointWidget("Length px  ")
        self._vec_len.changed.connect(self._emit)
        self._vec_sec.row_widget(self._vec_len)

        self._vec_color = _ColorButton()
        self._vec_color.color_changed.connect(self._emit)
        self._vec_sec.row("Color", self._vec_color)

        self._vec_width = QDoubleSpinBox()
        self._vec_width.setRange(0.5, 50.0); self._vec_width.setDecimals(1)
        self._vec_width.setValue(1.0)
        self._vec_width.valueChanged.connect(self._emit)
        self._vec_sec.row("Width px", self._vec_width)

        self._vec_cap = _NoScrollComboBox()
        self._vec_cap.addItems(["none", "triangle", "bar"])
        self._vec_cap.currentTextChanged.connect(self._on_vec_cap_changed)
        self._vec_cap.currentTextChanged.connect(self._emit)
        self._vec_sec.row("Cap", self._vec_cap)

        self._vec_cap_width = QDoubleSpinBox()
        self._vec_cap_width.setRange(1.0, 200.0); self._vec_cap_width.setDecimals(1)
        self._vec_cap_width.setValue(10.0); self._vec_cap_width.setFixedWidth(100)
        self._vec_cap_width.setEnabled(False)
        self._vec_cap_width.valueChanged.connect(self._emit)

        self._vec_cap_height = QDoubleSpinBox()
        self._vec_cap_height.setRange(1.0, 200.0); self._vec_cap_height.setDecimals(1)
        self._vec_cap_height.setValue(5.0); self._vec_cap_height.setFixedWidth(100)
        self._vec_cap_height.setEnabled(False)
        self._vec_cap_height.valueChanged.connect(self._emit)

        self._vec_cap_filled = QCheckBox("Filled")
        self._vec_cap_filled.setChecked(True)
        self._vec_cap_filled.setEnabled(False)
        self._vec_cap_filled.toggled.connect(self._emit)

        _cap_size_box = QWidget()
        _cap_size_hl = QHBoxLayout(_cap_size_box)
        _cap_size_hl.setContentsMargins(0, 0, 0, 0); _cap_size_hl.setSpacing(4)
        _cap_size_hl.addWidget(self._vec_cap_width)
        _cap_size_hl.addWidget(self._vec_cap_height)
        _cap_size_hl.addWidget(self._vec_cap_filled)
        _cap_size_hl.addStretch()
        self._vec_sec.row("Cap w / h px", _cap_size_box)

        self._vec_hide_if_short = QCheckBox("Hide if length < cap height")
        self._vec_hide_if_short.setEnabled(False)
        self._vec_hide_if_short.toggled.connect(self._emit)
        self._vec_sec.row("", self._vec_hide_if_short)

        self._vbox.addWidget(self._vec_sec)

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

        self._vt_wrap = QDoubleSpinBox()
        self._vt_wrap.setRange(0.0, 99999.0); self._vt_wrap.setDecimals(2)
        self._vt_wrap.setSpecialValueText("(none)")
        self._vt_wrap.setValue(0.0)
        self._vt_wrap.valueChanged.connect(self._emit)
        self._vt_sec.row("Wrap (modulo)", self._vt_wrap)

        self._vt_tick_side = _NoScrollComboBox()
        self._vt_tick_side.addItems(["left", "right", "top", "bottom"])
        self._vt_tick_side.currentTextChanged.connect(self._emit)
        self._vt_sec.row("Tick side", self._vt_tick_side)

        self._vt_tick_color = _ColorButton()
        self._vt_tick_color.color_changed.connect(self._emit)
        self._vt_sec.row("Tick color", self._vt_tick_color)

        _vt_bg_row = QWidget()
        _vt_bg_hl = QHBoxLayout(_vt_bg_row)
        _vt_bg_hl.setContentsMargins(0, 0, 0, 0); _vt_bg_hl.setSpacing(6)
        self._vt_bg_chk = QCheckBox()
        self._vt_bg_chk.toggled.connect(lambda on: self._vt_bg_color.setEnabled(on))
        self._vt_bg_chk.toggled.connect(self._emit)
        self._vt_bg_color = _ColorButton()
        self._vt_bg_color.setEnabled(False)
        self._vt_bg_color.color_changed.connect(self._emit)
        _vt_bg_hl.addWidget(self._vt_bg_chk)
        _vt_bg_hl.addWidget(self._vt_bg_color, 1)
        self._vt_sec.row("Background", _vt_bg_row)

        self._vt_ticks = _TableEditor("Interval", "Length", "Width", "X Offset", "Y Offset")
        self._vt_ticks.changed.connect(self._emit)
        self._vt_sec.row("Ticks", self._vt_ticks)

        self._vt_label_interval = QDoubleSpinBox()
        self._vt_label_interval.setRange(0.0, 9999.0); self._vt_label_interval.setDecimals(1)
        self._vt_label_interval.setSpecialValueText("(none)")
        self._vt_label_interval.valueChanged.connect(self._emit)
        self._vt_sec.row("Label interval - dataref unit", self._vt_label_interval)

        self._vt_label_format = QLineEdit()
        self._vt_label_format.setPlaceholderText("{:.0f}  (blank = default)")
        self._vt_label_format.setToolTip(_FORMAT_SPEC_TOOLTIP)
        self._vt_label_format.editingFinished.connect(self._emit)
        self._vt_sec.row("Label format", self._vt_label_format)

        self._vt_label_offset = QDoubleSpinBox()
        self._vt_label_offset.setRange(0.0, 200.0); self._vt_label_offset.setDecimals(1)
        self._vt_label_offset.setValue(8.0)
        self._vt_label_offset.valueChanged.connect(self._emit)
        self._vt_sec.row("Label offset px", self._vt_label_offset)

        self._vt_label_side = _NoScrollComboBox()
        self._vt_label_side.addItems(["(same as tick side)", "left", "right", "top", "bottom"])
        self._vt_label_side.currentTextChanged.connect(self._emit)
        self._vt_sec.row("Label side", self._vt_label_side)

        self._vt_label_justify = _NoScrollComboBox()
        self._vt_label_justify.addItems(
            ["(auto — flush against spine)", "left", "center", "right", "top", "bottom"])
        self._vt_label_justify.setToolTip(
            "Justifies the label text relative to its offset point, independent of\n"
            "which side of the spine it's on. Left/right/center apply to a\n"
            "vertical (y-axis) tape; top/center/bottom apply to a horizontal\n"
            "(x-axis) tape. Default flushes the text against the spine, matching\n"
            "the direction implied by Label side."
        )
        self._vt_label_justify.currentTextChanged.connect(self._emit)
        self._vt_sec.row("Label justify", self._vt_label_justify)

        self._vt_label_font_size = QDoubleSpinBox()
        self._vt_label_font_size.setRange(4.0, 120.0); self._vt_label_font_size.setDecimals(1)
        self._vt_label_font_size.setValue(18.0)
        self._vt_label_font_size.valueChanged.connect(self._emit)
        self._vt_sec.row("Label size px", self._vt_label_font_size)

        self._vt_label_emphasize_place = QDoubleSpinBox()
        self._vt_label_emphasize_place.setRange(0.0, 8.0)
        self._vt_label_emphasize_place.setDecimals(0)
        self._vt_label_emphasize_place.setSpecialValueText("(none)")
        self._vt_label_emphasize_place.setToolTip(
            "Number of trailing digits to keep at the regular label size — the\n"
            "leading digits above them render at Emphasize font size instead.\n"
            "E.g. 3 keeps \"000\" small and makes the leading \"30\" in \"30,000\"\n"
            "big. (none) disables the split; labels render as one uniform-size run."
        )
        self._vt_label_emphasize_place.valueChanged.connect(self._emit)
        self._vt_sec.row("Emphasize place", self._vt_label_emphasize_place)

        self._vt_label_emphasize_size = QDoubleSpinBox()
        self._vt_label_emphasize_size.setRange(4.0, 200.0); self._vt_label_emphasize_size.setDecimals(1)
        self._vt_label_emphasize_size.setValue(18.0)
        self._vt_label_emphasize_size.setToolTip(
            "Font size for the leading (emphasized) digits — everything except\n"
            "the last Emphasize place digits. Only used when Emphasize place is set."
        )
        self._vt_label_emphasize_size.valueChanged.connect(self._emit)
        self._vt_sec.row("Emphasize font size", self._vt_label_emphasize_size)

        self._vt_label_font = QLineEdit()
        self._vt_label_font.setPlaceholderText("Arial  (blank = default)")
        self._vt_label_font.editingFinished.connect(self._emit)
        _font_btn = QPushButton("…")
        _font_btn.setFixedWidth(28)
        _font_btn.setToolTip("Choose font")
        _font_btn.clicked.connect(self._pick_label_font)
        _font_row = QWidget()
        _font_hl = QHBoxLayout(_font_row)
        _font_hl.setContentsMargins(0, 0, 0, 0)
        _font_hl.setSpacing(4)
        _font_hl.addWidget(self._vt_label_font)
        _font_hl.addWidget(_font_btn)
        self._vt_sec.row("Label font", _font_row)

        _vt_style_row = QWidget()
        _vt_style_hl = QHBoxLayout(_vt_style_row)
        _vt_style_hl.setContentsMargins(0, 0, 0, 0)
        _vt_style_hl.setSpacing(12)
        self._vt_label_bold = QCheckBox("Bold")
        self._vt_label_bold.toggled.connect(self._emit)
        self._vt_label_italic = QCheckBox("Italic")
        self._vt_label_italic.toggled.connect(self._emit)
        _vt_style_hl.addWidget(self._vt_label_bold)
        _vt_style_hl.addWidget(self._vt_label_italic)
        _vt_style_hl.addStretch()
        self._vt_sec.row("Label style", _vt_style_row)

        hint = QLabel("Label color and ticks color are preserved as-is from YAML.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #999; font-size: 10px;")
        self._vt_sec.row_widget(hint)

        self._vt_bands = _BandsEditor()
        self._vt_bands.changed.connect(self._emit)
        self._vt_sec.row("Bands", self._vt_bands)

        self._vt_bugs = _BugsEditor()
        self._vt_bugs.changed.connect(self._emit)
        self._vt_sec.row("Bugs", self._vt_bugs)

        self._vbox.addWidget(self._vt_sec)

    def _mk_ai_sec(self):
        self._ai_sec = _Section("Attitude Indicator")
        self._ai_sec.setVisible(False)

        # ── Layout ───────────────────────────────────────────────────────────
        _ai_layout = _SubSection("Layout", collapsed=False)

        self._ai_vp_x = _sb(0, 4096); self._ai_vp_y = _sb(0, 4096)
        for w in (self._ai_vp_x, self._ai_vp_y):
            w.valueChanged.connect(self._emit)
        y_label = "VP X  /  Y top" if is_y_down() else "VP X  /  Y bottom"
        _ai_layout.row_pair(y_label, self._ai_vp_x, self._ai_vp_y)

        self._ai_vp_w = _sb(0, 4096); self._ai_vp_h = _sb(0, 4096)
        self._ai_vp_w.setValue(300); self._ai_vp_h.setValue(300)
        for w in (self._ai_vp_w, self._ai_vp_h):
            w.valueChanged.connect(self._emit)
        _ai_layout.row_pair("VP W  /  H", self._ai_vp_w, self._ai_vp_h)

        self._ai_pitch_dr = QLineEdit()
        self._ai_pitch_dr.setPlaceholderText("pitch dataref")
        self._ai_pitch_dr.editingFinished.connect(self._emit)
        _ai_layout.row("Pitch dataref", self._dr_field(self._ai_pitch_dr))

        self._ai_roll_dr = QLineEdit()
        self._ai_roll_dr.setPlaceholderText("roll/bank dataref")
        self._ai_roll_dr.editingFinished.connect(self._emit)
        _ai_layout.row("Roll dataref", self._dr_field(self._ai_roll_dr))

        self._ai_ppu = QDoubleSpinBox()
        self._ai_ppu.setRange(0.5, 50.0); self._ai_ppu.setDecimals(1)
        self._ai_ppu.setValue(8.0)
        self._ai_ppu.valueChanged.connect(self._emit)
        _ai_layout.row("Pixels / degree", self._ai_ppu)

        self._ai_smoothing = QDoubleSpinBox()
        self._ai_smoothing.setRange(0.0, 0.99); self._ai_smoothing.setDecimals(2)
        self._ai_smoothing.setSingleStep(0.05)
        self._ai_smoothing.setValue(0.0)
        self._ai_smoothing.setToolTip(
            "EMA smoothing factor (0 = none, 0.9 = heavy). "
            "Reduces jitter from UDP data at the cost of a small lag."
        )
        self._ai_smoothing.valueChanged.connect(self._emit)
        _ai_layout.row("Smoothing", self._ai_smoothing)

        _ai_cr_row = QWidget()
        _ai_cr_hl = QHBoxLayout(_ai_cr_row)
        _ai_cr_hl.setContentsMargins(0, 0, 0, 0); _ai_cr_hl.setSpacing(4)
        self._ai_corner_radius = QDoubleSpinBox()
        self._ai_corner_radius.setRange(0.0, 200.0); self._ai_corner_radius.setDecimals(1)
        self._ai_corner_radius.setValue(0.0); self._ai_corner_radius.setSuffix(" px")
        self._ai_corner_radius.setToolTip("Corner rounding radius in pixels (0 = sharp)")
        self._ai_corner_radius.valueChanged.connect(self._emit)
        self._ai_corner_bg = _ColorButton()
        self._ai_corner_bg.set_rgba([0, 0, 0, 255])
        self._ai_corner_bg.setToolTip("Background color used to mask corners in the runtime")
        self._ai_corner_bg.color_changed.connect(self._emit)
        _ai_cr_hl.addWidget(self._ai_corner_radius)
        _ai_cr_hl.addWidget(QLabel("bg"))
        _ai_cr_hl.addWidget(self._ai_corner_bg)
        _ai_layout.row("Corner radius", _ai_cr_row)

        self._ai_sec.row_widget(_ai_layout)

        # ── Background ───────────────────────────────────────────────────────
        _ai_bg = _SubSection("Background", collapsed=True)

        self._ai_sky_color = _ColorButton()
        self._ai_sky_color.set_rgba([0, 100, 180, 255])
        self._ai_sky_color.color_changed.connect(self._emit)
        _ai_bg.row("Sky color", self._ai_sky_color)

        self._ai_gnd_color = _ColorButton()
        self._ai_gnd_color.set_rgba([100, 60, 10, 255])
        self._ai_gnd_color.color_changed.connect(self._emit)
        _ai_bg.row("Ground color", self._ai_gnd_color)

        self._ai_hor_color = _ColorButton()
        self._ai_hor_color.color_changed.connect(self._emit)
        _ai_bg.row("Horizon color", self._ai_hor_color)

        self._ai_hor_width = QDoubleSpinBox()
        self._ai_hor_width.setRange(0.5, 20.0); self._ai_hor_width.setDecimals(1)
        self._ai_hor_width.setValue(3.0)
        self._ai_hor_width.valueChanged.connect(self._emit)
        _ai_bg.row("Horizon width", self._ai_hor_width)

        self._ai_sec.row_widget(_ai_bg)

        # ── Pitch Ladder ─────────────────────────────────────────────────────
        _ai_ladder = _SubSection("Pitch Ladder", collapsed=False)

        self._ai_ladder_step = QDoubleSpinBox()
        self._ai_ladder_step.setRange(0.5, 45.0); self._ai_ladder_step.setDecimals(1)
        self._ai_ladder_step.setValue(5.0)
        self._ai_ladder_step.setSuffix(" °")
        self._ai_ladder_step.valueChanged.connect(self._emit)
        _ai_ladder.row("Step", self._ai_ladder_step)

        self._ai_ladder_hw_4 = QDoubleSpinBox()
        self._ai_ladder_hw_4.setRange(0.05, 1.0); self._ai_ladder_hw_4.setDecimals(2)
        self._ai_ladder_hw_4.setValue(0.40)
        self._ai_ladder_hw_4.setToolTip("Half-width as fraction of half-viewport — every 4th step (also labeled)")
        self._ai_ladder_hw_4.valueChanged.connect(self._emit)
        _ai_ladder.row("Bar long (4th step)", self._ai_ladder_hw_4)

        self._ai_ladder_hw_2 = QDoubleSpinBox()
        self._ai_ladder_hw_2.setRange(0.05, 1.0); self._ai_ladder_hw_2.setDecimals(2)
        self._ai_ladder_hw_2.setValue(0.31)
        self._ai_ladder_hw_2.setToolTip("Half-width as fraction of half-viewport — every 2nd step")
        self._ai_ladder_hw_2.valueChanged.connect(self._emit)
        _ai_ladder.row("Bar mid (2nd step)", self._ai_ladder_hw_2)

        self._ai_ladder_hw_1 = QDoubleSpinBox()
        self._ai_ladder_hw_1.setRange(0.05, 1.0); self._ai_ladder_hw_1.setDecimals(2)
        self._ai_ladder_hw_1.setValue(0.22)
        self._ai_ladder_hw_1.setToolTip("Half-width as fraction of half-viewport — every step")
        self._ai_ladder_hw_1.valueChanged.connect(self._emit)
        _ai_ladder.row("Bar short (1st step)", self._ai_ladder_hw_1)

        self._ai_ldr_color = _ColorButton()
        self._ai_ldr_color.color_changed.connect(self._emit)
        _ai_ladder.row("Color", self._ai_ldr_color)

        self._ai_ldr_width = QDoubleSpinBox()
        self._ai_ldr_width.setRange(0.5, 20.0); self._ai_ldr_width.setDecimals(1)
        self._ai_ldr_width.setValue(2.0)
        self._ai_ldr_width.valueChanged.connect(self._emit)
        _ai_ladder.row("Line width", self._ai_ldr_width)

        self._ai_font_size = QSpinBox()
        self._ai_font_size.setRange(6, 36); self._ai_font_size.setValue(14)
        self._ai_font_size.setMinimumWidth(64)
        self._ai_font_size.valueChanged.connect(self._emit)
        _ai_ladder.row("Label font size", self._ai_font_size)

        self._ai_ladder_font = QLineEdit()
        self._ai_ladder_font.setPlaceholderText("Arial  (blank = default)")
        self._ai_ladder_font.editingFinished.connect(self._emit)
        _ai_font_btn = QPushButton("…"); _ai_font_btn.setFixedWidth(28)
        _ai_font_btn.setToolTip("Choose font")
        _ai_font_btn.clicked.connect(self._pick_ai_ladder_font)
        _ai_font_row = QWidget()
        _ai_font_hl = QHBoxLayout(_ai_font_row)
        _ai_font_hl.setContentsMargins(0, 0, 0, 0); _ai_font_hl.setSpacing(4)
        _ai_font_hl.addWidget(self._ai_ladder_font); _ai_font_hl.addWidget(_ai_font_btn)
        _ai_ladder.row("Label font", _ai_font_row)

        _ai_style_row = QWidget()
        _ai_style_hl = QHBoxLayout(_ai_style_row)
        _ai_style_hl.setContentsMargins(0, 0, 0, 0); _ai_style_hl.setSpacing(12)
        self._ai_ladder_bold = QCheckBox("Bold")
        self._ai_ladder_bold.toggled.connect(self._emit)
        self._ai_ladder_italic = QCheckBox("Italic")
        self._ai_ladder_italic.toggled.connect(self._emit)
        _ai_style_hl.addWidget(self._ai_ladder_bold)
        _ai_style_hl.addWidget(self._ai_ladder_italic)
        _ai_style_hl.addStretch()
        _ai_ladder.row("Label style", _ai_style_row)

        self._ai_sec.row_widget(_ai_ladder)

        # ── Bank Arc ─────────────────────────────────────────────────────────
        _ai_arc = _SubSection("Bank Arc", collapsed=True)

        self._ai_arc_color = _ColorButton()
        self._ai_arc_color.color_changed.connect(self._emit)
        _ai_arc.row("Color", self._ai_arc_color)

        self._ai_arc_width = QDoubleSpinBox()
        self._ai_arc_width.setRange(0.5, 20.0); self._ai_arc_width.setDecimals(1)
        self._ai_arc_width.setValue(2.0)
        self._ai_arc_width.valueChanged.connect(self._emit)
        _ai_arc.row("Line width", self._ai_arc_width)

        self._ai_arc_r = QDoubleSpinBox()
        self._ai_arc_r.setRange(0.0, 4096.0); self._ai_arc_r.setDecimals(1)
        self._ai_arc_r.setSpecialValueText("(auto)")
        self._ai_arc_r.valueChanged.connect(self._emit)
        _ai_arc.row("Radius  (0=auto)", self._ai_arc_r)

        self._ai_arc_y_offset = QDoubleSpinBox()
        self._ai_arc_y_offset.setRange(-2048.0, 2048.0); self._ai_arc_y_offset.setDecimals(1)
        self._ai_arc_y_offset.setValue(0.0)
        self._ai_arc_y_offset.valueChanged.connect(self._emit)
        _ai_arc.row("Centre Y offset", self._ai_arc_y_offset)

        for _deg, _default in ((10, 6.0), (20, 6.0), (30, 10.0), (45, 6.0), (60, 6.0)):
            sb = QDoubleSpinBox()
            sb.setRange(0.0, 100.0); sb.setDecimals(1); sb.setValue(_default)
            sb.valueChanged.connect(self._emit)
            setattr(self, f"_ai_tick_{_deg}", sb)
            _ai_arc.row(f"Tick {_deg}° len", sb)

        self._ai_ticks_inward = QCheckBox("Ticks point inward")
        self._ai_ticks_inward.setChecked(True)
        self._ai_ticks_inward.stateChanged.connect(self._emit)
        _ai_arc.row("Tick direction", self._ai_ticks_inward)

        _ai_arc_bg_row = QWidget()
        _ai_arc_bg_hl = QHBoxLayout(_ai_arc_bg_row)
        _ai_arc_bg_hl.setContentsMargins(0, 0, 0, 0); _ai_arc_bg_hl.setSpacing(6)
        self._ai_show_arc_bg = QCheckBox()
        self._ai_show_arc_bg.stateChanged.connect(self._on_arc_bg_toggle)
        self._ai_show_arc_bg.stateChanged.connect(self._emit)
        self._ai_arc_bg_color = _ColorButton()
        self._ai_arc_bg_color.set_rgba([0, 100, 180, 255])
        self._ai_arc_bg_color.setEnabled(False)
        self._ai_arc_bg_color.color_changed.connect(self._emit)
        self._ai_arc_bg_inset = QDoubleSpinBox()
        self._ai_arc_bg_inset.setRange(0.0, 200.0); self._ai_arc_bg_inset.setDecimals(1)
        self._ai_arc_bg_inset.setSuffix(" px"); self._ai_arc_bg_inset.setValue(0.0)
        self._ai_arc_bg_inset.setEnabled(False)
        self._ai_arc_bg_inset.valueChanged.connect(self._emit)
        _ai_arc_bg_hl.addWidget(self._ai_show_arc_bg)
        _ai_arc_bg_hl.addWidget(self._ai_arc_bg_color, 1)
        _ai_arc_bg_hl.addWidget(QLabel("inset"))
        _ai_arc_bg_hl.addWidget(self._ai_arc_bg_inset)
        _ai_arc.row("Arc background", _ai_arc_bg_row)

        _ai_arc_vis_row = QWidget()
        _ai_arc_vis_hl  = QHBoxLayout(_ai_arc_vis_row)
        _ai_arc_vis_hl.setContentsMargins(0, 0, 0, 0)
        self._ai_show_arc_line  = QCheckBox("Arc line")
        self._ai_show_arc_line.setChecked(True)
        self._ai_show_arc_line.stateChanged.connect(self._emit)
        self._ai_show_arc_ticks = QCheckBox("Ticks")
        self._ai_show_arc_ticks.setChecked(True)
        self._ai_show_arc_ticks.stateChanged.connect(self._emit)
        _ai_arc_vis_hl.addWidget(self._ai_show_arc_line)
        _ai_arc_vis_hl.addWidget(self._ai_show_arc_ticks)
        _ai_arc_vis_hl.addStretch()
        _ai_arc.row("Show", _ai_arc_vis_row)

        # 0° reference mark
        _ai_ref_row = QWidget()
        _ai_ref_hl  = QHBoxLayout(_ai_ref_row)
        _ai_ref_hl.setContentsMargins(0, 0, 0, 0); _ai_ref_hl.setSpacing(6)
        self._ai_ref_shape = QComboBox()
        self._ai_ref_shape.addItems(["Tick", "Arrow"])
        self._ai_ref_shape.currentIndexChanged.connect(self._on_arc_ref_shape_change)
        self._ai_ref_shape.currentIndexChanged.connect(self._emit)
        self._ai_ref_height = QDoubleSpinBox()
        self._ai_ref_height.setRange(1.0, 100.0); self._ai_ref_height.setDecimals(1)
        self._ai_ref_height.setValue(10.0); self._ai_ref_height.setSuffix(" H")
        self._ai_ref_height.valueChanged.connect(self._emit)
        self._ai_ref_offset = QDoubleSpinBox()
        self._ai_ref_offset.setRange(-200.0, 200.0); self._ai_ref_offset.setDecimals(1)
        self._ai_ref_offset.setValue(0.0); self._ai_ref_offset.setSuffix(" px")
        self._ai_ref_offset.valueChanged.connect(self._emit)
        _ai_ref_hl.addWidget(self._ai_ref_shape)
        _ai_ref_hl.addWidget(self._ai_ref_height)
        _ai_ref_hl.addWidget(QLabel("offset"))
        _ai_ref_hl.addWidget(self._ai_ref_offset)
        _ai_arc.row("0° mark", _ai_ref_row)

        _ai_ref_style_row = QWidget()
        _ai_ref_style_hl  = QHBoxLayout(_ai_ref_style_row)
        _ai_ref_style_hl.setContentsMargins(0, 0, 0, 0); _ai_ref_style_hl.setSpacing(6)
        self._ai_ref_filled = QCheckBox("Filled")
        self._ai_ref_filled.setChecked(True)
        self._ai_ref_filled.setEnabled(False)
        self._ai_ref_filled.stateChanged.connect(
            lambda on: self._ai_ref_line_w.setEnabled(not bool(on)))
        self._ai_ref_filled.stateChanged.connect(self._emit)
        self._ai_ref_width = QDoubleSpinBox()
        self._ai_ref_width.setRange(1.0, 100.0); self._ai_ref_width.setDecimals(1)
        self._ai_ref_width.setValue(10.0); self._ai_ref_width.setSuffix(" W")
        self._ai_ref_width.setEnabled(False)
        self._ai_ref_width.valueChanged.connect(self._emit)
        self._ai_ref_line_w = QDoubleSpinBox()
        self._ai_ref_line_w.setRange(0.5, 20.0); self._ai_ref_line_w.setDecimals(1)
        self._ai_ref_line_w.setValue(2.0); self._ai_ref_line_w.setSuffix(" px")
        self._ai_ref_line_w.setEnabled(False)
        self._ai_ref_line_w.valueChanged.connect(self._emit)
        _ai_ref_style_hl.addWidget(self._ai_ref_filled)
        _ai_ref_style_hl.addWidget(QLabel("W:"))
        _ai_ref_style_hl.addWidget(self._ai_ref_width)
        _ai_ref_style_hl.addWidget(QLabel("outline:"))
        _ai_ref_style_hl.addWidget(self._ai_ref_line_w)
        _ai_arc.row("Arrow style", _ai_ref_style_row)

        self._ai_sec.row_widget(_ai_arc)

        # ── Roll Pointer & Reference ──────────────────────────────────────────
        _ai_ptr = _SubSection("Roll Pointer & Reference", collapsed=True)

        self._ai_ptr_color = _ColorButton()
        self._ai_ptr_color.color_changed.connect(self._emit)
        _ai_ptr.row("Pointer color", self._ai_ptr_color)

        _ai_ptr_size_row = QWidget()
        _ai_ptr_size_hl  = QHBoxLayout(_ai_ptr_size_row)
        _ai_ptr_size_hl.setContentsMargins(0, 0, 0, 0); _ai_ptr_size_hl.setSpacing(6)
        self._ai_ptr_height = QDoubleSpinBox()
        self._ai_ptr_height.setRange(1.0, 200.0); self._ai_ptr_height.setDecimals(1)
        self._ai_ptr_height.setValue(12.0); self._ai_ptr_height.setSuffix(" H")
        self._ai_ptr_height.valueChanged.connect(self._emit)
        self._ai_ptr_width = QDoubleSpinBox()
        self._ai_ptr_width.setRange(1.0, 200.0); self._ai_ptr_width.setDecimals(1)
        self._ai_ptr_width.setValue(12.0); self._ai_ptr_width.setSuffix(" W")
        self._ai_ptr_width.valueChanged.connect(self._emit)
        _ai_ptr_size_hl.addWidget(self._ai_ptr_height)
        _ai_ptr_size_hl.addWidget(self._ai_ptr_width)
        _ai_ptr.row("Height / Width px", _ai_ptr_size_row)

        _ai_ptr_style_row = QWidget()
        _ai_ptr_style_hl  = QHBoxLayout(_ai_ptr_style_row)
        _ai_ptr_style_hl.setContentsMargins(0, 0, 0, 0); _ai_ptr_style_hl.setSpacing(6)
        self._ai_ptr_filled = QCheckBox("Filled")
        self._ai_ptr_filled.setChecked(True)
        self._ai_ptr_filled.stateChanged.connect(
            lambda on: self._ai_ptr_line_w.setEnabled(not bool(on)))
        self._ai_ptr_filled.stateChanged.connect(self._emit)
        self._ai_ptr_inward = QCheckBox("Inward")
        self._ai_ptr_inward.setChecked(True)
        self._ai_ptr_inward.stateChanged.connect(self._emit)
        self._ai_ptr_line_w = QDoubleSpinBox()
        self._ai_ptr_line_w.setRange(0.5, 20.0); self._ai_ptr_line_w.setDecimals(1)
        self._ai_ptr_line_w.setValue(2.0); self._ai_ptr_line_w.setSuffix(" px")
        self._ai_ptr_line_w.setEnabled(False)
        self._ai_ptr_line_w.valueChanged.connect(self._emit)
        _ai_ptr_style_hl.addWidget(self._ai_ptr_filled)
        _ai_ptr_style_hl.addWidget(self._ai_ptr_inward)
        _ai_ptr_style_hl.addWidget(QLabel("outline:"))
        _ai_ptr_style_hl.addWidget(self._ai_ptr_line_w)
        _ai_ptr.row("Style / Direction", _ai_ptr_style_row)

        self._ai_ptr_y_off = QDoubleSpinBox()
        self._ai_ptr_y_off.setRange(-200.0, 200.0); self._ai_ptr_y_off.setDecimals(1)
        self._ai_ptr_y_off.setValue(0.0); self._ai_ptr_y_off.setSuffix(" px")
        self._ai_ptr_y_off.valueChanged.connect(self._emit)
        _ai_ptr.row("Y offset from arc", self._ai_ptr_y_off)

        self._ai_sec.row_widget(_ai_ptr)

        # ── Slip Indicator ───────────────────────────────────────────────────
        _ai_slip = _SubSection("Slip Indicator", collapsed=True)

        self._ai_show_slip = QCheckBox("Show slip indicator")
        self._ai_show_slip.setChecked(False)
        self._ai_show_slip.stateChanged.connect(self._on_slip_toggle)
        self._ai_show_slip.stateChanged.connect(self._emit)
        _ai_slip.row("Show", self._ai_show_slip)

        self._ai_slip_dr = QLineEdit()
        self._ai_slip_dr.setPlaceholderText("slip/skid dataref")
        self._ai_slip_dr.setText("sim/cockpit2/gauges/indicators/slip_deg")
        self._ai_slip_dr.editingFinished.connect(self._emit)
        _ai_slip.row("Slip dataref", self._dr_field(self._ai_slip_dr))

        self._ai_slip_color = _ColorButton()
        self._ai_slip_color.set_rgba([255, 255, 255, 255])
        self._ai_slip_color.color_changed.connect(self._emit)
        _ai_slip.row("Color", self._ai_slip_color)

        _ai_slip_sz_row = QWidget(); _ai_slip_sz_hl = QHBoxLayout(_ai_slip_sz_row)
        _ai_slip_sz_hl.setContentsMargins(0, 0, 0, 0); _ai_slip_sz_hl.setSpacing(4)
        self._ai_slip_w = QDoubleSpinBox()
        self._ai_slip_w.setRange(1.0, 200.0); self._ai_slip_w.setDecimals(1)
        self._ai_slip_w.setValue(20.0); self._ai_slip_w.setSuffix(" W")
        self._ai_slip_w.valueChanged.connect(self._emit)
        self._ai_slip_h = QDoubleSpinBox()
        self._ai_slip_h.setRange(1.0, 200.0); self._ai_slip_h.setDecimals(1)
        self._ai_slip_h.setValue(8.0); self._ai_slip_h.setSuffix(" H")
        self._ai_slip_h.valueChanged.connect(self._emit)
        _ai_slip_sz_hl.addWidget(self._ai_slip_w)
        _ai_slip_sz_hl.addWidget(self._ai_slip_h)
        _ai_slip.row("Width / Height px", _ai_slip_sz_row)

        _ai_slip_style_row = QWidget(); _ai_slip_style_hl = QHBoxLayout(_ai_slip_style_row)
        _ai_slip_style_hl.setContentsMargins(0, 0, 0, 0); _ai_slip_style_hl.setSpacing(4)
        self._ai_slip_filled = QCheckBox("Filled")
        self._ai_slip_filled.setChecked(True)
        self._ai_slip_filled.stateChanged.connect(self._on_slip_style_toggle)
        self._ai_slip_filled.stateChanged.connect(self._emit)
        self._ai_slip_line_w = QDoubleSpinBox()
        self._ai_slip_line_w.setRange(0.5, 20.0); self._ai_slip_line_w.setDecimals(1)
        self._ai_slip_line_w.setValue(2.0); self._ai_slip_line_w.setSuffix(" px")
        self._ai_slip_line_w.setEnabled(False)
        self._ai_slip_line_w.valueChanged.connect(self._emit)
        _ai_slip_style_hl.addWidget(self._ai_slip_filled)
        _ai_slip_style_hl.addWidget(QLabel("outline:"))
        _ai_slip_style_hl.addWidget(self._ai_slip_line_w)
        _ai_slip.row("Style", _ai_slip_style_row)

        self._ai_slip_offset = QDoubleSpinBox()
        self._ai_slip_offset.setRange(-200.0, 200.0); self._ai_slip_offset.setDecimals(1)
        self._ai_slip_offset.setValue(0.0); self._ai_slip_offset.setSuffix(" px")
        self._ai_slip_offset.valueChanged.connect(self._emit)
        _ai_slip.row("Arc offset", self._ai_slip_offset)

        self._ai_slip_scale = QDoubleSpinBox()
        self._ai_slip_scale.setRange(0.1, 50.0); self._ai_slip_scale.setDecimals(2)
        self._ai_slip_scale.setValue(2.0); self._ai_slip_scale.setSuffix(" px/unit")
        self._ai_slip_scale.setToolTip("Lateral displacement in pixels per dataref unit")
        self._ai_slip_scale.valueChanged.connect(self._emit)
        _ai_slip.row("Scale", self._ai_slip_scale)

        self._ai_slip_controls = [
            self._ai_slip_dr, self._ai_slip_color,
            self._ai_slip_w, self._ai_slip_h,
            self._ai_slip_filled, self._ai_slip_line_w,
            self._ai_slip_offset, self._ai_slip_scale,
        ]
        for w in self._ai_slip_controls:
            w.setEnabled(False)

        self._ai_sec.row_widget(_ai_slip)

        # ── Aircraft Reference ────────────────────────────────────────────────
        _ai_ref = _SubSection("Aircraft Reference", collapsed=True)

        self._ai_show_ref = QCheckBox("Show aircraft reference")
        self._ai_show_ref.setChecked(True)
        self._ai_show_ref.stateChanged.connect(self._on_ref_toggle)
        self._ai_show_ref.stateChanged.connect(self._emit)
        _ai_ref.row("Show", self._ai_show_ref)

        _ai_ref.row("", QLabel("── Centre bug ──────────────────────"))
        self._ai_bug_pts = QLineEdit()
        self._ai_bug_pts.setPlaceholderText("x1,y1  x2,y2  …  (empty = legacy dot)")
        self._ai_bug_pts.editingFinished.connect(self._emit)
        _ai_ref.row("Points", self._ai_bug_pts)

        _ai_bug_style_row = QWidget(); _ai_bug_style_hl = QHBoxLayout(_ai_bug_style_row)
        _ai_bug_style_hl.setContentsMargins(0, 0, 0, 0); _ai_bug_style_hl.setSpacing(4)
        self._ai_bug_filled = QCheckBox("Filled")
        self._ai_bug_filled.setChecked(True)
        self._ai_bug_filled.stateChanged.connect(self._emit)
        self._ai_bug_fill_c = _ColorButton()
        self._ai_bug_fill_c.set_rgba([0, 0, 0, 255])
        self._ai_bug_fill_c.color_changed.connect(self._emit)
        self._ai_bug_outline_c = _ColorButton()
        self._ai_bug_outline_c.set_rgba([255, 255, 255, 255])
        self._ai_bug_outline_c.color_changed.connect(self._emit)
        self._ai_bug_outline_w = QDoubleSpinBox()
        self._ai_bug_outline_w.setRange(0.5, 20.0); self._ai_bug_outline_w.setDecimals(1)
        self._ai_bug_outline_w.setValue(2.0); self._ai_bug_outline_w.setSuffix(" px")
        self._ai_bug_outline_w.valueChanged.connect(self._emit)
        _ai_bug_style_hl.addWidget(self._ai_bug_filled)
        _ai_bug_style_hl.addWidget(QLabel("fill:"))
        _ai_bug_style_hl.addWidget(self._ai_bug_fill_c)
        _ai_bug_style_hl.addWidget(QLabel("outline:"))
        _ai_bug_style_hl.addWidget(self._ai_bug_outline_c)
        _ai_bug_style_hl.addWidget(self._ai_bug_outline_w)
        _ai_ref.row("Style", _ai_bug_style_row)

        _ai_ref.row("", QLabel("── Left wing (right auto-mirrored) ──"))
        self._ai_wing_pts = QLineEdit()
        self._ai_wing_pts.setPlaceholderText("x1,y1  x2,y2  …  (empty = legacy stubs)")
        self._ai_wing_pts.editingFinished.connect(self._emit)
        _ai_ref.row("Points", self._ai_wing_pts)

        _ai_wing_style_row = QWidget(); _ai_wing_style_hl = QHBoxLayout(_ai_wing_style_row)
        _ai_wing_style_hl.setContentsMargins(0, 0, 0, 0); _ai_wing_style_hl.setSpacing(4)
        self._ai_wing_filled = QCheckBox("Filled")
        self._ai_wing_filled.setChecked(True)
        self._ai_wing_filled.stateChanged.connect(self._emit)
        self._ai_wing_fill_c = _ColorButton()
        self._ai_wing_fill_c.set_rgba([0, 0, 0, 255])
        self._ai_wing_fill_c.color_changed.connect(self._emit)
        self._ai_wing_outline_c = _ColorButton()
        self._ai_wing_outline_c.set_rgba([255, 255, 255, 255])
        self._ai_wing_outline_c.color_changed.connect(self._emit)
        self._ai_wing_outline_w = QDoubleSpinBox()
        self._ai_wing_outline_w.setRange(0.5, 20.0); self._ai_wing_outline_w.setDecimals(1)
        self._ai_wing_outline_w.setValue(2.0); self._ai_wing_outline_w.setSuffix(" px")
        self._ai_wing_outline_w.valueChanged.connect(self._emit)
        _ai_wing_style_hl.addWidget(self._ai_wing_filled)
        _ai_wing_style_hl.addWidget(QLabel("fill:"))
        _ai_wing_style_hl.addWidget(self._ai_wing_fill_c)
        _ai_wing_style_hl.addWidget(QLabel("outline:"))
        _ai_wing_style_hl.addWidget(self._ai_wing_outline_c)
        _ai_wing_style_hl.addWidget(self._ai_wing_outline_w)
        _ai_ref.row("Style", _ai_wing_style_row)

        self._ai_ref_controls = [
            self._ai_bug_pts, self._ai_bug_filled, self._ai_bug_fill_c,
            self._ai_bug_outline_c, self._ai_bug_outline_w,
            self._ai_wing_pts, self._ai_wing_filled, self._ai_wing_fill_c,
            self._ai_wing_outline_c, self._ai_wing_outline_w,
        ]

        self._ai_sec.row_widget(_ai_ref)

        # ── Flight Director ──────────────────────────────────────────────────
        _ai_fd = _SubSection("Flight Director", collapsed=True)

        # Horizontal bar (pitch command)
        self._ai_fd_h_show = QCheckBox("Show horizontal bar  (pitch command)")
        self._ai_fd_h_show.setChecked(False)
        self._ai_fd_h_show.stateChanged.connect(self._on_fd_h_toggle)
        self._ai_fd_h_show.stateChanged.connect(self._emit)
        _ai_fd.row("H bar", self._ai_fd_h_show)

        self._ai_fd_h_dr = QLineEdit()
        self._ai_fd_h_dr.setPlaceholderText("pitch FD dataref")
        self._ai_fd_h_dr.editingFinished.connect(self._emit)
        _ai_fd.row("H deflect dataref", self._dr_field(self._ai_fd_h_dr))

        self._ai_fd_h_fn = _NoScrollComboBox()
        self._ai_fd_h_fn.addItems(_VALUE_FUNCS)
        self._ai_fd_h_fn.currentTextChanged.connect(self._emit)
        _ai_fd.row("H convert fn", self._ai_fd_h_fn)

        self._ai_fd_h_vis_dr = QLineEdit()
        self._ai_fd_h_vis_dr.setPlaceholderText("visibility dataref  (blank = always visible)")
        self._ai_fd_h_vis_dr.editingFinished.connect(self._emit)
        _ai_fd.row("H vis dataref", self._dr_field(self._ai_fd_h_vis_dr))

        self._ai_fd_h_vis_mode = _NoScrollComboBox()
        self._ai_fd_h_vis_mode.addItems(["Named predicate", "Compare value"])
        self._ai_fd_h_vis_mode.currentIndexChanged.connect(self._on_ai_fd_h_vis_mode_changed)
        self._ai_fd_h_vis_mode.currentIndexChanged.connect(self._emit)
        _ai_fd.row("H vis mode", self._ai_fd_h_vis_mode)

        self._ai_fd_h_vis_stack = QStackedWidget()
        _fd_h_pred_page = QWidget()
        _fd_h_pred_form = QFormLayout(_fd_h_pred_page)
        _fd_h_pred_form.setContentsMargins(0, 2, 0, 2)
        _fd_h_pred_form.setHorizontalSpacing(8)
        _fd_h_pred_form.setVerticalSpacing(4)
        self._ai_fd_h_vis_pred = _NoScrollComboBox(); self._ai_fd_h_vis_pred.addItems(_PREDICATES)
        self._ai_fd_h_vis_pred.currentTextChanged.connect(self._emit)
        _fd_h_pred_form.addRow("Predicate", self._ai_fd_h_vis_pred)

        _fd_h_cmp_page = QWidget()
        _fd_h_cmp_form = QFormLayout(_fd_h_cmp_page)
        _fd_h_cmp_form.setContentsMargins(0, 2, 0, 2)
        _fd_h_cmp_form.setHorizontalSpacing(8)
        _fd_h_cmp_form.setVerticalSpacing(4)
        self._ai_fd_h_vis_op = _NoScrollComboBox()
        self._ai_fd_h_vis_op.addItems(["<", "<=", "==", "!=", ">", ">="])
        self._ai_fd_h_vis_op.currentTextChanged.connect(self._emit)
        _fd_h_cmp_form.addRow("Operator", self._ai_fd_h_vis_op)
        self._ai_fd_h_vis_value = QDoubleSpinBox()
        self._ai_fd_h_vis_value.setRange(-1_000_000_000.0, 1_000_000_000.0)
        self._ai_fd_h_vis_value.setDecimals(3)
        self._ai_fd_h_vis_value.valueChanged.connect(self._emit)
        _fd_h_cmp_form.addRow("Value", self._ai_fd_h_vis_value)

        self._ai_fd_h_vis_stack.addWidget(_fd_h_pred_page)
        self._ai_fd_h_vis_stack.addWidget(_fd_h_cmp_page)
        _ai_fd.row_widget(self._ai_fd_h_vis_stack)

        _fd_h_style_row = QWidget(); _fd_h_style_hl = QHBoxLayout(_fd_h_style_row)
        _fd_h_style_hl.setContentsMargins(0, 0, 0, 0); _fd_h_style_hl.setSpacing(4)
        self._ai_fd_h_color = _ColorButton()
        self._ai_fd_h_color.set_rgba([255, 200, 0, 255])
        self._ai_fd_h_color.color_changed.connect(self._emit)
        self._ai_fd_h_len = QDoubleSpinBox()
        self._ai_fd_h_len.setRange(10.0, 4096.0); self._ai_fd_h_len.setDecimals(0)
        self._ai_fd_h_len.setValue(200.0); self._ai_fd_h_len.setSuffix(" L")
        self._ai_fd_h_len.valueChanged.connect(self._emit)
        self._ai_fd_h_width = QDoubleSpinBox()
        self._ai_fd_h_width.setRange(0.5, 20.0); self._ai_fd_h_width.setDecimals(1)
        self._ai_fd_h_width.setValue(3.0); self._ai_fd_h_width.setSuffix(" W")
        self._ai_fd_h_width.valueChanged.connect(self._emit)
        _fd_h_style_hl.addWidget(self._ai_fd_h_color)
        _fd_h_style_hl.addWidget(self._ai_fd_h_len)
        _fd_h_style_hl.addWidget(self._ai_fd_h_width)
        _ai_fd.row("H color / size", _fd_h_style_row)

        self._ai_fd_h_scale = QDoubleSpinBox()
        self._ai_fd_h_scale.setRange(0.1, 200.0); self._ai_fd_h_scale.setDecimals(2)
        self._ai_fd_h_scale.setValue(8.0); self._ai_fd_h_scale.setSuffix(" px/unit")
        self._ai_fd_h_scale.setToolTip("Pixels of vertical deflection per dataref unit")
        self._ai_fd_h_scale.valueChanged.connect(self._emit)
        _ai_fd.row("H scale", self._ai_fd_h_scale)

        self._ai_fd_h_controls = [
            self._ai_fd_h_dr, self._ai_fd_h_fn,
            self._ai_fd_h_vis_dr, self._ai_fd_h_vis_mode, self._ai_fd_h_vis_stack,
            self._ai_fd_h_color, self._ai_fd_h_len, self._ai_fd_h_width,
            self._ai_fd_h_scale,
        ]
        for w in self._ai_fd_h_controls:
            w.setEnabled(False)

        # Vertical bar (roll command)
        self._ai_fd_v_show = QCheckBox("Show vertical bar  (roll command)")
        self._ai_fd_v_show.setChecked(False)
        self._ai_fd_v_show.stateChanged.connect(self._on_fd_v_toggle)
        self._ai_fd_v_show.stateChanged.connect(self._emit)
        _ai_fd.row("V bar", self._ai_fd_v_show)

        self._ai_fd_v_dr = QLineEdit()
        self._ai_fd_v_dr.setPlaceholderText("roll FD dataref")
        self._ai_fd_v_dr.editingFinished.connect(self._emit)
        _ai_fd.row("V deflect dataref", self._dr_field(self._ai_fd_v_dr))

        self._ai_fd_v_fn = _NoScrollComboBox()
        self._ai_fd_v_fn.addItems(_VALUE_FUNCS)
        self._ai_fd_v_fn.currentTextChanged.connect(self._emit)
        _ai_fd.row("V convert fn", self._ai_fd_v_fn)

        self._ai_fd_v_vis_dr = QLineEdit()
        self._ai_fd_v_vis_dr.setPlaceholderText("visibility dataref  (blank = always visible)")
        self._ai_fd_v_vis_dr.editingFinished.connect(self._emit)
        _ai_fd.row("V vis dataref", self._dr_field(self._ai_fd_v_vis_dr))

        self._ai_fd_v_vis_mode = _NoScrollComboBox()
        self._ai_fd_v_vis_mode.addItems(["Named predicate", "Compare value"])
        self._ai_fd_v_vis_mode.currentIndexChanged.connect(self._on_ai_fd_v_vis_mode_changed)
        self._ai_fd_v_vis_mode.currentIndexChanged.connect(self._emit)
        _ai_fd.row("V vis mode", self._ai_fd_v_vis_mode)

        self._ai_fd_v_vis_stack = QStackedWidget()
        _fd_v_pred_page = QWidget()
        _fd_v_pred_form = QFormLayout(_fd_v_pred_page)
        _fd_v_pred_form.setContentsMargins(0, 2, 0, 2)
        _fd_v_pred_form.setHorizontalSpacing(8)
        _fd_v_pred_form.setVerticalSpacing(4)
        self._ai_fd_v_vis_pred = _NoScrollComboBox(); self._ai_fd_v_vis_pred.addItems(_PREDICATES)
        self._ai_fd_v_vis_pred.currentTextChanged.connect(self._emit)
        _fd_v_pred_form.addRow("Predicate", self._ai_fd_v_vis_pred)

        _fd_v_cmp_page = QWidget()
        _fd_v_cmp_form = QFormLayout(_fd_v_cmp_page)
        _fd_v_cmp_form.setContentsMargins(0, 2, 0, 2)
        _fd_v_cmp_form.setHorizontalSpacing(8)
        _fd_v_cmp_form.setVerticalSpacing(4)
        self._ai_fd_v_vis_op = _NoScrollComboBox()
        self._ai_fd_v_vis_op.addItems(["<", "<=", "==", "!=", ">", ">="])
        self._ai_fd_v_vis_op.currentTextChanged.connect(self._emit)
        _fd_v_cmp_form.addRow("Operator", self._ai_fd_v_vis_op)
        self._ai_fd_v_vis_value = QDoubleSpinBox()
        self._ai_fd_v_vis_value.setRange(-1_000_000_000.0, 1_000_000_000.0)
        self._ai_fd_v_vis_value.setDecimals(3)
        self._ai_fd_v_vis_value.valueChanged.connect(self._emit)
        _fd_v_cmp_form.addRow("Value", self._ai_fd_v_vis_value)

        self._ai_fd_v_vis_stack.addWidget(_fd_v_pred_page)
        self._ai_fd_v_vis_stack.addWidget(_fd_v_cmp_page)
        _ai_fd.row_widget(self._ai_fd_v_vis_stack)

        _fd_v_style_row = QWidget(); _fd_v_style_hl = QHBoxLayout(_fd_v_style_row)
        _fd_v_style_hl.setContentsMargins(0, 0, 0, 0); _fd_v_style_hl.setSpacing(4)
        self._ai_fd_v_color = _ColorButton()
        self._ai_fd_v_color.set_rgba([255, 200, 0, 255])
        self._ai_fd_v_color.color_changed.connect(self._emit)
        self._ai_fd_v_len = QDoubleSpinBox()
        self._ai_fd_v_len.setRange(10.0, 4096.0); self._ai_fd_v_len.setDecimals(0)
        self._ai_fd_v_len.setValue(200.0); self._ai_fd_v_len.setSuffix(" L")
        self._ai_fd_v_len.valueChanged.connect(self._emit)
        self._ai_fd_v_width = QDoubleSpinBox()
        self._ai_fd_v_width.setRange(0.5, 20.0); self._ai_fd_v_width.setDecimals(1)
        self._ai_fd_v_width.setValue(3.0); self._ai_fd_v_width.setSuffix(" W")
        self._ai_fd_v_width.valueChanged.connect(self._emit)
        _fd_v_style_hl.addWidget(self._ai_fd_v_color)
        _fd_v_style_hl.addWidget(self._ai_fd_v_len)
        _fd_v_style_hl.addWidget(self._ai_fd_v_width)
        _ai_fd.row("V color / size", _fd_v_style_row)

        self._ai_fd_v_scale = QDoubleSpinBox()
        self._ai_fd_v_scale.setRange(0.1, 200.0); self._ai_fd_v_scale.setDecimals(2)
        self._ai_fd_v_scale.setValue(4.0); self._ai_fd_v_scale.setSuffix(" px/unit")
        self._ai_fd_v_scale.setToolTip("Pixels of horizontal deflection per dataref unit")
        self._ai_fd_v_scale.valueChanged.connect(self._emit)
        _ai_fd.row("V scale", self._ai_fd_v_scale)

        self._ai_fd_v_controls = [
            self._ai_fd_v_dr, self._ai_fd_v_fn,
            self._ai_fd_v_vis_dr, self._ai_fd_v_vis_mode, self._ai_fd_v_vis_stack,
            self._ai_fd_v_color, self._ai_fd_v_len, self._ai_fd_v_width,
            self._ai_fd_v_scale,
        ]
        for w in self._ai_fd_v_controls:
            w.setEnabled(False)

        self._ai_sec.row_widget(_ai_fd)

        self._vbox.addWidget(self._ai_sec)

    def _mk_needlegauge_sec(self):
        self._ng_sec = _Section("Needle Gauge")
        self._ng_sec.setVisible(False)

        self._ng_cx = _sb(); self._ng_cy = _sb()
        for w in (self._ng_cx, self._ng_cy):
            w.valueChanged.connect(self._emit)
        y_label = "Center X  /  Y top" if is_y_down() else "Center X  /  Y"
        self._ng_sec.row_pair(y_label, self._ng_cx, self._ng_cy)

        self._ng_grad_type = _NoScrollComboBox()
        self._ng_grad_type.addItems(["circular", "linear"])
        self._ng_grad_type.currentIndexChanged.connect(self._on_ng_grad_type_changed)
        self._ng_grad_type.currentIndexChanged.connect(self._emit)
        self._ng_sec.row("Gradation type", self._ng_grad_type)

        self._ng_grad_stack = QStackedWidget()

        # ── Circular page (unchanged from the original CircularGauge) ──────
        circ_page = QWidget()
        cform = QFormLayout(circ_page)
        cform.setContentsMargins(0, 2, 0, 2)
        cform.setHorizontalSpacing(8); cform.setVerticalSpacing(6)

        self._ng_radius = QDoubleSpinBox()
        self._ng_radius.setRange(0.0, 4096.0); self._ng_radius.setDecimals(1)
        self._ng_radius.setValue(100.0)
        self._ng_radius.valueChanged.connect(self._emit)
        cform.addRow("Radius px", self._ng_radius)

        self._ng_arc_start = QDoubleSpinBox()
        self._ng_arc_start.setRange(-360.0, 360.0); self._ng_arc_start.setDecimals(1)
        self._ng_arc_start.setValue(-220.0)
        self._ng_arc_start.valueChanged.connect(self._emit)
        cform.addRow("Arc start °", self._ng_arc_start)

        self._ng_arc_end = QDoubleSpinBox()
        self._ng_arc_end.setRange(-360.0, 360.0); self._ng_arc_end.setDecimals(1)
        self._ng_arc_end.setValue(40.0)
        self._ng_arc_end.valueChanged.connect(self._emit)
        cform.addRow("Arc end °", self._ng_arc_end)

        _ng_angle_hint = QLabel("Angles: 0° = right, CCW positive.")
        _ng_angle_hint.setStyleSheet("color: #999; font-size: 10px;")
        cform.addRow(_ng_angle_hint)

        self._ng_arc_color = _ColorButton()
        self._ng_arc_color.color_changed.connect(self._emit)
        cform.addRow("Arc color", self._ng_arc_color)

        self._ng_arc_width = QDoubleSpinBox()
        self._ng_arc_width.setRange(0.5, 50.0); self._ng_arc_width.setDecimals(1)
        self._ng_arc_width.setValue(2.0)
        self._ng_arc_width.valueChanged.connect(self._emit)
        cform.addRow("Arc width px", self._ng_arc_width)

        self._ng_segments = QSpinBox()
        self._ng_segments.setRange(8, 256); self._ng_segments.setValue(64)
        self._ng_segments.valueChanged.connect(self._emit)
        cform.addRow("Arc segments", self._ng_segments)

        # ── Linear page (new) ───────────────────────────────────────────────
        lin_page = QWidget()
        lform = QFormLayout(lin_page)
        lform.setContentsMargins(0, 2, 0, 2)
        lform.setHorizontalSpacing(8); lform.setVerticalSpacing(6)

        self._ng_orientation = _NoScrollComboBox()
        self._ng_orientation.addItems(["vertical", "horizontal"])
        self._ng_orientation.currentTextChanged.connect(self._emit)
        lform.addRow("Orientation", self._ng_orientation)

        self._ng_spacing_table = _TableEditor("Value", "Offset px", use_spinboxes=True, decimals=2)
        self._ng_spacing_table.setToolTip(
            "Value -> pixel offset from centre, interpolated piecewise-\n"
            "linearly between rows. Not uniform spacing — hand-tune this\n"
            "to match a real gauge's scale (e.g. a VSI tape where spacing\n"
            "compresses at higher values)."
        )
        self._ng_spacing_table.changed.connect(self._emit)
        lform.addRow("Spacing table", self._ng_spacing_table)

        self._ng_tick_side = _NoScrollComboBox()
        self._ng_tick_side.addItems(["left", "right", "top", "bottom"])
        self._ng_tick_side.setToolTip(
            "left/right apply when Orientation is vertical;\n"
            "top/bottom apply when Orientation is horizontal."
        )
        self._ng_tick_side.currentTextChanged.connect(self._emit)
        lform.addRow("Tick side", self._ng_tick_side)

        self._ng_tick_color = _ColorButton()
        self._ng_tick_color.color_changed.connect(self._emit)
        lform.addRow("Tick color", self._ng_tick_color)

        self._ng_ticks = _TableEditor("Interval", "Length px", "Width px",
                                      use_spinboxes=True, decimals=2,
                                      value_range=(0.0, 99999.0))
        self._ng_ticks.setToolTip(
            "One row per tick group, e.g. a minor-tick row every 1 unit\n"
            "plus a thicker major-tick row every 2 units. Positioned via\n"
            "the Spacing table above, not a fixed pixels-per-unit."
        )
        self._ng_ticks.changed.connect(self._emit)
        lform.addRow("Ticks", self._ng_ticks)

        self._ng_label_interval = QDoubleSpinBox()
        self._ng_label_interval.setRange(0.0, 1000.0); self._ng_label_interval.setDecimals(2)
        self._ng_label_interval.setValue(1.0)
        self._ng_label_interval.setSpecialValueText("(no labels)")
        self._ng_label_interval.valueChanged.connect(self._emit)
        lform.addRow("Label interval", self._ng_label_interval)

        self._ng_label_format = QLineEdit()
        self._ng_label_format.setPlaceholderText("{:.0f}")
        self._ng_label_format.setToolTip(_FORMAT_SPEC_TOOLTIP)
        self._ng_label_format.editingFinished.connect(self._emit)
        lform.addRow("Label format", self._ng_label_format)

        self._ng_label_font_size = QDoubleSpinBox()
        self._ng_label_font_size.setRange(4.0, 120.0); self._ng_label_font_size.setDecimals(1)
        self._ng_label_font_size.setValue(14.0)
        self._ng_label_font_size.valueChanged.connect(self._emit)
        lform.addRow("Label font size", self._ng_label_font_size)

        self._ng_label_color = _ColorButton()
        self._ng_label_color.color_changed.connect(self._emit)
        lform.addRow("Label color", self._ng_label_color)

        self._ng_label_offset = QDoubleSpinBox()
        self._ng_label_offset.setRange(0.0, 500.0); self._ng_label_offset.setDecimals(1)
        self._ng_label_offset.setValue(8.0)
        self._ng_label_offset.valueChanged.connect(self._emit)
        lform.addRow("Label offset px", self._ng_label_offset)

        self._ng_grad_stack.addWidget(circ_page)   # index 0
        self._ng_grad_stack.addWidget(lin_page)    # index 1
        self._ng_sec.row_widget(self._ng_grad_stack)

        # ── Needle (shared by both gradation types) ─────────────────────────
        self._ng_needle_len = QDoubleSpinBox()
        self._ng_needle_len.setRange(0.0, 4096.0); self._ng_needle_len.setDecimals(1)
        self._ng_needle_len.setValue(80.0)
        self._ng_needle_len.valueChanged.connect(self._emit)
        self._ng_sec.row("Needle length px", self._ng_needle_len)

        self._ng_needle_width = QDoubleSpinBox()
        self._ng_needle_width.setRange(0.5, 50.0); self._ng_needle_width.setDecimals(1)
        self._ng_needle_width.setValue(2.0)
        self._ng_needle_width.valueChanged.connect(self._emit)
        self._ng_sec.row("Needle width px", self._ng_needle_width)

        self._ng_needle_color = _ColorButton()
        self._ng_needle_color.color_changed.connect(self._emit)
        self._ng_sec.row("Needle color", self._ng_needle_color)

        # Static angle or dataref-driven — reuses _BandEndpointWidget
        self._ng_needle_angle = _BandEndpointWidget("Needle angle °")
        self._ng_needle_angle.changed.connect(self._emit)
        self._ng_sec.row_widget(self._ng_needle_angle)

        self._vbox.addWidget(self._ng_sec)

    def _on_ng_grad_type_changed(self, idx: int) -> None:
        self._ng_grad_stack.setCurrentIndex(idx)

    def _mk_compassrose_sec(self):
        self._cr_sec = _Section("Compass Rose")
        self._cr_sec.setVisible(False)

        # ── Layout ───────────────────────────────────────────────────────────
        _cr_layout = _SubSection("Layout", collapsed=False)

        self._cr_cx = _sb(); self._cr_cy = _sb()
        for w in (self._cr_cx, self._cr_cy):
            w.valueChanged.connect(self._emit)
        y_label = "Center X  /  Y top" if is_y_down() else "Center X  /  Y"
        _cr_layout.row_pair(y_label, self._cr_cx, self._cr_cy)

        self._cr_radius = QDoubleSpinBox()
        self._cr_radius.setRange(1.0, 4096.0); self._cr_radius.setDecimals(1)
        self._cr_radius.setValue(150.0)
        self._cr_radius.valueChanged.connect(self._emit)
        _cr_layout.row("Radius px", self._cr_radius)

        self._cr_sec.row_widget(_cr_layout)

        # ── Circle ───────────────────────────────────────────────────────────
        _cr_circle = _SubSection("Circle", collapsed=True)

        _cr_bg_row = QWidget()
        _cr_bg_hl = QHBoxLayout(_cr_bg_row)
        _cr_bg_hl.setContentsMargins(0, 0, 0, 0); _cr_bg_hl.setSpacing(6)
        self._cr_bg_chk = QCheckBox()
        self._cr_bg_chk.toggled.connect(lambda on: self._cr_bg_color.setEnabled(on))
        self._cr_bg_chk.toggled.connect(self._emit)
        self._cr_bg_color = _ColorButton()
        self._cr_bg_color.setEnabled(False)
        self._cr_bg_color.color_changed.connect(self._emit)
        _cr_bg_hl.addWidget(self._cr_bg_chk)
        _cr_bg_hl.addWidget(self._cr_bg_color, 1)
        _cr_circle.row("Background", _cr_bg_row)

        self._cr_line_chk = QCheckBox("Show circle line")
        self._cr_line_chk.setChecked(True)
        self._cr_line_chk.toggled.connect(self._on_cr_line_toggled)
        self._cr_line_chk.toggled.connect(self._emit)
        _cr_circle.row_widget(self._cr_line_chk)

        _cr_line_row = QWidget()
        _cr_line_hl = QHBoxLayout(_cr_line_row)
        _cr_line_hl.setContentsMargins(0, 0, 0, 0); _cr_line_hl.setSpacing(4)
        self._cr_line_color = _ColorButton()
        self._cr_line_color.color_changed.connect(self._emit)
        self._cr_line_width = QDoubleSpinBox()
        self._cr_line_width.setRange(0.5, 50.0); self._cr_line_width.setDecimals(1)
        self._cr_line_width.setValue(2.0)
        self._cr_line_width.valueChanged.connect(self._emit)
        _cr_line_hl.addWidget(self._cr_line_color)
        _cr_line_hl.addWidget(self._cr_line_width)
        _cr_circle.row("Line color / width", _cr_line_row)

        self._cr_segments = QSpinBox()
        self._cr_segments.setRange(8, 360); self._cr_segments.setValue(128)
        self._cr_segments.valueChanged.connect(self._emit)
        _cr_circle.row("Circle segments", self._cr_segments)

        self._cr_sec.row_widget(_cr_circle)

        # ── 5° Ticks ─────────────────────────────────────────────────────────
        _cr_tick5 = _SubSection("5° Ticks", collapsed=True)

        self._cr_t5_len = QDoubleSpinBox()
        self._cr_t5_len.setRange(0.0, 200.0); self._cr_t5_len.setDecimals(1)
        self._cr_t5_len.setValue(8.0)
        self._cr_t5_len.valueChanged.connect(self._emit)
        _cr_tick5.row("Length px", self._cr_t5_len)
        self._cr_t5_color = _ColorButton()
        self._cr_t5_color.color_changed.connect(self._emit)
        _cr_tick5.row("Color", self._cr_t5_color)
        self._cr_t5_width = QDoubleSpinBox()
        self._cr_t5_width.setRange(0.5, 50.0); self._cr_t5_width.setDecimals(1)
        self._cr_t5_width.setValue(1.0)
        self._cr_t5_width.valueChanged.connect(self._emit)
        _cr_tick5.row("Width px", self._cr_t5_width)
        self._cr_t5_pos = _NoScrollComboBox()
        self._cr_t5_pos.addItems(["outside", "inside"])
        self._cr_t5_pos.currentTextChanged.connect(self._emit)
        _cr_tick5.row("Position", self._cr_t5_pos)

        self._cr_sec.row_widget(_cr_tick5)

        # ── 10° Ticks ────────────────────────────────────────────────────────
        _cr_tick10 = _SubSection("10° Ticks", collapsed=True)

        self._cr_t10_len = QDoubleSpinBox()
        self._cr_t10_len.setRange(0.0, 200.0); self._cr_t10_len.setDecimals(1)
        self._cr_t10_len.setValue(16.0)
        self._cr_t10_len.valueChanged.connect(self._emit)
        _cr_tick10.row("Length px", self._cr_t10_len)
        self._cr_t10_color = _ColorButton()
        self._cr_t10_color.color_changed.connect(self._emit)
        _cr_tick10.row("Color", self._cr_t10_color)
        self._cr_t10_width = QDoubleSpinBox()
        self._cr_t10_width.setRange(0.5, 50.0); self._cr_t10_width.setDecimals(1)
        self._cr_t10_width.setValue(2.0)
        self._cr_t10_width.valueChanged.connect(self._emit)
        _cr_tick10.row("Width px", self._cr_t10_width)
        self._cr_t10_pos = _NoScrollComboBox()
        self._cr_t10_pos.addItems(["outside", "inside"])
        self._cr_t10_pos.currentTextChanged.connect(self._emit)
        _cr_tick10.row("Position", self._cr_t10_pos)

        self._cr_sec.row_widget(_cr_tick10)

        # ── Heading Labels ───────────────────────────────────────────────────
        _cr_labels = _SubSection("Heading Labels", collapsed=True)

        self._cr_label_interval = QDoubleSpinBox()
        self._cr_label_interval.setRange(1.0, 180.0); self._cr_label_interval.setDecimals(0)
        self._cr_label_interval.setValue(30.0)
        self._cr_label_interval.valueChanged.connect(self._emit)
        _cr_labels.row("Interval °", self._cr_label_interval)
        self._cr_label_offset = QDoubleSpinBox()
        self._cr_label_offset.setRange(-200.0, 200.0); self._cr_label_offset.setDecimals(1)
        self._cr_label_offset.setValue(20.0)
        self._cr_label_offset.valueChanged.connect(self._emit)
        _cr_labels.row("Offset px (from arc)", self._cr_label_offset)
        self._cr_label_pos = _NoScrollComboBox()
        self._cr_label_pos.addItems(["inside", "outside"])
        self._cr_label_pos.currentTextChanged.connect(self._emit)
        _cr_labels.row("Position", self._cr_label_pos)
        self._cr_label_format = QLineEdit()
        self._cr_label_format.setPlaceholderText("{:02.0f}  (applied to heading/10)")
        self._cr_label_format.setToolTip(_FORMAT_SPEC_TOOLTIP)
        self._cr_label_format.editingFinished.connect(self._emit)
        _cr_labels.row("Format", self._cr_label_format)
        self._cr_label_font_size = QDoubleSpinBox()
        self._cr_label_font_size.setRange(4.0, 120.0); self._cr_label_font_size.setDecimals(1)
        self._cr_label_font_size.setValue(14.0)
        self._cr_label_font_size.valueChanged.connect(self._emit)
        _cr_labels.row("Font size", self._cr_label_font_size)
        self._cr_label_emph_interval = QDoubleSpinBox()
        self._cr_label_emph_interval.setRange(0.0, 180.0); self._cr_label_emph_interval.setDecimals(0)
        self._cr_label_emph_interval.setSpecialValueText("(none)")
        self._cr_label_emph_interval.setToolTip(
            "Headings on this coarser interval (must be a multiple of Interval °\n"
            "above) use a different font size — e.g. label every 10° but a bigger\n"
            "size every 30°. (none) disables the split; all labels use Font size."
        )
        self._cr_label_emph_interval.valueChanged.connect(self._emit)
        _cr_labels.row("Emphasize interval °", self._cr_label_emph_interval)
        self._cr_label_emph_size = QDoubleSpinBox()
        self._cr_label_emph_size.setRange(4.0, 120.0); self._cr_label_emph_size.setDecimals(1)
        self._cr_label_emph_size.setValue(20.0)
        self._cr_label_emph_size.setToolTip(
            "Font size for headings on the Emphasize interval. Only used when\n"
            "Emphasize interval ° is set."
        )
        self._cr_label_emph_size.valueChanged.connect(self._emit)
        _cr_labels.row("Emphasize font size", self._cr_label_emph_size)
        self._cr_label_font = QLineEdit()
        self._cr_label_font.setPlaceholderText("Arial  (blank = default)")
        self._cr_label_font.editingFinished.connect(self._emit)
        _cr_font_btn = QPushButton("…")
        _cr_font_btn.setFixedWidth(28)
        _cr_font_btn.setToolTip("Choose font")
        _cr_font_btn.clicked.connect(self._pick_cr_label_font)
        _cr_font_row = QWidget()
        _cr_font_hl = QHBoxLayout(_cr_font_row)
        _cr_font_hl.setContentsMargins(0, 0, 0, 0); _cr_font_hl.setSpacing(4)
        _cr_font_hl.addWidget(self._cr_label_font)
        _cr_font_hl.addWidget(_cr_font_btn)
        _cr_labels.row("Font", _cr_font_row)
        _cr_style_row = QWidget()
        _cr_style_hl = QHBoxLayout(_cr_style_row)
        _cr_style_hl.setContentsMargins(0, 0, 0, 0); _cr_style_hl.setSpacing(12)
        self._cr_label_bold = QCheckBox("Bold")
        self._cr_label_bold.toggled.connect(self._emit)
        self._cr_label_italic = QCheckBox("Italic")
        self._cr_label_italic.toggled.connect(self._emit)
        _cr_style_hl.addWidget(self._cr_label_bold)
        _cr_style_hl.addWidget(self._cr_label_italic)
        _cr_style_hl.addStretch()
        _cr_labels.row("Label style", _cr_style_row)
        self._cr_label_color = _ColorButton()
        self._cr_label_color.color_changed.connect(self._emit)
        _cr_labels.row("Label color", self._cr_label_color)
        self._cr_label_anchor_y = _NoScrollComboBox()
        self._cr_label_anchor_y.addItems(["baseline", "center", "top", "bottom"])
        self._cr_label_anchor_y.setToolTip(
            "Which part of the label glyph sits at the offset point (radius ±\n"
            "Offset px), in the label's own radial (rotated) orientation."
        )
        self._cr_label_anchor_y.currentTextChanged.connect(self._emit)
        _cr_labels.row("Label anchor", self._cr_label_anchor_y)

        self._cr_sec.row_widget(_cr_labels)

        # ── Heading Rotation ─────────────────────────────────────────────────
        _cr_heading = _SubSection("Heading Rotation", collapsed=True)

        self._cr_heading_dr = QLineEdit()
        self._cr_heading_dr.setPlaceholderText("heading dataref  (blank = no rotation)")
        self._cr_heading_dr.editingFinished.connect(self._emit)
        _cr_heading.row("Heading dataref", self._dr_field(self._cr_heading_dr))
        self._cr_heading_fn = _NoScrollComboBox()
        self._cr_heading_fn.addItems(_VALUE_FUNCS)
        self._cr_heading_fn.currentTextChanged.connect(self._emit)
        _cr_heading.row("Convert fn", self._cr_heading_fn)

        self._cr_sec.row_widget(_cr_heading)

        # ── Track Indicator ──────────────────────────────────────────────────
        _cr_track = _SubSection("Track Indicator", collapsed=True)

        self._cr_track_dr = QLineEdit()
        self._cr_track_dr.setPlaceholderText("track dataref  (blank = no track line)")
        self._cr_track_dr.editingFinished.connect(self._emit)
        _cr_track.row("Track dataref", self._dr_field(self._cr_track_dr))
        self._cr_track_fn = _NoScrollComboBox()
        self._cr_track_fn.addItems(_VALUE_FUNCS)
        self._cr_track_fn.currentTextChanged.connect(self._emit)
        _cr_track.row("Convert fn", self._cr_track_fn)

        _cr_track_style_row = QWidget()
        _cr_track_style_hl = QHBoxLayout(_cr_track_style_row)
        _cr_track_style_hl.setContentsMargins(0, 0, 0, 0); _cr_track_style_hl.setSpacing(4)
        self._cr_track_color = _ColorButton()
        self._cr_track_color.color_changed.connect(self._emit)
        self._cr_track_width = QDoubleSpinBox()
        self._cr_track_width.setRange(0.5, 50.0); self._cr_track_width.setDecimals(1)
        self._cr_track_width.setValue(2.0)
        self._cr_track_width.valueChanged.connect(self._emit)
        _cr_track_style_hl.addWidget(self._cr_track_color)
        _cr_track_style_hl.addWidget(self._cr_track_width)
        _cr_track.row("Color / width", _cr_track_style_row)
        _cr_track.row_widget(_sep_label("Shared by the line and its perpendicular tick"))

        self._cr_track_start = QDoubleSpinBox()
        self._cr_track_start.setRange(-4096.0, 4096.0); self._cr_track_start.setDecimals(1)
        self._cr_track_start.setValue(0.0)
        self._cr_track_start.setToolTip("Distance from the rose centre where the line starts, in px.")
        self._cr_track_start.valueChanged.connect(self._emit)
        _cr_track.row("Start px", self._cr_track_start)

        self._cr_track_end = QDoubleSpinBox()
        self._cr_track_end.setRange(-4096.0, 4096.0); self._cr_track_end.setDecimals(1)
        self._cr_track_end.setValue(150.0)
        self._cr_track_end.setToolTip("Distance from the rose centre where the line ends, in px.")
        self._cr_track_end.valueChanged.connect(self._emit)
        _cr_track.row("End px", self._cr_track_end)

        self._cr_track_tick_pos = QDoubleSpinBox()
        self._cr_track_tick_pos.setRange(0.0, 4096.0); self._cr_track_tick_pos.setDecimals(1)
        self._cr_track_tick_pos.setSpecialValueText("(none)")
        self._cr_track_tick_pos.setToolTip(
            "Distance from the rose centre, along the line, where a tick\n"
            "perpendicular to the line is drawn. (none) draws no tick."
        )
        self._cr_track_tick_pos.valueChanged.connect(self._emit)
        _cr_track.row("Tick position px", self._cr_track_tick_pos)

        self._cr_track_tick_len = QDoubleSpinBox()
        self._cr_track_tick_len.setRange(1.0, 200.0); self._cr_track_tick_len.setDecimals(1)
        self._cr_track_tick_len.setValue(20.0)
        self._cr_track_tick_len.setToolTip(
            "Full length of the perpendicular tick, split evenly across the line.\n"
            "Only used when Tick position px is set."
        )
        self._cr_track_tick_len.valueChanged.connect(self._emit)
        _cr_track.row("Tick length px", self._cr_track_tick_len)

        self._cr_sec.row_widget(_cr_track)

        # ── Heading Bug ──────────────────────────────────────────────────────
        _cr_bug = _SubSection("Heading Bug", collapsed=True)

        self._cr_bug_dr = QLineEdit()
        self._cr_bug_dr.setPlaceholderText("bug heading dataref  (blank = no bug)")
        self._cr_bug_dr.editingFinished.connect(self._emit)
        _cr_bug.row("Bug dataref", self._dr_field(self._cr_bug_dr))
        self._cr_bug_fn = _NoScrollComboBox()
        self._cr_bug_fn.addItems(_VALUE_FUNCS)
        self._cr_bug_fn.currentTextChanged.connect(self._emit)
        _cr_bug.row("Convert fn", self._cr_bug_fn)

        self._cr_bug_radius = QDoubleSpinBox()
        self._cr_bug_radius.setRange(-4096.0, 4096.0); self._cr_bug_radius.setDecimals(1)
        self._cr_bug_radius.setValue(150.0)
        self._cr_bug_radius.setToolTip(
            "Distance from the rose centre where the bug's local origin sits\n"
            "(usually the rose radius, so the bug rides on the arc)."
        )
        self._cr_bug_radius.valueChanged.connect(self._emit)
        _cr_bug.row("Radius px", self._cr_bug_radius)

        self._cr_bug_pts = _PointsTableEditor()
        self._cr_bug_pts.changed.connect(self._emit)
        self._cr_bug_pts.setToolTip(
            "Relative to the bug's own origin, in its unrotated local space\n"
            "where +Y points radially outward (away from the rose centre)."
        )
        _cr_bug.row("Points (relative to origin)", self._cr_bug_pts)

        self._cr_bug_color = _ColorButton()
        self._cr_bug_color.color_changed.connect(self._emit)
        _cr_bug.row("Fill color", self._cr_bug_color)

        self._cr_bug_filled = QCheckBox("Filled")
        self._cr_bug_filled.setChecked(True)
        self._cr_bug_filled.toggled.connect(self._on_cr_bug_filled_toggled)
        self._cr_bug_filled.toggled.connect(self._emit)
        _cr_bug.row_widget(self._cr_bug_filled)

        self._cr_bug_width = QDoubleSpinBox()
        self._cr_bug_width.setRange(0.5, 50.0); self._cr_bug_width.setDecimals(1)
        self._cr_bug_width.setValue(2.0)
        self._cr_bug_width.setEnabled(False)  # shown only when not filled
        self._cr_bug_width.valueChanged.connect(self._emit)
        _cr_bug.row("Outline width", self._cr_bug_width)

        self._cr_bug_outline_chk = QCheckBox("Add outline")
        self._cr_bug_outline_chk.toggled.connect(self._on_cr_bug_outline_toggled)
        self._cr_bug_outline_chk.toggled.connect(self._emit)
        _cr_bug.row_widget(self._cr_bug_outline_chk)

        self._cr_bug_outline_color = _ColorButton()
        self._cr_bug_outline_color.set_rgba((255, 255, 255, 255))
        self._cr_bug_outline_color.setEnabled(False)
        self._cr_bug_outline_color.color_changed.connect(self._emit)
        _cr_bug.row("Outline color", self._cr_bug_outline_color)

        self._cr_bug_outline_width = QDoubleSpinBox()
        self._cr_bug_outline_width.setRange(0.5, 50.0); self._cr_bug_outline_width.setDecimals(1)
        self._cr_bug_outline_width.setValue(1.0)
        self._cr_bug_outline_width.setEnabled(False)
        self._cr_bug_outline_width.valueChanged.connect(self._emit)
        _cr_bug.row("Outline width ", self._cr_bug_outline_width)

        self._cr_sec.row_widget(_cr_bug)

        # ── Heading Marker ───────────────────────────────────────────────────
        _cr_marker = _SubSection("Heading Marker", collapsed=True)
        _cr_marker.row_widget(_sep_label(
            "Fixed lubber-line/index at top-dead-centre — no dataref; the\n"
            "rose rotates underneath it."
        ))

        self._cr_marker_radius = QDoubleSpinBox()
        self._cr_marker_radius.setRange(-4096.0, 4096.0); self._cr_marker_radius.setDecimals(1)
        self._cr_marker_radius.setValue(150.0)
        self._cr_marker_radius.setToolTip(
            "Distance from the rose centre where the marker's local origin sits\n"
            "(usually the rose radius, so it sits right at the arc)."
        )
        self._cr_marker_radius.valueChanged.connect(self._emit)
        _cr_marker.row("Radius px", self._cr_marker_radius)

        self._cr_marker_pts = _PointsTableEditor()
        self._cr_marker_pts.changed.connect(self._emit)
        self._cr_marker_pts.setToolTip(
            "Relative to the marker's own origin, in plain screen space\n"
            "(no rotation applied — the marker never turns)."
        )
        _cr_marker.row("Points (relative to origin)", self._cr_marker_pts)

        self._cr_marker_color = _ColorButton()
        self._cr_marker_color.color_changed.connect(self._emit)
        _cr_marker.row("Fill color", self._cr_marker_color)

        self._cr_marker_filled = QCheckBox("Filled")
        self._cr_marker_filled.setChecked(True)
        self._cr_marker_filled.toggled.connect(self._on_cr_marker_filled_toggled)
        self._cr_marker_filled.toggled.connect(self._emit)
        _cr_marker.row_widget(self._cr_marker_filled)

        self._cr_marker_width = QDoubleSpinBox()
        self._cr_marker_width.setRange(0.5, 50.0); self._cr_marker_width.setDecimals(1)
        self._cr_marker_width.setValue(2.0)
        self._cr_marker_width.setEnabled(False)  # shown only when not filled
        self._cr_marker_width.valueChanged.connect(self._emit)
        _cr_marker.row("Outline width", self._cr_marker_width)

        self._cr_marker_outline_chk = QCheckBox("Add outline")
        self._cr_marker_outline_chk.toggled.connect(self._on_cr_marker_outline_toggled)
        self._cr_marker_outline_chk.toggled.connect(self._emit)
        _cr_marker.row_widget(self._cr_marker_outline_chk)

        self._cr_marker_outline_color = _ColorButton()
        self._cr_marker_outline_color.set_rgba((255, 255, 255, 255))
        self._cr_marker_outline_color.setEnabled(False)
        self._cr_marker_outline_color.color_changed.connect(self._emit)
        _cr_marker.row("Outline color", self._cr_marker_outline_color)

        self._cr_marker_outline_width = QDoubleSpinBox()
        self._cr_marker_outline_width.setRange(0.5, 50.0); self._cr_marker_outline_width.setDecimals(1)
        self._cr_marker_outline_width.setValue(1.0)
        self._cr_marker_outline_width.setEnabled(False)
        self._cr_marker_outline_width.valueChanged.connect(self._emit)
        _cr_marker.row("Outline width ", self._cr_marker_outline_width)

        self._cr_sec.row_widget(_cr_marker)

        self._vbox.addWidget(self._cr_sec)

    def _on_cr_marker_filled_toggled(self, filled: bool) -> None:
        self._cr_marker_width.setEnabled(not filled)
        self._cr_marker_outline_chk.setVisible(filled)
        self._cr_marker_outline_color.setVisible(filled)
        self._cr_marker_outline_width.setVisible(filled)
        if not filled:
            self._cr_marker_outline_chk.blockSignals(True)
            self._cr_marker_outline_chk.setChecked(False)
            self._cr_marker_outline_chk.blockSignals(False)

    def _on_cr_marker_outline_toggled(self, on: bool) -> None:
        self._cr_marker_outline_color.setEnabled(on)
        self._cr_marker_outline_width.setEnabled(on)

    def _on_cr_bug_filled_toggled(self, filled: bool) -> None:
        self._cr_bug_width.setEnabled(not filled)
        # Outline overlay only makes sense when filled; unfilled IS an outline
        self._cr_bug_outline_chk.setVisible(filled)
        self._cr_bug_outline_color.setVisible(filled)
        self._cr_bug_outline_width.setVisible(filled)
        if not filled:
            self._cr_bug_outline_chk.blockSignals(True)
            self._cr_bug_outline_chk.setChecked(False)
            self._cr_bug_outline_chk.blockSignals(False)

    def _on_cr_bug_outline_toggled(self, on: bool) -> None:
        self._cr_bug_outline_color.setEnabled(on)
        self._cr_bug_outline_width.setEnabled(on)

    def _on_cr_line_toggled(self, on: bool) -> None:
        self._cr_line_color.setEnabled(on)
        self._cr_line_width.setEnabled(on)

    def _pick_cr_label_font(self) -> None:
        from PySide6.QtGui import QFont
        from gauge_core.font_utils import strip_style_suffix
        current_name = self._cr_label_font.text().strip() or "Arial"
        current_size = int(self._cr_label_font_size.value())
        initial = QFont(current_name, current_size)
        initial.setBold(self._cr_label_bold.isChecked())
        initial.setItalic(self._cr_label_italic.isChecked())
        ok, font = QFontDialog.getFont(initial, self, "Choose label font")
        if ok:
            self._cr_label_font.setText(strip_style_suffix(font.family()))
            self._cr_label_font_size.setValue(float(font.pointSize()))
            self._cr_label_bold.setChecked(font.bold())
            self._cr_label_italic.setChecked(font.italic())
            self._emit()

    def _mk_rotary_encoder_sec(self):
        self._re_sec = _Section("Rotary Encoder")
        self._re_sec.setVisible(False)

        hint = QLabel(
            "Left-half tap = CCW · Right-half tap = CW\n"
            "Drag up = CW · Drag down = CCW · Scroll wheel = ±1 step"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #999; font-size: 10px;")
        self._re_sec.row_widget(hint)

        self._re_w = _sb(1, 4096); self._re_h = _sb(1, 4096)
        self._re_w.setValue(60); self._re_h.setValue(60)
        for w in (self._re_w, self._re_h):
            w.valueChanged.connect(self._emit)
        self._re_sec.row_pair("Width  ×  Height", self._re_w, self._re_h)

        self._re_cmd_cw = QLineEdit()
        self._re_cmd_cw.setPlaceholderText("sim/autopilot/heading_up")
        self._re_cmd_cw.editingFinished.connect(self._emit)
        self._re_sec.row("Command CW  (→ / ↑)", self._re_cmd_cw)

        self._re_cmd_ccw = QLineEdit()
        self._re_cmd_ccw.setPlaceholderText("sim/autopilot/heading_down")
        self._re_cmd_ccw.editingFinished.connect(self._emit)
        self._re_sec.row("Command CCW (← / ↓)", self._re_cmd_ccw)

        self._re_drag_px = QDoubleSpinBox()
        self._re_drag_px.setRange(0.5, 200.0); self._re_drag_px.setDecimals(1)
        self._re_drag_px.setValue(5.0)
        self._re_drag_px.setToolTip("Pixels of drag before one command step fires.")
        self._re_drag_px.valueChanged.connect(self._emit)
        self._re_sec.row("Drag px / step", self._re_drag_px)

        self._re_show_zones = QCheckBox("Show touch zones at runtime  (yellow = CCW · green = CW)")
        self._re_show_zones.toggled.connect(self._emit)
        self._re_sec.row_widget(self._re_show_zones)

        self._re_hit_padding = QDoubleSpinBox()
        self._re_hit_padding.setRange(0.0, 10.0)
        self._re_hit_padding.setDecimals(1)
        self._re_hit_padding.setSingleStep(0.1)
        self._re_hit_padding.setValue(0.0)
        self._re_hit_padding.setSpecialValueText("panel default (×1.5)")
        self._re_hit_padding.setToolTip(
            "Hit zone size multiplier for this knob.\n"
            "0 = use the panel's hit_padding_multiplier (default ×1.5).\n"
            "e.g. ×2.0 → touch area twice the knob size."
        )
        self._re_hit_padding.valueChanged.connect(self._emit)
        self._re_sec.row("Hit zone multiplier", self._re_hit_padding)

        # ── Background texture (static encoder body) ──────────────────────
        self._re_sec.row_widget(_sep_label("Background texture (optional — encoder body)"))

        self._re_bg_tex = QLineEdit()
        self._re_bg_tex.setPlaceholderText("assets/encoder_bg.png")
        self._re_bg_tex.editingFinished.connect(self._emit)
        self._re_bg_edit_btn = QPushButton("Edit"); self._re_bg_edit_btn.setFixedWidth(38)
        self._re_bg_edit_btn.setToolTip("Open texture editor for background")
        self._re_bg_edit_btn.clicked.connect(lambda: self._open_tex_editor(
            self._re_bg_tex,
            self._re_bg_ox, self._re_bg_oy,
            self._re_bg_cw, self._re_bg_ch,
        ))
        self._re_bg_tex.textChanged.connect(
            lambda t: self._re_bg_edit_btn.setEnabled(bool(t.strip()))
        )
        self._re_bg_edit_btn.setEnabled(False)
        re_bg_row = QWidget(); re_bgl = QHBoxLayout(re_bg_row)
        re_bgl.setContentsMargins(0, 0, 0, 0); re_bgl.setSpacing(4)
        re_bgl.addWidget(self._re_bg_edit_btn)
        re_bgl.addWidget(self._re_bg_tex)
        re_bg_btn = QPushButton("…"); re_bg_btn.setFixedWidth(26)
        re_bg_btn.clicked.connect(lambda: self._browse_tex(self._re_bg_tex))
        re_bgl.addWidget(re_bg_btn)
        self._re_sec.row("Texture", re_bg_row)

        self._re_bg_ox = _sb(0, 8192); self._re_bg_oy = _sb(0, 8192)
        for w in (self._re_bg_ox, self._re_bg_oy):
            w.valueChanged.connect(self._emit)
        self._re_sec.row_pair("Origin X  /  Y", self._re_bg_ox, self._re_bg_oy)

        self._re_bg_cw = _sb(1, 4096); self._re_bg_ch = _sb(1, 4096)
        self._re_bg_cw.setValue(120); self._re_bg_ch.setValue(120)
        for w in (self._re_bg_cw, self._re_bg_ch):
            w.valueChanged.connect(self._emit)
        self._re_sec.row_pair("Cliprect W  ×  H", self._re_bg_cw, self._re_bg_ch)

        # ── Face texture (rotating knob surface) ──────────────────────────
        self._re_sec.row_widget(_sep_label("Face texture (optional — rotating knob)"))

        self._re_face_tex = QLineEdit()
        self._re_face_tex.setPlaceholderText("assets/encoder_face.png")
        self._re_face_tex.editingFinished.connect(self._emit)
        self._re_face_edit_btn = QPushButton("Edit"); self._re_face_edit_btn.setFixedWidth(38)
        self._re_face_edit_btn.setToolTip("Open texture editor for face")
        self._re_face_edit_btn.clicked.connect(lambda: self._open_tex_editor(
            self._re_face_tex,
            self._re_face_ox, self._re_face_oy,
            self._re_face_cw, self._re_face_ch,
        ))
        self._re_face_tex.textChanged.connect(
            lambda t: self._re_face_edit_btn.setEnabled(bool(t.strip()))
        )
        self._re_face_edit_btn.setEnabled(False)
        re_face_row = QWidget(); re_facel = QHBoxLayout(re_face_row)
        re_facel.setContentsMargins(0, 0, 0, 0); re_facel.setSpacing(4)
        re_facel.addWidget(self._re_face_edit_btn)
        re_facel.addWidget(self._re_face_tex)
        re_face_btn = QPushButton("…"); re_face_btn.setFixedWidth(26)
        re_face_btn.clicked.connect(lambda: self._browse_tex(self._re_face_tex))
        re_facel.addWidget(re_face_btn)
        self._re_sec.row("Texture", re_face_row)

        self._re_face_ox = _sb(0, 8192); self._re_face_oy = _sb(0, 8192)
        for w in (self._re_face_ox, self._re_face_oy):
            w.valueChanged.connect(self._emit)
        self._re_sec.row_pair("Origin X  /  Y", self._re_face_ox, self._re_face_oy)

        self._re_face_cw = _sb(1, 4096); self._re_face_ch = _sb(1, 4096)
        self._re_face_cw.setValue(80); self._re_face_ch.setValue(80)
        for w in (self._re_face_cw, self._re_face_ch):
            w.valueChanged.connect(self._emit)
        self._re_sec.row_pair("Cliprect W  ×  H", self._re_face_cw, self._re_face_ch)

        self._re_face_sw = _sb(1, 4096); self._re_face_sh = _sb(1, 4096)
        self._re_face_sw.setValue(60); self._re_face_sh.setValue(60)
        for w in (self._re_face_sw, self._re_face_sh):
            w.valueChanged.connect(self._emit)
        self._re_sec.row_pair("Display W  ×  H", self._re_face_sw, self._re_face_sh)

        self._re_face_offx = _sb(-2048, 2048); self._re_face_offy = _sb(-2048, 2048)
        for w in (self._re_face_offx, self._re_face_offy):
            w.valueChanged.connect(self._emit)
        self._re_sec.row_pair("Centre offset X  /  Y", self._re_face_offx, self._re_face_offy)

        self._re_face_rcx = _sb(-2048, 2048); self._re_face_rcy = _sb(-2048, 2048)
        for w in (self._re_face_rcx, self._re_face_rcy):
            w.valueChanged.connect(self._emit)
        self._re_sec.row_pair("Rot centre X  /  Y", self._re_face_rcx, self._re_face_rcy)

        self._re_face_dr = QLineEdit()
        self._re_face_dr.setPlaceholderText("dataref driving face rotation")
        self._re_face_dr.editingFinished.connect(self._emit)
        self._re_sec.row("Rotation dataref", self._dr_field(self._re_face_dr))

        self._re_face_fn = _NoScrollComboBox()
        self._re_face_fn.addItems(_VALUE_FUNCS)
        self._re_face_fn.currentTextChanged.connect(self._emit)
        self._re_sec.row("Convert fn", self._re_face_fn)

        self._re_face_tbl = _TableEditor("Input value", "Angle °")
        self._re_face_tbl.changed.connect(self._emit)
        self._re_sec.row("Rotation table", self._re_face_tbl)

        self._vbox.addWidget(self._re_sec)

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
        _vp_xy_box = QWidget()
        _vp_xy_hl = QHBoxLayout(_vp_xy_box)
        _vp_xy_hl.setContentsMargins(0, 0, 0, 0); _vp_xy_hl.setSpacing(4)
        _vp_xy_hl.addWidget(self._vp_x); _vp_xy_hl.addWidget(self._vp_y)
        self._vp_sec._form.addRow(y_label, _vp_xy_box)
        self._vp_xy_row = _vp_xy_box

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

        self._vis_mode = _NoScrollComboBox()
        self._vis_mode.addItems(["Named predicate", "Compare value"])
        self._vis_mode.currentIndexChanged.connect(self._on_vis_mode_changed)
        self._vis_mode.currentIndexChanged.connect(self._emit)
        self._vis_sec.row("Mode", self._vis_mode)

        self._vis_stack = QStackedWidget()

        # Page 0 — named predicate (original mechanism: a registered convert
        # function used as a bool-returning predicate).
        pred_page = QWidget()
        pred_form = QFormLayout(pred_page)
        pred_form.setContentsMargins(0, 2, 0, 2)
        pred_form.setHorizontalSpacing(8)
        pred_form.setVerticalSpacing(4)
        self._vis_pred = _NoScrollComboBox(); self._vis_pred.addItems(_PREDICATES)
        self._vis_pred.currentTextChanged.connect(self._emit)
        pred_form.addRow("Predicate", self._vis_pred)

        # Page 1 — inline threshold comparison (dataref <op> value), no
        # convert.py function needed.
        cmp_page = QWidget()
        cmp_form = QFormLayout(cmp_page)
        cmp_form.setContentsMargins(0, 2, 0, 2)
        cmp_form.setHorizontalSpacing(8)
        cmp_form.setVerticalSpacing(4)
        self._vis_op = _NoScrollComboBox()
        self._vis_op.addItems(["<", "<=", "==", "!=", ">", ">="])
        self._vis_op.currentTextChanged.connect(self._emit)
        cmp_form.addRow("Operator", self._vis_op)
        self._vis_value = QDoubleSpinBox()
        self._vis_value.setRange(-1_000_000_000.0, 1_000_000_000.0)
        self._vis_value.setDecimals(3)
        self._vis_value.valueChanged.connect(self._emit)
        cmp_form.addRow("Value", self._vis_value)

        self._vis_stack.addWidget(pred_page)
        self._vis_stack.addWidget(cmp_page)
        self._vis_sec.row_widget(self._vis_stack)

        self._vbox.addWidget(self._vis_sec)

    def _on_vis_mode_changed(self, idx: int) -> None:
        self._vis_stack.setCurrentIndex(idx)

    def _on_ai_fd_h_vis_mode_changed(self, idx: int) -> None:
        self._ai_fd_h_vis_stack.setCurrentIndex(idx)

    def _on_ai_fd_v_vis_mode_changed(self, idx: int) -> None:
        self._ai_fd_v_vis_stack.setCurrentIndex(idx)

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
            "stride_x", "stride_y", "smooth", "pixels_per_unit", "shift_direction", "animation",
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
            "origin", "points", "filled",
            # shared across vector types
            "color", "width",
            "outline_color", "outline_width",
            # VectorTape (all form-managed)
            "pixels_per_unit", "wrap", "tick_side", "tick_color", "bg_color", "ticks", "labels", "bands", "bugs",
            # Text
            "text", "dataref", "text_format", "convert_function",
            "font_name", "font_size", "bold", "italic", "anchor_x", "anchor_y", "font_file",
            # Vector
            "direction", "length", "cap", "cap_width", "cap_height", "cap_filled", "hide_if_less_than_cap",
            # AttitudeIndicator
            "pitch_dataref", "roll_dataref", "pixels_per_degree",
            "sky_color", "ground_color", "horizon_color", "horizon_width",
            "ladder_color", "ladder_width", "label_font_size",
            "bank_arc_color", "bank_arc_width", "bank_arc_radius",
            "bank_arc_y_offset", "show_arc_line", "show_arc_ticks",
            "arc_ref_shape", "arc_ref_height", "arc_ref_width",
            "arc_ref_filled", "arc_ref_line_width", "arc_ref_offset",
            "bank_tick_10", "bank_tick_20", "bank_tick_30", "bank_tick_45", "bank_tick_60",
            "ticks_inward", "show_arc_bg", "arc_bg_color", "arc_bg_inset",
            "roll_pointer_color", "roll_pointer_size",
            "roll_pointer_height", "roll_pointer_width",
            "roll_pointer_filled", "roll_pointer_inward", "roll_pointer_line_width",
            "roll_pointer_y_offset",
            "ladder_step", "ladder_hw_1", "ladder_hw_2", "ladder_hw_4",
            "ladder_font_name", "ladder_bold", "ladder_italic", "smoothing", "show_reference",
            "corner_radius", "corner_bg_color",
            "centre_bug_points", "centre_bug_filled", "centre_bug_fill_color",
            "centre_bug_outline_color", "centre_bug_outline_width",
            "wing_points", "wing_filled", "wing_fill_color",
            "wing_outline_color", "wing_outline_width",
            "show_slip", "slip_dataref", "slip_color",
            "slip_width", "slip_height", "slip_filled", "slip_line_width",
            "slip_offset", "slip_scale", "slip_convert_function",
            "show_fd_h_bar", "fd_pitch_dataref", "fd_pitch_convert_function",
            "fd_h_visibility",
            "fd_h_color", "fd_h_length", "fd_h_width", "fd_h_scale",
            "show_fd_v_bar", "fd_roll_dataref", "fd_roll_convert_function",
            "fd_v_visibility",
            "fd_v_color", "fd_v_length", "fd_v_width", "fd_v_scale",
            # RotaryEncoder
            "command_cw", "command_ccw", "drag_px_per_step", "show_touch_zones", "hit_padding",
            "background_texture", "background_origin", "background_cliprect",
            "face_texture", "face_origin", "face_cliprect", "face_size",
            "face_offset", "face_rotation_center", "face_rotation",
            # NeedleGauge
            "gradation_type", "arc_color", "arc_width", "needle_length", "needle_width",
            "needle_color", "needle_angle", "linear",
            # VectorCompassRose
            "background_color", "show_line", "line_color", "line_width",
            "tick5_length", "tick5_color", "tick5_width", "tick5_position",
            "tick10_length", "tick10_color", "tick10_width", "tick10_position",
            "label_interval", "label_offset", "label_position",
            "label_font", "label_bold", "label_italic", "label_format", "label_color",
            "label_emphasize_interval", "label_emphasize_font_size", "label_anchor_y",
            "heading", "track", "heading_bug", "heading_marker",
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

        # VectorTape: "Position" means viewport origin, not the YAML position field
        if ct == "VectorTape":
            vp = comp.get("viewport", [0, 0, 100, 200])
            self._px.setValue(int(vp[0]))
            vy_bot, vh_val = int(vp[1]), int(vp[3])
            self._py.setValue((self._ref_height - vy_bot - vh_val) if is_y_down() else vy_bot)

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
        self._ss_ppu.setValue(float(comp.get("pixels_per_unit", 0.0)))
        sd = str(comp.get("shift_direction", "right")).lower()
        self._ss_shift_dir.setCurrentIndex(0 if sd != "left" else 1)

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
        poly_orig = comp.get("origin", [0, 0])
        self._poly_ox.setValue(int(poly_orig[0]))
        self._poly_oy.setValue(flip_y(int(poly_orig[1]), self._ref_height))
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

        # Vector
        self._vec_dir.load(comp.get("direction", 0.0))
        self._vec_len.load(comp.get("length", 50.0))
        self._vec_color.set_rgba(comp.get("color"))
        self._vec_width.setValue(float(comp.get("width", 1.0)))
        _cap = comp.get("cap", "none")
        _cap_idx = self._vec_cap.findText(_cap)
        self._vec_cap.setCurrentIndex(_cap_idx if _cap_idx >= 0 else 0)
        _cw = float(comp.get("cap_width", 10.0))
        self._vec_cap_width.setValue(_cw)
        self._vec_cap_width.setEnabled(_cap != "none")
        self._vec_cap_height.setValue(float(comp.get("cap_height", _cw / 2.0)))
        self._vec_cap_height.setEnabled(_cap == "triangle")
        self._vec_cap_filled.setChecked(bool(comp.get("cap_filled", True)))
        self._vec_cap_filled.setEnabled(_cap == "triangle")
        self._vec_hide_if_short.setChecked(bool(comp.get("hide_if_less_than_cap", False)))
        self._vec_hide_if_short.setEnabled(_cap == "triangle")

        # VectorTape
        self._vt_axis.setCurrentIndex(0 if str(comp.get("scroll_axis", "y")) == "y" else 1)
        self._vt_ppu.setValue(float(comp.get("pixels_per_unit", 5.0)))
        wrap_val = comp.get("wrap")
        self._vt_wrap.setValue(float(wrap_val) if wrap_val is not None else 0.0)
        ts = str(comp.get("tick_side", "left"))
        self._vt_tick_side.setCurrentIndex(max(self._vt_tick_side.findText(ts), 0))
        self._vt_tick_color.set_rgba(comp.get("tick_color"))
        bg_raw = comp.get("bg_color")
        self._vt_bg_chk.blockSignals(True)
        self._vt_bg_chk.setChecked(bg_raw is not None)
        self._vt_bg_chk.blockSignals(False)
        self._vt_bg_color.setEnabled(bg_raw is not None)
        self._vt_bg_color.set_rgba(bg_raw if bg_raw is not None else [15, 15, 35, 220])
        ticks = comp.get("ticks") or []
        self._vt_ticks.load(
            [[td["interval"], td.get("length", 15), td.get("width", 2),
              td.get("x_offset", 0), td.get("y_offset", 0)]
             for td in ticks]
        )
        lbl = comp.get("labels") or {}
        self._vt_labels_cache = {k: v for k, v in lbl.items()
                                 if k not in ("interval", "font_size", "font", "bold", "italic",
                                              "side", "justify", "offset", "format",
                                              "emphasize_place", "emphasize_font_size")}
        self._vt_label_interval.setValue(float(lbl.get("interval", 0.0)))
        self._vt_label_format.setText(str(lbl.get("format", "")))
        self._vt_label_offset.setValue(float(lbl.get("offset", 8.0)))
        ls = str(lbl.get("side", "")) if lbl.get("side") else ""
        self._vt_label_side.setCurrentIndex(
            max(self._vt_label_side.findText(ls), 0) if ls else 0
        )
        lj = str(lbl.get("justify", "")) if lbl.get("justify") else ""
        self._vt_label_justify.setCurrentIndex(
            max(self._vt_label_justify.findText(lj), 0) if lj else 0
        )
        self._vt_label_font_size.setValue(float(lbl.get("font_size", 18.0)))
        self._vt_label_emphasize_place.setValue(float(lbl.get("emphasize_place", 0.0)))
        self._vt_label_emphasize_size.setValue(
            float(lbl.get("emphasize_font_size") or lbl.get("font_size", 18.0)))
        self._vt_label_font.setText(str(lbl.get("font", "")))
        self._vt_label_bold.setChecked(bool(lbl.get("bold", False)))
        self._vt_label_italic.setChecked(bool(lbl.get("italic", False)))
        self._vt_bands.load(comp.get("bands", []))
        self._vt_bugs.load(comp.get("bugs", []))

        # Text component
        has_dr = "dataref" in comp
        self._txt_mode.blockSignals(True)
        self._txt_mode.setCurrentIndex(1 if has_dr else 0)
        self._txt_stack.setCurrentIndex(1 if has_dr else 0)
        self._txt_mode.blockSignals(False)
        self._txt_static.setText(str(comp.get("text", "")))
        self._txt_dr.setText(str(comp.get("dataref", "")))
        txt_cf = str(comp.get("convert_function") or _NONE)
        self._txt_fn.setCurrentIndex(max(self._txt_fn.findText(txt_cf), 0))
        txt_fmt = str(comp.get("text_format", ""))
        self._txt_fmt_custom.setText(txt_fmt)
        self._update_txt_format()  # refresh preview from builder
        if txt_fmt:
            self._txt_fmt_preview.setText(txt_fmt)  # custom overrides preview
        self._txt_emphasize_place.setValue(float(comp.get("emphasize_place", 0.0)))
        self._txt_emphasize_size.setValue(
            float(comp.get("emphasize_font_size") or comp.get("font_size", 12.0)))
        self._txt_font_name.setText(str(comp.get("font_name", "")))
        self._txt_font_size.setValue(float(comp.get("font_size", 12.0)))
        self._txt_bold.setChecked(bool(comp.get("bold", False)))
        self._txt_italic.setChecked(bool(comp.get("italic", False)))
        self._txt_color.set_rgba(comp.get("color"))
        ax = str(comp.get("anchor_x", "left"))
        self._txt_anchor_x.setCurrentIndex(max(self._txt_anchor_x.findText(ax), 0))
        ay = str(comp.get("anchor_y", "baseline"))
        self._txt_anchor_y.setCurrentIndex(max(self._txt_anchor_y.findText(ay), 0))

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

        # AttitudeIndicator fields
        ai_vp = comp.get("viewport", [0, 0, 300, 300])
        self._ai_vp_x.setValue(int(ai_vp[0]))
        self._ai_vp_w.setValue(int(ai_vp[2]))
        self._ai_vp_h.setValue(int(ai_vp[3]))
        ai_vy_display = (self._ref_height - int(ai_vp[1]) - int(ai_vp[3])) if is_y_down() else int(ai_vp[1])
        self._ai_vp_y.setValue(ai_vy_display)
        self._ai_pitch_dr.setText(str(comp.get("pitch_dataref", "")))
        self._ai_roll_dr.setText(str(comp.get("roll_dataref", "")))
        self._ai_ppu.setValue(float(comp.get("pixels_per_degree", 8.0)))
        self._ai_smoothing.setValue(float(comp.get("smoothing", 0.0)))
        self._ai_ladder_step.setValue(float(comp.get("ladder_step", 5.0)))
        self._ai_ladder_hw_4.setValue(float(comp.get("ladder_hw_4", 0.40)))
        self._ai_ladder_hw_2.setValue(float(comp.get("ladder_hw_2", 0.31)))
        self._ai_ladder_hw_1.setValue(float(comp.get("ladder_hw_1", 0.22)))
        self._ai_sky_color.set_rgba(comp.get("sky_color", [0, 100, 180]))
        self._ai_gnd_color.set_rgba(comp.get("ground_color", [100, 60, 10]))
        self._ai_hor_color.set_rgba(comp.get("horizon_color"))
        self._ai_hor_width.setValue(float(comp.get("horizon_width", 3.0)))
        self._ai_ldr_color.set_rgba(comp.get("ladder_color"))
        self._ai_ldr_width.setValue(float(comp.get("ladder_width", 2.0)))
        self._ai_font_size.setValue(int(comp.get("label_font_size", 14)))
        self._ai_ladder_font.setText(str(comp.get("ladder_font_name", "")))
        self._ai_ladder_bold.setChecked(bool(comp.get("ladder_bold", False)))
        self._ai_ladder_italic.setChecked(bool(comp.get("ladder_italic", False)))
        self._ai_arc_color.set_rgba(comp.get("bank_arc_color"))
        self._ai_arc_width.setValue(float(comp.get("bank_arc_width", 2.0)))
        self._ai_arc_r.setValue(float(comp.get("bank_arc_radius", 0.0)))
        self._ai_arc_y_offset.setValue(float(comp.get("bank_arc_y_offset", 0.0)))
        for _deg, _default in ((10, 6.0), (20, 6.0), (30, 10.0), (45, 6.0), (60, 6.0)):
            getattr(self, f"_ai_tick_{_deg}").setValue(
                float(comp.get(f"bank_tick_{_deg}", _default)))
        self._ai_ticks_inward.setChecked(bool(comp.get("ticks_inward", True)))
        _legacy_arc = bool(comp.get("show_bank_arc", True))
        self._ai_show_arc_line.setChecked(bool(comp.get("show_arc_line", _legacy_arc)))
        self._ai_show_arc_ticks.setChecked(bool(comp.get("show_arc_ticks", _legacy_arc)))
        _ref_shape = str(comp.get("arc_ref_shape", "tick")).capitalize()
        self._ai_ref_shape.setCurrentIndex(
            self._ai_ref_shape.findText(_ref_shape) if self._ai_ref_shape.findText(_ref_shape) >= 0 else 0)
        self._ai_ref_height.setValue(float(comp.get("arc_ref_height", 10.0)))
        self._ai_ref_offset.setValue(float(comp.get("arc_ref_offset", 0.0)))
        _ref_is_arrow = (_ref_shape.lower() == "arrow")
        self._ai_ref_width.setValue(float(comp.get("arc_ref_width", 10.0)))
        self._ai_ref_width.setEnabled(_ref_is_arrow)
        _ref_filled = bool(comp.get("arc_ref_filled", True))
        self._ai_ref_filled.setChecked(_ref_filled)
        self._ai_ref_filled.setEnabled(_ref_is_arrow)
        self._ai_ref_line_w.setValue(float(comp.get("arc_ref_line_width", 2.0)))
        self._ai_ref_line_w.setEnabled(_ref_is_arrow and not _ref_filled)
        _show_arc_bg = bool(comp.get("show_arc_bg", False))
        self._ai_show_arc_bg.blockSignals(True)
        self._ai_show_arc_bg.setChecked(_show_arc_bg)
        self._ai_show_arc_bg.blockSignals(False)
        self._ai_arc_bg_color.setEnabled(_show_arc_bg)
        self._ai_arc_bg_inset.setEnabled(_show_arc_bg)
        _raw_arc_bg = comp.get("arc_bg_color")
        self._ai_arc_bg_color.set_rgba(
            _raw_arc_bg if _raw_arc_bg is not None
            else comp.get("sky_color", [0, 100, 180])
        )
        self._ai_arc_bg_inset.setValue(float(comp.get("arc_bg_inset", 0.0)))
        self._ai_ptr_color.set_rgba(comp.get("roll_pointer_color"))
        _ptr_sz = float(comp.get("roll_pointer_size", 12.0))
        self._ai_ptr_height.setValue(float(comp.get("roll_pointer_height", _ptr_sz)))
        self._ai_ptr_width.setValue(float(comp.get("roll_pointer_width", _ptr_sz)))
        _ptr_filled = bool(comp.get("roll_pointer_filled", True))
        self._ai_ptr_filled.setChecked(_ptr_filled)
        self._ai_ptr_inward.setChecked(bool(comp.get("roll_pointer_inward", True)))
        self._ai_ptr_line_w.setValue(float(comp.get("roll_pointer_line_width", 2.0)))
        self._ai_ptr_line_w.setEnabled(not _ptr_filled)
        self._ai_ptr_y_off.setValue(float(comp.get("roll_pointer_y_offset", 0.0)))
        _show_ref = bool(comp.get("show_reference", True))
        self._ai_show_ref.setChecked(_show_ref)
        self._ai_bug_pts.setText(_pts_to_str(comp.get("centre_bug_points", [])))
        self._ai_bug_filled.setChecked(bool(comp.get("centre_bug_filled", True)))
        self._ai_bug_fill_c.set_rgba(comp.get("centre_bug_fill_color", [0, 0, 0, 255]))
        self._ai_bug_outline_c.set_rgba(comp.get("centre_bug_outline_color", [255, 255, 255, 255]))
        self._ai_bug_outline_w.setValue(float(comp.get("centre_bug_outline_width", 2.0)))
        self._ai_wing_pts.setText(_pts_to_str(comp.get("wing_points", [])))
        self._ai_wing_filled.setChecked(bool(comp.get("wing_filled", True)))
        self._ai_wing_fill_c.set_rgba(comp.get("wing_fill_color", [0, 0, 0, 255]))
        self._ai_wing_outline_c.set_rgba(comp.get("wing_outline_color", [255, 255, 255, 255]))
        self._ai_wing_outline_w.setValue(float(comp.get("wing_outline_width", 2.0)))
        for w in self._ai_ref_controls:
            w.setEnabled(_show_ref)
        self._ai_corner_radius.setValue(float(comp.get("corner_radius", 0.0)))
        _raw_cr_bg = comp.get("corner_bg_color")
        self._ai_corner_bg.set_rgba(_raw_cr_bg if _raw_cr_bg is not None else [0, 0, 0, 255])
        _show_slip = bool(comp.get("show_slip", False))
        self._ai_show_slip.blockSignals(True)
        self._ai_show_slip.setChecked(_show_slip)
        self._ai_show_slip.blockSignals(False)
        self._ai_slip_dr.setText(str(comp.get("slip_dataref",
                                               "sim/cockpit2/gauges/indicators/slip_deg")))
        self._ai_slip_color.set_rgba(comp.get("slip_color", [255, 255, 255, 255]))
        self._ai_slip_w.setValue(float(comp.get("slip_width", 20.0)))
        self._ai_slip_h.setValue(float(comp.get("slip_height", 8.0)))
        _slip_filled = bool(comp.get("slip_filled", True))
        self._ai_slip_filled.setChecked(_slip_filled)
        self._ai_slip_line_w.setValue(float(comp.get("slip_line_width", 2.0)))
        self._ai_slip_offset.setValue(float(comp.get("slip_offset", 0.0)))
        self._ai_slip_scale.setValue(float(comp.get("slip_scale", 2.0)))
        for w in self._ai_slip_controls:
            w.setEnabled(_show_slip)
        if _show_slip:
            self._ai_slip_line_w.setEnabled(not _slip_filled)
        _show_fd_h = bool(comp.get("show_fd_h_bar", False))
        self._ai_fd_h_show.blockSignals(True)
        self._ai_fd_h_show.setChecked(_show_fd_h)
        self._ai_fd_h_show.blockSignals(False)
        self._ai_fd_h_dr.setText(str(comp.get("fd_pitch_dataref", "")))
        self._ai_fd_h_fn.setCurrentIndex(
            max(self._ai_fd_h_fn.findText(str(comp.get("fd_pitch_convert_function") or _NONE)), 0))
        _fd_h_vis = comp.get("fd_h_visibility") or {}
        self._ai_fd_h_vis_dr.setText(str(_fd_h_vis.get("dataref", "")))
        if "operator" in _fd_h_vis:
            self._ai_fd_h_vis_mode.setCurrentIndex(1)
            self._ai_fd_h_vis_stack.setCurrentIndex(1)
            self._ai_fd_h_vis_op.setCurrentIndex(
                max(self._ai_fd_h_vis_op.findText(str(_fd_h_vis.get("operator", "<"))), 0))
            self._ai_fd_h_vis_value.setValue(float(_fd_h_vis.get("value", 0.0)))
        else:
            self._ai_fd_h_vis_mode.setCurrentIndex(0)
            self._ai_fd_h_vis_stack.setCurrentIndex(0)
            self._ai_fd_h_vis_pred.setCurrentIndex(
                max(self._ai_fd_h_vis_pred.findText(str(_fd_h_vis.get("predicate", ""))), 0))
        self._ai_fd_h_color.set_rgba(comp.get("fd_h_color", [255, 200, 0, 255]))
        self._ai_fd_h_len.setValue(float(comp.get("fd_h_length", 200.0)))
        self._ai_fd_h_width.setValue(float(comp.get("fd_h_width", 3.0)))
        self._ai_fd_h_scale.setValue(float(comp.get("fd_h_scale", 8.0)))
        for w in self._ai_fd_h_controls:
            w.setEnabled(_show_fd_h)
        _show_fd_v = bool(comp.get("show_fd_v_bar", False))
        self._ai_fd_v_show.blockSignals(True)
        self._ai_fd_v_show.setChecked(_show_fd_v)
        self._ai_fd_v_show.blockSignals(False)
        self._ai_fd_v_dr.setText(str(comp.get("fd_roll_dataref", "")))
        self._ai_fd_v_fn.setCurrentIndex(
            max(self._ai_fd_v_fn.findText(str(comp.get("fd_roll_convert_function") or _NONE)), 0))
        _fd_v_vis = comp.get("fd_v_visibility") or {}
        self._ai_fd_v_vis_dr.setText(str(_fd_v_vis.get("dataref", "")))
        if "operator" in _fd_v_vis:
            self._ai_fd_v_vis_mode.setCurrentIndex(1)
            self._ai_fd_v_vis_stack.setCurrentIndex(1)
            self._ai_fd_v_vis_op.setCurrentIndex(
                max(self._ai_fd_v_vis_op.findText(str(_fd_v_vis.get("operator", "<"))), 0))
            self._ai_fd_v_vis_value.setValue(float(_fd_v_vis.get("value", 0.0)))
        else:
            self._ai_fd_v_vis_mode.setCurrentIndex(0)
            self._ai_fd_v_vis_stack.setCurrentIndex(0)
            self._ai_fd_v_vis_pred.setCurrentIndex(
                max(self._ai_fd_v_vis_pred.findText(str(_fd_v_vis.get("predicate", ""))), 0))
        self._ai_fd_v_color.set_rgba(comp.get("fd_v_color", [255, 200, 0, 255]))
        self._ai_fd_v_len.setValue(float(comp.get("fd_v_length", 200.0)))
        self._ai_fd_v_width.setValue(float(comp.get("fd_v_width", 3.0)))
        self._ai_fd_v_scale.setValue(float(comp.get("fd_v_scale", 4.0)))
        for w in self._ai_fd_v_controls:
            w.setEnabled(_show_fd_v)

        # RotaryEncoder
        re_sz = comp.get("size", [60, 60])
        self._re_w.setValue(int(re_sz[0])); self._re_h.setValue(int(re_sz[1]))
        self._re_cmd_cw.setText(str(comp.get("command_cw", "")))
        self._re_cmd_ccw.setText(str(comp.get("command_ccw", "")))
        self._re_drag_px.setValue(float(comp.get("drag_px_per_step", 5.0)))
        self._re_show_zones.setChecked(bool(comp.get("show_touch_zones", False)))
        self._re_hit_padding.setValue(float(comp.get("hit_padding", 0.0)))
        # background texture
        bg_tex_val = str(comp.get("background_texture", ""))
        self._re_bg_tex.setText(bg_tex_val)
        self._re_bg_edit_btn.setEnabled(bool(bg_tex_val.strip()))
        bg_orig = comp.get("background_origin", [0, 0])
        self._re_bg_ox.setValue(int(bg_orig[0])); self._re_bg_oy.setValue(int(bg_orig[1]))
        bg_clip = comp.get("background_cliprect", [120, 120])
        self._re_bg_cw.setValue(int(bg_clip[0])); self._re_bg_ch.setValue(int(bg_clip[1]))
        # face texture
        face_tex_val = str(comp.get("face_texture", ""))
        self._re_face_tex.setText(face_tex_val)
        self._re_face_edit_btn.setEnabled(bool(face_tex_val.strip()))
        face_orig = comp.get("face_origin", [0, 0])
        self._re_face_ox.setValue(int(face_orig[0])); self._re_face_oy.setValue(int(face_orig[1]))
        face_clip = comp.get("face_cliprect", [80, 80])
        self._re_face_cw.setValue(int(face_clip[0])); self._re_face_ch.setValue(int(face_clip[1]))
        face_sz = comp.get("face_size", re_sz)
        self._re_face_sw.setValue(int(face_sz[0])); self._re_face_sh.setValue(int(face_sz[1]))
        face_off = comp.get("face_offset", [0, 0])
        self._re_face_offx.setValue(int(face_off[0])); self._re_face_offy.setValue(int(face_off[1]))
        face_rc = comp.get("face_rotation_center", [0, 0])
        self._re_face_rcx.setValue(int(face_rc[0])); self._re_face_rcy.setValue(int(face_rc[1]))
        fr = comp.get("face_rotation") or {}
        self._re_face_dr.setText(str(fr.get("dataref", "")))
        fn_idx = self._re_face_fn.findText(str(fr.get("convert_function") or "identity"))
        self._re_face_fn.setCurrentIndex(max(fn_idx, 0))
        self._re_face_tbl.load(fr.get("table", []))

        # NeedleGauge
        ng_ctr = comp.get("center", [0, 0])
        self._ng_cx.setValue(int(ng_ctr[0]))
        self._ng_cy.setValue(flip_y(int(ng_ctr[1]), self._ref_height))
        ng_grad = str(comp.get("gradation_type", "circular"))
        self._ng_grad_type.setCurrentIndex(max(self._ng_grad_type.findText(ng_grad), 0))
        self._ng_grad_stack.setCurrentIndex(1 if ng_grad == "linear" else 0)
        self._ng_radius.setValue(float(comp.get("radius", 100.0)))
        self._ng_arc_start.setValue(float(comp.get("start_angle", -220.0)))
        self._ng_arc_end.setValue(float(comp.get("end_angle", 40.0)))
        self._ng_arc_color.set_rgba(comp.get("arc_color") or comp.get("color"))
        self._ng_arc_width.setValue(float(comp.get("arc_width", 2.0)))
        self._ng_segments.setValue(int(comp.get("num_segments", 64)))
        ng_lin = comp.get("linear") or {}
        self._ng_orientation.setCurrentText(str(ng_lin.get("orientation", "vertical")))
        self._ng_spacing_table.load(ng_lin.get("spacing_table", []))
        self._ng_tick_side.setCurrentText(str(ng_lin.get("tick_side", "left")))
        self._ng_tick_color.set_rgba(ng_lin.get("tick_color", [255, 255, 255, 255]))
        self._ng_ticks.load([
            [t.get("interval", 1.0), t.get("length", 10.0), t.get("width", 1.0)]
            for t in ng_lin.get("ticks", [])
        ])
        ng_labels = ng_lin.get("labels") or {}
        self._ng_label_interval.setValue(float(ng_labels.get("interval", 1.0)))
        self._ng_label_format.setText(str(ng_labels.get("format", "")))
        self._ng_label_font_size.setValue(float(ng_labels.get("font_size", 14.0)))
        self._ng_label_color.set_rgba(ng_labels.get("color", [255, 255, 255, 255]))
        self._ng_label_offset.setValue(float(ng_labels.get("offset", 8.0)))
        self._ng_needle_len.setValue(float(comp.get("needle_length", 80.0)))
        self._ng_needle_width.setValue(float(comp.get("needle_width", 2.0)))
        self._ng_needle_color.set_rgba(comp.get("needle_color") or comp.get("color"))
        self._ng_needle_angle.load(comp.get("needle_angle", -220.0))

        # VectorCompassRose
        cr_ctr = comp.get("center", [0, 0])
        self._cr_cx.setValue(int(cr_ctr[0]))
        self._cr_cy.setValue(flip_y(int(cr_ctr[1]), self._ref_height))
        self._cr_radius.setValue(float(comp.get("radius", 150.0)))
        cr_bg = comp.get("background_color")
        self._cr_bg_chk.blockSignals(True)
        self._cr_bg_chk.setChecked(cr_bg is not None)
        self._cr_bg_chk.blockSignals(False)
        self._cr_bg_color.setEnabled(cr_bg is not None)
        self._cr_bg_color.set_rgba(cr_bg if cr_bg is not None else [20, 20, 30, 255])
        _cr_show_line = bool(comp.get("show_line", True))
        self._cr_line_chk.blockSignals(True)
        self._cr_line_chk.setChecked(_cr_show_line)
        self._cr_line_chk.blockSignals(False)
        self._cr_line_color.set_rgba(comp.get("line_color", [255, 255, 255, 255]))
        self._cr_line_width.setValue(float(comp.get("line_width", 2.0)))
        self._cr_line_color.setEnabled(_cr_show_line)
        self._cr_line_width.setEnabled(_cr_show_line)
        self._cr_segments.setValue(int(comp.get("num_segments", 128)))
        self._cr_t5_len.setValue(float(comp.get("tick5_length", 8.0)))
        self._cr_t5_color.set_rgba(comp.get("tick5_color", [255, 255, 255, 255]))
        self._cr_t5_width.setValue(float(comp.get("tick5_width", 1.0)))
        self._cr_t5_pos.setCurrentText(str(comp.get("tick5_position", "outside")))
        self._cr_t10_len.setValue(float(comp.get("tick10_length", 16.0)))
        self._cr_t10_color.set_rgba(comp.get("tick10_color", [255, 255, 255, 255]))
        self._cr_t10_width.setValue(float(comp.get("tick10_width", 2.0)))
        self._cr_t10_pos.setCurrentText(str(comp.get("tick10_position", "outside")))
        self._cr_label_interval.setValue(float(comp.get("label_interval", 30.0)))
        self._cr_label_offset.setValue(float(comp.get("label_offset", 20.0)))
        self._cr_label_pos.setCurrentText(str(comp.get("label_position", "inside")))
        self._cr_label_format.setText(str(comp.get("label_format", "")))
        self._cr_label_font_size.setValue(float(comp.get("label_font_size", 14.0)))
        self._cr_label_emph_interval.setValue(float(comp.get("label_emphasize_interval", 0.0)))
        self._cr_label_emph_size.setValue(
            float(comp.get("label_emphasize_font_size") or comp.get("label_font_size", 14.0)))
        self._cr_label_font.setText(str(comp.get("label_font", "")))
        self._cr_label_bold.setChecked(bool(comp.get("label_bold", False)))
        self._cr_label_italic.setChecked(bool(comp.get("label_italic", False)))
        self._cr_label_color.set_rgba(comp.get("label_color", [255, 255, 255, 255]))
        self._cr_label_anchor_y.setCurrentText(str(comp.get("label_anchor_y", "center")))
        cr_heading = comp.get("heading") or {}
        self._cr_heading_dr.setText(str(cr_heading.get("dataref", "")))
        self._cr_heading_fn.setCurrentIndex(
            max(self._cr_heading_fn.findText(str(cr_heading.get("convert_function") or _NONE)), 0))
        cr_track = comp.get("track") or {}
        self._cr_track_dr.setText(str(cr_track.get("dataref", "")))
        self._cr_track_fn.setCurrentIndex(
            max(self._cr_track_fn.findText(str(cr_track.get("convert_function") or _NONE)), 0))
        self._cr_track_color.set_rgba(cr_track.get("color", [0, 255, 0, 255]))
        self._cr_track_width.setValue(float(cr_track.get("width", 2.0)))
        self._cr_track_start.setValue(float(cr_track.get("start", 0.0)))
        self._cr_track_end.setValue(float(cr_track.get("end", 150.0)))
        self._cr_track_tick_pos.setValue(float(cr_track.get("tick_position", 0.0)))
        self._cr_track_tick_len.setValue(float(cr_track.get("tick_length", 20.0)))
        cr_bug = comp.get("heading_bug") or {}
        self._cr_bug_dr.setText(str(cr_bug.get("dataref", "")))
        self._cr_bug_fn.setCurrentIndex(
            max(self._cr_bug_fn.findText(str(cr_bug.get("convert_function") or _NONE)), 0))
        self._cr_bug_radius.setValue(float(cr_bug.get("radius", comp.get("radius", 150.0))))
        self._cr_bug_pts.load([[p[0], p[1]] for p in cr_bug.get("points", [])])
        self._cr_bug_color.set_rgba(cr_bug.get("color", [255, 255, 255, 255]))
        bug_filled = bool(cr_bug.get("filled", True))
        self._cr_bug_filled.blockSignals(True)
        self._cr_bug_filled.setChecked(bug_filled)
        self._cr_bug_filled.blockSignals(False)
        self._cr_bug_width.setEnabled(not bug_filled)
        self._cr_bug_width.setValue(float(cr_bug.get("width", 2.0)))
        bug_oc = cr_bug.get("outline_color")
        has_bug_outline = bug_oc is not None and bug_filled
        self._cr_bug_outline_chk.blockSignals(True)
        self._cr_bug_outline_chk.setChecked(has_bug_outline)
        self._cr_bug_outline_chk.blockSignals(False)
        self._cr_bug_outline_chk.setVisible(bug_filled)
        self._cr_bug_outline_color.setEnabled(has_bug_outline)
        self._cr_bug_outline_color.setVisible(bug_filled)
        self._cr_bug_outline_color.set_rgba(bug_oc if bug_oc is not None else (255, 255, 255, 255))
        self._cr_bug_outline_width.setEnabled(has_bug_outline)
        self._cr_bug_outline_width.setVisible(bug_filled)
        self._cr_bug_outline_width.setValue(float(cr_bug.get("outline_width", 1.0)))
        cr_marker = comp.get("heading_marker") or {}
        self._cr_marker_radius.setValue(float(cr_marker.get("radius", comp.get("radius", 150.0))))
        self._cr_marker_pts.load([[p[0], p[1]] for p in cr_marker.get("points", [])])
        self._cr_marker_color.set_rgba(cr_marker.get("color", [255, 255, 255, 255]))
        marker_filled = bool(cr_marker.get("filled", True))
        self._cr_marker_filled.blockSignals(True)
        self._cr_marker_filled.setChecked(marker_filled)
        self._cr_marker_filled.blockSignals(False)
        self._cr_marker_width.setEnabled(not marker_filled)
        self._cr_marker_width.setValue(float(cr_marker.get("width", 2.0)))
        marker_oc = cr_marker.get("outline_color")
        has_marker_outline = marker_oc is not None and marker_filled
        self._cr_marker_outline_chk.blockSignals(True)
        self._cr_marker_outline_chk.setChecked(has_marker_outline)
        self._cr_marker_outline_chk.blockSignals(False)
        self._cr_marker_outline_chk.setVisible(marker_filled)
        self._cr_marker_outline_color.setEnabled(has_marker_outline)
        self._cr_marker_outline_color.setVisible(marker_filled)
        self._cr_marker_outline_color.set_rgba(
            marker_oc if marker_oc is not None else (255, 255, 255, 255))
        self._cr_marker_outline_width.setEnabled(has_marker_outline)
        self._cr_marker_outline_width.setVisible(marker_filled)
        self._cr_marker_outline_width.setValue(float(cr_marker.get("outline_width", 1.0)))

        # Viewport (shared) — not for AttitudeIndicator which manages its own viewport
        if ct != "AttitudeIndicator":
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
        else:
            self._vp_sec.set_active(False)

        # Visibility (shared)
        vis = comp.get("visibility")
        self._vis_sec.set_active(vis is not None)
        if vis:
            self._vis_dr.setText(str(vis.get("dataref", "")))
            if "operator" in vis:
                self._vis_mode.setCurrentIndex(1)
                self._vis_stack.setCurrentIndex(1)
                self._vis_op.setCurrentIndex(
                    max(self._vis_op.findText(str(vis.get("operator", "<"))), 0))
                self._vis_value.setValue(float(vis.get("value", 0.0)))
            else:
                self._vis_mode.setCurrentIndex(0)
                self._vis_stack.setCurrentIndex(0)
                self._vis_pred.setCurrentIndex(
                    max(self._vis_pred.findText(str(vis.get("predicate", ""))), 0))
        else:
            self._vis_dr.clear()
            self._vis_mode.setCurrentIndex(0)
            self._vis_stack.setCurrentIndex(0)
            if self._vis_pred.count():
                self._vis_pred.setCurrentIndex(0)
            self._vis_op.setCurrentIndex(0)
            self._vis_value.setValue(0.0)

        self._loading = False

    def get_data(self) -> dict:
        data: dict = {}
        data["name"] = self._name.text().strip()
        ct = self._type.currentText()
        data["type"] = ct

        # Position only for types that use a single centre point
        # VectorTape uses position spinboxes for viewport origin (written below with viewport)
        if ct not in ("Line", "Arc", "Polygon", "AttitudeIndicator", "NeedleGauge",
                      "VectorCompassRose", "VectorTape"):
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
            data["origin"] = [self._poly_ox.value(), flip_y(self._poly_oy.value(), self._ref_height)]
            data["points"] = [[row[0], row[1]] for row in self._poly_pts.get_data()]
            data["color"]  = list(self._poly_color.get_rgba())
            if not self._poly_filled.isChecked():
                data["filled"] = False
                data["width"]  = self._poly_width.value()
            elif self._poly_outline_chk.isChecked():
                data["outline_color"] = list(self._poly_outline_color.get_rgba())
                data["outline_width"] = self._poly_outline_width.value()

        elif ct == "Vector":
            data["direction"] = self._vec_dir.get_data()
            data["length"]    = self._vec_len.get_data()
            data["color"]     = list(self._vec_color.get_rgba())
            w = self._vec_width.value()
            if w != 1.0:
                data["width"] = w
            _cap = self._vec_cap.currentText()
            if _cap != "none":
                data["cap"] = _cap
                data["cap_width"] = self._vec_cap_width.value()
                if _cap == "triangle":
                    data["cap_height"] = self._vec_cap_height.value()
                    if not self._vec_cap_filled.isChecked():
                        data["cap_filled"] = False
                    if self._vec_hide_if_short.isChecked():
                        data["hide_if_less_than_cap"] = True

        elif ct == "RotaryEncoder":
            data["size"] = [self._re_w.value(), self._re_h.value()]
            cw = self._re_cmd_cw.text().strip()
            if cw:
                data["command_cw"] = cw
            ccw = self._re_cmd_ccw.text().strip()
            if ccw:
                data["command_ccw"] = ccw
            drag = self._re_drag_px.value()
            if abs(drag - 5.0) > 0.05:
                data["drag_px_per_step"] = round(drag, 1)
            if self._re_show_zones.isChecked():
                data["show_touch_zones"] = True
            hp = self._re_hit_padding.value()
            if hp > 0.0:
                data["hit_padding"] = round(hp, 1)
            # background texture
            bg = self._re_bg_tex.text().strip()
            if bg:
                data["background_texture"] = bg
                data["background_origin"]  = [self._re_bg_ox.value(), self._re_bg_oy.value()]
                data["background_cliprect"] = [self._re_bg_cw.value(), self._re_bg_ch.value()]
            # face texture
            face = self._re_face_tex.text().strip()
            if face:
                data["face_texture"]  = face
                data["face_origin"]   = [self._re_face_ox.value(), self._re_face_oy.value()]
                data["face_cliprect"] = [self._re_face_cw.value(), self._re_face_ch.value()]
                data["face_size"] = [self._re_face_sw.value(), self._re_face_sh.value()]
                fox, foy = self._re_face_offx.value(), self._re_face_offy.value()
                if fox != 0 or foy != 0:
                    data["face_offset"] = [fox, foy]
                frcx, frcy = self._re_face_rcx.value(), self._re_face_rcy.value()
                if frcx != 0 or frcy != 0:
                    data["face_rotation_center"] = [frcx, frcy]
                fdr = self._re_face_dr.text().strip()
                ftbl = self._re_face_tbl.get_data()
                if fdr or ftbl:
                    fr: dict = {"dataref": fdr, "table": ftbl}
                    fn = self._re_face_fn.currentText()
                    if fn and fn != "identity":
                        fr["convert_function"] = fn
                    data["face_rotation"] = fr

        elif ct == "NeedleGauge":
            data["center"] = [self._ng_cx.value(), flip_y(self._ng_cy.value(), self._ref_height)]
            grad = self._ng_grad_type.currentText()
            if grad != "circular":
                data["gradation_type"] = grad
            if grad == "linear":
                lin: dict = {
                    "orientation": self._ng_orientation.currentText(),
                    "spacing_table": self._ng_spacing_table.get_data(),
                    "tick_side": self._ng_tick_side.currentText(),
                    "tick_color": list(self._ng_tick_color.get_rgba()),
                    "ticks": [
                        {"interval": row[0], "length": row[1], "width": row[2]}
                        for row in self._ng_ticks.get_data()
                    ],
                }
                li = self._ng_label_interval.value()
                if li > 0:
                    labels: dict = {"interval": li}
                    fmt = self._ng_label_format.text().strip()
                    if fmt:
                        labels["format"] = fmt
                    labels["font_size"] = self._ng_label_font_size.value()
                    labels["color"] = list(self._ng_label_color.get_rgba())
                    labels["offset"] = self._ng_label_offset.value()
                    lin["labels"] = labels
                data["linear"] = lin
            else:
                data["radius"] = self._ng_radius.value()
                data["start_angle"] = self._ng_arc_start.value()
                data["end_angle"] = self._ng_arc_end.value()
                data["arc_color"] = list(self._ng_arc_color.get_rgba())
                aw = self._ng_arc_width.value()
                if aw != 2.0:
                    data["arc_width"] = aw
                s = self._ng_segments.value()
                if s != 64:
                    data["num_segments"] = s
            data["needle_length"] = self._ng_needle_len.value()
            nw = self._ng_needle_width.value()
            if nw != 2.0:
                data["needle_width"] = nw
            data["needle_color"] = list(self._ng_needle_color.get_rgba())
            data["needle_angle"] = self._ng_needle_angle.get_data()

        elif ct == "VectorCompassRose":
            data["center"] = [self._cr_cx.value(), flip_y(self._cr_cy.value(), self._ref_height)]
            data["radius"] = self._cr_radius.value()
            if self._cr_bg_chk.isChecked():
                data["background_color"] = list(self._cr_bg_color.get_rgba())
            if not self._cr_line_chk.isChecked():
                data["show_line"] = False
            data["line_color"] = list(self._cr_line_color.get_rgba())
            lw = self._cr_line_width.value()
            if lw != 2.0:
                data["line_width"] = lw
            segs = self._cr_segments.value()
            if segs != 128:
                data["num_segments"] = segs
            data["tick5_length"] = self._cr_t5_len.value()
            data["tick5_color"] = list(self._cr_t5_color.get_rgba())
            data["tick5_width"] = self._cr_t5_width.value()
            data["tick5_position"] = self._cr_t5_pos.currentText()
            data["tick10_length"] = self._cr_t10_len.value()
            data["tick10_color"] = list(self._cr_t10_color.get_rgba())
            data["tick10_width"] = self._cr_t10_width.value()
            data["tick10_position"] = self._cr_t10_pos.currentText()
            data["label_interval"] = self._cr_label_interval.value()
            data["label_offset"] = self._cr_label_offset.value()
            data["label_position"] = self._cr_label_pos.currentText()
            cr_fmt = self._cr_label_format.text().strip()
            if cr_fmt:
                data["label_format"] = cr_fmt
            data["label_font_size"] = self._cr_label_font_size.value()
            cr_emph_interval = self._cr_label_emph_interval.value()
            if cr_emph_interval > 0:
                data["label_emphasize_interval"] = cr_emph_interval
                data["label_emphasize_font_size"] = self._cr_label_emph_size.value()
            cr_font = self._cr_label_font.text().strip()
            if cr_font:
                data["label_font"] = cr_font
            if self._cr_label_bold.isChecked():
                data["label_bold"] = True
            if self._cr_label_italic.isChecked():
                data["label_italic"] = True
            data["label_color"] = list(self._cr_label_color.get_rgba())
            cr_anchor_y = self._cr_label_anchor_y.currentText()
            if cr_anchor_y != "center":
                data["label_anchor_y"] = cr_anchor_y
            cr_hdr = self._cr_heading_dr.text().strip()
            if cr_hdr:
                heading: dict = {"dataref": cr_hdr}
                cr_hfn = self._cr_heading_fn.currentText()
                if cr_hfn != _NONE:
                    heading["convert_function"] = cr_hfn
                data["heading"] = heading
            cr_tdr = self._cr_track_dr.text().strip()
            if cr_tdr:
                track: dict = {
                    "dataref": cr_tdr,
                    "color": list(self._cr_track_color.get_rgba()),
                    "width": self._cr_track_width.value(),
                    "start": self._cr_track_start.value(),
                    "end": self._cr_track_end.value(),
                }
                cr_tfn = self._cr_track_fn.currentText()
                if cr_tfn != _NONE:
                    track["convert_function"] = cr_tfn
                cr_tick_pos = self._cr_track_tick_pos.value()
                if cr_tick_pos > 0:
                    track["tick_position"] = cr_tick_pos
                    track["tick_length"] = self._cr_track_tick_len.value()
                data["track"] = track
            cr_bdr = self._cr_bug_dr.text().strip()
            if cr_bdr:
                bug_filled = self._cr_bug_filled.isChecked()
                bug: dict = {
                    "dataref": cr_bdr,
                    "radius": self._cr_bug_radius.value(),
                    "points": self._cr_bug_pts.get_data(),
                    "color": list(self._cr_bug_color.get_rgba()),
                    "filled": bug_filled,
                }
                cr_bfn = self._cr_bug_fn.currentText()
                if cr_bfn != _NONE:
                    bug["convert_function"] = cr_bfn
                if not bug_filled:
                    bug["width"] = self._cr_bug_width.value()
                elif self._cr_bug_outline_chk.isChecked():
                    bug["outline_color"] = list(self._cr_bug_outline_color.get_rgba())
                    bug["outline_width"] = self._cr_bug_outline_width.value()
                data["heading_bug"] = bug
            cr_marker_pts = self._cr_marker_pts.get_data()
            if cr_marker_pts:
                marker_filled = self._cr_marker_filled.isChecked()
                marker: dict = {
                    "radius": self._cr_marker_radius.value(),
                    "points": cr_marker_pts,
                    "color": list(self._cr_marker_color.get_rgba()),
                    "filled": marker_filled,
                }
                if not marker_filled:
                    marker["width"] = self._cr_marker_width.value()
                elif self._cr_marker_outline_chk.isChecked():
                    marker["outline_color"] = list(self._cr_marker_outline_color.get_rgba())
                    marker["outline_width"] = self._cr_marker_outline_width.value()
                data["heading_marker"] = marker

        elif ct == "AttitudeIndicator":
            ai_vh = self._ai_vp_h.value()
            ai_vy_display = self._ai_vp_y.value()
            ai_vy_yaml = (self._ref_height - ai_vy_display - ai_vh) if is_y_down() else ai_vy_display
            data["viewport"] = [self._ai_vp_x.value(), ai_vy_yaml,
                                 self._ai_vp_w.value(), ai_vh]
            pd = self._ai_pitch_dr.text().strip()
            if pd:
                data["pitch_dataref"] = pd
            rd = self._ai_roll_dr.text().strip()
            if rd:
                data["roll_dataref"] = rd
            ppu = self._ai_ppu.value()
            if ppu != 8.0:
                data["pixels_per_degree"] = ppu
            sm = self._ai_smoothing.value()
            if sm > 0.0:
                data["smoothing"] = round(sm, 2)
            data["sky_color"]    = list(self._ai_sky_color.get_rgba())
            data["ground_color"] = list(self._ai_gnd_color.get_rgba())
            data["horizon_color"] = list(self._ai_hor_color.get_rgba())
            hw = self._ai_hor_width.value()
            if hw != 3.0:
                data["horizon_width"] = hw
            data["ladder_color"] = list(self._ai_ldr_color.get_rgba())
            lw = self._ai_ldr_width.value()
            if lw != 2.0:
                data["ladder_width"] = lw
            fs = self._ai_font_size.value()
            if fs != 14:
                data["label_font_size"] = fs
            fn = self._ai_ladder_font.text().strip()
            if fn:
                data["ladder_font_name"] = fn
            if self._ai_ladder_bold.isChecked():
                data["ladder_bold"] = True
            if self._ai_ladder_italic.isChecked():
                data["ladder_italic"] = True
            data["bank_arc_color"] = list(self._ai_arc_color.get_rgba())
            aw = self._ai_arc_width.value()
            if aw != 2.0:
                data["bank_arc_width"] = aw
            ar = self._ai_arc_r.value()
            if ar > 0:
                data["bank_arc_radius"] = ar
            ayo = self._ai_arc_y_offset.value()
            if ayo != 0.0:
                data["bank_arc_y_offset"] = ayo
            for _deg, _default in ((10, 6.0), (20, 6.0), (30, 10.0), (45, 6.0), (60, 6.0)):
                v = getattr(self, f"_ai_tick_{_deg}").value()
                if v != _default:
                    data[f"bank_tick_{_deg}"] = v
            if not self._ai_ticks_inward.isChecked():
                data["ticks_inward"] = False
            if not self._ai_show_arc_line.isChecked():
                data["show_arc_line"] = False
            _ref_shape_out = self._ai_ref_shape.currentText().lower()
            if _ref_shape_out != "tick":
                data["arc_ref_shape"] = _ref_shape_out
            if self._ai_ref_height.value() != 10.0:
                data["arc_ref_height"] = self._ai_ref_height.value()
            if self._ai_ref_offset.value() != 0.0:
                data["arc_ref_offset"] = self._ai_ref_offset.value()
            if _ref_shape_out == "arrow":
                if self._ai_ref_width.value() != 10.0:
                    data["arc_ref_width"] = self._ai_ref_width.value()
                if not self._ai_ref_filled.isChecked():
                    data["arc_ref_filled"] = False
                    data["arc_ref_line_width"] = self._ai_ref_line_w.value()
            if not self._ai_show_arc_ticks.isChecked():
                data["show_arc_ticks"] = False
            if self._ai_show_arc_bg.isChecked():
                data["show_arc_bg"] = True
                data["arc_bg_color"] = list(self._ai_arc_bg_color.get_rgba())
                if self._ai_arc_bg_inset.value() != 0.0:
                    data["arc_bg_inset"] = self._ai_arc_bg_inset.value()
            data["roll_pointer_color"] = list(self._ai_ptr_color.get_rgba())
            ph = self._ai_ptr_height.value()
            pw = self._ai_ptr_width.value()
            if ph != 12.0 or pw != ph:
                data["roll_pointer_height"] = ph
            if pw != 12.0 or pw != ph:
                data["roll_pointer_width"] = pw
            if not self._ai_ptr_filled.isChecked():
                data["roll_pointer_filled"] = False
                data["roll_pointer_line_width"] = self._ai_ptr_line_w.value()
            if not self._ai_ptr_inward.isChecked():
                data["roll_pointer_inward"] = False
            if self._ai_ptr_y_off.value() != 0.0:
                data["roll_pointer_y_offset"] = self._ai_ptr_y_off.value()
            if not self._ai_show_ref.isChecked():
                data["show_reference"] = False
            _bug_pts = _str_to_pts(self._ai_bug_pts.text())
            if _bug_pts:
                data["centre_bug_points"] = _bug_pts
                if not self._ai_bug_filled.isChecked():
                    data["centre_bug_filled"] = False
                data["centre_bug_fill_color"] = list(self._ai_bug_fill_c.get_rgba())
                data["centre_bug_outline_color"] = list(self._ai_bug_outline_c.get_rgba())
                if self._ai_bug_outline_w.value() != 2.0:
                    data["centre_bug_outline_width"] = self._ai_bug_outline_w.value()
            _wing_pts = _str_to_pts(self._ai_wing_pts.text())
            if _wing_pts:
                data["wing_points"] = _wing_pts
                if not self._ai_wing_filled.isChecked():
                    data["wing_filled"] = False
                data["wing_fill_color"] = list(self._ai_wing_fill_c.get_rgba())
                data["wing_outline_color"] = list(self._ai_wing_outline_c.get_rgba())
                if self._ai_wing_outline_w.value() != 2.0:
                    data["wing_outline_width"] = self._ai_wing_outline_w.value()
            _cr = self._ai_corner_radius.value()
            if _cr > 0.0:
                data["corner_radius"] = _cr
                data["corner_bg_color"] = list(self._ai_corner_bg.get_rgba())
            if self._ai_show_slip.isChecked():
                data["show_slip"] = True
                _sdr = self._ai_slip_dr.text().strip()
                if _sdr:
                    data["slip_dataref"] = _sdr
                data["slip_color"]   = list(self._ai_slip_color.get_rgba())
                if self._ai_slip_w.value() != 20.0:
                    data["slip_width"] = self._ai_slip_w.value()
                if self._ai_slip_h.value() != 8.0:
                    data["slip_height"] = self._ai_slip_h.value()
                if not self._ai_slip_filled.isChecked():
                    data["slip_filled"]     = False
                    data["slip_line_width"] = self._ai_slip_line_w.value()
                if self._ai_slip_offset.value() != 0.0:
                    data["slip_offset"] = self._ai_slip_offset.value()
                if self._ai_slip_scale.value() != 2.0:
                    data["slip_scale"] = self._ai_slip_scale.value()
            if self._ai_fd_h_show.isChecked():
                data["show_fd_h_bar"] = True
                _fdr = self._ai_fd_h_dr.text().strip()
                if _fdr:
                    data["fd_pitch_dataref"] = _fdr
                _ffn = self._ai_fd_h_fn.currentText()
                if _ffn != _NONE:
                    data["fd_pitch_convert_function"] = _ffn
                _fvdr = self._ai_fd_h_vis_dr.text().strip()
                if _fvdr:
                    if self._ai_fd_h_vis_mode.currentIndex() == 1:
                        data["fd_h_visibility"] = {
                            "dataref": _fvdr,
                            "operator": self._ai_fd_h_vis_op.currentText(),
                            "value": self._ai_fd_h_vis_value.value(),
                        }
                    else:
                        _fvp = self._ai_fd_h_vis_pred.currentText()
                        if _fvp:
                            data["fd_h_visibility"] = {"dataref": _fvdr, "predicate": _fvp}
                data["fd_h_color"] = list(self._ai_fd_h_color.get_rgba())
                if self._ai_fd_h_len.value() != 200.0:
                    data["fd_h_length"] = self._ai_fd_h_len.value()
                if self._ai_fd_h_width.value() != 3.0:
                    data["fd_h_width"] = self._ai_fd_h_width.value()
                if self._ai_fd_h_scale.value() != 8.0:
                    data["fd_h_scale"] = self._ai_fd_h_scale.value()
            if self._ai_fd_v_show.isChecked():
                data["show_fd_v_bar"] = True
                _fdr = self._ai_fd_v_dr.text().strip()
                if _fdr:
                    data["fd_roll_dataref"] = _fdr
                _ffn = self._ai_fd_v_fn.currentText()
                if _ffn != _NONE:
                    data["fd_roll_convert_function"] = _ffn
                _fvdr = self._ai_fd_v_vis_dr.text().strip()
                if _fvdr:
                    if self._ai_fd_v_vis_mode.currentIndex() == 1:
                        data["fd_v_visibility"] = {
                            "dataref": _fvdr,
                            "operator": self._ai_fd_v_vis_op.currentText(),
                            "value": self._ai_fd_v_vis_value.value(),
                        }
                    else:
                        _fvp = self._ai_fd_v_vis_pred.currentText()
                        if _fvp:
                            data["fd_v_visibility"] = {"dataref": _fvdr, "predicate": _fvp}
                data["fd_v_color"] = list(self._ai_fd_v_color.get_rgba())
                if self._ai_fd_v_len.value() != 200.0:
                    data["fd_v_length"] = self._ai_fd_v_len.value()
                if self._ai_fd_v_width.value() != 3.0:
                    data["fd_v_width"] = self._ai_fd_v_width.value()
                if self._ai_fd_v_scale.value() != 4.0:
                    data["fd_v_scale"] = self._ai_fd_v_scale.value()
            ls = self._ai_ladder_step.value()
            if ls != 5.0:
                data["ladder_step"] = ls
            hw4 = self._ai_ladder_hw_4.value()
            if hw4 != 0.40:
                data["ladder_hw_4"] = hw4
            hw2 = self._ai_ladder_hw_2.value()
            if hw2 != 0.31:
                data["ladder_hw_2"] = hw2
            hw1 = self._ai_ladder_hw_1.value()
            if hw1 != 0.22:
                data["ladder_hw_1"] = hw1

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
            ppu = self._ss_ppu.value()
            if ppu > 0.0:
                data["pixels_per_unit"] = round(ppu, 2)
            sd = self._ss_shift_dir.currentData()
            if sd == "left":
                data["shift_direction"] = "left"
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

        elif ct == "Text":
            if self._txt_mode.currentIndex() == 0:  # Static
                txt = self._txt_static.text()
                if txt:
                    data["text"] = txt
            else:  # Dataref
                dr = self._txt_dr.text().strip()
                if dr:
                    data["dataref"] = dr
                cf = self._txt_fn.currentText()
                if cf != _NONE:
                    data["convert_function"] = cf
                custom_fmt = self._txt_fmt_custom.text().strip()
                if custom_fmt:
                    data["text_format"] = custom_fmt
                else:
                    d = self._txt_decimals.value()
                    w = self._txt_width.value()
                    z = self._txt_zerofill.isChecked()
                    fill = "0" if z and w > 0 else ""
                    width_str = str(w) if w > 0 else ""
                    data["text_format"] = "{:" + fill + width_str + "." + str(d) + "f}"
                emph_place = self._txt_emphasize_place.value()
                if emph_place > 0:
                    data["emphasize_place"] = emph_place
                    data["emphasize_font_size"] = self._txt_emphasize_size.value()
            fn = self._txt_font_name.text().strip()
            if fn:
                data["font_name"] = fn
            data["font_size"] = self._txt_font_size.value()
            if self._txt_bold.isChecked():
                data["bold"] = True
            if self._txt_italic.isChecked():
                data["italic"] = True
            data["color"] = list(self._txt_color.get_rgba())
            ax = self._txt_anchor_x.currentText()
            if ax != "left":
                data["anchor_x"] = ax
            ay = self._txt_anchor_y.currentText()
            if ay != "baseline":
                data["anchor_y"] = ay

        elif ct == "VectorTape":
            data["scroll_axis"] = "y" if self._vt_axis.currentIndex() == 0 else "x"
            data["pixels_per_unit"] = self._vt_ppu.value()
            wrap = self._vt_wrap.value()
            if wrap > 0.0:
                data["wrap"] = wrap
            data["tick_side"] = self._vt_tick_side.currentText()
            data["tick_color"] = list(self._vt_tick_color.get_rgba())
            if self._vt_bg_chk.isChecked():
                data["bg_color"] = list(self._vt_bg_color.get_rgba())
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
                    {"interval": r[0], "length": r[1], "width": r[2],
                     **( {"x_offset": r[3]} if len(r) > 3 and r[3] != 0 else {} ),
                     **( {"y_offset": r[4]} if len(r) > 4 and r[4] != 0 else {} )}
                    for r in ticks_raw
                ]
            # Labels dict: cache preserves color and any other unmodeled keys;
            # form controls interval, format, font_size, font, and side.
            lbl_dict = dict(self._vt_labels_cache)
            lbl_interval = self._vt_label_interval.value()
            if lbl_interval > 0:
                lbl_dict["interval"] = lbl_interval
            else:
                lbl_dict.pop("interval", None)
            lbl_fmt = self._vt_label_format.text().strip()
            if lbl_fmt:
                lbl_dict["format"] = lbl_fmt
            else:
                lbl_dict.pop("format", None)
            lbl_dict["font_size"] = self._vt_label_font_size.value()
            emph_place = self._vt_label_emphasize_place.value()
            if emph_place > 0:
                lbl_dict["emphasize_place"] = emph_place
                lbl_dict["emphasize_font_size"] = self._vt_label_emphasize_size.value()
            else:
                lbl_dict.pop("emphasize_place", None)
                lbl_dict.pop("emphasize_font_size", None)
            lbl_dict["offset"] = self._vt_label_offset.value()
            fn = self._vt_label_font.text().strip()
            if fn:
                lbl_dict["font"] = fn
            else:
                lbl_dict.pop("font", None)
            if self._vt_label_bold.isChecked():
                lbl_dict["bold"] = True
            else:
                lbl_dict.pop("bold", None)
            if self._vt_label_italic.isChecked():
                lbl_dict["italic"] = True
            else:
                lbl_dict.pop("italic", None)
            ls = self._vt_label_side.currentText()
            if ls != "(same as tick side)":
                lbl_dict["side"] = ls
            else:
                lbl_dict.pop("side", None)
            lj = self._vt_label_justify.currentText()
            if lj != "(auto — flush against spine)":
                lbl_dict["justify"] = lj
            else:
                lbl_dict.pop("justify", None)
            if lbl_dict:
                data["labels"] = lbl_dict
            bands = self._vt_bands.get_data()
            if bands:
                data["bands"] = bands
            bugs = self._vt_bugs.get_data()
            if bugs:
                data["bugs"] = bugs

        if self._vp_sec.active:
            vh = self._vp_h.value()
            if ct == "VectorTape":
                # x/y origin comes from Position spinboxes, not the viewport x/y row
                vy_display = self._py.value()
                vy_yaml = (self._ref_height - vy_display - vh) if is_y_down() else vy_display
                data["viewport"] = [self._px.value(), vy_yaml, self._vp_w.value(), vh]
            else:
                vy_display = self._vp_y.value()
                # Convert display Y back to y-up bottom edge for the YAML.
                vy_yaml = (self._ref_height - vy_display - vh) if is_y_down() else vy_display
                data["viewport"] = [self._vp_x.value(), vy_yaml, self._vp_w.value(), vh]

        if self._vis_sec.active:
            if self._vis_mode.currentIndex() == 1:
                data["visibility"] = {
                    "dataref":  self._vis_dr.text().strip(),
                    "operator": self._vis_op.currentText(),
                    "value":    self._vis_value.value(),
                }
            else:
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
        self._ss_ppu.setValue(0.0)
        self._ss_shift_dir.setCurrentIndex(0)
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
        self._poly_ox.setValue(0); self._poly_oy.setValue(0)
        self._poly_pts.load([])
        self._poly_color.set_rgba(None)
        self._poly_filled.setChecked(True); self._poly_width.setValue(1.0)
        self._poly_outline_chk.setChecked(False)
        self._poly_outline_color.set_rgba(None); self._poly_outline_width.setValue(1.0)
        self._vec_dir.load(0.0)
        self._vec_len.load(50.0)
        self._vec_color.set_rgba(None); self._vec_width.setValue(1.0)
        self._vec_cap.setCurrentIndex(0)
        self._vec_cap_width.setValue(10.0); self._vec_cap_width.setEnabled(False)
        self._vec_cap_height.setValue(5.0); self._vec_cap_height.setEnabled(False)
        self._vec_cap_filled.setChecked(True); self._vec_cap_filled.setEnabled(False)
        # RotaryEncoder
        self._re_w.setValue(60); self._re_h.setValue(60)
        self._re_cmd_cw.clear(); self._re_cmd_ccw.clear()
        self._re_drag_px.setValue(5.0)
        self._re_show_zones.setChecked(False)
        self._re_hit_padding.setValue(0.0)
        self._re_bg_tex.clear(); self._re_bg_edit_btn.setEnabled(False)
        self._re_bg_ox.setValue(0); self._re_bg_oy.setValue(0)
        self._re_bg_cw.setValue(120); self._re_bg_ch.setValue(120)
        self._re_face_tex.clear(); self._re_face_edit_btn.setEnabled(False)
        self._re_face_ox.setValue(0); self._re_face_oy.setValue(0)
        self._re_face_cw.setValue(80); self._re_face_ch.setValue(80)
        self._re_face_sw.setValue(60); self._re_face_sh.setValue(60)
        self._re_face_offx.setValue(0); self._re_face_offy.setValue(0)
        self._re_face_rcx.setValue(0); self._re_face_rcy.setValue(0)
        self._re_face_dr.clear()
        self._re_face_fn.setCurrentIndex(0)
        self._re_face_tbl.load([])
        # NeedleGauge
        self._ng_cx.setValue(0); self._ng_cy.setValue(0)
        self._ng_grad_type.setCurrentIndex(0); self._ng_grad_stack.setCurrentIndex(0)
        self._ng_radius.setValue(100.0)
        self._ng_arc_start.setValue(-220.0); self._ng_arc_end.setValue(40.0)
        self._ng_arc_color.set_rgba(None); self._ng_arc_width.setValue(2.0)
        self._ng_segments.setValue(64)
        self._ng_orientation.setCurrentIndex(0)
        self._ng_spacing_table.load([])
        self._ng_tick_side.setCurrentIndex(0)
        self._ng_tick_color.set_rgba(None)
        self._ng_ticks.load([])
        self._ng_label_interval.setValue(1.0); self._ng_label_format.clear()
        self._ng_label_font_size.setValue(14.0); self._ng_label_color.set_rgba(None)
        self._ng_label_offset.setValue(8.0)
        self._ng_needle_len.setValue(80.0); self._ng_needle_width.setValue(2.0)
        self._ng_needle_color.set_rgba(None)
        self._ng_needle_angle.load(-220.0)
        # VectorCompassRose
        self._cr_cx.setValue(0); self._cr_cy.setValue(0)
        self._cr_radius.setValue(150.0)
        self._cr_bg_chk.setChecked(False); self._cr_bg_color.set_rgba(None)
        self._cr_line_chk.setChecked(True)
        self._cr_line_color.set_rgba(None); self._cr_line_width.setValue(2.0)
        self._cr_segments.setValue(128)
        self._cr_t5_len.setValue(8.0); self._cr_t5_color.set_rgba(None)
        self._cr_t5_width.setValue(1.0); self._cr_t5_pos.setCurrentIndex(0)
        self._cr_t10_len.setValue(16.0); self._cr_t10_color.set_rgba(None)
        self._cr_t10_width.setValue(2.0); self._cr_t10_pos.setCurrentIndex(0)
        self._cr_label_interval.setValue(30.0); self._cr_label_offset.setValue(20.0)
        self._cr_label_pos.setCurrentIndex(0); self._cr_label_format.clear()
        self._cr_label_font_size.setValue(14.0); self._cr_label_font.clear()
        self._cr_label_emph_interval.setValue(0.0); self._cr_label_emph_size.setValue(20.0)
        self._cr_label_bold.setChecked(False); self._cr_label_italic.setChecked(False)
        self._cr_label_color.set_rgba(None)
        self._cr_label_anchor_y.setCurrentIndex(1)  # "center"
        self._cr_heading_dr.clear(); self._cr_heading_fn.setCurrentIndex(0)
        self._cr_track_dr.clear(); self._cr_track_fn.setCurrentIndex(0)
        self._cr_track_color.set_rgba(None); self._cr_track_width.setValue(2.0)
        self._cr_track_start.setValue(0.0); self._cr_track_end.setValue(150.0)
        self._cr_track_tick_pos.setValue(0.0); self._cr_track_tick_len.setValue(20.0)
        self._cr_bug_dr.clear(); self._cr_bug_fn.setCurrentIndex(0)
        self._cr_bug_radius.setValue(150.0); self._cr_bug_pts.load([])
        self._cr_bug_color.set_rgba(None)
        self._cr_bug_filled.setChecked(True); self._cr_bug_width.setValue(2.0)
        self._cr_bug_outline_chk.setChecked(False)
        self._cr_bug_outline_color.set_rgba(None); self._cr_bug_outline_width.setValue(1.0)
        self._cr_marker_radius.setValue(150.0); self._cr_marker_pts.load([])
        self._cr_marker_color.set_rgba(None)
        self._cr_marker_filled.setChecked(True); self._cr_marker_width.setValue(2.0)
        self._cr_marker_outline_chk.setChecked(False)
        self._cr_marker_outline_color.set_rgba(None); self._cr_marker_outline_width.setValue(1.0)
        # AttitudeIndicator
        self._ai_vp_x.setValue(0); self._ai_vp_y.setValue(0)
        self._ai_vp_w.setValue(300); self._ai_vp_h.setValue(300)
        self._ai_pitch_dr.clear(); self._ai_roll_dr.clear()
        self._ai_ppu.setValue(8.0)
        self._ai_smoothing.setValue(0.0)
        self._ai_ladder_step.setValue(5.0)
        self._ai_ladder_hw_4.setValue(0.40)
        self._ai_ladder_hw_2.setValue(0.31)
        self._ai_ladder_hw_1.setValue(0.22)
        self._ai_sky_color.set_rgba([0, 100, 180, 255])
        self._ai_gnd_color.set_rgba([100, 60, 10, 255])
        self._ai_hor_color.set_rgba(None); self._ai_hor_width.setValue(3.0)
        self._ai_ldr_color.set_rgba(None); self._ai_ldr_width.setValue(2.0)
        self._ai_font_size.setValue(14)
        self._ai_ladder_font.clear()
        self._ai_ladder_bold.setChecked(False); self._ai_ladder_italic.setChecked(False)
        self._ai_arc_color.set_rgba(None); self._ai_arc_width.setValue(2.0)
        self._ai_arc_r.setValue(0.0); self._ai_arc_y_offset.setValue(0.0)
        for _deg, _default in ((10, 6.0), (20, 6.0), (30, 10.0), (45, 6.0), (60, 6.0)):
            getattr(self, f"_ai_tick_{_deg}").setValue(_default)
        self._ai_ticks_inward.setChecked(True)
        self._ai_show_arc_line.setChecked(True); self._ai_show_arc_ticks.setChecked(True)
        self._ai_ref_shape.setCurrentIndex(0)   # Tick
        self._ai_ref_height.setValue(10.0); self._ai_ref_offset.setValue(0.0)
        self._ai_ref_width.setValue(10.0); self._ai_ref_width.setEnabled(False)
        self._ai_ref_filled.setChecked(True); self._ai_ref_filled.setEnabled(False)
        self._ai_ref_line_w.setValue(2.0); self._ai_ref_line_w.setEnabled(False)
        self._ai_show_arc_bg.setChecked(False)
        self._ai_arc_bg_color.set_rgba([0, 100, 180, 255]); self._ai_arc_bg_color.setEnabled(False)
        self._ai_arc_bg_inset.setValue(0.0); self._ai_arc_bg_inset.setEnabled(False)
        self._ai_ptr_color.set_rgba(None)
        self._ai_ptr_height.setValue(12.0); self._ai_ptr_width.setValue(12.0)
        self._ai_ptr_filled.setChecked(True); self._ai_ptr_inward.setChecked(True)
        self._ai_ptr_line_w.setValue(2.0); self._ai_ptr_line_w.setEnabled(False)
        self._ai_ptr_y_off.setValue(0.0)
        self._ai_show_ref.setChecked(True)
        self._ai_bug_pts.clear()
        self._ai_bug_filled.setChecked(True)
        self._ai_bug_fill_c.set_rgba([0, 0, 0, 255])
        self._ai_bug_outline_c.set_rgba([255, 255, 255, 255])
        self._ai_bug_outline_w.setValue(2.0)
        self._ai_wing_pts.clear()
        self._ai_wing_filled.setChecked(True)
        self._ai_wing_fill_c.set_rgba([0, 0, 0, 255])
        self._ai_wing_outline_c.set_rgba([255, 255, 255, 255])
        self._ai_wing_outline_w.setValue(2.0)
        for w in self._ai_ref_controls:
            w.setEnabled(True)
        self._ai_corner_radius.setValue(0.0)
        self._ai_corner_bg.set_rgba([0, 0, 0, 255])
        self._ai_show_slip.setChecked(False)
        self._ai_slip_dr.setText("sim/cockpit2/gauges/indicators/slip_deg")
        self._ai_slip_color.set_rgba([255, 255, 255, 255])
        self._ai_slip_w.setValue(20.0); self._ai_slip_h.setValue(8.0)
        self._ai_slip_filled.setChecked(True)
        self._ai_slip_line_w.setValue(2.0)
        self._ai_slip_offset.setValue(0.0); self._ai_slip_scale.setValue(2.0)
        for w in self._ai_slip_controls:
            w.setEnabled(False)
        self._ai_fd_h_show.setChecked(False)
        self._ai_fd_h_dr.clear(); self._ai_fd_h_fn.setCurrentIndex(0)
        self._ai_fd_h_vis_dr.clear()
        self._ai_fd_h_vis_mode.setCurrentIndex(0); self._ai_fd_h_vis_stack.setCurrentIndex(0)
        self._ai_fd_h_vis_pred.setCurrentIndex(0)
        self._ai_fd_h_vis_op.setCurrentIndex(0); self._ai_fd_h_vis_value.setValue(0.0)
        self._ai_fd_h_color.set_rgba([255, 200, 0, 255])
        self._ai_fd_h_len.setValue(200.0); self._ai_fd_h_width.setValue(3.0)
        self._ai_fd_h_scale.setValue(8.0)
        for w in self._ai_fd_h_controls:
            w.setEnabled(False)
        self._ai_fd_v_show.setChecked(False)
        self._ai_fd_v_dr.clear(); self._ai_fd_v_fn.setCurrentIndex(0)
        self._ai_fd_v_vis_dr.clear()
        self._ai_fd_v_vis_mode.setCurrentIndex(0); self._ai_fd_v_vis_stack.setCurrentIndex(0)
        self._ai_fd_v_vis_pred.setCurrentIndex(0)
        self._ai_fd_v_vis_op.setCurrentIndex(0); self._ai_fd_v_vis_value.setValue(0.0)
        self._ai_fd_v_color.set_rgba([255, 200, 0, 255])
        self._ai_fd_v_len.setValue(200.0); self._ai_fd_v_width.setValue(3.0)
        self._ai_fd_v_scale.setValue(4.0)
        for w in self._ai_fd_v_controls:
            w.setEnabled(False)
        self._vt_axis.setCurrentIndex(0)
        self._vt_ppu.setValue(5.0)
        self._vt_wrap.setValue(0.0)
        self._vt_tick_side.setCurrentIndex(0)
        self._vt_tick_color.set_rgba(None)
        self._vt_bg_chk.setChecked(False)
        self._vt_bg_color.setEnabled(False)
        self._vt_bg_color.set_rgba(None)
        self._vt_ticks.load([])
        self._vt_labels_cache = {}
        self._vt_label_interval.setValue(0.0)
        self._vt_label_format.clear()
        self._vt_label_offset.setValue(8.0)
        self._vt_label_side.setCurrentIndex(0)
        self._vt_label_justify.setCurrentIndex(0)
        self._vt_label_font_size.setValue(18.0)
        self._vt_label_emphasize_place.setValue(0.0)
        self._vt_label_emphasize_size.setValue(18.0)
        self._vt_label_font.clear()
        self._vt_label_bold.setChecked(False)
        self._vt_label_italic.setChecked(False)
        self._vt_bands.load([])
        self._vt_bugs.load([])
        self._txt_mode.setCurrentIndex(0)
        self._txt_stack.setCurrentIndex(0)
        self._txt_static.clear()
        self._txt_dr.clear()
        self._txt_fn.setCurrentIndex(0)
        self._txt_decimals.setValue(1)
        self._txt_width.setValue(0)
        self._txt_zerofill.setChecked(False)
        self._txt_fmt_custom.clear()
        self._txt_emphasize_place.setValue(0.0)
        self._txt_emphasize_size.setValue(12.0)
        self._txt_font_name.clear()
        self._txt_font_size.setValue(12.0)
        self._txt_bold.setChecked(False)
        self._txt_italic.setChecked(False)
        self._txt_color.set_rgba(None)
        self._txt_anchor_x.setCurrentIndex(0)
        self._txt_anchor_y.setCurrentIndex(0)
        self._extra = {}
        self._loading = False

    # ── Internal ──────────────────────────────────────────────────────────

    def _on_arc_ref_shape_change(self, idx: int) -> None:
        is_arrow = (self._ai_ref_shape.currentText().lower() == "arrow")
        self._ai_ref_width.setEnabled(is_arrow)
        self._ai_ref_filled.setEnabled(is_arrow)
        self._ai_ref_line_w.setEnabled(is_arrow and not self._ai_ref_filled.isChecked())

    def _on_arc_bg_toggle(self, on: int) -> None:
        enabled = bool(on)
        self._ai_arc_bg_color.setEnabled(enabled)
        self._ai_arc_bg_inset.setEnabled(enabled)

    def _on_ref_toggle(self, on: int) -> None:
        enabled = bool(on)
        for w in self._ai_ref_controls:
            w.setEnabled(enabled)

    def _on_slip_toggle(self, on: int) -> None:
        enabled = bool(on)
        for w in self._ai_slip_controls:
            w.setEnabled(enabled)
        if enabled:
            self._on_slip_style_toggle(self._ai_slip_filled.isChecked())

    def _on_fd_h_toggle(self, on: int) -> None:
        for w in self._ai_fd_h_controls:
            w.setEnabled(bool(on))

    def _on_fd_v_toggle(self, on: int) -> None:
        for w in self._ai_fd_v_controls:
            w.setEnabled(bool(on))

    def _on_slip_style_toggle(self, checked) -> None:
        filled = bool(checked) if isinstance(checked, bool) else bool(checked)
        self._ai_slip_line_w.setEnabled(
            not filled and self._ai_show_slip.isChecked()
        )

    def _emit(self):
        if not self._loading:
            self.changed.emit()

    def _on_type_changed(self, ct: str):
        is_ip   = ct == "ImagePanel"
        is_ss   = ct == "SpriteSheet"
        is_st   = ct == "ScrollingTape"
        is_img  = is_ip or is_ss or is_st
        is_line = ct == "Line"
        is_arc  = ct == "Arc"
        is_frt  = ct == "FilledRect"
        is_poly = ct == "Polygon"
        is_vt   = ct == "VectorTape"
        is_text = ct == "Text"
        is_vec  = ct == "Vector"
        is_ai   = ct == "AttitudeIndicator"
        is_ng   = ct == "NeedleGauge"
        is_cr   = ct == "VectorCompassRose"
        is_re   = ct == "RotaryEncoder"

        # Position: hide for types that define geometry without a single centre point
        self._pos_sec.setVisible(not is_line and not is_arc and not is_poly and not is_ai
                                  and not is_ng and not is_cr)

        # Texture section visible for image types; atlas detail only for ImagePanel
        self._tex_sec.setVisible(is_img)
        self._atlas_detail.setVisible(is_ip)
        self._tex_edit_btn.setVisible(is_ip)

        # Type-specific sections
        self._ss_sec.setVisible(is_ss)
        self._st_sec.setVisible(is_st)
        self._txt_sec.setVisible(is_text)
        self._line_sec.setVisible(is_line)
        self._arc_sec.setVisible(is_arc)
        self._frt_sec.setVisible(is_frt)
        self._poly_sec.setVisible(is_poly)
        self._vec_sec.setVisible(is_vec)
        self._vt_sec.setVisible(is_vt)
        self._ai_sec.setVisible(is_ai)
        self._ng_sec.setVisible(is_ng)
        self._cr_sec.setVisible(is_cr)
        self._re_sec.setVisible(is_re)

        # Rotation and Translation: ImagePanel only
        self._rot_sec.setVisible(is_ip)
        self._tr_sec.setVisible(is_ip)

        # Animation: SpriteSheet, ScrollingTape, and VectorTape (scroll dataref)
        self._anim_sec.setVisible(is_ss or is_st or is_vt)

        # Viewport clip: image types, VectorTape, and VectorCompassRose;
        # AI uses its own viewport spinboxes
        self._vp_sec.setVisible(is_img or is_vt or is_cr)
        if is_vt:
            self._vp_sec.set_active(True)
        # VectorTape: x/y comes from Position section; only W/H shown in Viewport Clip
        self._vp_sec._form.setRowVisible(self._vp_xy_row, not is_vt)

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

    def _pick_label_font(self) -> None:
        from PySide6.QtGui import QFont
        from gauge_core.font_utils import strip_style_suffix
        current_name = self._vt_label_font.text().strip() or "Arial"
        current_size = int(self._vt_label_font_size.value())
        initial = QFont(current_name, current_size)
        initial.setBold(self._vt_label_bold.isChecked())
        initial.setItalic(self._vt_label_italic.isChecked())
        ok, font = QFontDialog.getFont(initial, self, "Choose label font")
        if ok:
            self._vt_label_font.setText(strip_style_suffix(font.family()))
            self._vt_label_font_size.setValue(float(font.pointSize()))
            self._vt_label_bold.setChecked(font.bold())
            self._vt_label_italic.setChecked(font.italic())
            self._emit()

    def _pick_ai_ladder_font(self) -> None:
        from PySide6.QtGui import QFont
        from gauge_core.font_utils import strip_style_suffix
        current_name = self._ai_ladder_font.text().strip() or "Arial"
        current_size = self._ai_font_size.value()
        initial = QFont(current_name, current_size)
        initial.setBold(self._ai_ladder_bold.isChecked())
        initial.setItalic(self._ai_ladder_italic.isChecked())
        ok, font = QFontDialog.getFont(initial, self, "Choose ladder font")
        if ok:
            self._ai_ladder_font.setText(strip_style_suffix(font.family()))
            self._ai_font_size.setValue(font.pointSize())
            self._ai_ladder_bold.setChecked(font.bold())
            self._ai_ladder_italic.setChecked(font.italic())
            self._emit()

    def _pick_txt_font(self) -> None:
        from PySide6.QtGui import QFont
        from gauge_core.font_utils import strip_style_suffix
        current_name = self._txt_font_name.text().strip() or "Arial"
        current_size = int(self._txt_font_size.value())
        initial = QFont(current_name, current_size)
        initial.setBold(self._txt_bold.isChecked())
        initial.setItalic(self._txt_italic.isChecked())
        ok, font = QFontDialog.getFont(initial, self, "Choose font")
        if ok:
            self._txt_font_name.setText(strip_style_suffix(font.family()))
            self._txt_font_size.setValue(float(font.pointSize()))
            self._txt_bold.setChecked(font.bold())
            self._txt_italic.setChecked(font.italic())
            self._emit()

    def _on_vec_cap_changed(self, text: str) -> None:
        self._vec_cap_width.setEnabled(text != "none")
        self._vec_cap_height.setEnabled(text == "triangle")
        self._vec_cap_filled.setEnabled(text == "triangle")
        self._vec_hide_if_short.setEnabled(text == "triangle")

    def _on_txt_mode_changed(self, idx: int) -> None:
        self._txt_stack.setCurrentIndex(idx)

    def _update_txt_format(self) -> None:
        d = self._txt_decimals.value()
        w = self._txt_width.value()
        z = self._txt_zerofill.isChecked()
        fill = "0" if z and w > 0 else ""
        width_str = str(w) if w > 0 else ""
        fmt = "{:" + fill + width_str + "." + str(d) + "f}"
        if not self._txt_fmt_custom.text().strip():
            self._txt_fmt_preview.setText(fmt)

    def _on_txt_fmt_custom_changed(self) -> None:
        custom = self._txt_fmt_custom.text().strip()
        if custom:
            self._txt_fmt_preview.setText(custom)
        else:
            self._update_txt_format()

    def _pick_dataref(self, lineedit: QLineEdit) -> None:
        from gauge_designer.dataref_picker import DatarefPickerDialog
        dlg = DatarefPickerDialog(current=lineedit.text().strip(), parent=self)
        if dlg.exec() == QDialog.Accepted:
            dr = dlg.selected_dataref()
            if dr:
                lineedit.setText(dr)
                self._emit()

    def _open_tex_editor(
        self,
        tex_field: QLineEdit,
        ox_sb: QSpinBox, oy_sb: QSpinBox,
        cw_sb: QSpinBox, ch_sb: QSpinBox,
    ) -> None:
        """Open the texture editor for any texture field + origin/cliprect spinboxes."""
        tex_rel = tex_field.text().strip()
        if not tex_rel:
            return
        tex_abs = str((Path(self._yaml_dir) / tex_rel).resolve()) if self._yaml_dir else tex_rel
        from gauge_designer.texture_editor import TextureEditorDialog
        dlg = TextureEditorDialog(
            texture_path=tex_abs,
            clip_w=cw_sb.value(),
            clip_h=ch_sb.value(),
            origin_x=ox_sb.value(),
            origin_y=oy_sb.value(),
            parent=self,
        )
        if dlg.exec() == QDialog.Accepted:
            cw, ch, ox, oy = dlg.get_values()
            self._loading = True
            cw_sb.setValue(cw); ch_sb.setValue(ch)
            ox_sb.setValue(ox); oy_sb.setValue(oy)
            self._loading = False
            self._emit()

    def _open_texture_editor(self):
        """Edit button handler for the main ImagePanel texture."""
        self._open_tex_editor(
            self._tex,
            self._orig_x, self._orig_y,
            self._clip_w, self._clip_h,
        )

    def _browse_tex(self, target: QLineEdit | None = None):
        """Open a file browser for a texture. *target* defaults to self._tex."""
        if target is None:
            target = self._tex
        start = self._yaml_dir
        if target.text() and self._yaml_dir:
            try:
                start = str((Path(self._yaml_dir) / target.text()).resolve())
            except Exception:
                pass
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Texture", start, "Images (*.png *.jpg *.bmp)"
        )
        if not path:
            return
        if self._yaml_dir:
            rel = os.path.relpath(path, self._yaml_dir).replace("\\", "/")
            target.setText(rel)
        else:
            target.setText(path)
        self._emit()
