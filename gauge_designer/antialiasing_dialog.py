"""Antialiasing quality dialog — configures AA method and level for the
panel runtime.

Stored in config.yaml (top-level `aa_mode:`/`ssaa:` keys, sibling of
`udp:`) rather than QSettings, so the setting is shared with every launch
method that reads that same file — gauge_core.runner loads it directly
regardless of how it was started (designer preview, a generated launch
script, or a bare `python -m gauge_core.runner`), not just designer-
launched subprocesses.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QRadioButton, QDialogButtonBox,
    QGroupBox, QLabel, QPushButton, QMessageBox,
)

# level -> (button label, description-when-software)
_LEVELS = [
    (0, "Off",  "No anti-aliasing — fastest."),
    (2, "2×",   "light smoothing."),
    (4, "4×",   "good quality (recommended)."),
    (8, "8×",   "high quality, higher GPU cost."),
]


def _load_aa(config_path: Path) -> tuple[str, int]:
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        mode = data.get("aa_mode", "software")
        level = int(data.get("ssaa", 4))
        return (mode if mode in ("software", "hardware") else "software", level)
    return ("software", 4)


def _save_aa(config_path: Path, mode: str, level: int) -> None:
    existing: dict = {}
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            existing = yaml.safe_load(f) or {}
    existing["aa_mode"] = mode
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
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)

        # ── AA method ────────────────────────────────────────────────────
        method_group = QGroupBox("AA Method")
        mg = QVBoxLayout(method_group)

        self._sw_rb = QRadioButton("Software (supersampling) — always works")
        self._hw_rb = QRadioButton("Hardware (GPU multisampling) — free when supported")
        mg.addWidget(self._sw_rb)
        mg.addWidget(self._hw_rb)

        hw_note = QLabel(
            "Hardware AA depends on your GPU driver honoring OpenGL's multisample "
            "request. This is known to silently fail on Windows with NVIDIA GPUs — "
            "their per-application driver profiles are keyed by executable name and "
            "never recognize a generic Python interpreter, so the request is quietly "
            "ignored. If unsupported, the runtime detects this automatically at "
            "launch and falls back to Software at the same level (a console warning "
            "is logged, nothing breaks). Use “Test on this machine” below "
            "to check ahead of time."
        )
        hw_note.setWordWrap(True)
        hw_note.setStyleSheet("color: #888; font-size: 11px;")
        mg.addWidget(hw_note)

        test_row = QHBoxLayout()
        self._test_btn = QPushButton("Test on this machine…")
        self._test_btn.clicked.connect(self._run_test)
        test_row.addWidget(self._test_btn)
        test_row.addStretch()
        mg.addLayout(test_row)

        self._test_result = QLabel("")
        self._test_result.setWordWrap(True)
        mg.addWidget(self._test_result)

        layout.addWidget(method_group)

        # ── Level ────────────────────────────────────────────────────────
        level_group = QGroupBox("Level")
        gl = QVBoxLayout(level_group)
        self._rbs: dict[int, QRadioButton] = {}
        for level, label, _desc in _LEVELS:
            rb = QRadioButton()
            self._rbs[level] = rb
            gl.addWidget(rb)
        layout.addWidget(level_group)

        # ── Load current state ──────────────────────────────────────────
        mode, level = _load_aa(self._config_path)
        self._sw_rb.setChecked(mode != "hardware")
        self._hw_rb.setChecked(mode == "hardware")
        (self._rbs.get(level) or self._rbs[4]).setChecked(True)

        self._sw_rb.toggled.connect(self._refresh)
        self._hw_rb.toggled.connect(self._refresh)
        for rb in self._rbs.values():
            rb.toggled.connect(self._refresh)
        self._refresh()

        # ── Buttons ──────────────────────────────────────────────────────
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _selected_level(self) -> int:
        for level, rb in self._rbs.items():
            if rb.isChecked():
                return level
        return 4

    def _refresh(self):
        """Level descriptions differ by mode: software SSAA gives N² samples
        per pixel, hardware MSAA gives exactly N — showing the same text for
        both would overstate what hardware mode actually delivers."""
        is_hw = self._hw_rb.isChecked()
        for level, label, sw_desc in _LEVELS:
            rb = self._rbs[level]
            if level == 0:
                rb.setText(f"{label}   —   {sw_desc}")
            elif is_hw:
                rb.setText(f"{label}   —   {level} samples per pixel (if supported)")
            else:
                rb.setText(f"{label}   —   {level * level} samples per pixel — {sw_desc}")
        self._test_btn.setEnabled(is_hw and self._selected_level() >= 2)
        if not is_hw:
            self._test_result.setText("")

    def _run_test(self):
        level = self._selected_level()
        self._test_btn.setEnabled(False)
        self._test_result.setStyleSheet("color: #888; font-size: 11px;")
        self._test_result.setText("Testing…")
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        try:
            result = subprocess.run(
                [sys.executable, "-m", "gauge_core.aa_probe", "--samples", str(level)],
                capture_output=True, text=True, timeout=20,
            )
            actual = int(result.stdout.strip())
        except Exception as exc:
            self._test_result.setStyleSheet("color: #d9822b; font-size: 11px;")
            self._test_result.setText(f"Could not run the test: {exc}")
        else:
            if actual >= level:
                self._test_result.setStyleSheet("color: #4caf50; font-size: 11px;")
                self._test_result.setText(
                    f"✓ Hardware AA confirmed working on this machine (samples={actual})."
                )
            else:
                self._test_result.setStyleSheet("color: #d9822b; font-size: 11px;")
                self._test_result.setText(
                    f"✗ This GPU/driver only provided samples={actual} (requested {level}). "
                    "Hardware mode will automatically fall back to Software here — "
                    "safe to leave selected if you're sharing this config with a machine "
                    "where it does work."
                )
        finally:
            self._test_btn.setEnabled(True)

    def _save_and_accept(self):
        mode = "hardware" if self._hw_rb.isChecked() else "software"
        level = self._selected_level()
        try:
            _save_aa(self._config_path, mode, level)
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))
            return
        self.accept()
