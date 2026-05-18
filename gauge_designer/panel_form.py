"""Properties forms for panel entries.

Three form types:
  PanelForm          — plain instrument entry (file, position, scale)
  GridForm           — grid layout entry (name, position, columns, rows, cell size)
  GridInstrumentForm — instrument within a grid (file, col, row, scale)
"""

from pathlib import Path

from gauge_designer.ui_utils import is_y_down
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QDoubleSpinBox, QFileDialog,
)
from PySide6.QtCore import Signal


class PanelForm(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._yaml_dir: str = ""
        self._ref_height: int = 920
        self._item_height: int = 310
        self._loading = False

        form = QFormLayout(self)
        form.setContentsMargins(6, 4, 6, 4)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)

        # Instrument file
        file_row = QWidget()
        frl = QHBoxLayout(file_row)
        frl.setContentsMargins(0, 0, 0, 0); frl.setSpacing(4)
        self._file = QLineEdit()
        self._file.editingFinished.connect(self._emit)
        frl.addWidget(self._file)
        btn = QPushButton("…"); btn.setFixedWidth(26)
        btn.clicked.connect(self._browse)
        frl.addWidget(btn)
        form.addRow("File", file_row)

        # Position X / Y
        pos_row = QWidget()
        prl = QHBoxLayout(pos_row)
        prl.setContentsMargins(0, 0, 0, 0); prl.setSpacing(4)
        self._pos_x = QSpinBox(); self._pos_x.setRange(-9999, 9999); self._pos_x.setFixedWidth(80)
        self._pos_y = QSpinBox(); self._pos_y.setRange(-9999, 9999); self._pos_y.setFixedWidth(80)
        for w in (self._pos_x, self._pos_y):
            w.valueChanged.connect(self._emit)
        prl.addWidget(self._pos_x)
        prl.addWidget(QLabel("/"))
        prl.addWidget(self._pos_y)
        prl.addStretch()
        form.addRow("Position X / Y", pos_row)

        # Scale
        self._scale = QDoubleSpinBox()
        self._scale.setRange(0.01, 10.0)
        self._scale.setDecimals(3)
        self._scale.setSingleStep(0.05)
        self._scale.setValue(1.0)
        self._scale.setMinimumWidth(90)
        self._scale.valueChanged.connect(self._emit)
        form.addRow("Scale", self._scale)

    def set_yaml_dir(self, d: str):
        self._yaml_dir = d

    def set_ref_height(self, h: int):
        self._ref_height = h

    def set_item_height(self, h: int):
        self._item_height = h

    def _y_disp(self, y: int) -> int:
        """Convert YAML y-up (bottom-left origin) ↔ display y (self-inverse).
        In y-down mode the displayed origin is the top-left of the instrument.
        """
        if is_y_down():
            return self._ref_height - y - self._item_height
        return y

    def load(self, entry: dict):
        self._loading = True
        self._file.setText(str(entry.get("file", "")))
        pos = entry.get("position", [0, 0])
        self._pos_x.setValue(int(pos[0]))
        self._pos_y.setValue(self._y_disp(int(pos[1])))
        self._scale.setValue(float(entry.get("scale", 1.0)))
        self._loading = False

    def get_data(self) -> dict:
        data: dict = {"file": self._file.text().strip()}
        data["position"] = [self._pos_x.value(), self._y_disp(self._pos_y.value())]
        scale = round(self._scale.value(), 3)
        if abs(scale - 1.0) > 1e-4:
            data["scale"] = scale
        return data

    def clear(self):
        self._loading = True
        self._file.clear()
        self._pos_x.setValue(0)
        self._pos_y.setValue(0)
        self._scale.setValue(1.0)
        self._loading = False

    def _emit(self):
        if not self._loading:
            self.changed.emit()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Instrument YAML", self._yaml_dir,
            "YAML files (*.yaml *.yml)"
        )
        if not path:
            return
        try:
            rel = str(Path(path).relative_to(self._yaml_dir)).replace("\\", "/")
        except ValueError:
            rel = path
        self._file.setText(rel)
        self._emit()


# ---------------------------------------------------------------------------


