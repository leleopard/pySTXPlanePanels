import sys
import subprocess
from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QPushButton


class PreviewBar(QObject):
    """Manages the Arcade --test subprocess; exposes self.button for toolbar use."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._yaml_path: str | None = None
        self._proc: subprocess.Popen | None = None

        self.button = QPushButton("Preview (test mode)")
        self.button.setEnabled(False)
        self.button.clicked.connect(self._launch)

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._poll)

    def set_yaml(self, path: str | None):
        self._yaml_path = path
        self.button.setEnabled(path is not None and self._proc is None)

    def _launch(self):
        if not self._yaml_path:
            return
        if self._proc and self._proc.poll() is None:
            return
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "gauge_core.runner", self._yaml_path, "--test"],
        )
        self.button.setEnabled(False)
        self._timer.start()

    def _poll(self):
        if self._proc and self._proc.poll() is not None:
            self._timer.stop()
            self._proc = None
            self.button.setEnabled(self._yaml_path is not None)
