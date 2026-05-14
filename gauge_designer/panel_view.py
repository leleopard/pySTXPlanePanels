"""Panel tab — compose and edit a panel YAML (list of instruments at positions)."""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QSplitter, QListWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox,
    QSpinBox, QFileDialog,
)
from PySide6.QtCore import Qt, Signal

from gauge_designer.panel_form import PanelForm
from gauge_designer.panel_canvas import PanelCanvas


class PanelView(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._instruments: list[dict] = []
        self._yaml_dir: str = ""
        self._loading = False

        # Panel size bar
        size_bar = QHBoxLayout()
        size_bar.setContentsMargins(0, 0, 0, 4)
        size_bar.setSpacing(4)
        size_bar.addWidget(QLabel("Panel size:"))
        self._panel_w = QSpinBox(); self._panel_w.setRange(1, 9999); self._panel_w.setFixedWidth(90)
        self._panel_h = QSpinBox(); self._panel_h.setRange(1, 9999); self._panel_h.setFixedWidth(90)
        self._panel_w.valueChanged.connect(self._on_size_changed)
        self._panel_h.valueChanged.connect(self._on_size_changed)
        size_bar.addWidget(self._panel_w)
        size_bar.addWidget(QLabel("×"))
        size_bar.addWidget(self._panel_h)
        size_bar.addStretch()

        splitter = QSplitter(Qt.Horizontal)

        # Pane 1: instrument list + toolbar
        left = QWidget()
        ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("Instruments"))
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_row_changed)
        ll.addWidget(self._list)
        btn_bar = QHBoxLayout(); btn_bar.setSpacing(2)
        for label, slot in [("+", self._add_instrument), ("−", self._remove_instrument),
                            ("▲", self._move_up), ("▼", self._move_down)]:
            btn = QPushButton(label); btn.setFixedWidth(32)
            btn.clicked.connect(slot)
            btn_bar.addWidget(btn)
        btn_bar.addStretch()
        ll.addLayout(btn_bar)

        # Pane 2: entry properties form
        mid = QWidget()
        ml = QVBoxLayout(mid); ml.setContentsMargins(0, 0, 0, 0)
        ml.addWidget(QLabel("Properties"))
        self._form = PanelForm()
        self._form.changed.connect(self._on_form_changed)
        ml.addWidget(self._form)
        ml.addStretch()

        # Pane 3: panel layout canvas
        right = QWidget()
        rl = QVBoxLayout(right); rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel("Layout"))
        self._canvas = PanelCanvas()
        self._canvas.instrument_selected.connect(self._on_canvas_selected)
        rl.addWidget(self._canvas)

        splitter.addWidget(left)
        splitter.addWidget(mid)
        splitter.addWidget(right)
        splitter.setSizes([180, 260, 420])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(size_bar)
        layout.addWidget(splitter)

    # ── Public API ────────────────────────────────────────────────────────

    def load(self, panel_data: dict, yaml_path: str = ""):
        self._loading = True
        self._yaml_dir = str(Path(yaml_path).parent) if yaml_path else ""
        self._instruments = panel_data.setdefault("instruments", [])
        self._list.clear()
        self._form.clear()

        w, h = panel_data.get("size", [1540, 920])
        self._panel_w.blockSignals(True); self._panel_h.blockSignals(True)
        self._panel_w.setValue(int(w)); self._panel_h.setValue(int(h))
        self._panel_w.blockSignals(False); self._panel_h.blockSignals(False)

        for entry in self._instruments:
            self._list.addItem(Path(entry.get("file", "(unknown)")).stem)

        self._loading = False
        self._form.set_yaml_dir(self._yaml_dir)
        self._canvas.load(panel_data, self._yaml_dir)
        if self._instruments:
            self._list.setCurrentRow(0)

    def clear(self):
        self._loading = True
        self._instruments = []
        self._yaml_dir = ""
        self._list.clear()
        self._form.clear()
        self._loading = False
        self._canvas.clear()

    def get_instruments(self) -> list[dict]:
        return self._instruments

    def get_size(self) -> list[int]:
        return [self._panel_w.value(), self._panel_h.value()]

    # ── Panel size ────────────────────────────────────────────────────────

    def _on_size_changed(self):
        if not self._loading:
            self._canvas.set_size(self._panel_w.value(), self._panel_h.value())
            self.changed.emit()

    # ── Row selection ─────────────────────────────────────────────────────

    def _on_row_changed(self, row: int):
        if 0 <= row < len(self._instruments):
            self._form.load(self._instruments[row])
        else:
            self._form.clear()
        self._canvas.set_selected(row)

    # ── Form change ───────────────────────────────────────────────────────

    def _on_form_changed(self):
        row = self._list.currentRow()
        if row < 0 or row >= len(self._instruments):
            return
        updated = self._form.get_data()
        self._instruments[row].clear()
        self._instruments[row].update(updated)
        label = Path(updated.get("file", "(unknown)")).stem
        if self._list.item(row):
            self._list.item(row).setText(label)
        self._canvas.refresh()
        self.changed.emit()

    # ── Canvas selection ──────────────────────────────────────────────────

    def _on_canvas_selected(self, idx: int):
        if self._list.currentRow() != idx:
            self._list.setCurrentRow(idx)

    # ── List toolbar ──────────────────────────────────────────────────────

    def _add_instrument(self):
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
        entry = {"file": rel, "position": [0, 0]}
        self._instruments.append(entry)
        self._list.addItem(Path(rel).stem)
        self._list.setCurrentRow(len(self._instruments) - 1)
        self._canvas.refresh()
        self.changed.emit()

    def _remove_instrument(self):
        row = self._list.currentRow()
        if row < 0:
            return
        label = Path(self._instruments[row].get("file", "?")).stem
        if QMessageBox.question(
            self, "Remove Instrument", f"Remove '{label}'?",
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        self._instruments.pop(row)
        self._list.takeItem(row)
        self._canvas.refresh()
        self.changed.emit()

    def _move_up(self):
        row = self._list.currentRow()
        if row <= 0:
            return
        self._instruments.insert(row - 1, self._instruments.pop(row))
        item = self._list.takeItem(row)
        self._list.insertItem(row - 1, item)
        self._list.setCurrentRow(row - 1)
        self._canvas.refresh()
        self.changed.emit()

    def _move_down(self):
        row = self._list.currentRow()
        if row < 0 or row >= len(self._instruments) - 1:
            return
        self._instruments.insert(row + 1, self._instruments.pop(row))
        item = self._list.takeItem(row)
        self._list.insertItem(row + 1, item)
        self._list.setCurrentRow(row + 1)
        self._canvas.refresh()
        self.changed.emit()
