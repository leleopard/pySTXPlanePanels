import sys
import subprocess
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton
from PySide6.QtCore import QTimer


class PreviewBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._yaml_path: str | None = None
        self._proc: subprocess.Popen | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        self._btn = QPushButton("Preview (test mode)")
        self._btn.setEnabled(False)
        self._btn.clicked.connect(self._launch)
        layout.addWidget(self._btn)
        layout.addStretch()

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._poll)

    def set_yaml(self, path: str | None):
        self._yaml_path = path
        self._btn.setEnabled(path is not None)

    def _launch(self):
        if not self._yaml_path:
            return
        if self._proc and self._proc.poll() is None:
            return
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "gauge_core.runner", self._yaml_path, "--test"],
        )
        self._btn.setEnabled(False)
        self._timer.start()

    def _poll(self):
        if self._proc and self._proc.poll() is not None:
            self._timer.stop()
            self._proc = None
            self._btn.setEnabled(self._yaml_path is not None)
