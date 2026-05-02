from PySide6.QtWidgets import (
    QWidget, QSplitter, QListWidget, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QInputDialog, QMessageBox,
)
from PySide6.QtCore import Qt, Signal


def _coerce(text: str):
    """bool > int > float > str, matching how PyYAML round-trips values."""
    if text.lower() == "true":
        return True
    if text.lower() == "false":
        return False
    try:
        if "." not in text and "e" not in text.lower():
            return int(text)
        return float(text)
    except ValueError:
        return text


def _item_key_path(item: QTreeWidgetItem) -> list:
    """Return key/index path from the component-root to this item."""
    path = []
    while item is not None:
        key = item.text(0)
        if key.startswith("[") and key.endswith("]"):
            path.append(int(key[1:-1]))
        else:
            path.append(key)
        item = item.parent()
    path.reverse()
    return path


def _set_nested(data, path: list, value):
    for key in path[:-1]:
        data = data[key]
    data[path[-1]] = value


def _populate_tree(parent, data, editable: bool = True):
    """Recursively build tree rows from a dict, list, or scalar."""
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                node = QTreeWidgetItem(parent, [str(key), ""])
                _populate_tree(node, value, editable)
            else:
                item = QTreeWidgetItem(parent, [str(key), str(value)])
                if editable:
                    item.setFlags(item.flags() | Qt.ItemIsEditable)
    elif isinstance(data, list):
        for i, elem in enumerate(data):
            if isinstance(elem, (dict, list)):
                node = QTreeWidgetItem(parent, [f"[{i}]", ""])
                _populate_tree(node, elem, editable)
            else:
                item = QTreeWidgetItem(parent, [f"[{i}]", str(elem)])
                if editable:
                    item.setFlags(item.flags() | Qt.ItemIsEditable)


class InstrumentView(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._components: list[dict] = []
        self._loading = False

        splitter = QSplitter(Qt.Horizontal)

        # ── Left: component list + toolbar ──────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Components"))
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_row_changed)
        left_layout.addWidget(self._list)

        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(2)
        for label, slot in [("▲", self._move_up), ("▼", self._move_down),
                             ("+", self._add_component), ("−", self._remove_component)]:
            btn = QPushButton(label)
            btn.setFixedWidth(32)
            btn.clicked.connect(slot)
            btn_bar.addWidget(btn)
        btn_bar.addStretch()
        left_layout.addLayout(btn_bar)

        # ── Right: property tree ─────────────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("Properties"))
        self._tree = QTreeWidget()
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels(["Key", "Value"])
        self._tree.setColumnWidth(0, 160)
        self._tree.itemChanged.connect(self._on_item_changed)
        right_layout.addWidget(self._tree)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([200, 400])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(splitter)

    # ── Public API ───────────────────────────────────────────────────────

    def load(self, instrument_data: dict):
        self._loading = True
        self._list.clear()
        self._tree.blockSignals(True)
        self._tree.clear()
        self._tree.blockSignals(False)
        self._components = instrument_data.get("components", [])
        for comp in self._components:
            self._list.addItem(comp.get("name", "(unnamed)"))
        self._loading = False
        if self._components:
            self._list.setCurrentRow(0)

    def clear(self):
        self._loading = True
        self._list.clear()
        self._tree.blockSignals(True)
        self._tree.clear()
        self._tree.blockSignals(False)
        self._components = []
        self._loading = False

    def get_components(self) -> list[dict]:
        return self._components

    # ── Tree editing ──────────────────────────────────────────────────────

    def _on_row_changed(self, row: int):
        self._tree.blockSignals(True)
        self._tree.clear()
        if 0 <= row < len(self._components):
            comp = self._components[row]
            for key, value in comp.items():
                if isinstance(value, (dict, list)):
                    node = QTreeWidgetItem(self._tree, [key, ""])
                    _populate_tree(node, value, editable=True)
                    node.setExpanded(True)
                else:
                    item = QTreeWidgetItem(self._tree, [key, str(value)])
                    item.setFlags(item.flags() | Qt.ItemIsEditable)
        self._tree.blockSignals(False)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        if column != 1 or self._loading:
            return
        row = self._list.currentRow()
        if row < 0 or row >= len(self._components):
            return
        path = _item_key_path(item)
        value = _coerce(item.text(1))
        try:
            _set_nested(self._components[row], path, value)
        except (KeyError, IndexError, TypeError):
            return
        if path == ["name"]:
            self._list.currentItem().setText(str(value))
        self.changed.emit()

    # ── List toolbar ──────────────────────────────────────────────────────

    def _move_up(self):
        row = self._list.currentRow()
        if row <= 0:
            return
        self._components.insert(row - 1, self._components.pop(row))
        item = self._list.takeItem(row)
        self._list.insertItem(row - 1, item)
        self._list.setCurrentRow(row - 1)
        self.changed.emit()

    def _move_down(self):
        row = self._list.currentRow()
        if row < 0 or row >= len(self._components) - 1:
            return
        self._components.insert(row + 1, self._components.pop(row))
        item = self._list.takeItem(row)
        self._list.insertItem(row + 1, item)
        self._list.setCurrentRow(row + 1)
        self.changed.emit()

    def _add_component(self):
        name, ok = QInputDialog.getText(self, "Add Component", "Component name:")
        if not ok or not name.strip():
            return
        new_comp = {
            "name": name.strip(),
            "type": "ImagePanel",
            "texture": "../assets/c172_text_standard6.png",
            "origin": [0, 0],
            "cliprect": [100, 100],
            "position": [155, 155],
        }
        self._components.append(new_comp)
        self._list.addItem(new_comp["name"])
        self._list.setCurrentRow(len(self._components) - 1)
        self.changed.emit()

    def _remove_component(self):
        row = self._list.currentRow()
        if row < 0:
            return
        name = self._components[row].get("name", "(unnamed)")
        reply = QMessageBox.question(
            self, "Remove Component", f"Remove '{name}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._components.pop(row)
        self._list.takeItem(row)
        self.changed.emit()
