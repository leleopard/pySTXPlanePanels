"""Antialiasing quality dialog — configures the SSAA level for the panel runtime.

Stored in config.yaml (top-level `ssaa:` key, sibling of `udp:`) rather than
QSettings, so the setting is shared with every launch method that reads
that same file — gauge_core.runner loads it directly regardless of how it
was started (designer preview, a generated launch script, or a bare
`python -m gauge_core.runner`), not just designer-launched subprocesses.
"""

from pathlib import Path

import yaml
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QRadioButton, QDialogButtonBox, QGroupBox, QLabel,
    QMessageBox,
)

# (level, label, description)
_LEVELS = [
    (0, "Off",  "No anti-aliasing — fastest."),
    (2, "2×",   "4 samples per pixel — light smoothing."),
    (4, "4×",   "16 samples per pixel — good quality (recommended)."),
    (8, "8×",   "64 samples per pixel — high quality, higher GPU cost."),
]


def _load_ssaa(config_path: Path) -> int:
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return int(data.get("ssaa", 4))
    return 4


def _save_ssaa(config_path: Path, level: int) -> None:
    existing: dict = {}
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            existing = yaml.safe_load(f) or {}
    existing["ssaa"] = level
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(existing, f, default_flow_style=False,
                  allow_unicode=True, sort_keys=False)


class AntialiasingDialog(QDialog):
    def __init__(self, project_root: str, parent=None):
        super().__init__(parent)
        self._config_path = Path(project_root) / "config.yaml"

        self.setWindowTitle("Antialiasing")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        group = QGroupBox("Rendering Quality")
        gl = QVBoxLayout(group)

        note = QLabel(
            "Supersampling anti-aliasing (SSAA) applied to the gauge panel window. "
            "The scene is rendered at N× resolution and downsampled in 2:1 passes "
            "via GL_LINEAR, giving N² samples per output pixel without any driver "
            "configuration.\n\n"
            "Applies to every launch method (designer preview, generated launch "
            "scripts, running the runtime directly) — changes take effect on the "
            "next launch."
        )
        note.setWordWrap(True)
        gl.addWidget(note)

        current = _load_ssaa(self._config_path)
        self._rbs: dict[int, QRadioButton] = {}
        for level, label, desc in _LEVELS:
            rb = QRadioButton(f"{label}   —   {desc}")
            rb.setChecked(current == level)
            self._rbs[level] = rb
            gl.addWidget(rb)

        layout.addWidget(group)

        path_lbl = QLabel(f"Saved to: {self._config_path}")
        path_lbl.setStyleSheet("color: #888; font-size: 11px;")
        path_lbl.setWordWrap(True)
        layout.addWidget(path_lbl)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save_and_accept(self):
        for level, rb in self._rbs.items():
            if rb.isChecked():
                try:
                    _save_ssaa(self._config_path, level)
                except Exception as exc:
                    QMessageBox.critical(self, "Save Error", str(exc))
                    return
                break
        self.accept()
