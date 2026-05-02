import os
import sys
import subprocess
import tempfile
from typing import Callable
from pathlib import Path

import yaml
from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QPushButton


class PreviewBar(QObject):
    """Manages the Arcade --test subprocess; exposes self.button for toolbar use.

    If a data_provider callable is set (via set_yaml), the current in-memory
    instrument data is written to a temp file beside the original YAML so that
    relative texture paths resolve correctly.  The temp file is deleted when
    the Arcade window closes.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._yaml_path: str | None = None
        self._data_provider: Callable[[], dict] | None = None
        self._proc: subprocess.Popen | None = None
        self._tmp_path: str | None = None

        self.button = QPushButton("Preview (test mode)")
        self.button.setEnabled(False)
        self.button.clicked.connect(self._launch)

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._poll)

    def set_yaml(self, path: str | None, data_provider: Callable[[], dict] | None = None):
        self._yaml_path = path
        self._data_provider = data_provider
        self.button.setEnabled(path is not None and self._proc is None)

    def _launch(self):
        if not self._yaml_path:
            return
        if self._proc and self._proc.poll() is None:
            return

        launch_path = self._yaml_path

        if self._data_provider is not None:
            data = self._data_provider()
            if data:
                yaml_dir = Path(self._yaml_path).parent
                try:
                    tmp = tempfile.NamedTemporaryFile(
                        mode="w", suffix=".yaml", dir=yaml_dir,
                        delete=False, encoding="utf-8",
                    )
                    yaml.dump(data, tmp, default_flow_style=False,
                              allow_unicode=True, sort_keys=False)
                    tmp.close()
                    self._tmp_path = tmp.name
                    launch_path = tmp.name
                except Exception:
                    pass  # fall back to the saved file

        self._proc = subprocess.Popen(
            [sys.executable, "-m", "gauge_core.runner", launch_path, "--test"],
        )
        self.button.setEnabled(False)
        self._timer.start()

    def _poll(self):
        if self._proc and self._proc.poll() is not None:
            self._timer.stop()
            self._proc = None
            if self._tmp_path:
                try:
                    os.unlink(self._tmp_path)
                except OSError:
                    pass
                self._tmp_path = None
            self.button.setEnabled(self._yaml_path is not None)
