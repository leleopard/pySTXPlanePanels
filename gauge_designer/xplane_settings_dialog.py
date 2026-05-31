"""Dialog for editing the shared X-Plane UDP settings in config.yaml."""

import socket
from pathlib import Path

import yaml
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QVBoxLayout,
)
from gauge_designer.ui_utils import QSpinBox


def _load_config(config_path: Path) -> dict:
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("udp", {})
    return {}


def _save_config(config_path: Path, udp: dict) -> None:
    existing: dict = {}
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            existing = yaml.safe_load(f) or {}
    existing["udp"] = udp
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(existing, f, default_flow_style=False,
                  allow_unicode=True, sort_keys=False)


class XPlaneSettingsDialog(QDialog):
    def __init__(self, project_root: str, parent=None):
        super().__init__(parent)
        self._config_path = Path(project_root) / "config.yaml"
        cfg = _load_config(self._config_path)

        self.setWindowTitle("X-Plane Network Settings")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        # ── X-Plane (outbound) ────────────────────────────────────────────
        xp_group = QGroupBox("X-Plane")
        xp_form = QFormLayout(xp_group)

        self._xp_host = QLineEdit(cfg.get("xplane_host", "127.0.0.1"))
        xp_form.addRow("Host / IP:", self._xp_host)

        self._xp_port = QSpinBox()
        self._xp_port.setRange(1024, 65535)
        self._xp_port.setValue(int(cfg.get("xplane_port", 49000)))
        xp_form.addRow("Port:", self._xp_port)

        name_row = QHBoxLayout()
        default_name = cfg.get("xplane_name") or socket.gethostname()
        self._xp_name = QLineEdit(default_name)
        name_row.addWidget(self._xp_name)
        use_hostname_btn = QPushButton("Use hostname")
        use_hostname_btn.setFixedWidth(110)
        use_hostname_btn.clicked.connect(
            lambda: self._xp_name.setText(socket.gethostname())
        )
        name_row.addWidget(use_hostname_btn)
        xp_form.addRow("Computer name:", name_row)

        note = QLabel(
            "Computer name is sent to X-Plane when subscribing to datarefs. "
            "Only matters when X-Plane and this app are on different machines."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #888; font-size: 11px;")
        xp_form.addRow(note)

        layout.addWidget(xp_group)

        # ── This application (inbound) ────────────────────────────────────
        app_group = QGroupBox("This application (inbound)")
        app_form = QFormLayout(app_group)

        self._listen_host = QLineEdit(cfg.get("listen_host", "127.0.0.1"))
        app_form.addRow("Listen host:", self._listen_host)

        self._listen_port = QSpinBox()
        self._listen_port.setRange(1024, 65535)
        self._listen_port.setValue(int(cfg.get("listen_port", 49008)))
        app_form.addRow("Default listen port:", self._listen_port)

        fallback_note = QLabel(
            "Individual panels can override this port via the listen port "
            "field in the panel designer. Each panel running simultaneously "
            "must use a different port."
        )
        fallback_note.setWordWrap(True)
        fallback_note.setStyleSheet("color: #888; font-size: 11px;")
        app_form.addRow(fallback_note)

        layout.addWidget(app_group)

        # ── Config file path hint ─────────────────────────────────────────
        path_lbl = QLabel(f"Saved to: {self._config_path}")
        path_lbl.setStyleSheet("color: #888; font-size: 11px;")
        path_lbl.setWordWrap(True)
        layout.addWidget(path_lbl)

        # ── Buttons ───────────────────────────────────────────────────────
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_ok(self):
        udp = {
            "listen_host": self._listen_host.text().strip() or "127.0.0.1",
            "listen_port": self._listen_port.value(),
            "xplane_host": self._xp_host.text().strip() or "127.0.0.1",
            "xplane_port": self._xp_port.value(),
            "xplane_name": self._xp_name.text().strip() or socket.gethostname(),
        }
        try:
            _save_config(self._config_path, udp)
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))
            return
        self.accept()
