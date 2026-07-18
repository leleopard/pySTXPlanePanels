"""Dialog for generating a platform-appropriate multi-panel launch script."""

import stat
import sys
from pathlib import Path

import yaml
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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

_DEFAULT_LISTEN_PORT = 49008  # config.yaml's own default, when a panel has no udp.listen_port override


def _default_fmt_index() -> int:
    return 0 if sys.platform == "win32" else 2


def _run_line(fmt: str, py_cmd: str, panel_rel: str) -> str:
    """One panel's launch line, backgrounded so a multi-panel script doesn't
    block after the first entry — each panel is its own OS process (same
    pattern gauge_designer/preview.py already uses via subprocess.Popen),
    since arcade.run() is a blocking single-window loop per process."""
    if fmt == "bat":
        win_panel = panel_rel.replace("/", "\\")
        return f'start "" {py_cmd} -m gauge_core.runner "{win_panel}"\n'
    if fmt == "ps1":
        return f"Start-Process -FilePath '{py_cmd}' -ArgumentList '-m','gauge_core.runner','{panel_rel}'\n"
    # sh
    return f'{py_cmd} -m gauge_core.runner "{panel_rel}" &\n'


def _desktop_entry_content(name: str, sh_path: Path, project_root: Path) -> str:
    """A .desktop launcher (XDG Desktop Entry) whose Exec runs the
    generated .sh script — plain .sh files are not reliably double-
    clickable in Linux file managers (GNOME/Nautilus in particular
    defaults to opening executable text files in an editor, or asking,
    rather than running them), even with the executable bit set. A
    .desktop entry is what file managers actually treat as a launcher."""
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={name}\n"
        f'Exec=bash "{sh_path}"\n'
        f'Path={project_root}\n'
        "Terminal=false\n"
    )


def _generate_script(fmt: str, project_root: Path, panel_rels: list[str], py_cmd: str) -> str:
    root = str(project_root)
    run_lines = "".join(_run_line(fmt, py_cmd, p) for p in panel_rels)
    if fmt == "bat":
        win_root = root.replace("/", "\\")
        return (
            "@echo off\n"
            f'cd /d "{win_root}"\n'
            f"{run_lines}"
            "pause\n"
        )
    if fmt == "ps1":
        win_root = root.replace("/", "\\")
        return (
            f'Set-Location "{win_root}"\n'
            f"{run_lines}"
            'Read-Host "Press Enter to exit"\n'
        )
    # sh
    return (
        "#!/bin/bash\n"
        f'cd "{root}"\n'
        f"{run_lines}"
        "wait\n"
    )


