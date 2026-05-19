import os
import sys
import subprocess
import tempfile
from typing import Callable
from pathlib import Path

import yaml
from PySide6.QtCore import QObject, QTimer, Signal


class PreviewBar(QObject):
    """Manages the Arcade --test subprocess for panel preview.

    If a data_provider callable is set (via set_yaml), the current in-memory
    data is written to a temp file beside the original YAML so that relative
    texture paths resolve correctly. The temp file is deleted when the process
    closes.
    """

    running_changed = Signal(bool)  # True when process starts, False when it stops

    def __init__(self, parent=None):
        super().__init__(parent)
        self._yaml_path: str | None = None
        self._data_provider: Callable[[], dict] | None = None
        self._proc: subprocess.Popen | None = None
        self._tmp_path: str | None = None
        self._harness_win = None

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._poll)

    def set_yaml(self, path: str | None, data_provider: Callable[[], dict] | None = None):
        self._yaml_path = path
        self._data_provider = data_provider

    @property
    def is_running(self) -> bool:
        return self._proc is not None

    def launch(self):
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
            [sys.executable, "-m", "gauge_core.runner", launch_path, "--mock"],
        )

        try:
            from gauge_test_harness.harness import TestHarnessWindow
            self._harness_win = TestHarnessWindow(self._yaml_path)
            self._harness_win.closed.connect(self._on_harness_closed)
            self._harness_win.show()
        except Exception:
            self._harness_win = None

        self.running_changed.emit(True)
        self._timer.start()

    def _on_harness_closed(self):
        self._harness_win = None

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
            if self._harness_win is not None:
                self._harness_win.closed.disconnect(self._on_harness_closed)
                self._harness_win.close()
                self._harness_win = None
            self.running_changed.emit(False)
