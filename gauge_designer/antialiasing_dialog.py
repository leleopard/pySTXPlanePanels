"""Antialiasing quality dialog — configures the SSAA level for the panel runtime."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QRadioButton, QDialogButtonBox, QGroupBox, QLabel,
)
from PySide6.QtCore import QSettings

# (level, label, description)
_LEVELS = [
    (0, "Off",  "No anti-aliasing — fastest."),
    (2, "2×",   "4 samples per pixel — light smoothing."),
    (4, "4×",   "16 samples per pixel — good quality (recommended)."),
    (8, "8×",   "64 samples per pixel — high quality, higher GPU cost."),
]


class AntialiasingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
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
            "Changes take effect on the next launch."
        )
        note.setWordWrap(True)
        gl.addWidget(note)

        current = QSettings().value("preferences/ssaa", 4, type=int)
        self._rbs: dict[int, QRadioButton] = {}
        for level, label, desc in _LEVELS:
            rb = QRadioButton(f"{label}   —   {desc}")
            rb.setChecked(current == level)
            self._rbs[level] = rb
            gl.addWidget(rb)

        layout.addWidget(group)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save_and_accept(self):
        for level, rb in self._rbs.items():
            if rb.isChecked():
                QSettings().setValue("preferences/ssaa", level)
                break
        self.accept()
