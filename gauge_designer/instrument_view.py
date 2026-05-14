from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QSplitter, QListWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QInputDialog, QMessageBox,
    QStyledItemDelegate, QStyleOptionViewItem, QSpinBox,
    QTreeWidget, QTreeWidgetItem, QFileDialog, QStyle,
)
from PySide6.QtCore import Qt, Signal, QEvent, QRect, QPoint
from PySide6.QtGui import QPainter, QPen, QBrush, QColor

from gauge_designer.canvas import InstrumentCanvas
from gauge_designer.properties_form import PropertiesForm


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


# ── Main widget ───────────────────────────────────────────────────────────────

class InstrumentView(QWidget):
    changed = Signal()
    open_requested = Signal(str)  # emitted when user activates a file in the tree

    def __init__(self, parent=None):
        super().__init__(parent)
        self._components: list[dict] = []
        self._hidden: set[str] = set()
        self._loading = False
        self._instruments_root: str = ""

        # cache standard icons once (requires a live QWidget)
        self._dir_icon = None
        self._file_icon = None

        splitter = QSplitter(Qt.Horizontal)

        # ── Pane 0: instrument file tree ─────────────────────────────────
        tree_pane = QWidget()
        tl = QVBoxLayout(tree_pane); tl.setContentsMargins(0, 0, 0, 0); tl.setSpacing(2)

        tree_hdr = QHBoxLayout(); tree_hdr.setContentsMargins(0, 0, 0, 0); tree_hdr.setSpacing(4)
        self._root_label = QLabel("(no folder)")
        self._root_label.setStyleSheet("font-size: 10px; color: #aaa;")
        self._root_label.setToolTip("")
        tree_hdr.addWidget(self._root_label, stretch=1)
        root_btn = QPushButton("…"); root_btn.setFixedWidth(26)
        root_btn.setToolTip("Choose instruments folder")
        root_btn.clicked.connect(self._browse_instruments_root)
        tree_hdr.addWidget(root_btn)
        tl.addLayout(tree_hdr)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setColumnCount(1)
        self._tree.itemActivated.connect(self._on_tree_activated)
        tl.addWidget(self._tree)

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

        # ── Pane 2: properties form ──────────────────────────────────────
        mid = QWidget()
        mid_layout = QVBoxLayout(mid)
        mid_layout.setContentsMargins(0, 0, 0, 0)
        mid_layout.addWidget(QLabel("Properties"))
        self._form = PropertiesForm()
        self._form.changed.connect(self._on_form_changed)
        mid_layout.addWidget(self._form)

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

        splitter.addWidget(tree_pane)
        splitter.addWidget(left)
        splitter.addWidget(mid)
        splitter.addWidget(right)
        splitter.setSizes([200, 160, 300, 360])

        # Gauge size bar — sits above the component/form/canvas splitter
        size_bar = QHBoxLayout()
        size_bar.setContentsMargins(0, 0, 0, 4)
        size_bar.setSpacing(4)
        size_bar.addWidget(QLabel("Gauge size:"))
        self._gauge_w = QSpinBox(); self._gauge_w.setRange(1, 9999); self._gauge_w.setFixedWidth(90)
        self._gauge_h = QSpinBox(); self._gauge_h.setRange(1, 9999); self._gauge_h.setFixedWidth(90)
        self._gauge_w.valueChanged.connect(self._on_size_changed)
        self._gauge_h.valueChanged.connect(self._on_size_changed)
        size_bar.addWidget(self._gauge_w)
        size_bar.addWidget(QLabel("×"))
        size_bar.addWidget(self._gauge_h)
        size_bar.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(size_bar)
        layout.addWidget(splitter)

    # ── Public API ───────────────────────────────────────────────────────

    def load(self, instrument_data: dict, yaml_path: str = ""):
        self._loading = True
        self._hidden = set()
        self._list.clear()
        self._form.clear()
        self._components = instrument_data.get("components", [])
        for comp in self._components:
            self._list.addItem(comp.get("name", "(unnamed)"))
            self._list.item(self._list.count() - 1).setData(Qt.UserRole, True)

        w, h = instrument_data.get("size", [310, 310])
        self._gauge_w.blockSignals(True); self._gauge_h.blockSignals(True)
        self._gauge_w.setValue(int(w)); self._gauge_h.setValue(int(h))
        self._gauge_w.blockSignals(False); self._gauge_h.blockSignals(False)

        self._loading = False
        yaml_dir = str(Path(yaml_path).parent) if yaml_path else ""
        self._form.set_yaml_dir(yaml_dir)
        self._canvas.load(instrument_data, yaml_dir)
        self._canvas.set_hidden(set())
        if self._components:
            self._list.setCurrentRow(0)

    def clear(self):
        self._loading = True
        self._hidden = set()
        self._list.clear()
        self._form.clear()
        self._components = []
        self._loading = False
        self._canvas.clear()

    def get_components(self) -> list[dict]:
        return self._components

    def get_size(self) -> list[int]:
        return [self._gauge_w.value(), self._gauge_h.value()]

    def set_instruments_root(self, path: str) -> None:
        self._instruments_root = path
        p = Path(path)
        self._root_label.setText(p.name)
        self._root_label.setToolTip(path)
        self._populate_tree(p)

    # ── Instrument tree ───────────────────────────────────────────────────

    def _populate_tree(self, root: Path) -> None:
        if self._dir_icon is None:
            self._dir_icon = self.style().standardIcon(QStyle.SP_DirIcon)
            self._file_icon = self.style().standardIcon(QStyle.SP_FileIcon)
        self._tree.clear()
        if not root.is_dir():
            return
        self._add_tree_items(self._tree.invisibleRootItem(), root)
        self._tree.expandAll()

    def _add_tree_items(self, parent: QTreeWidgetItem, directory: Path) -> None:
        entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        for entry in entries:
            if entry.is_dir():
                item = QTreeWidgetItem(parent, [entry.name])
                item.setIcon(0, self._dir_icon)
                item.setData(0, Qt.UserRole, None)
                self._add_tree_items(item, entry)
            elif entry.is_file() and entry.suffix.lower() in (".yaml", ".yml"):
                item = QTreeWidgetItem(parent, [entry.stem])
                item.setIcon(0, self._file_icon)
                item.setData(0, Qt.UserRole, str(entry))

    def _on_tree_activated(self, item: QTreeWidgetItem, _col: int) -> None:
        path = item.data(0, Qt.UserRole)
        if path:
            self.open_requested.emit(path)

    def _browse_instruments_root(self) -> None:
        start = self._instruments_root or ""
        path = QFileDialog.getExistingDirectory(self, "Select Instruments Folder", start)
        if path:
            self.set_instruments_root(path)

    # ── Gauge size ────────────────────────────────────────────────────────

    def _on_size_changed(self):
        self._canvas.set_size(self._gauge_w.value(), self._gauge_h.value())
        self.changed.emit()

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

    # ── Row selection ─────────────────────────────────────────────────────

    def _on_row_changed(self, row: int):
        name = None
        if 0 <= row < len(self._components):
            comp = self._components[row]
            name = comp.get("name")
            self._form.load(comp)
        else:
            self._form.clear()
        self._canvas.set_selected(name)

    # ── Form change callback ──────────────────────────────────────────────

    def _on_form_changed(self):
        row = self._list.currentRow()
        if row < 0 or row >= len(self._components):
            return
        updated = self._form.get_data()
        old_name = self._components[row].get("name", "")
        # update in-place so canvas references stay valid
        self._components[row].clear()
        self._components[row].update(updated)
        new_name = updated.get("name", "")
        if self._list.item(row) and self._list.item(row).text() != new_name:
            self._list.item(row).setText(new_name)
        # if name changed, _selected_name in canvas is stale — force sync
        if old_name != new_name:
            self._canvas.force_selected(new_name)
        self.changed.emit()

    # ── Canvas callbacks ──────────────────────────────────────────────────

    def _on_canvas_selected(self, name: str):
        for i, comp in enumerate(self._components):
            if comp.get("name") == name:
                if self._list.currentRow() != i:
                    self._list.setCurrentRow(i)
                break

    def _on_canvas_moved(self, name: str, x: int, y: int):
        row = self._list.currentRow()
        if 0 <= row < len(self._components):
            comp = self._components[row]
            if comp.get("name") == name:
                self._loading = True
                self._form.load(comp)
                self._loading = False
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
