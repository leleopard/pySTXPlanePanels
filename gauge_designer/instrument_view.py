from PySide6.QtWidgets import (
    QWidget, QSplitter, QListWidget, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QLabel,
)
from PySide6.QtCore import Qt


def _populate_tree(parent: QTreeWidgetItem | QTreeWidget, data):
    """Recursively build tree rows from a dict, list, or scalar."""
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                node = QTreeWidgetItem(parent, [str(key), ""])
                _populate_tree(node, value)
            else:
                QTreeWidgetItem(parent, [str(key), str(value)])
    elif isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, (dict, list)):
                node = QTreeWidgetItem(parent, [f"[{i}]", ""])
                _populate_tree(node, item)
            else:
                QTreeWidgetItem(parent, [f"[{i}]", str(item)])
    else:
        if isinstance(parent, QTreeWidgetItem):
            parent.setText(1, str(data))


class InstrumentView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._components: list[dict] = []

        splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Components"))
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_row_changed)
        left_layout.addWidget(self._list)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("Properties"))
        self._tree = QTreeWidget()
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels(["Key", "Value"])
        self._tree.setColumnWidth(0, 160)
        right_layout.addWidget(self._tree)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([200, 400])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(splitter)

    def load(self, instrument_data: dict):
        self._list.clear()
        self._tree.clear()
        self._components = instrument_data.get("components", [])
        for comp in self._components:
            self._list.addItem(comp.get("name", "(unnamed)"))
        if self._components:
            self._list.setCurrentRow(0)

    def clear(self):
        self._list.clear()
        self._tree.clear()
        self._components = []

    def _on_row_changed(self, row: int):
        self._tree.clear()
        if row < 0 or row >= len(self._components):
            return
        comp = self._components[row]
        for key, value in comp.items():
            if isinstance(value, (dict, list)):
                node = QTreeWidgetItem(self._tree, [key, ""])
                _populate_tree(node, value)
                node.setExpanded(True)
            else:
                QTreeWidgetItem(self._tree, [key, str(value)])
