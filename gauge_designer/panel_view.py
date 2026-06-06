"""Panel tab — compose and edit a panel YAML (list of instruments at positions).

Left pane: file tree listing panel YAMLs under the panels root (double-click to open).
Right area (hidden until a panel is loaded):
  - instrument tree (plain entries + grid layout entries with drag-and-drop)
  - stacked properties forms (plain instrument / grid header / grid instrument)
  - PIL layout canvas
"""

from pathlib import Path

import yaml
from PySide6.QtWidgets import (
    QWidget, QSplitter, QTreeWidget, QTreeWidgetItem, QAbstractItemView,
    QStackedWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QMessageBox, QInputDialog, QFileDialog, QColorDialog,
    QCheckBox, QComboBox, QApplication,
)
from PySide6.QtCore import Qt, Signal, QSettings, QSize
from gauge_designer.ui_utils import QSpinBox, QDoubleSpinBox
from PySide6.QtGui import QColor

from gauge_designer.panel_form import PanelForm, GridForm, GridInstrumentForm
from gauge_designer.panel_canvas import PanelCanvas
from gauge_designer.ui_utils import header_label, make_svg_icon

_ROLE_TYPE = Qt.UserRole          # "instrument" | "grid"

_DEFAULT_PANELS_ROOT = Path(__file__).parent.parent / "panels"


# ---------------------------------------------------------------------------
# Panels file-browser tree
# ---------------------------------------------------------------------------

