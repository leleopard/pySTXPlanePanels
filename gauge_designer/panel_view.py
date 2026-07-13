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
    QMessageBox, QInputDialog, QFileDialog,
    QCheckBox, QComboBox, QApplication,
)
from PySide6.QtCore import Qt, Signal, QSettings, QSize
from gauge_designer.ui_utils import QSpinBox, QDoubleSpinBox, is_y_down

from gauge_designer.panel_form import PanelForm, GridForm, GridInstrumentForm, ContainerForm
from gauge_designer.panel_canvas import PanelCanvas
from gauge_designer.properties_form import _ColorButton
from gauge_designer.ui_utils import header_label, make_svg_icon

_ROLE_TYPE = Qt.UserRole          # "instrument" | "grid" | "container"

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

    _DRAGGABLE_ROLES = ("instrument", "container")

    def __init__(self, panel_view: "PanelView", parent=None):
        super().__init__(parent)
        self._pv = panel_view
        self.setHeaderHidden(True)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

    def item_path(self, item: QTreeWidgetItem) -> tuple[int, ...]:
        """Walk an item's parent chain to reconstruct its full index path."""
        path: list[int] = []
        while item is not None:
            parent = item.parent()
            if parent is None:
                path.append(self.indexOfTopLevelItem(item))
            else:
                path.append(parent.indexOfChild(item))
            item = parent
        return tuple(reversed(path))

    def dragEnterEvent(self, event):
        current = self.currentItem()
        if current and current.data(0, _ROLE_TYPE) in self._DRAGGABLE_ROLES:
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        source = self.currentItem()
        if source is None or source.data(0, _ROLE_TYPE) not in self._DRAGGABLE_ROLES:
            event.ignore()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        source = self.currentItem()
        if source is None or source.data(0, _ROLE_TYPE) not in self._DRAGGABLE_ROLES:
            event.ignore()
            return

        target = self.itemAt(event.position().toPoint())
        drop_pos = self.dropIndicatorPosition()

        if source.parent() is not None and target is None:
            event.ignore()
            return

        src_path = self.item_path(source)
        target_path = self.item_path(target) if target is not None else None

        if not self._pv._handle_tree_drop(src_path, target_path, drop_pos):
            event.ignore()
            return
        event.setDropAction(Qt.IgnoreAction)
        event.accept()


# ---------------------------------------------------------------------------
# Main panel view
# ---------------------------------------------------------------------------