class GridForm(QWidget):
    """Properties form for a grid layout entry."""
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ref_height: int = 920
        self._loading = False

        form = QFormLayout(self)
        form.setContentsMargins(6, 4, 6, 4)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)

        self._name = QLineEdit()
        self._name.editingFinished.connect(self._emit)
        form.addRow("Name", self._name)

        pos_row = QWidget()
        prl = QHBoxLayout(pos_row); prl.setContentsMargins(0,0,0,0); prl.setSpacing(4)
        self._pos_x = QSpinBox(); self._pos_x.setRange(-9999, 9999); self._pos_x.setFixedWidth(80)
        self._pos_y = QSpinBox(); self._pos_y.setRange(-9999, 9999); self._pos_y.setFixedWidth(80)
        for w in (self._pos_x, self._pos_y):
            w.valueChanged.connect(self._emit)
        prl.addWidget(self._pos_x); prl.addWidget(QLabel("/")); prl.addWidget(self._pos_y)
        prl.addStretch()
        form.addRow("Position X / Y", pos_row)

        cr_row = QWidget()
        crl = QHBoxLayout(cr_row); crl.setContentsMargins(0,0,0,0); crl.setSpacing(4)
        self._cols = QSpinBox(); self._cols.setRange(1, 99); self._cols.setFixedWidth(70)
        self._rows_sb = QSpinBox(); self._rows_sb.setRange(1, 99); self._rows_sb.setFixedWidth(70)
        for w in (self._cols, self._rows_sb):
            w.valueChanged.connect(self._emit)
        crl.addWidget(self._cols); crl.addWidget(QLabel("cols"))
        crl.addWidget(self._rows_sb); crl.addWidget(QLabel("rows"))
        crl.addStretch()
        form.addRow("Grid size", cr_row)

        sz_row = QWidget()
        szl = QHBoxLayout(sz_row); szl.setContentsMargins(0,0,0,0); szl.setSpacing(4)
        self._cell_w = QSpinBox(); self._cell_w.setRange(1, 9999); self._cell_w.setFixedWidth(80)
        self._cell_h = QSpinBox(); self._cell_h.setRange(1, 9999); self._cell_h.setFixedWidth(80)
        for w in (self._cell_w, self._cell_h):
            w.valueChanged.connect(self._emit)
        szl.addWidget(self._cell_w); szl.addWidget(QLabel("×")); szl.addWidget(self._cell_h)
        szl.addStretch()
        form.addRow("Cell W × H", sz_row)

    def _y_disp(self, y: int, grid_h: int) -> int:
        """Convert YAML y-up (bottom-left origin) ↔ display y (self-inverse).
        In y-down mode the displayed origin is the top-left of the grid.
        """
        if is_y_down():
            return self._ref_height - y - grid_h
        return y

    def set_ref_height(self, h: int):
        self._ref_height = h

    def load(self, grid_cfg: dict):
        self._loading = True
        self._name.setText(grid_cfg.get("name", ""))
        pos = grid_cfg.get("position", [0, 0])
        rows = int(grid_cfg.get("rows", 1))
        ch = int(grid_cfg.get("cell_height", 310))
        grid_h = rows * ch
        self._pos_x.setValue(int(pos[0]))
        self._pos_y.setValue(self._y_disp(int(pos[1]), grid_h))
        self._cols.setValue(int(grid_cfg.get("columns", 1)))
        self._rows_sb.setValue(int(grid_cfg.get("rows", 1)))
        self._cell_w.setValue(int(grid_cfg.get("cell_width", 310)))
        self._cell_h.setValue(int(grid_cfg.get("cell_height", 310)))
        self._loading = False

    def get_data(self) -> dict:
        grid_h = self._rows_sb.value() * self._cell_h.value()
        data: dict = {
            "position": [self._pos_x.value(), self._y_disp(self._pos_y.value(), grid_h)],
            "columns": self._cols.value(),
            "rows": self._rows_sb.value(),
            "cell_width": self._cell_w.value(),
            "cell_height": self._cell_h.value(),
        }
        name = self._name.text().strip()
        if name:
            data["name"] = name
        return data

    def clear(self):
        self._loading = True
        self._name.clear()
        self._pos_x.setValue(0); self._pos_y.setValue(0)
        self._cols.setValue(2); self._rows_sb.setValue(1)
        self._cell_w.setValue(310); self._cell_h.setValue(310)
        self._loading = False

    def _emit(self):
        if not self._loading:
            self.changed.emit()


# ---------------------------------------------------------------------------


class GridInstrumentForm(QWidget):
    """Properties form for an instrument entry inside a grid.

    Grid position is determined entirely by list order (first = top-left,
    filling left-to-right then top-to-bottom), so there are no col/row fields.
    """
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._yaml_dir: str = ""
        self._loading = False

        form = QFormLayout(self)
        form.setContentsMargins(6, 4, 6, 4)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)

        file_row = QWidget()
        frl = QHBoxLayout(file_row); frl.setContentsMargins(0,0,0,0); frl.setSpacing(4)
        self._file = QLineEdit()
        self._file.editingFinished.connect(self._emit)
        frl.addWidget(self._file)
        btn = QPushButton("…"); btn.setFixedWidth(26)
        btn.clicked.connect(self._browse)
        frl.addWidget(btn)
        form.addRow("File", file_row)

        self._scale = QDoubleSpinBox()
        self._scale.setRange(0.01, 10.0); self._scale.setDecimals(3)
        self._scale.setSingleStep(0.05); self._scale.setValue(1.0)
        self._scale.setMinimumWidth(90)
        self._scale.valueChanged.connect(self._emit)
        form.addRow("Scale", self._scale)

        form.addRow(QLabel("Drag to reorder within the grid."))

    def set_yaml_dir(self, d: str):
        self._yaml_dir = d

    def load(self, entry: dict):
        self._loading = True
        self._file.setText(str(entry.get("file", "")))
        self._scale.setValue(float(entry.get("scale", 1.0)))
        self._loading = False

    def get_data(self) -> dict:
        data: dict = {"file": self._file.text().strip()}
        scale = round(self._scale.value(), 3)
        if abs(scale - 1.0) > 1e-4:
            data["scale"] = scale
        return data

    def clear(self):
        self._loading = True
        self._file.clear()
        self._scale.setValue(1.0)
        self._loading = False

    def _emit(self):
        if not self._loading:
            self.changed.emit()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Instrument YAML", self._yaml_dir,
            "YAML files (*.yaml *.yml)"
        )
        if not path:
            return
        try:
            rel = str(Path(path).relative_to(self._yaml_dir)).replace("\\", "/")
        except ValueError:
            rel = path
        self._file.setText(rel)
        self._emit()