class LaunchScriptDialog(QDialog):
    def __init__(self, panel_path: str, project_root: str, panels_root: str, parent=None):
        super().__init__(parent)
        self._panel_path   = Path(panel_path).resolve()
        self._project_root = Path(project_root).resolve()
        self._panels_root  = Path(panels_root).resolve()
        self._save_dir     = self._project_root

        self.setWindowTitle("Create Launch Script")
        self.resize(600, 520)

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

        # Panels to launch
        layout.addWidget(QLabel("Panels to launch (each opens its own window):"))
        self._panel_list = QListWidget()
        self._panel_list.setMaximumHeight(140)
        self._populate_panel_list()
        self._panel_list.itemChanged.connect(self._refresh)
        layout.addWidget(self._panel_list)

        self._port_warning = QLabel()
        self._port_warning.setStyleSheet("color: #b8860b; font-size: 11px;")
        self._port_warning.setWordWrap(True)
        layout.addWidget(self._port_warning)

        self._sh_note = QLabel(
            "A companion .desktop launcher will also be created, so the script "
            "can be started by double-clicking in a Linux file manager "
            "(plain .sh files usually aren't run on double-click by default)."
        )
        self._sh_note.setStyleSheet("color: #888; font-size: 11px;")
        self._sh_note.setWordWrap(True)
        layout.addWidget(self._sh_note)

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
        self._btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self._btns.accepted.connect(self._on_ok)
        self._btns.rejected.connect(self.reject)
        layout.addWidget(self._btns)

        self._refresh()

    # ── panel discovery ──────────────────────────────────────────────────

    def _populate_panel_list(self) -> None:
        """One checkable row per panel YAML found under panels_root, the
        currently-open panel pinned first and pre-checked, the rest sorted
        by display name and unchecked (matches the dialog's previous
        single-panel default of "just this panel")."""
        entries: list[tuple[str, Path]] = []
        if self._panels_root.is_dir():
            for p in sorted(self._panels_root.rglob("*.yaml")):
                try:
                    with open(p, encoding="utf-8") as f:
                        data = yaml.safe_load(f) or {}
                except Exception:
                    continue
                if "instruments" not in data:
                    continue  # not a panel YAML
                entries.append((str(data.get("name") or p.stem), p))

        current_resolved = self._panel_path
        entries.sort(key=lambda t: (t[1].resolve() != current_resolved, t[0].lower()))

        for name, path in entries:
            resolved = path.resolve()
            try:
                rel = resolved.relative_to(self._project_root).as_posix()
            except ValueError:
                rel = resolved.as_posix()
            item = QListWidgetItem(f"{name}  ({rel})")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if resolved == current_resolved else Qt.Unchecked)
            item.setData(Qt.UserRole, resolved)
            self._panel_list.addItem(item)

    def _selected_panels(self) -> list[Path]:
        out = []
        for i in range(self._panel_list.count()):
            item = self._panel_list.item(i)
            if item.checkState() == Qt.Checked:
                out.append(item.data(Qt.UserRole))
        return out

    def _panel_rel(self, path: Path) -> str:
        try:
            return path.relative_to(self._project_root).as_posix()
        except ValueError:
            return path.as_posix()

    def _check_port_collisions(self, panels: list[Path]) -> str:
        """Return a warning string if 2+ selected panels would bind the
        same UDP listen port when launched together (explicit
        udp.listen_port, or the config.yaml default when unset) — each
        is a separate process, so a collision means one panel silently
        loses the socket, not just a config quirk to fix later."""
        if len(panels) < 2:
            return ""
        by_port: dict[int, list[str]] = {}
        for p in panels:
            try:
                with open(p, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            except Exception:
                continue
            port = (data.get("udp") or {}).get("listen_port") or _DEFAULT_LISTEN_PORT
            by_port.setdefault(int(port), []).append(str(data.get("name") or p.stem))
        clashes = [f"port {port} ({', '.join(names)})" for port, names in by_port.items() if len(names) > 1]
        if not clashes:
            return ""
        return "⚠ Listen port collision — " + "; ".join(clashes) + \
            ". Give each panel its own udp.listen_port before running these together."

    # ── helpers ───────────────────────────────────────────────────────────

    def _fmt(self) -> str:
        return _FORMATS[self._fmt_combo.currentIndex()][1]

    def _out_path(self) -> Path:
        name = self._name_edit.text().strip() or "launch"
        ext  = f".{self._fmt()}"
        if not name.endswith(ext):
            name += ext
        return Path(self._save_dir) / name

    # ── slots ─────────────────────────────────────────────────────────────

    def _refresh(self):
        from gauge_designer.ui_utils import get_python_cmd
        panels = self._selected_panels()
        rels = [self._panel_rel(p) for p in panels]
        content = _generate_script(self._fmt(), self._project_root, rels, get_python_cmd())
        self._preview.setPlainText(content)
        self._out_label.setText(f"Output: {self._out_path()}")
        self._port_warning.setText(self._check_port_collisions(panels))
        self._sh_note.setVisible(self._fmt() == "sh")
        self._btns.button(QDialogButtonBox.Ok).setEnabled(bool(panels))

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
        extra_msg = ""
        try:
            newline = "\n" if fmt == "sh" else None
            with open(out, "w", encoding="utf-8", newline=newline) as f:
                f.write(content)
            if fmt == "sh":
                out.chmod(out.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

                desktop_out = out.with_suffix(".desktop")
                desktop_name = self._name_edit.text().strip() or "launch"
                desktop_content = _desktop_entry_content(desktop_name, out, self._project_root)
                with open(desktop_out, "w", encoding="utf-8", newline="\n") as f:
                    f.write(desktop_content)
                desktop_out.chmod(desktop_out.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                extra_msg = (
                    f"\n\nA double-click launcher was also created:\n{desktop_out}\n\n"
                    "On first use, most Linux file managers require you to right-click "
                    "it and choose \"Allow Launching\" (or similar) once — a standard "
                    "trust step for new local launchers."
                )
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return
        self.accept()
        QMessageBox.information(
            self.parent(), "Script Created",
            f"Launch script saved to:\n{out}{extra_msg}",
        )