class PanelView(QWidget):
    changed = Signal()
    open_requested = Signal(str)  # emitted when a panel file is double-clicked
    context_changed = Signal()    # emitted when the active editing context changes

    def __init__(self, parent=None):
        super().__init__(parent)
        self._instruments: list[dict] = []
        self._yaml_dir: str = ""
        self._yaml_path: str = ""
        self._add_context: str | None = None  # "panel" | None
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

        self._file_tree = _PanelFileTree()
        self._file_tree.file_activated.connect(self.open_requested)
        self._file_tree.itemClicked.connect(lambda: self._set_add_context("panel"))
        self._file_tree.currentItemChanged.connect(self._on_ctx_selection_changed)
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
        color_bar = QHBoxLayout()
        color_bar.setContentsMargins(0, 0, 0, 4)
        color_bar.setSpacing(4)
        color_bar.addWidget(QLabel("Background:"))
        self._bg_color_btn = _ColorButton()
        self._bg_color_btn.set_rgba((13, 13, 13))
        self._bg_color_btn.setToolTip("Click to choose panel background colour")
        self._bg_color_btn.color_changed.connect(self._on_bg_color_changed)
        color_bar.addWidget(self._bg_color_btn)
        color_bar.addStretch()
        ea.addLayout(color_bar)

        # Layout scale/offset — uniformly rescales and repositions the whole
        # arrangement of instruments as a unit, without touching any single
        # instrument's own position/scale. Live in the preview.
        layout_bar = QHBoxLayout()
        layout_bar.setContentsMargins(0, 0, 0, 4)
        layout_bar.setSpacing(4)
        layout_bar.addWidget(QLabel("Layout scale:"))
        self._layout_scale_sb = QDoubleSpinBox()
        self._layout_scale_sb.setRange(0.1, 5.0)
        self._layout_scale_sb.setDecimals(3)
        self._layout_scale_sb.setSingleStep(0.05)
        self._layout_scale_sb.setValue(1.0)
        self._layout_scale_sb.setFixedWidth(90)
        self._layout_scale_sb.setToolTip(
            "Rescales every instrument's own scale and position together,\n"
            "pivoting around the panel origin — shrinks/grows the whole\n"
            "arrangement as a single unit without editing instruments\n"
            "individually."
        )
        self._layout_scale_sb.valueChanged.connect(self._on_layout_transform_changed)
        layout_bar.addWidget(self._layout_scale_sb)

        layout_bar.addSpacing(12)
        layout_bar.addWidget(QLabel("Layout offset X / Y:"))
        self._layout_offset_x = QDoubleSpinBox()
        self._layout_offset_x.setRange(-9999.0, 9999.0)
        self._layout_offset_x.setDecimals(1)
        self._layout_offset_x.setFixedWidth(80)
        self._layout_offset_x.valueChanged.connect(self._on_layout_transform_changed)
        layout_bar.addWidget(self._layout_offset_x)
        self._layout_offset_y = QDoubleSpinBox()
        self._layout_offset_y.setRange(-9999.0, 9999.0)
        self._layout_offset_y.setDecimals(1)
        self._layout_offset_y.setFixedWidth(80)
        self._layout_offset_y.setToolTip(
            "Translates the (possibly rescaled) whole arrangement, applied\n"
            "after Layout scale — repositions where the instrument cluster\n"
            "shows up in the panel."
        )
        self._layout_offset_y.valueChanged.connect(self._on_layout_transform_changed)
        layout_bar.addWidget(self._layout_offset_y)
        layout_bar.addStretch()
        ea.addLayout(layout_bar)

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
        self._tree.itemClicked.connect(lambda: self._set_add_context("instrument"))
        self._tree.currentItemChanged.connect(self._on_ctx_selection_changed)
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

        self._container_form = ContainerForm()
        self._container_form.changed.connect(self._on_container_form_changed)

        self._stack.addWidget(self._inst_form)        # index 0
        self._stack.addWidget(self._grid_form)        # index 1
        self._stack.addWidget(self._grid_inst_form)   # index 2
        self._stack.addWidget(self._container_form)   # index 3

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
            self._bg_color_btn.set_rgba((
                int(round(bg[0] * 255)),
                int(round(bg[1] * 255)),
                int(round(bg[2] * 255)),
            ))
        except (TypeError, IndexError, ValueError):
            self._bg_color_btn.set_rgba((13, 13, 13))

        layout_scale = float(panel_data.get("layout_scale", 1.0))
        layout_offset = panel_data.get("layout_offset", [0.0, 0.0])
        self._layout_scale_sb.blockSignals(True)
        self._layout_offset_x.blockSignals(True)
        self._layout_offset_y.blockSignals(True)
        self._layout_scale_sb.setValue(layout_scale)
        self._layout_offset_x.setValue(float(layout_offset[0]))
        self._layout_offset_y.setValue(self._layout_offset_y_disp(float(layout_offset[1])))
        self._layout_scale_sb.blockSignals(False)
        self._layout_offset_x.blockSignals(False)
        self._layout_offset_y.blockSignals(False)

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
        self._container_form.set_ref_height(int(h))
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
        self._bg_color_btn.set_rgba((13, 13, 13))
        self._layout_scale_sb.setValue(1.0)
        self._layout_offset_x.setValue(0.0)
        self._layout_offset_y.setValue(0.0)
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
        r, g, b, _a = self._bg_color_btn.get_rgba()
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
            new_h = self._panel_h.value()
            # In Y-down mode the user thinks in distance-from-top, so adjust all
            # Y-up positions by the height delta so instruments stay anchored to top.
            if is_y_down() and self._canvas._data:
                old_h = self._canvas._data.get("size", [0, new_h])[1]
                delta = new_h - old_h
                if delta:
                    for entry in self._instruments:
                        if "grid" in entry:
                            g = entry["grid"]
                            pos = g.get("position", [0, 0])
                            g["position"] = [pos[0], float(pos[1]) + delta]
                        elif "container" in entry:
                            c = entry["container"]
                            pos = c.get("position", [0, 0])
                            c["position"] = [pos[0], float(pos[1]) + delta]
                        else:
                            pos = entry.get("position", [0, 0])
                            entry["position"] = [float(pos[0]), float(pos[1]) + delta]
            self._inst_form.set_ref_height(new_h)
            self._grid_form.set_ref_height(new_h)
            self._container_form.set_ref_height(new_h)
            self._canvas.set_size(self._panel_w.value(), new_h)
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

    def _on_bg_color_changed(self):
        r, g, b, _a = self._bg_color_btn.get_rgba()
        self._canvas.set_background_color(r, g, b)
        self.changed.emit()

    # ── Layout scale/offset ─────────────────────────────────────────────────

    @staticmethod
    def _layout_offset_y_disp(dy: float) -> float:
        """Convert layout_offset's Y between YAML y-up and display y-down
        (self-inverse). Unlike an absolute position, this is a pure delta —
        no reference height needed, just a sign flip: "move up" in y-up
        storage is still "move up" on screen, but a y-down-oriented control
        reads that as a decreasing distance-from-top."""
        return -dy if is_y_down() else dy

    def _on_layout_transform_changed(self):
        if self._loading:
            return
        self._canvas.set_layout_scale(self._layout_scale_sb.value())
        dy = self._layout_offset_y_disp(self._layout_offset_y.value())
        self._canvas.set_layout_offset(self._layout_offset_x.value(), dy)
        self.changed.emit()

    def get_layout_scale(self) -> float:
        return round(self._layout_scale_sb.value(), 3)

    def get_layout_offset(self) -> list[float]:
        dy = self._layout_offset_y_disp(self._layout_offset_y.value())
        return [round(self._layout_offset_x.value(), 1), round(dy, 1)]

    def refresh_form(self):
        """Re-populate the active form using the current coord convention."""
        current = self._tree.currentItem()
        if current:
            self._on_tree_selection_changed(current, None)

    # ── Context actions (Add / Delete / Duplicate / Copy / Paste) ─────────

    _CTX_BORDER = "border: 2px solid #6682c5; border-radius: 3px;"

    def _on_ctx_selection_changed(self, *_) -> None:
        if self._add_context is not None:
            self.context_changed.emit()

    def _set_add_context(self, ctx: str) -> None:
        if self._add_context != ctx:
            self._add_context = ctx
            self._file_tree.setStyleSheet(self._CTX_BORDER if ctx == "panel" else "")
            self._tree.setStyleSheet(self._CTX_BORDER if ctx == "instrument" else "")
            self.context_changed.emit()

    def _file_tree_has_file(self) -> bool:
        item = self._file_tree.currentItem()
        return item is not None and bool(item.data(0, Qt.UserRole))

    def can_add(self) -> bool:
        return self._add_context is not None

    def can_delete(self) -> bool:
        if self._add_context == "panel":
            return self._file_tree_has_file()
        if self._add_context == "instrument":
            return self._tree.currentItem() is not None
        return False

    def can_duplicate(self) -> bool:
        return self._add_context == "panel" and self._file_tree_has_file()

    def can_copy(self) -> bool:
        return False

    def can_paste(self) -> bool:
        return False

    def do_add(self) -> None:
        if self._add_context == "panel":
            self._new_panel()
        elif self._add_context == "instrument":
            self._add_instrument()

    def do_delete(self) -> None:
        if self._add_context == "panel":
            self._delete_panel()
        elif self._add_context == "instrument":
            self._remove_item()

    def do_duplicate(self) -> None:
        if self._add_context == "panel":
            self._duplicate_panel()

    # ── Path helpers (generalize over arbitrary grid/container nesting) ────

    @staticmethod
    def _entry_children(entry: dict) -> list | None:
        """The nested instruments list for a grid/container entry, or None
        for a leaf instrument. Uses setdefault so the returned list is
        always the one actually stored in the dict (safe to mutate)."""
        if "grid" in entry:
            return entry["grid"].setdefault("instruments", [])
        if "container" in entry:
            return entry["container"].setdefault("instruments", [])
        return None

    def _entry_at_path(self, path: tuple[int, ...]) -> dict | None:
        entries = self._instruments
        entry = None
        for idx in path:
            if entries is None or idx >= len(entries):
                return None
            entry = entries[idx]
            entries = self._entry_children(entry)
        return entry

    def _children_list_for_path(self, path: tuple[int, ...]) -> list:
        """The list containing the entry at `path` (i.e. its siblings)."""
        if len(path) <= 1:
            return self._instruments
        parent_entry = self._entry_at_path(path[:-1])
        return self._entry_children(parent_entry)

    def _item_at_path(self, path: tuple[int, ...]) -> QTreeWidgetItem | None:
        if not path:
            return None
        item = self._tree.topLevelItem(path[0])
        for idx in path[1:]:
            if item is None:
                return None
            item = item.child(idx)
        return item

    @staticmethod
    def _shift_path_after_pop(
        path: tuple[int, ...] | None, popped_parent_path: tuple[int, ...], popped_idx: int,
    ) -> tuple[int, ...] | None:
        """Adjust `path` after popping index `popped_idx` from the list at
        `popped_parent_path`, if `path` referenced a later sibling in that
        same list (only the one matching segment shifts; deeper segments,
        if any, are relative to whatever entry ends up at the corrected
        position and are left untouched)."""
        if path is None:
            return None
        depth = len(popped_parent_path)
        if len(path) > depth and path[:depth] == popped_parent_path and path[depth] > popped_idx:
            return path[:depth] + (path[depth] - 1,) + path[depth + 1:]
        return path

    # ── Tree helpers ────────────────────────────────────────────────────────

    def _rebuild_tree(self, select_path: tuple | None = None):
        self._tree.blockSignals(True)
        self._tree.clear()
        expand_items: list[QTreeWidgetItem] = []
        self._add_tree_children(None, self._instruments, expand_items)
        # Expand group nodes AFTER unblocking so Qt lays out all children.
        self._tree.blockSignals(False)
        for item in expand_items:
            item.setExpanded(True)
        if select_path is not None:
            self._select_path(select_path)
        else:
            self._sel_path = None
            self._stack.setCurrentIndex(0)
            self._inst_form.clear()

    def _add_tree_children(
        self, parent_item: QTreeWidgetItem | None, entries: list[dict],
        expand_items: list[QTreeWidgetItem],
    ) -> None:
        for entry in entries:
            if "grid" in entry:
                g = entry["grid"]
                name = g.get("name", "") or "Grid"
                item = QTreeWidgetItem([f"[{name}]"])
                item.setData(0, _ROLE_TYPE, "grid")
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDropEnabled)
                self._add_tree_item(parent_item, item)
                self._add_tree_children(item, g.get("instruments", []), expand_items)
                expand_items.append(item)
            elif "container" in entry:
                c = entry["container"]
                name = c.get("name", "") or "Container"
                item = QTreeWidgetItem([f"[{name}]"])
                item.setData(0, _ROLE_TYPE, "container")
                # Containers, unlike grids, are themselves draggable (into a grid cell).
                item.setFlags(
                    Qt.ItemIsEnabled | Qt.ItemIsSelectable
                    | Qt.ItemIsDropEnabled | Qt.ItemIsDragEnabled
                )
                self._add_tree_item(parent_item, item)
                self._add_tree_children(item, c.get("instruments", []), expand_items)
                expand_items.append(item)
            else:
                item = QTreeWidgetItem([Path(entry.get("file", "?")).stem])
                item.setData(0, _ROLE_TYPE, "instrument")
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
                self._add_tree_item(parent_item, item)

    def _add_tree_item(self, parent_item: QTreeWidgetItem | None, item: QTreeWidgetItem) -> None:
        if parent_item is None:
            self._tree.addTopLevelItem(item)
        else:
            parent_item.addChild(item)

    def _select_path(self, path: tuple):
        item = self._item_at_path(path)
        if item:
            self._tree.setCurrentItem(item)
            self._tree.scrollToItem(item)

    # ── Tree selection ─────────────────────────────────────────────────────

    def _on_tree_selection_changed(self, current, _prev):
        if current is None or self._loading:
            self._sel_path = None
            self._canvas.set_selected(-1)
            return

        path = self._tree.item_path(current)
        self._sel_path = path
        entry = self._entry_at_path(path)
        if entry is None:
            return

        if "grid" in entry:
            self._stack.setCurrentIndex(1)
            self._grid_form.load(entry["grid"])
        elif "container" in entry:
            c = entry["container"]
            top_level = len(path) == 1
            self._container_form.set_position_editable(top_level)
            self._container_form.set_ref_height(
                self._panel_h.value() if top_level else int(c.get("size", [0, 300])[1])
            )
            self._stack.setCurrentIndex(3)
            self._container_form.load(c)
        else:
            # Leaf instrument — its properties form depends on the parent.
            parent_path = path[:-1]
            parent_entry = self._entry_at_path(parent_path) if parent_path else None
            if parent_entry is not None and "grid" in parent_entry:
                self._stack.setCurrentIndex(2)
                self._grid_inst_form.load(entry)
            else:
                # Top-level, or a container child: PanelForm covers both —
                # only the reference height (panel vs. container) differs.
                if parent_entry is not None and "container" in parent_entry:
                    ref_h = int(parent_entry["container"].get("size", [0, 300])[1])
                else:
                    ref_h = self._panel_h.value()
                scale = float(entry.get("scale", 1.0))
                _, ih = self._canvas.inst_size(entry.get("file", ""), scale)
                self._inst_form.set_ref_height(ref_h)
                self._inst_form.set_item_height(ih)
                self._stack.setCurrentIndex(0)
                self._inst_form.load(entry)

        self._canvas.set_selected(path[0])

    # ── Form changes ───────────────────────────────────────────────────────

    def _on_inst_form_changed(self):
        if self._loading or self._sel_path is None:
            return
        entry = self._entry_at_path(self._sel_path)
        if entry is None or "grid" in entry or "container" in entry:
            return
        updated = self._inst_form.get_data()
        entry.clear()
        entry.update(updated)
        item = self._item_at_path(self._sel_path)
        if item:
            item.setText(0, Path(updated.get("file", "?")).stem)
        self._canvas.refresh()
        self.changed.emit()

    def _on_grid_form_changed(self):
        if self._loading or self._sel_path is None:
            return
        entry = self._entry_at_path(self._sel_path)
        if entry is None or "grid" not in entry:
            return
        updated = self._grid_form.get_data()
        grid = entry["grid"]
        insts = grid.pop("instruments", [])
        grid.clear()
        grid.update(updated)
        grid["instruments"] = insts
        item = self._item_at_path(self._sel_path)
        if item:
            name = updated.get("name", "") or "Grid"
            item.setText(0, f"[{name}]")
        self._canvas.refresh()
        self.changed.emit()

    def _on_container_form_changed(self):
        if self._loading or self._sel_path is None:
            return
        entry = self._entry_at_path(self._sel_path)
        if entry is None or "container" not in entry:
            return
        updated = self._container_form.get_data()
        if len(self._sel_path) > 1:
            updated.pop("position", None)  # nested in a grid: grid computes it
        container = entry["container"]
        insts = container.pop("instruments", [])
        container.clear()
        container.update(updated)
        container["instruments"] = insts
        item = self._item_at_path(self._sel_path)
        if item:
            name = updated.get("name", "") or "Container"
            item.setText(0, f"[{name}]")
        self._canvas.refresh()
        self.changed.emit()

    def _on_grid_inst_form_changed(self):
        if self._loading or self._sel_path is None or len(self._sel_path) < 2:
            return
        entry = self._entry_at_path(self._sel_path)
        parent_entry = self._entry_at_path(self._sel_path[:-1])
        if entry is None or parent_entry is None or "grid" not in parent_entry:
            return
        updated = self._grid_inst_form.get_data()
        entry.clear()
        entry.update(updated)
        item = self._item_at_path(self._sel_path)
        if item:
            item.setText(0, Path(updated.get("file", "?")).stem)
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
        target_path: tuple | None,
        drop_pos: QAbstractItemView.DropIndicatorPosition,
    ) -> bool:
        """Move the entry at src_path to wherever target_path indicates.

        Returns True if the drop was performed, False if it was rejected
        (so the caller can event.ignore() and leave the tree untouched).
        Generalizes over arbitrary grid/container nesting via the path
        helpers above — see the plan doc for the full validation matrix:
        instrument <-> top-level / grid / container all work; a container
        may itself become a grid cell; a container can never be dropped
        into another container, into itself, or into its own descendant.
        """
        src_entry = self._entry_at_path(src_path)
        if src_entry is None:
            return False
        is_container = "container" in src_entry
        src_parent_path = src_path[:-1]
        src_idx = src_path[-1]

        if is_container and target_path is not None and target_path[: len(src_path)] == src_path:
            return False  # can't drop a container into itself or its own descendant

        # Fast path: reorder among existing siblings, one level deep or more
        # (grid/container children) — top-level drags always use the slower
        # general path below, matching the pre-existing top-level UX.
        if (
            len(src_path) > 1
            and target_path is not None
            and len(target_path) == len(src_path)
            and target_path[:-1] == src_parent_path
            and target_path[-1] != src_idx
        ):
            siblings = self._children_list_for_path(src_path)
            j = target_path[-1]
            siblings[src_idx], siblings[j] = siblings[j], siblings[src_idx]
            self._rebuild_tree(select_path=src_parent_path + (j,))
            self._canvas.refresh()
            self.changed.emit()
            return True

        # Classify the target -> (dst_parent_path, dst_kind, insert_idx).
        if target_path is None:
            dst_parent_path, dst_kind, insert_idx = (), "toplevel", len(self._instruments)
        else:
            target_entry = self._entry_at_path(target_path)
            if target_entry is not None and "grid" in target_entry:
                dst_parent_path, dst_kind = target_path, "grid"
                insert_idx = len(self._entry_children(target_entry))
            elif target_entry is not None and "container" in target_entry:
                if is_container:
                    return False  # no container-in-container
                dst_parent_path, dst_kind = target_path, "container"
                insert_idx = len(self._entry_children(target_entry))
            elif len(target_path) > 1:
                parent_path = target_path[:-1]
                parent_entry = self._entry_at_path(parent_path)
                dst_kind = "grid" if "grid" in parent_entry else "container"
                if dst_kind == "container" and is_container:
                    return False
                dst_parent_path = parent_path
                insert_idx = target_path[-1] + (1 if drop_pos == QAbstractItemView.BelowItem else 0)
            else:
                dst_parent_path, dst_kind = (), "toplevel"
                insert_idx = target_path[0] + (1 if drop_pos == QAbstractItemView.BelowItem else 0)

        # Inserting later in the SAME list the source is leaving needs to
        # account for the upcoming removal shifting everything after it down.
        if dst_parent_path == src_parent_path and insert_idx > src_idx:
            insert_idx -= 1

        src_siblings = self._children_list_for_path(src_path)
        src_siblings.pop(src_idx)

        # The removal may also have shifted an unrelated target ancestor
        # (e.g. dropping a top-level item onto something nested inside a
        # later top-level grid/container).
        dst_parent_path = self._shift_path_after_pop(dst_parent_path, src_parent_path, src_idx)
        dst_list = (
            self._instruments if not dst_parent_path
            else self._entry_children(self._entry_at_path(dst_parent_path))
        )
        insert_idx = max(0, min(insert_idx, len(dst_list)))

        if is_container:
            new_entry = src_entry
            c_cfg = new_entry["container"]
            if dst_kind == "toplevel":
                c_cfg.setdefault("position", [0, 0])
            else:
                c_cfg.pop("position", None)
        else:
            new_entry = {"file": src_entry.get("file", "")}
            if dst_kind in ("toplevel", "container"):
                new_entry["position"] = [0, 0]
            scale = src_entry.get("scale", 1.0)
            if abs(float(scale) - 1.0) > 1e-4:
                new_entry["scale"] = scale

        dst_list.insert(insert_idx, new_entry)
        new_path = dst_parent_path + (insert_idx,)

        self._rebuild_tree(select_path=new_path)
        self._canvas.refresh()
        self.changed.emit()
        return True

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

    def _add_container(self):
        n = sum(1 for e in self._instruments if "container" in e)
        self._instruments.append({"container": {
            "name": f"Container {n + 1}",
            "position": [0, 0],
            "size": [300, 300],
            "instruments": [],
        }})
        new_idx = len(self._instruments) - 1
        self._rebuild_tree(select_path=(new_idx,))
        self._canvas.refresh()
        self.changed.emit()

    def _remove_item(self):
        if self._sel_path is None:
            return
        entry = self._entry_at_path(self._sel_path)
        if entry is None:
            return
        if "grid" in entry:
            label = f"[{entry['grid'].get('name', '') or 'Grid'}]"
        elif "container" in entry:
            label = f"[{entry['container'].get('name', '') or 'Container'}]"
        else:
            label = Path(entry.get("file", "?")).stem
        prompt = (
            f"Remove '{label}'?" if len(self._sel_path) == 1
            else f"Remove '{label}' from its parent?"
        )
        if QMessageBox.question(
            self, "Remove", prompt, QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        siblings = self._children_list_for_path(self._sel_path)
        siblings.pop(self._sel_path[-1])
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
