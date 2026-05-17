"""Panel tab — compose and edit a panel YAML (list of instruments at positions).

The instrument tree supports two entry types:
  - Plain instrument entries (file / position / scale)
  - Grid layout entries  (expandable; contain instrument entries with col/row)

Instruments can be dragged from anywhere in the tree and dropped onto a grid
node (to place them inside it) or onto the blank tree area / a plain
instrument row (to make them top-level).
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QSplitter, QTreeWidget, QTreeWidgetItem, QAbstractItemView,
    QStackedWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox, QSpinBox, QFileDialog,
)
from PySide6.QtCore import Qt, Signal

from gauge_designer.panel_form import PanelForm, GridForm, GridInstrumentForm
from gauge_designer.panel_canvas import PanelCanvas

# UserRole stored on every tree item to distinguish types quickly.
_ROLE_TYPE = Qt.UserRole          # "instrument" | "grid"


class _InstrumentTree(QTreeWidget):
    """QTreeWidget that intercepts drops to keep the data model in sync."""

    def __init__(self, panel_view: "PanelView", parent=None):
        super().__init__(parent)
        self._pv = panel_view
        self.setHeaderHidden(True)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

    def dropEvent(self, event):
        source = self.currentItem()
        if source is None or source.data(0, _ROLE_TYPE) != "instrument":
            event.ignore()
            return

        target = self.itemAt(event.position().toPoint())
        drop_pos = self.dropIndicatorPosition()

        # Compute source path from current tree state (BEFORE any modifications)
        src_parent = source.parent()
        if src_parent is None:
            src_path = (self.indexOfTopLevelItem(source),)
        else:
            src_path = (self.indexOfTopLevelItem(src_parent),
                        src_parent.indexOfChild(source))

        self._pv._handle_tree_drop(src_path, target, drop_pos)
        event.accept()          # we rebuilt the tree; skip Qt's default move


class PanelView(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._instruments: list[dict] = []
        self._yaml_dir: str = ""
        self._loading = False
        self._sel_path: tuple[int, ...] | None = None  # (i,) or (i,j)

        # ── Panel size bar ─────────────────────────────────────────────────
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

        # ── Pane 1: tree + toolbar ─────────────────────────────────────────
        left = QWidget()
        ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("Instruments"))
        self._tree = _InstrumentTree(self)
        self._tree.currentItemChanged.connect(self._on_tree_selection_changed)
        ll.addWidget(self._tree)
        btn_bar = QHBoxLayout(); btn_bar.setSpacing(2)
        for label, slot in [
            ("+Inst", self._add_instrument),
            ("+Grid", self._add_grid),
            ("−",     self._remove_item),
            ("▲",     self._move_up),
            ("▼",     self._move_down),
        ]:
            btn = QPushButton(label)
            if len(label) <= 1:
                btn.setFixedWidth(32)
            else:
                btn.setFixedWidth(46)
            btn.clicked.connect(slot)
            btn_bar.addWidget(btn)
        btn_bar.addStretch()
        ll.addLayout(btn_bar)

        # ── Pane 2: stacked properties forms ──────────────────────────────
        mid = QWidget()
        ml = QVBoxLayout(mid); ml.setContentsMargins(0, 0, 0, 0)
        ml.addWidget(QLabel("Properties"))
        self._stack = QStackedWidget()

        self._inst_form = PanelForm()
        self._inst_form.changed.connect(self._on_inst_form_changed)

        self._grid_form = GridForm()
        self._grid_form.changed.connect(self._on_grid_form_changed)

        self._grid_inst_form = GridInstrumentForm()
        self._grid_inst_form.changed.connect(self._on_grid_inst_form_changed)

        self._stack.addWidget(self._inst_form)     # index 0
        self._stack.addWidget(self._grid_form)     # index 1
        self._stack.addWidget(self._grid_inst_form)  # index 2

        ml.addWidget(self._stack)
        ml.addStretch()

        # ── Pane 3: canvas ─────────────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right); rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel("Layout"))
        self._canvas = PanelCanvas()
        self._canvas.instrument_selected.connect(self._on_canvas_selected)
        rl.addWidget(self._canvas)

        splitter.addWidget(left)
        splitter.addWidget(mid)
        splitter.addWidget(right)
        splitter.setSizes([200, 280, 420])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(size_bar)
        layout.addWidget(splitter)

    # ── Public API ─────────────────────────────────────────────────────────

    def load(self, panel_data: dict, yaml_path: str = ""):
        self._loading = True
        self._yaml_dir = str(Path(yaml_path).parent) if yaml_path else ""
        self._instruments = panel_data.setdefault("instruments", [])

        w, h = panel_data.get("size", [1540, 920])
        self._panel_w.blockSignals(True); self._panel_h.blockSignals(True)
        self._panel_w.setValue(int(w)); self._panel_h.setValue(int(h))
        self._panel_w.blockSignals(False); self._panel_h.blockSignals(False)

        for entry in self._instruments:
            if "grid" in entry:
                self._sort_grid(entry["grid"])

        self._loading = False
        self._inst_form.set_yaml_dir(self._yaml_dir)
        self._grid_inst_form.set_yaml_dir(self._yaml_dir)
        self._rebuild_tree()
        self._canvas.load(panel_data, self._yaml_dir)
        if self._instruments:
            self._select_path((0,))

    def clear(self):
        self._loading = True
        self._instruments = []
        self._yaml_dir = ""
        self._sel_path = None
        self._tree.clear()
        self._inst_form.clear()
        self._loading = False
        self._canvas.clear()

    def get_instruments(self) -> list[dict]:
        return self._instruments

    def get_size(self) -> list[int]:
        return [self._panel_w.value(), self._panel_h.value()]

    # ── Panel size ─────────────────────────────────────────────────────────

    def _on_size_changed(self):
        if not self._loading:
            self._canvas.set_size(self._panel_w.value(), self._panel_h.value())
            self.changed.emit()

    # ── Tree helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _sort_grid(grid: dict) -> None:
        """Sort a grid's instruments in-place: top row to bottom, left to right."""
        grid.setdefault("instruments", []).sort(
            key=lambda e: (e.get("row", 0), e.get("col", 0))
        )

    def _rebuild_tree(self, select_path: tuple | None = None):
        self._tree.blockSignals(True)
        self._tree.clear()
        grid_items: list[QTreeWidgetItem] = []
        for i, entry in enumerate(self._instruments):
            if "grid" in entry:
                g = entry["grid"]
                # Sort in place so tree order == data model order.
                self._sort_grid(g)
                name = g.get("name", "") or f"Grid {i}"
                item = QTreeWidgetItem([f"[{name}]"])
                item.setData(0, _ROLE_TYPE, "grid")
                item.setFlags(
                    Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDropEnabled
                )
                for inst_e in g["instruments"]:
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
        grid = self._instruments[i]["grid"]
        target_entry = grid["instruments"][j]
        target_entry.clear()
        target_entry.update(updated)
        self._sort_grid(grid)
        new_j = next(k for k, e in enumerate(grid["instruments"]) if e is target_entry)
        self._rebuild_tree(select_path=(i, new_j))
        self._canvas.refresh()
        self.changed.emit()

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
        # Extract the instrument file/scale before removing it.
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

        # Resolve target BEFORE removing source (indices are still valid).
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

        # Remove source from data model.
        if src_is_toplevel:
            self._instruments.pop(src_top)
            # Adjust target indices if source was ahead of target.
            if target_type in ("toplevel_append", "toplevel_insert"):
                if target_top > src_top:
                    target_top -= 1
            elif target_type == "into_grid":
                if target_grid_top > src_top:
                    target_grid_top -= 1
        else:
            self._instruments[src_top]["grid"]["instruments"].pop(src_child)

        # Insert at destination.
        if target_type in ("toplevel_append", "toplevel_insert"):
            new_entry: dict = {"file": inst_file, "position": [0, 0]}
            if abs(inst_scale - 1.0) > 1e-4:
                new_entry["scale"] = inst_scale
            idx = min(target_top, len(self._instruments))
            self._instruments.insert(idx, new_entry)
            new_path: tuple = (idx,)
        else:
            tg = self._instruments[target_grid_top]["grid"]
            used = {(e.get("col", 0), e.get("row", 0)) for e in tg["instruments"]}
            cols = tg.get("columns", 1)
            rows = tg.get("rows", 1)
            cell = (0, 0)
            found = False
            for r in range(rows):
                for c in range(cols):
                    if (c, r) not in used:
                        cell = (c, r)
                        found = True
                        break
                if found:
                    break
            new_inst: dict = {"file": inst_file, "col": cell[0], "row": cell[1]}
            if abs(inst_scale - 1.0) > 1e-4:
                new_inst["scale"] = inst_scale
            tg["instruments"].append(new_inst)
            self._sort_grid(tg)
            new_j = next(k for k, e in enumerate(tg["instruments"]) if e is new_inst)
            new_path = (target_grid_top, new_j)

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
            label = Path(self._instruments[i]["grid"]["instruments"][j].get("file","?")).stem
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