class _PanelFileTree(QTreeWidget):
    """Lists panel YAML files under a root directory.

    Double-clicking a file emits file_activated(absolute_path).
    Subdirectories are shown as expandable nodes.
    """
    file_activated = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._root: str = ""
        self.setHeaderHidden(True)
        self.setAnimated(True)
        self.itemDoubleClicked.connect(self._on_double_click)

    def set_root(self, root: str):
        self._root = root
        self._reload()

    def _reload(self):
        self.clear()
        if not self._root:
            return
        root_path = Path(self._root)
        if not root_path.is_dir():
            return
        self._populate(root_path, None)

    def _populate(self, directory: Path, parent):
        try:
            entries = sorted(directory.iterdir(),
                             key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            return
        for entry in entries:
            if entry.is_dir() and not entry.name.startswith('.'):
                dir_item = QTreeWidgetItem([entry.name])
                dir_item.setData(0, Qt.UserRole, None)
                if parent is None:
                    self.addTopLevelItem(dir_item)
                else:
                    parent.addChild(dir_item)
                self._populate(entry, dir_item)
                dir_item.setExpanded(True)
            elif entry.suffix.lower() in ('.yaml', '.yml'):
                file_item = QTreeWidgetItem([entry.stem])
                file_item.setData(0, Qt.UserRole, str(entry))
                if parent is None:
                    self.addTopLevelItem(file_item)
                else:
                    parent.addChild(file_item)

    def _on_double_click(self, item, _col):
        path = item.data(0, Qt.UserRole)
        if path:
            self.file_activated.emit(path)

    def highlight(self, path: str):
        """Select the item whose UserRole data matches path."""
        def _walk(item):
            if item.data(0, Qt.UserRole) == path:
                self.setCurrentItem(item)
                self.scrollToItem(item)
                return True
            for i in range(item.childCount()):
                if _walk(item.child(i)):
                    return True
            return False
        root = self.invisibleRootItem()
        for i in range(root.childCount()):
            if _walk(root.child(i)):
                break


# ---------------------------------------------------------------------------
# Instrument tree (with drag-and-drop for reordering / grid placement)
# ---------------------------------------------------------------------------

class _InstrumentTree(QTreeWidget):
    """QTreeWidget that intercepts drops to keep the data model in sync.

    Uses DragDrop mode (not InternalMove) so Qt's startDrag() never tries
    to remove source items from the model after a MoveAction — we rebuild
    the whole tree ourselves in _handle_tree_drop.
    """

    def __init__(self, panel_view: "PanelView", parent=None):
        super().__init__(parent)
        self._pv = panel_view
        self.setHeaderHidden(True)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

    def dragEnterEvent(self, event):
        if self.currentItem() and self.currentItem().data(0, _ROLE_TYPE) == "instrument":
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        source = self.currentItem()
        if source is None or source.data(0, _ROLE_TYPE) != "instrument":
            event.ignore()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        source = self.currentItem()
        if source is None or source.data(0, _ROLE_TYPE) != "instrument":
            event.ignore()
            return

        target = self.itemAt(event.position().toPoint())
        drop_pos = self.dropIndicatorPosition()

        if source.parent() is not None and target is None:
            event.ignore()
            return

        src_parent = source.parent()
        if src_parent is None:
            src_path = (self.indexOfTopLevelItem(source),)
        else:
            src_path = (self.indexOfTopLevelItem(src_parent),
                        src_parent.indexOfChild(source))

        self._pv._handle_tree_drop(src_path, target, drop_pos)
        event.setDropAction(Qt.IgnoreAction)
        event.accept()


# ---------------------------------------------------------------------------
# Main panel view
# ---------------------------------------------------------------------------

class PanelView(QWidget):
    changed = Signal()
    open_requested = Signal(str)  # emitted when a panel file is double-clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self._instruments: list[dict] = []
        self._yaml_dir: str = ""
        self._yaml_path: str = ""
        self._panels_root: str = str(_DEFAULT_PANELS_ROOT)
        self._loading = False
        self._sel_path: tuple[int, ...] | None = None
        self._zoom_cache: dict[str, float] = {}

        # ── Outer splitter: panels file tree | editor area ─────────────────
        self._outer_splitter = QSplitter(Qt.Horizontal)

        # ── Left pane: panels file tree ────────────────────────────────────
        panels_pane = QWidget()
        pl = QVBoxLayout(panels_pane)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(0)
        pl.addWidget(header_label("Panels"))

        panels_btn_bar = QHBoxLayout()
        panels_btn_bar.setContentsMargins(2, 2, 2, 2)
        panels_btn_bar.setSpacing(2)
        for icon_name, tip, slot in [
            ("plus-circle-outline",          "New Panel",       self._new_panel),
            ("plus-circle-multiple-outline", "Duplicate Panel", self._duplicate_panel),
            ("trash-can-outline",            "Delete Panel",    self._delete_panel),
        ]:
            btn = QPushButton()
            btn.setIcon(make_svg_icon(icon_name))
            btn.setIconSize(QSize(20, 20))
            btn.setFixedSize(28, 28)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            panels_btn_bar.addWidget(btn)
        panels_btn_bar.addStretch()
        pl.addLayout(panels_btn_bar)

        self._file_tree = _PanelFileTree()
        self._file_tree.file_activated.connect(self.open_requested)
        pl.addWidget(self._file_tree)

        # ── Right area: always visible; placeholder shown when no panel is loaded ─
        self._editor_area = QWidget()
        _ea_outer = QVBoxLayout(self._editor_area)
        _ea_outer.setContentsMargins(0, 0, 0, 0)
        _ea_outer.setSpacing(0)

        self._editor_placeholder = QLabel(
            "Double-click a panel from the list to open it."
        )
        self._editor_placeholder.setAlignment(Qt.AlignCenter)
        self._editor_placeholder.setStyleSheet("color: #888; font-size: 13px;")
        _ea_outer.addWidget(self._editor_placeholder, 1)

        self._editor_content = QWidget()
        ea = QVBoxLayout(self._editor_content)
        ea.setContentsMargins(0, 0, 0, 0)
        ea.setSpacing(4)
        self._editor_content.setVisible(False)
        _ea_outer.addWidget(self._editor_content, 1)

        # Panel name header
        self._name_header = header_label("")
        ea.addWidget(self._name_header)

        # Name edit row
        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 2, 0, 0)
        name_row.setSpacing(6)
        name_row.addWidget(QLabel("Name:"))
        self._name_edit = QLineEdit()
        self._name_edit.editingFinished.connect(self._on_name_changed)
        name_row.addWidget(self._name_edit)
        ea.addLayout(name_row)

        # Panel size bar
        size_bar = QHBoxLayout()
        size_bar.setContentsMargins(0, 0, 0, 4)
        size_bar.setSpacing(4)
        size_bar.addWidget(QLabel("Panel size:"))
        self._panel_w = QSpinBox()
        self._panel_w.setRange(1, 9999)
        self._panel_w.setFixedWidth(90)
        self._panel_h = QSpinBox()
        self._panel_h.setRange(1, 9999)
        self._panel_h.setFixedWidth(90)
        self._panel_w.valueChanged.connect(self._on_size_changed)
        self._panel_h.valueChanged.connect(self._on_size_changed)
        size_bar.addWidget(self._panel_w)
        size_bar.addWidget(QLabel("×"))
        size_bar.addWidget(self._panel_h)
        size_bar.addSpacing(16)

        self._fullscreen_chk = QCheckBox("Fullscreen")
        self._fullscreen_chk.setToolTip(
            "Launch the panel in fullscreen mode.\n"
            "The selected screen below determines which display is used."
        )
        self._fullscreen_chk.toggled.connect(self._on_window_opts_changed)
        size_bar.addWidget(self._fullscreen_chk)

        size_bar.addSpacing(8)
        size_bar.addWidget(QLabel("Screen:"))
        self._screen_combo = QComboBox()
        self._screen_combo.setMinimumWidth(180)
        self._screen_combo.setToolTip("Screen to launch the panel on (fullscreen or windowed).")
        self._screen_combo.currentIndexChanged.connect(self._on_window_opts_changed)
        self._populate_screen_combo()
        size_bar.addWidget(self._screen_combo)

        size_bar.addStretch()
        ea.addLayout(size_bar)

        # Background colour
        self._bg_color = QColor(13, 13, 13)
        color_bar = QHBoxLayout()
        color_bar.setContentsMargins(0, 0, 0, 4)
        color_bar.setSpacing(4)
        color_bar.addWidget(QLabel("Background:"))
        self._bg_color_btn = QPushButton()
        self._bg_color_btn.setFixedSize(60, 22)
        self._bg_color_btn.setToolTip("Click to choose panel background colour")
        self._bg_color_btn.clicked.connect(self._pick_bg_color)
        color_bar.addWidget(self._bg_color_btn)
        color_bar.addStretch()
        ea.addLayout(color_bar)
        self._update_bg_swatch()

        # UDP listen port bar
        port_bar = QHBoxLayout()
        port_bar.setContentsMargins(0, 0, 0, 4)
        port_bar.setSpacing(4)
        port_bar.addWidget(QLabel("UDP listen port:"))
        self._listen_port_sb = QSpinBox()
        self._listen_port_sb.setRange(0, 65535)
        self._listen_port_sb.setFixedWidth(110)
        self._listen_port_sb.setSpecialValueText("— (global)")
        self._listen_port_sb.setToolTip(
            "Per-panel listen port. Set to 0 to use the global default from config.yaml.\n"
            "Each panel running simultaneously must use a unique port."
        )
        self._listen_port_sb.valueChanged.connect(self._on_listen_port_changed)
        port_bar.addWidget(self._listen_port_sb)
        self._port_warning = QLabel("")
        self._port_warning.setStyleSheet("color: #c0392b; font-size: 11px;")
        port_bar.addWidget(self._port_warning)
        port_bar.addStretch()
        ea.addLayout(port_bar)

        # Inner 3-way splitter: instrument tree | properties | canvas
        self._splitter = QSplitter(Qt.Horizontal)

        # Pane 1: instrument tree + toolbar
        left = QWidget()
        ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0); ll.setSpacing(0)
        ll.addWidget(header_label("Instruments"))

        btn_bar = QHBoxLayout()
        btn_bar.setContentsMargins(2, 2, 2, 2)
        btn_bar.setSpacing(2)
        for icon_name, tip, slot in [
            ("plus-circle-outline", "Add Instrument", self._add_instrument),
            ("table-plus",          "Add Grid",        self._add_grid),
            ("trash-can-outline",   "Remove",          self._remove_item),
        ]:
            btn = QPushButton()
            btn.setIcon(make_svg_icon(icon_name))
            btn.setIconSize(QSize(20, 20))
            btn.setFixedSize(28, 28)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            btn_bar.addWidget(btn)
        btn_bar.addSpacing(6)
        for icon_name, tip, slot in [
            ("menu-up",   "Move Up",   self._move_up),
            ("menu-down", "Move Down", self._move_down),
        ]:
            btn = QPushButton()
            btn.setIcon(make_svg_icon(icon_name))
            btn.setIconSize(QSize(20, 20))
            btn.setFixedSize(28, 28)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            btn_bar.addWidget(btn)
        btn_bar.addStretch()
        ll.addLayout(btn_bar)

        self._tree = _InstrumentTree(self)
        self._tree.currentItemChanged.connect(self._on_tree_selection_changed)
        ll.addWidget(self._tree)

        # Pane 2: stacked properties forms
        mid = QWidget()
        ml = QVBoxLayout(mid); ml.setContentsMargins(0, 0, 0, 0)
        ml.addWidget(header_label("Properties"))
        self._stack = QStackedWidget()

        self._inst_form = PanelForm()
        self._inst_form.changed.connect(self._on_inst_form_changed)

        self._grid_form = GridForm()
        self._grid_form.changed.connect(self._on_grid_form_changed)

        self._grid_inst_form = GridInstrumentForm()
        self._grid_inst_form.changed.connect(self._on_grid_inst_form_changed)

        self._stack.addWidget(self._inst_form)        # index 0
        self._stack.addWidget(self._grid_form)        # index 1
        self._stack.addWidget(self._grid_inst_form)   # index 2

        ml.addWidget(self._stack)
        ml.addStretch()

        # Pane 3: layout canvas
        right = QWidget()
        rl = QVBoxLayout(right); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(2)
        rl.addWidget(header_label("Layout"))

        ctrl_bar = QHBoxLayout(); ctrl_bar.setContentsMargins(0, 0, 0, 0); ctrl_bar.setSpacing(6)
        self._coord_label = QLabel("x: —    y: —")
        self._coord_label.setMinimumWidth(130)
        ctrl_bar.addWidget(self._coord_label)
        ctrl_bar.addStretch()
        ctrl_bar.addWidget(QLabel("Zoom:"))
        self._zoom_sb = QDoubleSpinBox()
        self._zoom_sb.setRange(0.05, 4.0)
        self._zoom_sb.setSingleStep(0.05)
        self._zoom_sb.setDecimals(2)
        self._zoom_sb.setValue(0.3)
        self._zoom_sb.setFixedWidth(85)
        ctrl_bar.addWidget(self._zoom_sb)
        rl.addLayout(ctrl_bar)

        self._canvas = PanelCanvas()
        self._canvas.instrument_selected.connect(self._on_canvas_selected)
        self._canvas.mouse_moved.connect(self._on_canvas_mouse_moved)
        self._canvas.mouse_left.connect(self._on_canvas_mouse_left)
        self._canvas.zoom_changed.connect(self._on_canvas_zoom_changed)
        self._zoom_sb.valueChanged.connect(self._on_zoom_spinbox_changed)
        rl.addWidget(self._canvas)

        self._splitter.addWidget(left)
        self._splitter.addWidget(mid)
        self._splitter.addWidget(right)
        self._splitter.setSizes([200, 280, 420])
        ea.addWidget(self._splitter, 1)

        self._outer_splitter.addWidget(panels_pane)
        self._outer_splitter.addWidget(self._editor_area)
        self._outer_splitter.setSizes([180, 920])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._outer_splitter)

        if _DEFAULT_PANELS_ROOT.is_dir():
            self._file_tree.set_root(str(_DEFAULT_PANELS_ROOT))

    # ── State persistence ──────────────────────────────────────────────────

    def save_state(self, settings: QSettings):
        settings.setValue("panelView/outerSplitterState", self._outer_splitter.saveState())
        settings.setValue("panelView/innerSplitterState", self._splitter.saveState())
        settings.setValue("panelView/zoomCache", self._zoom_cache)

    def restore_state(self, settings: QSettings):
        outer = settings.value("panelView/outerSplitterState")
        if outer:
            self._outer_splitter.restoreState(outer)
        inner = settings.value("panelView/innerSplitterState")
        if inner:
            self._splitter.restoreState(inner)
        raw = settings.value("panelView/zoomCache", {})
        if isinstance(raw, dict):
            self._zoom_cache = {k: float(v) for k, v in raw.items()}

    # ── Public API ─────────────────────────────────────────────────────────

    def set_panels_root(self, root: str):
        self._panels_root = root
        self._file_tree.set_root(root)

    def _new_panel(self):
        root = Path(self._panels_root)
        name, ok = QInputDialog.getText(self, "New Panel", "Panel name (without .yaml):")
        if not ok or not name.strip():
            return
        file_path = root / f"{name.strip()}.yaml"
        if file_path.exists():
            QMessageBox.warning(self, "Exists", f"'{file_path.name}' already exists.")
            return
        data = {"name": name.strip(), "size": [1540, 920], "instruments": []}
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return
        self._file_tree.set_root(str(root))
        self.open_requested.emit(str(file_path))

    def _duplicate_panel(self):
        item = self._file_tree.currentItem()
        if item is None:
            return
        src_str = item.data(0, Qt.UserRole)
        if not src_str:
            return  # folder node selected
        src = Path(src_str)
        default = src.stem + "_copy"
        name, ok = QInputDialog.getText(
            self, "Duplicate Panel",
            "Name for the duplicate (without .yaml):",
            text=default,
        )
        if not ok or not name.strip():
            return
        dst = src.parent / f"{name.strip()}.yaml"
        if dst.exists():
            QMessageBox.warning(self, "Exists", f"'{dst.name}' already exists.")
            return
        try:
            with open(src, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            data["name"] = name.strip()
            with open(dst, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return
        self._file_tree.set_root(self._panels_root)
        self.open_requested.emit(str(dst))

    def _delete_panel(self):
        item = self._file_tree.currentItem()
        if item is None:
            return
        path = item.data(0, Qt.UserRole)
        if not path:
            return
        reply = QMessageBox.question(
            self, "Delete Panel",
            f"Delete '{Path(path).name}'?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            Path(path).unlink()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return
        if self._yaml_path == path:
            self.clear()
        self._file_tree.set_root(self._panels_root)

    def load(self, panel_data: dict, yaml_path: str = ""):
        self._loading = True
        self._yaml_path = yaml_path
        # Use the project root (parent of panels/) as base for instrument paths
        # so that moving a panel YAML within panels/ never breaks references.
        if self._panels_root:
            self._yaml_dir = str(Path(self._panels_root).parent)
        else:
            self._yaml_dir = str(Path(yaml_path).parent) if yaml_path else ""
        self._instruments = panel_data.setdefault("instruments", [])

        name = panel_data.get("name", "")
        self._name_header.setText(name)
        self._name_edit.setText(name)

        w, h = panel_data.get("size", [1540, 920])
        self._panel_w.blockSignals(True); self._panel_h.blockSignals(True)
        self._panel_w.setValue(int(w)); self._panel_h.setValue(int(h))
        self._panel_w.blockSignals(False); self._panel_h.blockSignals(False)

        port = (panel_data.get("udp") or {}).get("listen_port", 0) or 0
        self._listen_port_sb.blockSignals(True)
        self._listen_port_sb.setValue(int(port))
        self._listen_port_sb.blockSignals(False)
        self._port_warning.setText("")

        bg = panel_data.get("background_color", [0.05, 0.05, 0.05])
        try:
            self._bg_color = QColor(
                int(round(bg[0] * 255)),
                int(round(bg[1] * 255)),
                int(round(bg[2] * 255)),
            )
        except (TypeError, IndexError, ValueError):
            self._bg_color = QColor(13, 13, 13)
        self._update_bg_swatch()

        win = panel_data.get("window") or {}
        self._fullscreen_chk.blockSignals(True)
        self._screen_combo.blockSignals(True)
        self._populate_screen_combo()
        self._fullscreen_chk.setChecked(bool(win.get("fullscreen", False)))
        scr = int(win.get("screen", 0))
        self._screen_combo.setCurrentIndex(
            min(scr, self._screen_combo.count() - 1) if self._screen_combo.count() > 0 else 0
        )
        self._fullscreen_chk.blockSignals(False)
        self._screen_combo.blockSignals(False)

        self._loading = False
        self._inst_form.set_yaml_dir(self._yaml_dir)
        self._inst_form.set_ref_height(int(h))
        self._grid_form.set_ref_height(int(h))
        self._grid_inst_form.set_yaml_dir(self._yaml_dir)
        self._rebuild_tree()
        self._canvas.load(panel_data, self._yaml_dir)
        if self._instruments:
            self._select_path((0,))

        # Restore per-panel zoom (default 0.3 for new panels).
        zoom = self._zoom_cache.get(yaml_path, 0.3) if yaml_path else 0.3
        self._zoom_sb.blockSignals(True)
        self._zoom_sb.setValue(zoom)
        self._zoom_sb.blockSignals(False)
        self._canvas.set_zoom(zoom)

        self._editor_placeholder.setVisible(False)
        self._editor_content.setVisible(True)
        if yaml_path:
            self._file_tree.highlight(yaml_path)

    def clear(self):
        self._loading = True
        self._instruments = []
        self._yaml_dir = ""
        self._yaml_path = ""
        self._sel_path = None
        self._name_header.setText("")
        self._name_edit.clear()
        self._listen_port_sb.setValue(0)
        self._port_warning.setText("")
        self._bg_color = QColor(13, 13, 13)
        self._update_bg_swatch()
        self._fullscreen_chk.blockSignals(True)
        self._fullscreen_chk.setChecked(False)
        self._fullscreen_chk.blockSignals(False)
        self._screen_combo.blockSignals(True)
        self._screen_combo.setCurrentIndex(0)
        self._screen_combo.blockSignals(False)
        self._tree.clear()
        self._inst_form.clear()
        self._loading = False
        self._canvas.clear()
        self._editor_content.setVisible(False)
        self._editor_placeholder.setVisible(True)

    def get_instruments(self) -> list[dict]:
        return self._instruments

    def get_name(self) -> str:
        return self._name_edit.text().strip()

    def get_size(self) -> list[int]:
        return [self._panel_w.value(), self._panel_h.value()]

    def get_listen_port(self) -> int | None:
        """Return the per-panel listen port, or None if set to global default."""
        v = self._listen_port_sb.value()
        return v if v > 0 else None

    def get_background_color(self) -> list[float]:
        r, g, b = self._bg_color.red(), self._bg_color.green(), self._bg_color.blue()
        return [round(r / 255, 4), round(g / 255, 4), round(b / 255, 4)]

    def get_window_opts(self) -> dict | None:
        """Return window launch options dict, or None if all defaults."""
        fullscreen = self._fullscreen_chk.isChecked()
        screen_idx = self._screen_combo.currentIndex()
        if not fullscreen and screen_idx == 0:
            return None
        opts: dict = {}
        if fullscreen:
            opts["fullscreen"] = True
        if screen_idx > 0:
            opts["screen"] = screen_idx
        return opts

    def _populate_screen_combo(self):
        self._screen_combo.blockSignals(True)
        self._screen_combo.clear()
        for i, scr in enumerate(QApplication.screens()):
            geo = scr.geometry()
            label = f"{i}: {scr.name()}  {geo.width()}×{geo.height()}"
            self._screen_combo.addItem(label)
        self._screen_combo.blockSignals(False)

    def _on_window_opts_changed(self):
        if not self._loading:
            self.changed.emit()

    # ── Panel name ─────────────────────────────────────────────────────────

    def _on_name_changed(self):
        name = self._name_edit.text().strip()
        self._name_header.setText(name)
        self.changed.emit()

    # ── Panel size ─────────────────────────────────────────────────────────

    def _on_size_changed(self):
        if not self._loading:
            h = self._panel_h.value()
            self._inst_form.set_ref_height(h)
            self._grid_form.set_ref_height(h)
            self._canvas.set_size(self._panel_w.value(), h)
            self.changed.emit()

    # ── UDP listen port ────────────────────────────────────────────────────

    def _used_listen_ports(self) -> dict[int, str]:
        """Return {port: panel_name} for all panels in the root except this one."""
        result: dict[int, str] = {}
        if not self._panels_root:
            return result
        current = str(Path(self._yaml_path).resolve()) if self._yaml_path else ""
        for p in Path(self._panels_root).rglob("*.yaml"):
            if str(p.resolve()) == current:
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                port = (data.get("udp") or {}).get("listen_port")
                if port:
                    result[int(port)] = data.get("name", p.stem)
            except Exception:
                continue
        return result

    def _on_listen_port_changed(self, value: int):
        if self._loading:
            return
        if value > 0:
            used = self._used_listen_ports()
            if value in used:
                self._port_warning.setText(
                    f"⚠ Port {value} already used by '{used[value]}'"
                )
            else:
                self._port_warning.setText("")
        else:
            self._port_warning.setText("")
        self.changed.emit()

    # ── Background colour ──────────────────────────────────────────────────

    def _pick_bg_color(self):
        color = QColorDialog.getColor(self._bg_color, self, "Panel Background Colour")
        if color.isValid():
            self._bg_color = color
            self._update_bg_swatch()
            self._canvas.set_background_color(color.red(), color.green(), color.blue())
            self.changed.emit()

    def _update_bg_swatch(self):
        r, g, b = self._bg_color.red(), self._bg_color.green(), self._bg_color.blue()
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        text_color = "#ffffff" if lum < 128 else "#000000"
        self._bg_color_btn.setStyleSheet(
            f"background-color: rgb({r},{g},{b}); color: {text_color}; "
            f"border: 1px solid #888; border-radius: 2px;"
        )

    def refresh_form(self):
        """Re-populate the active form using the current coord convention."""
        current = self._tree.currentItem()
        if current:
            self._on_tree_selection_changed(current, None)

    # ── Tree helpers ────────────────────────────────────────────────────────

    def _rebuild_tree(self, select_path: tuple | None = None):
        self._tree.blockSignals(True)
        self._tree.clear()
        grid_items: list[QTreeWidgetItem] = []
        for i, entry in enumerate(self._instruments):
            if "grid" in entry:
                g = entry["grid"]
                name = g.get("name", "") or f"Grid {i}"
                item = QTreeWidgetItem([f"[{name}]"])
                item.setData(0, _ROLE_TYPE, "grid")
                item.setFlags(
                    Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDropEnabled
                )
                for inst_e in g.get("instruments", []):
                    child = QTreeWidgetItem([Path(inst_e.get("file", "?")).stem])
                    child.setData(0, _ROLE_TYPE, "instrument")
                    child.setFlags(
                        Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled
                    )
                    item.addChild(child)
                self._tree.addTopLevelItem(item)
                grid_items.append(item)
            else:
                item = QTreeWidgetItem([Path(entry.get("file", "?")).stem])
                item.setData(0, _ROLE_TYPE, "instrument")
                item.setFlags(
                    Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled
                )
                self._tree.addTopLevelItem(item)
        # Expand grid nodes AFTER unblocking so Qt lays out all children.
        self._tree.blockSignals(False)
        for g_item in grid_items:
            g_item.setExpanded(True)
        if select_path is not None:
            self._select_path(select_path)
        else:
            self._sel_path = None
            self._stack.setCurrentIndex(0)
            self._inst_form.clear()

    def _select_path(self, path: tuple):
        if len(path) == 1:
            item = self._tree.topLevelItem(path[0])
        elif len(path) == 2:
            parent = self._tree.topLevelItem(path[0])
            item = parent.child(path[1]) if parent else None
        else:
            item = None
        if item:
            self._tree.setCurrentItem(item)
            self._tree.scrollToItem(item)

    # ── Tree selection ─────────────────────────────────────────────────────

    def _on_tree_selection_changed(self, current, _prev):
        if current is None or self._loading:
            self._sel_path = None
            self._canvas.set_selected(-1)
            return

        parent = current.parent()
        if parent is None:
            i = self._tree.indexOfTopLevelItem(current)
            self._sel_path = (i,)
            entry = self._instruments[i]
            if "grid" in entry:
                self._stack.setCurrentIndex(1)
                self._grid_form.load(entry["grid"])
            else:
                scale = float(entry.get("scale", 1.0))
                _, ih = self._canvas.inst_size(entry.get("file", ""), scale)
                self._inst_form.set_item_height(ih)
                self._stack.setCurrentIndex(0)
                self._inst_form.load(entry)
            self._canvas.set_selected(i)
        else:
            i = self._tree.indexOfTopLevelItem(parent)
            j = parent.indexOfChild(current)
            self._sel_path = (i, j)
            grid_insts = self._instruments[i]["grid"]["instruments"]
            self._stack.setCurrentIndex(2)
            self._grid_inst_form.load(grid_insts[j])
            self._canvas.set_selected(i)

    # ── Form changes ───────────────────────────────────────────────────────

    def _on_inst_form_changed(self):
        if self._loading or self._sel_path is None or len(self._sel_path) != 1:
            return
        i = self._sel_path[0]
        if "grid" in self._instruments[i]:
            return
        updated = self._inst_form.get_data()
        self._instruments[i].clear()
        self._instruments[i].update(updated)
        item = self._tree.topLevelItem(i)
        if item:
            item.setText(0, Path(updated.get("file", "?")).stem)
        self._canvas.refresh()
        self.changed.emit()

    def _on_grid_form_changed(self):
        if self._loading or self._sel_path is None or len(self._sel_path) != 1:
            return
        i = self._sel_path[0]
        if "grid" not in self._instruments[i]:
            return
        updated = self._grid_form.get_data()
        grid = self._instruments[i]["grid"]
        insts = grid.pop("instruments", [])
        grid.clear()
        grid.update(updated)
        grid["instruments"] = insts
        item = self._tree.topLevelItem(i)
        if item:
            name = updated.get("name", "") or f"Grid {i}"
            item.setText(0, f"[{name}]")
        self._canvas.refresh()
        self.changed.emit()

    def _on_grid_inst_form_changed(self):
        if self._loading or self._sel_path is None or len(self._sel_path) != 2:
            return
        i, j = self._sel_path
        updated = self._grid_inst_form.get_data()
        grid_insts = self._instruments[i]["grid"]["instruments"]
        grid_insts[j].clear()
        grid_insts[j].update(updated)
        parent = self._tree.topLevelItem(i)
        if parent and parent.child(j):
            parent.child(j).setText(0, Path(updated.get("file", "?")).stem)
        self._canvas.refresh()
        self.changed.emit()

    # ── Canvas overlay (coords + zoom) ────────────────────────────────────

    def _on_canvas_mouse_moved(self, x: int, y: int):
        self._coord_label.setText(f"x: {x}    y: {y}")

    def _on_canvas_mouse_left(self):
        self._coord_label.setText("x: —    y: —")

    def _on_canvas_zoom_changed(self, z: float):
        self._zoom_sb.blockSignals(True)
        self._zoom_sb.setValue(z)
        self._zoom_sb.blockSignals(False)
        self._save_zoom(z)

    def _on_zoom_spinbox_changed(self, value: float):
        self._canvas.set_zoom(value)
        self._save_zoom(value)

    def _save_zoom(self, z: float):
        if self._yaml_path:
            self._zoom_cache[self._yaml_path] = z

    # ── Canvas selection sync ──────────────────────────────────────────────

    def _on_canvas_selected(self, idx: int):
        if self._sel_path != (idx,):
            self._select_path((idx,))

    # ── Drag-and-drop ──────────────────────────────────────────────────────

    def _handle_tree_drop(
        self,
        src_path: tuple,
        target_item,
        drop_pos: QAbstractItemView.DropIndicatorPosition,
    ):
        # Fast path: same-grid reorder — swap list positions.
        if (
            len(src_path) == 2
            and target_item is not None
            and target_item.parent() is not None
        ):
            src_top, src_child = src_path
            tpar = target_item.parent()
            tgt_top = self._tree.indexOfTopLevelItem(tpar)
            tgt_child = tpar.indexOfChild(target_item)
            if tgt_top == src_top and tgt_child != src_child:
                insts = self._instruments[src_top]["grid"]["instruments"]
                insts[src_child], insts[tgt_child] = insts[tgt_child], insts[src_child]
                self._rebuild_tree(select_path=(src_top, tgt_child))
                self._canvas.refresh()
                self.changed.emit()
                return

        if len(src_path) == 1:
            src_top = src_path[0]
            entry = self._instruments[src_top]
            inst_file = entry.get("file", "")
            inst_scale = entry.get("scale", 1.0)
            src_is_toplevel = True
        else:
            src_top, src_child = src_path
            grid_insts = self._instruments[src_top]["grid"]["instruments"]
            entry = grid_insts[src_child]
            inst_file = entry.get("file", "")
            inst_scale = entry.get("scale", 1.0)
            src_is_toplevel = False

        if target_item is None:
            target_type = "toplevel_append"
            target_top = len(self._instruments)
            target_grid_top = -1
        else:
            tpar = target_item.parent()
            if tpar is None:
                target_top = self._tree.indexOfTopLevelItem(target_item)
                if target_item.data(0, _ROLE_TYPE) == "grid":
                    target_type = "into_grid"
                    target_grid_top = target_top
                else:
                    target_type = "toplevel_insert"
                    if drop_pos == QAbstractItemView.BelowItem:
                        target_top += 1
                    target_grid_top = -1
            else:
                target_type = "into_grid"
                target_grid_top = self._tree.indexOfTopLevelItem(tpar)
                target_top = target_grid_top

        if src_is_toplevel:
            self._instruments.pop(src_top)
            if target_type in ("toplevel_append", "toplevel_insert"):
                if target_top > src_top:
                    target_top -= 1
            elif target_type == "into_grid":
                if target_grid_top > src_top:
                    target_grid_top -= 1
        else:
            self._instruments[src_top]["grid"]["instruments"].pop(src_child)

        if target_type in ("toplevel_append", "toplevel_insert"):
            new_entry: dict = {"file": inst_file, "position": [0, 0]}
            if abs(inst_scale - 1.0) > 1e-4:
                new_entry["scale"] = inst_scale
            idx = min(target_top, len(self._instruments))
            self._instruments.insert(idx, new_entry)
            new_path: tuple = (idx,)
        else:
            tg = self._instruments[target_grid_top]["grid"]
            new_inst: dict = {"file": inst_file}
            if abs(inst_scale - 1.0) > 1e-4:
                new_inst["scale"] = inst_scale
            tg["instruments"].append(new_inst)
            new_path = (target_grid_top, len(tg["instruments"]) - 1)

        self._rebuild_tree(select_path=new_path)
        self._canvas.refresh()
        self.changed.emit()

    # ── Toolbar buttons ────────────────────────────────────────────────────

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
        self._instruments.append({"file": rel, "position": [0, 0]})
        new_idx = len(self._instruments) - 1
        self._rebuild_tree(select_path=(new_idx,))
        self._canvas.refresh()
        self.changed.emit()

    def _add_grid(self):
        n = sum(1 for e in self._instruments if "grid" in e)
        self._instruments.append({"grid": {
            "name": f"Grid {n + 1}",
            "position": [0, 0],
            "columns": 2,
            "rows": 1,
            "cell_width": 310,
            "cell_height": 310,
            "instruments": [],
        }})
        new_idx = len(self._instruments) - 1
        self._rebuild_tree(select_path=(new_idx,))
        self._canvas.refresh()
        self.changed.emit()

    def _remove_item(self):
        if self._sel_path is None:
            return
        if len(self._sel_path) == 1:
            i = self._sel_path[0]
            entry = self._instruments[i]
            if "grid" in entry:
                label = entry["grid"].get("name", "") or f"Grid {i}"
                label = f"[{label}]"
            else:
                label = Path(entry.get("file", "?")).stem
            if QMessageBox.question(
                self, "Remove", f"Remove '{label}'?",
                QMessageBox.Yes | QMessageBox.No,
            ) != QMessageBox.Yes:
                return
            self._instruments.pop(i)
        elif len(self._sel_path) == 2:
            i, j = self._sel_path
            label = Path(self._instruments[i]["grid"]["instruments"][j].get("file", "?")).stem
            if QMessageBox.question(
                self, "Remove", f"Remove '{label}' from grid?",
                QMessageBox.Yes | QMessageBox.No,
            ) != QMessageBox.Yes:
                return
            self._instruments[i]["grid"]["instruments"].pop(j)
        self._rebuild_tree()
        self._canvas.refresh()
        self.changed.emit()

    def _move_up(self):
        if self._sel_path is None or len(self._sel_path) != 1:
            return
        i = self._sel_path[0]
        if i <= 0:
            return
        self._instruments.insert(i - 1, self._instruments.pop(i))
        self._rebuild_tree(select_path=(i - 1,))
        self._canvas.refresh()
        self.changed.emit()

    def _move_down(self):
        if self._sel_path is None or len(self._sel_path) != 1:
            return
        i = self._sel_path[0]
        if i >= len(self._instruments) - 1:
            return
        self._instruments.insert(i + 1, self._instruments.pop(i))
        self._rebuild_tree(select_path=(i + 1,))
        self._canvas.refresh()
        self.changed.emit()
