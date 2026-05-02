import yaml
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QFileDialog, QMessageBox, QVBoxLayout, QWidget,
)
from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction

from gauge_designer.instrument_view import InstrumentView
from gauge_designer.preview import PreviewBar

_MAX_RECENT = 8


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gauge Designer")
        self.resize(1060, 620)

        self._settings = QSettings()
        self._current_path: str | None = None
        self._instrument_data: dict = {}
        self._dirty = False

        self._view = InstrumentView()
        self._view.changed.connect(self._mark_dirty)
        self._preview = PreviewBar()

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._view)
        layout.addWidget(self._preview)
        self.setCentralWidget(container)

        self._build_menu()
        self.statusBar().showMessage("Open an instrument YAML to begin.")

    def _build_menu(self):
        menu = self.menuBar()
        file_menu = menu.addMenu("&File")

        open_act = QAction("&Open…", self)
        open_act.setShortcut("Ctrl+O")
        open_act.triggered.connect(self._open_dialog)
        file_menu.addAction(open_act)

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

    def _refresh_recent_menu(self):
        self._recent_menu.clear()
        recent = self._settings.value("recentFiles", []) or []
        if not recent:
            self._recent_menu.setEnabled(False)
            return
        self._recent_menu.setEnabled(True)
        for path in recent:
            act = QAction(path, self)
            act.triggered.connect(lambda checked=False, p=path: self._load(p))
            self._recent_menu.addAction(act)

    def _open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Instrument YAML", "", "YAML files (*.yaml *.yml)"
        )
        if path:
            self._load(path)

    def _load(self, path: str):
        if self._dirty and not self._confirm_discard():
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
            return

        if not isinstance(data, dict) or "components" not in data:
            QMessageBox.warning(
                self, "Invalid File",
                "File does not look like an instrument YAML\n(missing 'components' key)."
            )
            return

        self._current_path = path
        self._instrument_data = data
        self._dirty = False
        self._view.load(data, path)
        self._preview.set_yaml(path)
        self._save_act.setEnabled(True)
        self._update_title()

        n = len(data.get("components", []))
        size = data.get("size", "?")
        self.statusBar().showMessage(f"{path}  |  {n} components  |  size {size}")
        self._push_recent(path)

    # ── Dirty tracking ────────────────────────────────────────────────────

    def _mark_dirty(self):
        if not self._dirty:
            self._dirty = True
            self._update_title()

    def _update_title(self):
        if self._current_path:
            name = self._instrument_data.get("name", Path(self._current_path).stem)
        else:
            name = ""
        prefix = "* " if self._dirty else ""
        self.setWindowTitle(f"{prefix}Gauge Designer — {name}" if name else "Gauge Designer")

    # ── Save ──────────────────────────────────────────────────────────────

    def _save(self):
        if not self._current_path:
            self._save_as()
            return
        self._write(self._current_path)

    def _save_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Instrument YAML",
            self._current_path or "",
            "YAML files (*.yaml *.yml)"
        )
        if path:
            self._write(path)
            self._current_path = path
            self._preview.set_yaml(path)
            self._push_recent(path)

    def _write(self, path: str):
        # components list is already mutated in-place; sync reference just in case
        self._instrument_data["components"] = self._view.get_components()
        try:
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(
                    self._instrument_data, f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))
            return
        self._dirty = False
        self._update_title()
        self.statusBar().showMessage(f"Saved: {path}")

    def _confirm_discard(self) -> bool:
        reply = QMessageBox.question(
            self, "Unsaved Changes",
            "You have unsaved changes. Discard and continue?",
            QMessageBox.Discard | QMessageBox.Cancel,
        )
        return reply == QMessageBox.Discard

    def closeEvent(self, event):
        if self._dirty and not self._confirm_discard():
            event.ignore()
        else:
            event.accept()

    def _push_recent(self, path: str):
        recent = self._settings.value("recentFiles", []) or []
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        recent = recent[:_MAX_RECENT]
        self._settings.setValue("recentFiles", recent)
        self._refresh_recent_menu()
