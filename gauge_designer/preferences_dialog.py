"""User preferences dialog."""

import sys

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QDialogButtonBox,
    QGroupBox, QLabel, QLineEdit, QPushButton, QRadioButton,
)
from PySide6.QtCore import QSettings


class PreferencesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setModal(True)
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)

        # ── Coordinate System ─────────────────────────────────────────────
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

        # ── Python Interpreter ────────────────────────────────────────────
        py_group = QGroupBox("Python Interpreter (for generated launch scripts)")
        py_layout = QVBoxLayout(py_group)

        py_note = QLabel(
            "Command written into .bat / .ps1 / .sh scripts. "
            "Use a short name like <b>py</b>, <b>python</b>, or <b>python3</b>, "
            "or paste the full interpreter path."
        )
        py_note.setWordWrap(True)
        py_layout.addWidget(py_note)

        cmd_row = QHBoxLayout()
        from gauge_designer.ui_utils import get_python_cmd
        self._py_edit = QLineEdit(get_python_cmd())
        cmd_row.addWidget(self._py_edit)
        use_current_btn = QPushButton("Use current interpreter")
        use_current_btn.setToolTip(sys.executable)
        use_current_btn.clicked.connect(lambda: self._py_edit.setText(sys.executable))
        cmd_row.addWidget(use_current_btn)
        py_layout.addLayout(cmd_row)

        current_lbl = QLabel(f"Current interpreter: <code>{sys.executable}</code>")
        current_lbl.setWordWrap(True)
        current_lbl.setStyleSheet("color: #888; font-size: 11px;")
        py_layout.addWidget(current_lbl)

        layout.addWidget(py_group)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save_and_accept(self):
        s = QSettings()
        s.setValue("preferences/coordSystem", "y_down" if self._rb_y_down.isChecked() else "y_up")
        cmd = self._py_edit.text().strip()
        if cmd:
            s.setValue("preferences/pythonCommand", cmd)
        self.accept()
