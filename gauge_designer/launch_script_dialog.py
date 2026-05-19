"""Dialog for generating a platform-appropriate panel launch script."""

import stat
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

# (display label, file extension)
_FORMATS = [
    ("Windows Batch (.bat)", "bat"),
    ("PowerShell (.ps1)",    "ps1"),
    ("Shell Script (.sh)",   "sh"),
]


def _default_fmt_index() -> int:
    return 0 if sys.platform == "win32" else 2


def _generate_script(fmt: str, project_root: Path, panel_rel: str, py_cmd: str) -> str:
    root = str(project_root)
    if fmt == "bat":
        win_root  = root.replace("/", "\\")
        win_panel = panel_rel.replace("/", "\\")
        return (
            "@echo off\n"
            f'cd /d "{win_root}"\n'
            f'{py_cmd} -m gauge_core.runner "{win_panel}"\n'
            "pause\n"
        )
    if fmt == "ps1":
        win_root = root.replace("/", "\\")
        return (
            f'Set-Location "{win_root}"\n'
            f'{py_cmd} -m gauge_core.runner "{panel_rel}"\n'
            'Read-Host "Press Enter to exit"\n'
        )
    # sh
    return (
        "#!/bin/bash\n"
        f'cd "{root}"\n'
        f'{py_cmd} -m gauge_core.runner "{panel_rel}"\n'
    )


class LaunchScriptDialog(QDialog):
    def __init__(self, panel_path: str, project_root: str, parent=None):
        super().__init__(parent)
        self._panel_path   = Path(panel_path).resolve()
        self._project_root = Path(project_root).resolve()
        self._save_dir     = self._project_root

        self.setWindowTitle("Create Launch Script")
        self.resize(600, 420)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Script name
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Script name:"))
        self._name_edit = QLineEdit(self._panel_path.stem.replace(" ", "_"))
        self._name_edit.textChanged.connect(self._refresh)
        name_row.addWidget(self._name_edit)
        layout.addLayout(name_row)

        # Format selector
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Format:"))
        self._fmt_combo = QComboBox()
        for label, _ in _FORMATS:
            self._fmt_combo.addItem(label)
        self._fmt_combo.setCurrentIndex(_default_fmt_index())
        self._fmt_combo.currentIndexChanged.connect(self._refresh)
        fmt_row.addWidget(self._fmt_combo)
        fmt_row.addStretch()
        layout.addLayout(fmt_row)

        # Save location
        loc_row = QHBoxLayout()
        loc_row.addWidget(QLabel("Save to:"))
        self._loc_edit = QLineEdit(str(self._save_dir))
        self._loc_edit.setReadOnly(True)
        loc_row.addWidget(self._loc_edit)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)
        loc_row.addWidget(browse_btn)
        layout.addLayout(loc_row)

        # Preview
        layout.addWidget(QLabel("Script preview:"))
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setFont(QFont("Courier New", 9))
        layout.addWidget(self._preview, 1)

        # Output path hint
        self._out_label = QLabel()
        self._out_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._out_label)

        # OK / Cancel
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self._refresh()

    # ── helpers ───────────────────────────────────────────────────────────

    def _fmt(self) -> str:
        return _FORMATS[self._fmt_combo.currentIndex()][1]

    def _panel_rel(self) -> str:
        try:
            return self._panel_path.relative_to(self._project_root).as_posix()
        except ValueError:
            return self._panel_path.as_posix()

    def _out_path(self) -> Path:
        name = self._name_edit.text().strip() or "launch"
        ext  = f".{self._fmt()}"
        if not name.endswith(ext):
            name += ext
        return Path(self._save_dir) / name

    # ── slots ─────────────────────────────────────────────────────────────

    def _refresh(self):
        from gauge_designer.ui_utils import get_python_cmd
        content = _generate_script(self._fmt(), self._project_root, self._panel_rel(), get_python_cmd())
        self._preview.setPlainText(content)
        self._out_label.setText(f"Output: {self._out_path()}")

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Save script to", str(self._save_dir))
        if d:
            self._save_dir = Path(d)
            self._loc_edit.setText(str(self._save_dir))
            self._refresh()

    def _on_ok(self):
        out = self._out_path()
        fmt = self._fmt()
        content = self._preview.toPlainText()
        try:
            newline = "\n" if fmt == "sh" else None
            with open(out, "w", encoding="utf-8", newline=newline) as f:
                f.write(content)
            if fmt == "sh":
                out.chmod(out.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return
        self.accept()
        QMessageBox.information(
            self.parent(), "Script Created",
            f"Launch script saved to:\n{out}",
        )
