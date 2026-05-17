import yaml
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QFileDialog, QMessageBox, QTabWidget,
)
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction

from gauge_designer.instrument_view import InstrumentView
from gauge_designer.panel_view import PanelView
from gauge_designer.preview import PreviewBar

_MAX_RECENT = 8
_TAB_GAUGE = 0
_TAB_PANEL = 1


def _find_instruments_root(yaml_path: str) -> str:
    """Walk up from the YAML's directory to find an ancestor named 'instruments'."""
    p = Path(yaml_path).parent.resolve()
    candidate = p
    while candidate != candidate.parent:
        if candidate.name.lower() == "instruments":
            return str(candidate)
        candidate = candidate.parent
    return str(p)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gauge Designer")
        self.resize(1060, 640)

        self._settings = QSettings()

        # Per-tab file state
        self._gauge_path: str | None = None
        self._gauge_data: dict = {}
        self._gauge_dirty = False

        self._panel_path: str | None = None
        self._panel_data: dict = {}
        self._panel_dirty = False

        # Widgets
        self._gauge_view = InstrumentView()
        self._gauge_view.changed.connect(self._mark_gauge_dirty)
        self._gauge_view.open_requested.connect(
            lambda p: (self._tabs.setCurrentIndex(_TAB_GAUGE), self._load_gauge(p))
        )

        self._panel_view = PanelView()
        self._panel_view.changed.connect(self._mark_panel_dirty)

        self._preview = PreviewBar(self)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._gauge_view, "Instruments")
        self._tabs.addTab(self._panel_view, "Panels")
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self._tabs)

        self._build_menu()
        self._build_toolbar()
        self.statusBar().showMessage("Open a gauge or panel YAML to begin.")

        geometry = self._settings.value("windowGeometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.showMaximized()
        self._gauge_view.restore_state(self._settings)
        self._panel_view.restore_state(self._settings)

    # ── Menu ─────────────────────────────────────────────────────────────

    def _build_menu(self):
        menu = self.menuBar()
        file_menu = menu.addMenu("&File")

        self._open_gauge_act = QAction("Open &Gauge…", self)
        self._open_gauge_act.setShortcut("Ctrl+O")
        self._open_gauge_act.triggered.connect(self._open_gauge_dialog)
        file_menu.addAction(self._open_gauge_act)

        self._open_panel_act = QAction("Open &Panel…", self)
        self._open_panel_act.setShortcut("Ctrl+Shift+O")
        self._open_panel_act.triggered.connect(self._open_panel_dialog)
        file_menu.addAction(self._open_panel_act)

        self._recent_menu = file_menu.addMenu("Open &Recent")
        self._refresh_recent_menu()

        file_menu.addSeparator()

        self._save_act = QAction("&Save", self)
        self._save_act.setShortcut("Ctrl+S")
        self._save_act.setEnabled(False)
        self._save_act.triggered.connect(self._save)
        file_menu.addAction(self._save_act)

        save_as_act = QAction("Save &As…", self)
        save_as_act.setShortcut("Ctrl+Shift+S")
        save_as_act.triggered.connect(self._save_as)
        file_menu.addAction(save_as_act)

        file_menu.addSeparator()
        quit_act = QAction("&Quit", self)
        quit_act.setShortcut("Ctrl+Q")
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

    # ── Toolbar ───────────────────────────────────────────────────────────

    def _build_toolbar(self):
        tb = self.addToolBar("Tools")
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        tb.addAction(self._open_gauge_act)
        tb.addAction(self._open_panel_act)
        tb.addAction(self._save_act)
        tb.addSeparator()
        tb.addWidget(self._preview.button)

    # ── Tab handling ──────────────────────────────────────────────────────

    def _on_tab_changed(self, idx: int):
        if idx == _TAB_GAUGE and self._gauge_path:
            self._preview.set_yaml(self._gauge_path, data_provider=lambda: self._gauge_data)
        elif idx == _TAB_PANEL and self._panel_path:
            self._preview.set_yaml(self._panel_path, data_provider=lambda: self._panel_data)
        self._save_act.setEnabled(
            (idx == _TAB_GAUGE and self._gauge_path is not None)
            or (idx == _TAB_PANEL and self._panel_path is not None)
        )
        self._update_title()

    # ── Recent files ──────────────────────────────────────────────────────

    def _refresh_recent_menu(self):
        self._recent_menu.clear()
        recent = self._settings.value("recentFiles", []) or []
        if not recent:
            self._recent_menu.setEnabled(False)
            return
        self._recent_menu.setEnabled(True)
        for path in recent:
            act = QAction(path, self)
            act.triggered.connect(lambda checked=False, p=path: self._load_recent(p))
            self._recent_menu.addAction(act)

    def _push_recent(self, path: str):
        recent = self._settings.value("recentFiles", []) or []
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        recent = recent[:_MAX_RECENT]
        self._settings.setValue("recentFiles", recent)
        self._refresh_recent_menu()

    # ── Open ──────────────────────────────────────────────────────────────

    def _open_gauge_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Gauge YAML", "", "YAML files (*.yaml *.yml)"
        )
        if path:
            self._tabs.setCurrentIndex(_TAB_GAUGE)
            self._load_gauge(path)

    def _open_panel_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Panel YAML", "", "YAML files (*.yaml *.yml)"
        )
        if path:
            self._tabs.setCurrentIndex(_TAB_PANEL)
            self._load_panel(path)

    def _load_recent(self, path: str):
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
            return
        if "components" in data:
            self._tabs.setCurrentIndex(_TAB_GAUGE)
            self._load_gauge(path, data)
        elif "instruments" in data:
            self._tabs.setCurrentIndex(_TAB_PANEL)
            self._load_panel(path, data)
        else:
            QMessageBox.warning(
                self, "Unknown File",
                "Cannot determine file type\n(missing 'components' or 'instruments' key)."
            )

    # ── Load ──────────────────────────────────────────────────────────────

    def _load_gauge(self, path: str, data: dict | None = None):
        if self._gauge_dirty and not self._confirm_discard("gauge"):
            return
        if data is None:
            try:
                with open(path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
            except Exception as exc:
                QMessageBox.critical(self, "Load Error", str(exc))
                return
        if not isinstance(data, dict) or "components" not in data:
            QMessageBox.warning(
                self, "Invalid File",
                "File does not look like a gauge YAML\n(missing 'components' key)."
            )
            return
        self._gauge_path = path
        self._gauge_data = data
        self._gauge_dirty = False
        self._gauge_view.load(data, path)
        self._gauge_view.set_instruments_root(_find_instruments_root(path))
        self._preview.set_yaml(path, data_provider=lambda: self._gauge_data)
        self._save_act.setEnabled(True)
        self._update_title()
        n = len(data.get("components", []))
        self.statusBar().showMessage(
            f"{path}  |  {n} components  |  size {data.get('size', '?')}"
        )
        self._push_recent(path)

    def _load_panel(self, path: str, data: dict | None = None):
        if self._panel_dirty and not self._confirm_discard("panel"):
            return
        if data is None:
            try:
                with open(path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
            except Exception as exc:
                QMessageBox.critical(self, "Load Error", str(exc))
                return
        if not isinstance(data, dict) or "instruments" not in data:
            QMessageBox.warning(
                self, "Invalid File",
                "File does not look like a panel YAML\n(missing 'instruments' key)."
            )
            return
        self._panel_path = path
        self._panel_data = data
        self._panel_dirty = False
        self._panel_view.load(data, path)
        self._preview.set_yaml(path, data_provider=lambda: self._panel_data)
        self._save_act.setEnabled(True)
        self._update_title()
        n = len(data.get("instruments", []))
        self.statusBar().showMessage(
            f"{path}  |  {n} instruments  |  size {data.get('size', '?')}"
        )
        self._push_recent(path)

    # ── Dirty tracking ────────────────────────────────────────────────────

    def _mark_gauge_dirty(self):
        if not self._gauge_dirty:
            self._gauge_dirty = True
            self._update_title()

    def _mark_panel_dirty(self):
        if not self._panel_dirty:
            self._panel_dirty = True
            self._update_title()

    def _update_title(self):
        idx = self._tabs.currentIndex()
        if idx == _TAB_GAUGE:
            path = self._gauge_path
            name = self._gauge_data.get("name", Path(path).stem if path else "")
            dirty = self._gauge_dirty
        else:
            path = self._panel_path
            name = self._panel_data.get("name", Path(path).stem if path else "")
            dirty = self._panel_dirty
        prefix = "* " if dirty else ""
        self.setWindowTitle(
            f"{prefix}Gauge Designer — {name}" if name else "Gauge Designer"
        )

    # ── Save ──────────────────────────────────────────────────────────────

    def _save(self):
        if self._tabs.currentIndex() == _TAB_GAUGE:
            if not self._gauge_path:
                self._save_as()
                return
            self._write_gauge(self._gauge_path)
        else:
            if not self._panel_path:
                self._save_as()
                return
            self._write_panel(self._panel_path)

    def _save_as(self):
        if self._tabs.currentIndex() == _TAB_GAUGE:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Gauge YAML",
                self._gauge_path or "",
                "YAML files (*.yaml *.yml)"
            )
            if path:
                self._gauge_path = path
                self._write_gauge(path)
                self._save_act.setEnabled(True)
                self._preview.set_yaml(path, data_provider=lambda: self._gauge_data)
                self._push_recent(path)
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Panel YAML",
                self._panel_path or "",
                "YAML files (*.yaml *.yml)"
            )
            if path:
                self._panel_path = path
                self._write_panel(path)
                self._save_act.setEnabled(True)
                self._preview.set_yaml(path, data_provider=lambda: self._panel_data)
                self._push_recent(path)

    def _write_gauge(self, path: str):
        self._gauge_data["name"] = self._gauge_view.get_name()
        self._gauge_data["components"] = self._gauge_view.get_components()
        self._gauge_data["size"] = self._gauge_view.get_size()
        try:
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(
                    self._gauge_data, f,
                    default_flow_style=False, allow_unicode=True, sort_keys=False,
                )
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))
            return
        self._gauge_dirty = False
        self._update_title()
        self.statusBar().showMessage(f"Saved: {path}")

    def _write_panel(self, path: str):
        self._panel_data["instruments"] = self._panel_view.get_instruments()
        self._panel_data["size"] = self._panel_view.get_size()
        try:
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(
                    self._panel_data, f,
                    default_flow_style=False, allow_unicode=True, sort_keys=False,
                )
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))
            return
        self._panel_dirty = False
        self._update_title()
        self.statusBar().showMessage(f"Saved: {path}")

    # ── Close ─────────────────────────────────────────────────────────────

    def _confirm_discard(self, mode: str) -> bool:
        reply = QMessageBox.question(
            self, "Unsaved Changes",
            f"The {mode} has unsaved changes. Discard and continue?",
            QMessageBox.Discard | QMessageBox.Cancel,
        )
        return reply == QMessageBox.Discard

    def closeEvent(self, event):
        if self._gauge_dirty and not self._confirm_discard("gauge"):
            event.ignore()
            return
        if self._panel_dirty and not self._confirm_discard("panel"):
            event.ignore()
            return
        self._gauge_view.stop_test()
        self._settings.setValue("windowGeometry", self.saveGeometry())
        self._gauge_view.save_state(self._settings)
        self._panel_view.save_state(self._settings)
        event.accept()
