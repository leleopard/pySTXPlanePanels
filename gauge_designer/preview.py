import os
import sys
import subprocess
import tempfile
from typing import Callable
from pathlib import Path

import yaml
from PySide6.QtCore import QObject, QTimer, Signal


class PreviewBar(QObject):
    """Manages the Arcade subprocess for panel mock-preview and live X-Plane runs.

    If a data_provider callable is set (via set_yaml), the current in-memory
    data is written to a temp file beside the original YAML so that relative
    texture paths resolve correctly. The temp file is deleted when the process
    closes.
    """

    running_changed = Signal(bool)       # True when mock process starts/stops
    live_running_changed = Signal(bool)  # True when live process starts/stops

    def __init__(self, parent=None):
        super().__init__(parent)
        self._yaml_path: str | None = None
        self._data_provider: Callable[[], dict] | None = None
        self._proc: subprocess.Popen | None = None
        self._tmp_path: str | None = None
        self._harness_win = None

        self._live_proc: subprocess.Popen | None = None
        self._live_tmp_path: str | None = None

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._poll)

        self._live_timer = QTimer(self)
        self._live_timer.setInterval(500)
        self._live_timer.timeout.connect(self._poll_live)

    def set_yaml(self, path: str | None, data_provider: Callable[[], dict] | None = None):
        self._yaml_path = path
        self._data_provider = data_provider

    @property
    def is_running(self) -> bool:
        return self._proc is not None

    @property
    def is_live(self) -> bool:
        return self._live_proc is not None

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

        from gauge_designer.ui_utils import get_ssaa_args
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "gauge_core.runner", launch_path, "--mock"] + get_ssaa_args(),
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

    def launch_live(self):
        """Launch the runtime connected to X-Plane (no mock, no test harness)."""
        if not self._yaml_path:
            return
        if self._live_proc and self._live_proc.poll() is None:
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
                    self._live_tmp_path = tmp.name
                    launch_path = tmp.name
                except Exception:
                    pass

        from gauge_designer.ui_utils import get_ssaa_args
        self._live_proc = subprocess.Popen(
            [sys.executable, "-m", "gauge_core.runner", launch_path] + get_ssaa_args(),
        )
        self.live_running_changed.emit(True)
        self._live_timer.start()

    def stop_live(self):
        self._live_timer.stop()
        if self._live_proc is not None:
            self._live_proc.terminate()
            self._live_proc = None
        if self._live_tmp_path:
            try:
                os.unlink(self._live_tmp_path)
            except OSError:
                pass
            self._live_tmp_path = None
        self.live_running_changed.emit(False)

    def _poll_live(self):
        if self._live_proc and self._live_proc.poll() is not None:
            self._live_timer.stop()
            self._live_proc = None
            if self._live_tmp_path:
                try:
                    os.unlink(self._live_tmp_path)
                except OSError:
                    pass
                self._live_tmp_path = None
            self.live_running_changed.emit(False)

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
