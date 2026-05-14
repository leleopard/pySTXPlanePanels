import shutil
from pathlib import Path

import yaml
from PySide6.QtWidgets import (
    QWidget, QSplitter, QListWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QInputDialog, QMessageBox,
    QStyledItemDelegate, QStyleOptionViewItem, QSpinBox,
    QTreeWidget, QTreeWidgetItem, QFileDialog, QStyle, QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal, QEvent, QRect, QPoint
from PySide6.QtGui import QPainter, QPen, QBrush, QColor

from gauge_designer.canvas import InstrumentCanvas
from gauge_designer.properties_form import PropertiesForm

# UserRole slots for tree items
_ROLE_PATH = Qt.UserRole        # absolute path string (both files and dirs)
_ROLE_TYPE = Qt.UserRole + 1    # "file" or "dir"

_DEFAULT_ROOT = Path(__file__).parent.parent / "instruments"

_INSTRUMENT_SKELETON = {
    "name": "",
    "size": [310, 310],
    "components": [],
}


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


# ── Instrument file tree with drag-and-drop ──────────────────────────────────

class _InstrumentTree(QTreeWidget):
    """QTreeWidget that supports dragging instrument YAMLs into sub-folders."""

    file_moved = Signal(str, str)  # old_path, new_path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setColumnCount(1)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)

    def dragEnterEvent(self, event):
        if event.source() is self:
            item = self.currentItem()
            if item and item.data(0, _ROLE_TYPE) == "file":
                event.accept()
                return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.source() is not self:
            event.ignore()
            return
        target = self.itemAt(event.position().toPoint())
        if target is not None and target.data(0, _ROLE_TYPE) == "dir":
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.source() is not self:
            event.ignore()
            return
        src_item = self.currentItem()
        if src_item is None or src_item.data(0, _ROLE_TYPE) != "file":
            event.ignore()
            return
        target = self.itemAt(event.position().toPoint())
        if target is None or target.data(0, _ROLE_TYPE) != "dir":
            event.ignore()
            return
        src_path = Path(src_item.data(0, _ROLE_PATH))
        dst_dir = Path(target.data(0, _ROLE_PATH))
        dst_path = dst_dir / src_path.name
        if dst_path == src_path or dst_path.exists():
            event.ignore()
            return
        try:
            shutil.move(str(src_path), str(dst_path))
        except Exception as exc:
            QMessageBox.critical(self, "Move Error", str(exc))
            event.ignore()
            return
        self.file_moved.emit(str(src_path), str(dst_path))
        event.accept()


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

        outer_splitter = QSplitter(Qt.Horizontal)

        # ── Left pane: instrument file tree (always visible, full height) ──
        tree_pane = QWidget()
        tl = QVBoxLayout(tree_pane)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(2)

        tree_lbl = QLabel("Instruments")
        tree_lbl.setStyleSheet("font-weight: bold; color: black;")
        tl.addWidget(tree_lbl)

        self._tree = _InstrumentTree()
        self._tree.itemActivated.connect(self._on_tree_activated)
        self._tree.file_moved.connect(self._on_file_moved)
        tl.addWidget(self._tree)

        crud_bar = QHBoxLayout()
        crud_bar.setContentsMargins(0, 2, 0, 0)
        crud_bar.setSpacing(2)
        for label, slot, tip in [
            ("+ Folder",  self._new_folder,      "Create a new sub-folder"),
            ("+ Instr",   self._new_instrument,  "Create a new instrument YAML"),
            ("Delete",    self._delete_selected, "Delete selected file or folder"),
        ]:
            btn = QPushButton(label)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            crud_bar.addWidget(btn)
        crud_bar.addStretch()
        tl.addLayout(crud_bar)

        # ── Right pane: always visible (provides empty space on startup) ──────
        self._editor_pane = QWidget()
        el = QVBoxLayout(self._editor_pane)
        el.setContentsMargins(0, 0, 0, 0)

        # Content widget — hidden until an instrument is loaded
        self._editor_content = QWidget()
        cl = QVBoxLayout(self._editor_content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(4)

        # Gauge size bar — top of the editor area
        size_bar = QHBoxLayout()
        size_bar.setContentsMargins(0, 0, 0, 4)
        size_bar.setSpacing(4)
        size_bar.addWidget(QLabel("Gauge size:"))
        self._gauge_w = QSpinBox()
        self._gauge_w.setRange(1, 9999)
        self._gauge_w.setFixedWidth(90)
        self._gauge_h = QSpinBox()
        self._gauge_h.setRange(1, 9999)
        self._gauge_h.setFixedWidth(90)
        self._gauge_w.valueChanged.connect(self._on_size_changed)
        self._gauge_h.valueChanged.connect(self._on_size_changed)
        size_bar.addWidget(self._gauge_w)
        size_bar.addWidget(QLabel("×"))
        size_bar.addWidget(self._gauge_h)
        size_bar.addStretch()
        cl.addLayout(size_bar)

        # Inner splitter: components | properties | canvas
        inner_splitter = QSplitter(Qt.Horizontal)

        # components pane
        comp_pane = QWidget()
        comp_layout = QVBoxLayout(comp_pane)
        comp_layout.setContentsMargins(0, 0, 0, 0)
        comp_layout.addWidget(QLabel("Components"))
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_row_changed)
        self._delegate = _EyeDelegate(self._list)
        self._delegate.visibility_toggled.connect(self._on_visibility_toggled)
        self._list.setItemDelegate(self._delegate)
        comp_layout.addWidget(self._list)
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(2)
        for label, slot in [("▲", self._move_up), ("▼", self._move_down),
                             ("+", self._add_component), ("−", self._remove_component)]:
            btn = QPushButton(label)
            btn.setFixedWidth(32)
            btn.clicked.connect(slot)
            btn_bar.addWidget(btn)
        btn_bar.addStretch()
        comp_layout.addLayout(btn_bar)

        # properties pane
        prop_pane = QWidget()
        prop_layout = QVBoxLayout(prop_pane)
        prop_layout.setContentsMargins(0, 0, 0, 0)
        prop_layout.addWidget(QLabel("Properties"))
        self._form = PropertiesForm()
        self._form.changed.connect(self._on_form_changed)
        prop_layout.addWidget(self._form)

        # canvas pane
        canvas_pane = QWidget()
        canvas_layout = QVBoxLayout(canvas_pane)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.addWidget(QLabel("Preview"))
        self._canvas = InstrumentCanvas()
        canvas_layout.addWidget(self._canvas)

        self.changed.connect(self._canvas.refresh)
        self._canvas.component_selected.connect(self._on_canvas_selected)
        self._canvas.component_moved.connect(self._on_canvas_moved)

        inner_splitter.addWidget(comp_pane)
        inner_splitter.addWidget(prop_pane)
        inner_splitter.addWidget(canvas_pane)
        inner_splitter.setSizes([160, 300, 360])
        cl.addWidget(inner_splitter)

        self._editor_content.setVisible(False)
        el.addWidget(self._editor_content)

        outer_splitter.addWidget(tree_pane)
        outer_splitter.addWidget(self._editor_pane)
        outer_splitter.setSizes([220, 840])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(outer_splitter)

        # Load default instruments root from project structure
        if _DEFAULT_ROOT.is_dir():
            self.set_instruments_root(str(_DEFAULT_ROOT))

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
        self._editor_content.setVisible(True)

    def clear(self):
        self._loading = True
        self._hidden = set()
        self._list.clear()
        self._form.clear()
        self._components = []
        self._loading = False
        self._canvas.clear()
        self._editor_content.setVisible(False)

    def get_components(self) -> list[dict]:
        return self._components

    def get_size(self) -> list[int]:
        return [self._gauge_w.value(), self._gauge_h.value()]

    def set_instruments_root(self, path: str) -> None:
        self._instruments_root = path
        self._populate_tree(Path(path))

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
                item.setData(0, _ROLE_PATH, str(entry))
                item.setData(0, _ROLE_TYPE, "dir")
                self._add_tree_items(item, entry)
            elif entry.is_file() and entry.suffix.lower() in (".yaml", ".yml"):
                item = QTreeWidgetItem(parent, [entry.stem])
                item.setIcon(0, self._file_icon)
                item.setData(0, _ROLE_PATH, str(entry))
                item.setData(0, _ROLE_TYPE, "file")

    def _on_tree_activated(self, item: QTreeWidgetItem, _col: int) -> None:
        if item.data(0, _ROLE_TYPE) == "file":
            self.open_requested.emit(item.data(0, _ROLE_PATH))

    def _on_file_moved(self, _old: str, _new: str) -> None:
        self._populate_tree(Path(self._instruments_root))

    # ── Tree CRUD ─────────────────────────────────────────────────────────

    def _target_dir(self) -> Path | None:
        """Return the directory where a new item should be created."""
        if not self._instruments_root:
            return None
        item = self._tree.currentItem()
        if item is None:
            return Path(self._instruments_root)
        if item.data(0, _ROLE_TYPE) == "dir":
            return Path(item.data(0, _ROLE_PATH))
        return Path(item.data(0, _ROLE_PATH)).parent

    def _new_folder(self) -> None:
        parent_dir = self._target_dir()
        if parent_dir is None:
            return
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if not ok or not name.strip():
            return
        try:
            (parent_dir / name.strip()).mkdir(parents=False, exist_ok=False)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return
        self._populate_tree(Path(self._instruments_root))

    def _new_instrument(self) -> None:
        parent_dir = self._target_dir()
        if parent_dir is None:
            return
        name, ok = QInputDialog.getText(self, "New Instrument", "Instrument name (without .yaml):")
        if not ok or not name.strip():
            return
        file_path = parent_dir / f"{name.strip()}.yaml"
        if file_path.exists():
            QMessageBox.warning(self, "Exists", f"'{file_path.name}' already exists.")
            return
        skeleton = dict(_INSTRUMENT_SKELETON)
        skeleton["name"] = name.strip()
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                yaml.dump(skeleton, f, default_flow_style=False,
                          allow_unicode=True, sort_keys=False)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return
        self._populate_tree(Path(self._instruments_root))
        self.open_requested.emit(str(file_path))

    def _delete_selected(self) -> None:
        item = self._tree.currentItem()
        if item is None:
            return
        path = Path(item.data(0, _ROLE_PATH))
        typ = item.data(0, _ROLE_TYPE)
        if typ == "file":
            reply = QMessageBox.question(
                self, "Delete Instrument",
                f"Delete '{path.name}'?\nThis cannot be undone.",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            try:
                path.unlink()
            except Exception as exc:
                QMessageBox.critical(self, "Error", str(exc))
                return
        elif typ == "dir":
            if any(path.iterdir()):
                QMessageBox.warning(
                    self, "Not Empty",
                    f"'{path.name}' is not empty.\nRemove its contents first."
                )
                return
            reply = QMessageBox.question(
                self, "Delete Folder",
                f"Delete empty folder '{path.name}'?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            try:
                path.rmdir()
            except Exception as exc:
                QMessageBox.critical(self, "Error", str(exc))
                return
        self._populate_tree(Path(self._instruments_root))

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
