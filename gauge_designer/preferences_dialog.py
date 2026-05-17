"""User preferences dialog."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QRadioButton, QDialogButtonBox, QGroupBox, QLabel,
)
from PySide6.QtCore import QSettings


class PreferencesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setModal(True)
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)

        group = QGroupBox("Coordinate System")
        gl = QVBoxLayout(group)

        note = QLabel(
            "Controls how Y coordinates are displayed in position fields and the "
            "mouse cursor readout.\n"
            "YAML files always store coordinates in y-up convention internally."
        )
        note.setWordWrap(True)
        gl.addWidget(note)

        self._rb_y_up = QRadioButton(
            "Y-up  —  origin bottom-left, Y increases upward  (Arcade / OpenGL)"
        )
        self._rb_y_down = QRadioButton(
            "Y-down  —  origin top-left, Y increases downward  (screen / image convention)"
        )

        current = QSettings().value("preferences/coordSystem", "y_up")
        self._rb_y_down.setChecked(current == "y_down")
        self._rb_y_up.setChecked(current != "y_down")

        gl.addWidget(self._rb_y_up)
        gl.addWidget(self._rb_y_down)
        layout.addWidget(group)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save_and_accept(self):
        mode = "y_down" if self._rb_y_down.isChecked() else "y_up"
        QSettings().setValue("preferences/coordSystem", mode)
        self.accept()
