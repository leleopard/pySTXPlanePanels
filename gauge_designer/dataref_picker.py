"""DatarefPickerDialog — searchable X-Plane dataref browser.

Loads the static DataRefs.txt bundled with the designer on first use and
caches the tree model for the session.  Subsequent opens are instant.

The tree mirrors the dataref path hierarchy:
    sim/
      cockpit2/
        gauges/
          indicators/
            airspeed_kts_pilot   [float]  [r]  kts  Indicated airspeed

Typing in the search box filters leaves by full path and description;
matching branches are auto-expanded.

Usage:
    dlg = DatarefPickerDialog(current="sim/cockpit/...", parent=self)
    if dlg.exec() == QDialog.Accepted:
        dataref = dlg.selected_dataref()
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QSortFilterProxyModel, QModelIndex
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTreeView,
    QVBoxLayout,
)

_DATAREFS_FILE = Path(__file__).parent / "data" / "DataRefs.txt"

# Built once per session.
_CACHED_MODEL: QStandardItemModel | None = None
_CACHED_LEAF_ITEMS: dict[str, QStandardItem] = {}   # full_path → leaf item


def _build_model() -> QStandardItemModel:
    global _CACHED_MODEL, _CACHED_LEAF_ITEMS
    if _CACHED_MODEL is not None:
        return _CACHED_MODEL

    model = QStandardItemModel()
    model.setHorizontalHeaderLabels(["Dataref", "Type", "W", "Units", "Description"])

    # folder_key (tuple of segments) → QStandardItem
    folder_items: dict[tuple, QStandardItem] = {}

    with open(_DATAREFS_FILE, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line[0].isdigit():
                continue
            parts = line.split("\t")
            dataref = parts[0].strip()
            if not dataref:
                continue
            while len(parts) < 5:
                parts.append("")
            meta = [p.strip() for p in parts[1:5]]

            segments = dataref.split("/")

            # Build / reuse intermediate folder nodes
            parent_item = model.invisibleRootItem()
            for depth, seg in enumerate(segments[:-1]):
                key = tuple(segments[: depth + 1])
                if key not in folder_items:
                    node = QStandardItem(seg)
                    node.setEditable(False)
                    # Placeholder columns so the row has the right column count
                    placeholders = [QStandardItem("") for _ in range(4)]
                    for ph in placeholders:
                        ph.setEditable(False)
                    parent_item.appendRow([node] + placeholders)
                    folder_items[key] = node
                parent_item = folder_items[key]

            # Leaf node — store full path in UserRole for retrieval & filtering
            leaf = QStandardItem(segments[-1])
            leaf.setEditable(False)
            leaf.setData(dataref, Qt.UserRole)
            meta_items = [QStandardItem(m) for m in meta]
            for mi in meta_items:
                mi.setEditable(False)
            parent_item.appendRow([leaf] + meta_items)
            _CACHED_LEAF_ITEMS[dataref] = leaf

    _CACHED_MODEL = model
    return model


# ── Custom filter proxy ───────────────────────────────────────────────────────

class _DatarefFilterProxy(QSortFilterProxyModel):
    """Filters leaves by full path + description; folders shown if any child matches."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRecursiveFilteringEnabled(True)
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self._pat = ""

    def set_filter(self, text: str) -> None:
        self._pat = text.lower().strip()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        src = self.sourceModel()
        idx = src.index(source_row, 0, source_parent)
        item = src.itemFromIndex(idx)

        if not self._pat:
            return True

        # Folder — return False here; recursive mode will re-show it if a
        # descendant leaf passes the filter.
        if item and item.hasChildren():
            return False

        # Leaf — match full path (UserRole) and description (col 4)
        full_path = (item.data(Qt.UserRole) or "") if item else ""
        if self._pat in full_path.lower():
            return True

        desc_idx = src.index(source_row, 4, source_parent)
        desc_item = src.itemFromIndex(desc_idx)
        if desc_item and self._pat in desc_item.text().lower():
            return True

        return False


# ── Dialog ────────────────────────────────────────────────────────────────────

class DatarefPickerDialog(QDialog):
    def __init__(self, current: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Dataref")
        self.resize(1000, 640)

        self._selected: str = current

        # Model + proxy
        source = _build_model()
        self._proxy = _DatarefFilterProxy(self)
        self._proxy.setSourceModel(source)

        # Search bar
        self._search = QLineEdit()
        self._search.setPlaceholderText(
            "Filter — searches full dataref path and description…"
        )
        self._search.textChanged.connect(self._on_filter_changed)

        # Selection label
        self._sel_label = QLabel(current or "(none selected)")
        self._sel_label.setStyleSheet("color: #aaa; font-size: 11px;")

        # Tree
        self._tree = QTreeView()
        self._tree.setModel(self._proxy)
        self._tree.setSelectionBehavior(QTreeView.SelectRows)
        self._tree.setSelectionMode(QTreeView.SingleSelection)
        self._tree.setEditTriggers(QTreeView.NoEditTriggers)
        self._tree.setUniformRowHeights(True)
        self._tree.setAnimated(False)
        self._tree.setSortingEnabled(True)
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._tree.header().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._tree.header().setSectionResizeMode(4, QHeaderView.Stretch)
        self._tree.doubleClicked.connect(self._on_double_click)
        self._tree.selectionModel().currentChanged.connect(self._on_current_changed)

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Search:"))
        layout.addWidget(self._search)
        layout.addWidget(self._tree, 1)
        layout.addWidget(self._sel_label)
        layout.addWidget(btns)

        # Pre-select current value
        if current:
            self._search.setText(current)
            # Search fires _on_filter_changed which will expand + select

        self._search.setFocus()

    # ── Filter ────────────────────────────────────────────────────────────────

    def _on_filter_changed(self, text: str) -> None:
        self._proxy.set_filter(text)
        if text.strip():
            self._tree.expandAll()
        else:
            self._tree.collapseAll()
        # After filter, try to select the leaf that exactly matches the text
        self._try_select_exact(text.strip())

    def _try_select_exact(self, full_path: str) -> None:
        item = _CACHED_LEAF_ITEMS.get(full_path)
        if item is None:
            return
        src_idx = self._proxy.sourceModel().indexFromItem(item)
        proxy_idx = self._proxy.mapFromSource(src_idx)
        if proxy_idx.isValid():
            self._tree.setCurrentIndex(proxy_idx)
            self._tree.scrollTo(proxy_idx)

    # ── Selection callbacks ───────────────────────────────────────────────────

    def _on_current_changed(self, current: QModelIndex, _prev: QModelIndex) -> None:
        src_idx = self._proxy.mapToSource(current)
        item = self._proxy.sourceModel().itemFromIndex(src_idx)
        if item:
            path = item.data(Qt.UserRole)
            if path:  # leaves carry the full path; folders do not
                self._selected = path
                self._sel_label.setText(path)

    def _on_double_click(self, index: QModelIndex) -> None:
        src_idx = self._proxy.mapToSource(index)
        item = self._proxy.sourceModel().itemFromIndex(src_idx)
        if item:
            path = item.data(Qt.UserRole)
            if path:
                self._selected = path
                self.accept()

    def selected_dataref(self) -> str:
        return self._selected
