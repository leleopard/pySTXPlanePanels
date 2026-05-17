"""Properties form for a single instrument entry within a panel."""

from pathlib import Path

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

    def load(self, entry: dict):
        self._loading = True
        self._file.setText(str(entry.get("file", "")))
        pos = entry.get("position", [0, 0])
        self._pos_x.setValue(int(pos[0]))
        self._pos_y.setValue(int(pos[1]))
        self._scale.setValue(float(entry.get("scale", 1.0)))
        self._loading = False

    def get_data(self) -> dict:
        data: dict = {"file": self._file.text().strip()}
        data["position"] = [self._pos_x.value(), self._pos_y.value()]
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
