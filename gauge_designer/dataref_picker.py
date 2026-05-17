"""DatarefPickerDialog — searchable X-Plane dataref browser.

Loads the static DataRefs.txt bundled with the designer on first use and
caches the model for the session.  Subsequent opens are instant.

Usage:
    dlg = DatarefPickerDialog(current="sim/cockpit/...", parent=self)
    if dlg.exec() == QDialog.Accepted:
        dataref = dlg.selected_dataref()
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QSortFilterProxyModel
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableView,
    QVBoxLayout,
)

_DATAREFS_FILE = Path(__file__).parent / "data" / "DataRefs.txt"

# Parsed once per session; reused for all picker opens.
_CACHED_MODEL: QStandardItemModel | None = None


def _build_model() -> QStandardItemModel:
    global _CACHED_MODEL
    if _CACHED_MODEL is not None:
        return _CACHED_MODEL

    model = QStandardItemModel()
    model.setHorizontalHeaderLabels(["Dataref", "Type", "W", "Units", "Description"])

    with open(_DATAREFS_FILE, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line[0].isdigit():   # skip blank and version header
                continue
            parts = line.split("\t")
            if not parts[0].strip():
                continue
            while len(parts) < 5:
                parts.append("")
            row = [QStandardItem(p.strip()) for p in parts[:5]]
            for item in row:
                item.setEditable(False)
            model.appendRow(row)

    _CACHED_MODEL = model
    return _CACHED_MODEL


class DatarefPickerDialog(QDialog):
    def __init__(self, current: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Dataref")
        self.resize(980, 580)

        self._selected: str = current

        # Model + proxy
        source = _build_model()
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(source)
        self._proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self._proxy.setFilterKeyColumn(-1)   # search across all columns

        # Search bar
        self._search = QLineEdit()
        self._search.setPlaceholderText("Type to filter — searches dataref path and description…")
        self._search.textChanged.connect(self._proxy.setFilterFixedString)
        if current:
            self._search.setText(current)

        # Table
        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSelectionBehavior(QTableView.SelectRows)
        self._table.setSelectionMode(QTableView.SingleSelection)
        self._table.setEditTriggers(QTableView.NoEditTriggers)
        self._table.setSortingEnabled(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setWordWrap(False)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.Stretch)
        self._table.doubleClicked.connect(self._on_double_click)
        self._table.selectionModel().currentChanged.connect(self._on_current_changed)

        # Pre-select the current value if it exists in the list
        if current:
            hits = self._proxy.match(
                self._proxy.index(0, 0), Qt.DisplayRole,
                current, 1, Qt.MatchExactly,
            )
            if hits:
                self._table.setCurrentIndex(hits[0])
                self._table.scrollTo(hits[0])

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Search:"))
        layout.addWidget(self._search)
        layout.addWidget(self._table, 1)
        layout.addWidget(btns)

        self._search.setFocus()

    # ── Callbacks ─────────────────────────────────────────────────────────

    def _on_current_changed(self, current, _prev):
        src = self._proxy.mapToSource(current)
        item = self._proxy.sourceModel().item(src.row(), 0)
        if item:
            self._selected = item.text()

    def _on_double_click(self, index):
        src = self._proxy.mapToSource(index)
        item = self._proxy.sourceModel().item(src.row(), 0)
        if item:
            self._selected = item.text()
            self.accept()

    def selected_dataref(self) -> str:
        return self._selected
