import yaml
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QFileDialog, QMessageBox, QVBoxLayout, QWidget, QLabel,
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
        self.resize(720, 560)

        self._settings = QSettings()
        self._current_path: str | None = None

        self._view = InstrumentView()
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
        self._view.load(data)
        self._preview.set_yaml(path)

        name = data.get("name", Path(path).stem)
        size = data.get("size", "?")
        self.setWindowTitle(f"Gauge Designer — {name}")
        self.statusBar().showMessage(
            f"{path}  |  {len(data.get('components', []))} components  |  size {size}"
        )
        self._push_recent(path)

    def _push_recent(self, path: str):
        recent = self._settings.value("recentFiles", []) or []
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        recent = recent[:_MAX_RECENT]
        self._settings.setValue("recentFiles", recent)
        self._refresh_recent_menu()
