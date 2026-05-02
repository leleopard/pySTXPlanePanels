from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QSplitter, QListWidget, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QInputDialog, QMessageBox,
    QStyledItemDelegate, QStyleOptionViewItem,
)
from PySide6.QtCore import Qt, Signal, QEvent, QRect, QPoint
from PySide6.QtGui import QPainter, QPen, QBrush, QColor

from gauge_designer.canvas import InstrumentCanvas


# ── Eye icon drawing ─────────────────────────────────────────────────────────

def _draw_eye(painter: QPainter, rect: QRect, visible: bool):
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)

    fg = QColor(180, 180, 180) if visible else QColor(90, 90, 90)
    painter.setPen(QPen(fg, 1.5))
    painter.setBrush(Qt.NoBrush)

    cx = rect.center().x()
    cy = rect.center().y()
    ew = rect.width() - 4
    eh = max(rect.height() * 5 // 12, 5)

    painter.drawEllipse(QRect(cx - ew // 2, cy - eh // 2, ew, eh))

    pr = max(eh // 3, 2)
    painter.setBrush(QBrush(fg))
    painter.drawEllipse(QPoint(cx, cy), pr, pr)

    if not visible:
        painter.setPen(QPen(QColor(200, 60, 60), 1.5))
        painter.drawLine(rect.left() + 3, rect.bottom() - 2,
                         rect.right() - 3, rect.top() + 2)

    painter.restore()


class _EyeDelegate(QStyledItemDelegate):
    """Draws an eye icon on the right of each list item; click toggles visibility."""

    visibility_toggled = Signal(int, bool)  # row, new visible state
    EYE_W = 22

    def paint(self, painter, option, index):
        text_opt = QStyleOptionViewItem(option)
        text_opt.rect = option.rect.adjusted(0, 0, -(self.EYE_W + 6), 0)
        super().paint(painter, text_opt, index)
        vis = index.data(Qt.UserRole)
        _draw_eye(painter, self._eye_rect(option.rect),
                  vis if vis is not None else True)

    def _eye_rect(self, item_rect: QRect) -> QRect:
        sz = self.EYE_W
        return QRect(
            item_rect.right() - sz - 4,
            item_rect.top() + (item_rect.height() - sz) // 2,
            sz, sz,
        )

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.Type.MouseButtonRelease:
            if self._eye_rect(option.rect).contains(event.position().toPoint()):
                current = index.data(Qt.UserRole)
                new_val = not (current if current is not None else True)
                model.setData(index, new_val, Qt.UserRole)
                self.visibility_toggled.emit(index.row(), new_val)
                return True
        return super().editorEvent(event, model, option, index)


# ── Helpers ───────────────────────────────────────────────────────────────────

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


# ── Main widget ───────────────────────────────────────────────────────────────

class InstrumentView(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._components: list[dict] = []
        self._hidden: set[str] = set()
        self._loading = False

        splitter = QSplitter(Qt.Horizontal)

        # ── Pane 1: component list + toolbar ────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Components"))
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_row_changed)
        self._delegate = _EyeDelegate(self._list)
        self._delegate.visibility_toggled.connect(self._on_visibility_toggled)
        self._list.setItemDelegate(self._delegate)
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

        # ── Pane 2: property tree ────────────────────────────────────────
        mid = QWidget()
        mid_layout = QVBoxLayout(mid)
        mid_layout.setContentsMargins(0, 0, 0, 0)
        mid_layout.addWidget(QLabel("Properties"))
        self._tree = QTreeWidget()
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels(["Key", "Value"])
        self._tree.setColumnWidth(0, 160)
        self._tree.itemChanged.connect(self._on_item_changed)
        mid_layout.addWidget(self._tree)

        # ── Pane 3: canvas preview ───────────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("Preview"))
        self._canvas = InstrumentCanvas()
        right_layout.addWidget(self._canvas)

        self.changed.connect(self._canvas.refresh)
        self._canvas.component_selected.connect(self._on_canvas_selected)
        self._canvas.component_moved.connect(self._on_canvas_moved)

        splitter.addWidget(left)
        splitter.addWidget(mid)
        splitter.addWidget(right)
        splitter.setSizes([180, 280, 360])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(splitter)

    # ── Public API ───────────────────────────────────────────────────────

    def load(self, instrument_data: dict, yaml_path: str = ""):
        self._loading = True
        self._hidden = set()
        self._list.clear()
        self._tree.blockSignals(True)
        self._tree.clear()
        self._tree.blockSignals(False)
        self._components = instrument_data.get("components", [])
        for comp in self._components:
            item = self._list.item(self._list.count())  # not yet added
            self._list.addItem(comp.get("name", "(unnamed)"))
            self._list.item(self._list.count() - 1).setData(Qt.UserRole, True)
        self._loading = False
        yaml_dir = str(Path(yaml_path).parent) if yaml_path else ""
        self._canvas.load(instrument_data, yaml_dir)
        self._canvas.set_hidden(set())
        if self._components:
            self._list.setCurrentRow(0)

    def clear(self):
        self._loading = True
        self._hidden = set()
        self._list.clear()
        self._tree.blockSignals(True)
        self._tree.clear()
        self._tree.blockSignals(False)
        self._components = []
        self._loading = False
        self._canvas.clear()

    def get_components(self) -> list[dict]:
        return self._components

    # ── Visibility toggle ─────────────────────────────────────────────────

    def _on_visibility_toggled(self, row: int, visible: bool):
        if row < 0 or row >= len(self._components):
            return
        name = self._components[row].get("name", "")
        if visible:
            self._hidden.discard(name)
        else:
            self._hidden.add(name)
        self._canvas.set_hidden(self._hidden.copy())

    # ── Tree editing ──────────────────────────────────────────────────────

    def _on_row_changed(self, row: int):
        self._tree.blockSignals(True)
        self._tree.clear()
        name = None
        if 0 <= row < len(self._components):
            comp = self._components[row]
            name = comp.get("name")
            for key, value in comp.items():
                if isinstance(value, (dict, list)):
                    node = QTreeWidgetItem(self._tree, [key, ""])
                    _populate_tree(node, value, editable=True)
                    node.setExpanded(True)
                else:
                    item = QTreeWidgetItem(self._tree, [key, str(value)])
                    item.setFlags(item.flags() | Qt.ItemIsEditable)
        self._tree.blockSignals(False)
        self._canvas.set_selected(name)

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

    # ── Canvas callbacks ──────────────────────────────────────────────────

    def _on_canvas_selected(self, name: str):
        for i, comp in enumerate(self._components):
            if comp.get("name") == name:
                if self._list.currentRow() != i:
                    self._list.setCurrentRow(i)
                break

    def _on_canvas_moved(self, name: str, x: int, y: int):
        self._on_row_changed(self._list.currentRow())
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
        self._list.item(self._list.count() - 1).setData(Qt.UserRole, True)
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
        self._hidden.discard(name)
        self._components.pop(row)
        self._list.takeItem(row)
        self.changed.emit()
