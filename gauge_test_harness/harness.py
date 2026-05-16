"""Test harness window.

Parses a panel or instrument YAML, collects every unique dataref referenced
by any component (rotation / translation / visibility transforms), and
presents a table:

    Dataref  |  Value spinbox  |  Output  |  Used by

- Value spinbox: drives the raw value sent to the gauge.
- Output: applies the component's lookup table so you see the result in the
  gauge's own units (degrees, pixels, etc.). When multiple components share
  a dataref with different tables the first table found is used.
- Used by: comma-separated list of instrument+component names (tooltip shows
  full detail).

Each spinbox change fires a JSON UDP packet to 127.0.0.1:<port> which
MockDataSource in the runner picks up immediately.
"""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gauge_core.lookup import lookup_piecewise
from gauge_core.mock_source import DEFAULT_MOCK_PORT


# ── Dataref descriptor ────────────────────────────────────────────────────────

@dataclass
class _DatarefInfo:
    dataref: str
    # first lookup table found for this dataref (used for Output column)
    table: list[list[float]] = field(default_factory=list)
    # human-readable uses: "InstrName / CompName (rotation)", …
    used_by: list[str] = field(default_factory=list)
    # suggested spinbox range derived from the table's input column
    input_min: float = -1000.0
    input_max: float = 1000.0


def _dr_key(raw: Any) -> str:
    """Normalise a YAML dataref value to a string key."""
    if isinstance(raw, list):
        return str(tuple(raw))
    return str(raw)


def _table_range(table: list) -> tuple[float, float]:
    if not table:
        return -1000.0, 1000.0
    inputs = [row[0] for row in table if len(row) >= 2]
    if not inputs:
        return -1000.0, 1000.0
    return float(min(inputs)), float(max(inputs))


def _collect_from_instrument(
    inst_data: dict,
    inst_name: str,
    registry: dict[str, _DatarefInfo],
) -> None:
    """Extract datarefs from a parsed instrument YAML dict."""

    def _register(raw_dr: Any, table: list, label: str) -> None:
        key = _dr_key(raw_dr)
        if key not in registry:
            lo, hi = _table_range(table)
            registry[key] = _DatarefInfo(
                dataref=key,
                table=table,
                input_min=lo,
                input_max=hi,
            )
        registry[key].used_by.append(label)

    # instrument-level visibility
    if "visibility" in inst_data:
        vis = inst_data["visibility"]
        _register(vis["dataref"], [], f"{inst_name}  (inst visibility)")

    for comp in inst_data.get("components", []):
        cname = comp.get("name", "(unnamed)")
        label_base = f"{inst_name} / {cname}"

        if "rotation" in comp:
            rot = comp["rotation"]
            _register(rot["dataref"], rot.get("table", []),
                      f"{label_base}  (rotation)")

        if "translation" in comp:
            tr = comp["translation"]
            _register(tr["dataref"], tr.get("table", []),
                      f"{label_base}  (translation)")

        if "visibility" in comp:
            vis = comp["visibility"]
            _register(vis["dataref"], [],
                      f"{label_base}  (visibility)")


def collect_datarefs(yaml_path: Path) -> list[_DatarefInfo]:
    """Return one _DatarefInfo per unique dataref found in a panel or instrument YAML."""
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    registry: dict[str, _DatarefInfo] = {}

    if "instruments" in data:
        # panel YAML
        base = yaml_path.parent
        for entry in data.get("instruments", []):
            inst_path = (base / entry["file"]).resolve()
            with open(inst_path, encoding="utf-8") as f:
                inst_data = yaml.safe_load(f)
            inst_name = inst_data.get("name", inst_path.stem)
            _collect_from_instrument(inst_data, inst_name, registry)
    else:
        # single instrument YAML
        inst_name = data.get("name", yaml_path.stem)
        _collect_from_instrument(data, inst_name, registry)

    return list(registry.values())


# ── No-scroll spinbox ─────────────────────────────────────────────────────────

class _NoScrollSpin(QDoubleSpinBox):
    def wheelEvent(self, event):
        event.ignore()


# ── Main window ───────────────────────────────────────────────────────────────

_COL_DATAREF = 0
_COL_VALUE   = 1
_COL_OUTPUT  = 2
_COL_USED_BY = 3


class TestHarnessWindow(QMainWindow):
    def __init__(self, yaml_path: str, port: int = DEFAULT_MOCK_PORT, parent=None):
        super().__init__(parent)
        self._port = port
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._infos: list[_DatarefInfo] = []

        self.setWindowTitle("Gauge Test Harness")
        self.resize(860, 520)

        central = QWidget()
        self.setCentralWidget(central)
        vbox = QVBoxLayout(central)
        vbox.setContentsMargins(6, 6, 6, 6)
        vbox.setSpacing(4)

        # ── header bar ───────────────────────────────────────────────────
        hdr = QHBoxLayout()
        self._file_label = QLabel()
        self._file_label.setStyleSheet("font-weight: bold;")
        hdr.addWidget(self._file_label)
        hdr.addStretch()
        port_lbl = QLabel(f"→ 127.0.0.1:{port}")
        port_lbl.setStyleSheet("color: #888; font-size: 11px;")
        hdr.addWidget(port_lbl)
        vbox.addLayout(hdr)

        # ── table ─────────────────────────────────────────────────────────
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            ["Dataref", "Value", "Output", "Used by"]
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setMinimumSectionSize(60)
        self._table.setColumnWidth(_COL_DATAREF, 320)
        self._table.setColumnWidth(_COL_VALUE,   110)
        self._table.setColumnWidth(_COL_OUTPUT,   90)
        self._table.setSelectionBehavior(self._table.SelectRows)
        self._table.setEditTriggers(self._table.NoEditTriggers)
        vbox.addWidget(self._table, 1)

        # ── footer bar ────────────────────────────────────────────────────
        foot = QHBoxLayout()
        reset_btn = QPushButton("Reset all to 0")
        reset_btn.clicked.connect(self._reset_all)
        foot.addWidget(reset_btn)
        foot.addStretch()
        vbox.addLayout(foot)

        self._load(yaml_path)

    # ── Loading ───────────────────────────────────────────────────────────

    def _load(self, yaml_path: str) -> None:
        p = Path(yaml_path).resolve()
        self._file_label.setText(p.name)
        self.setWindowTitle(f"Gauge Test Harness — {p.name}")

        self._infos = collect_datarefs(p)
        self._table.setRowCount(0)
        self._table.setRowCount(len(self._infos))

        for row, info in enumerate(self._infos):
            # Dataref cell
            dr_item = QTableWidgetItem(info.dataref)
            dr_item.setToolTip(info.dataref)
            self._table.setItem(row, _COL_DATAREF, dr_item)

            # Value spinbox
            spin = _NoScrollSpin()
            spin.setRange(info.input_min, info.input_max)
            spin.setDecimals(2)
            spin.setSingleStep(max(1.0, (info.input_max - info.input_min) / 100))
            spin.setValue(0.0)
            spin.setMinimumWidth(90)
            # capture row/info in closure
            spin.valueChanged.connect(
                lambda val, r=row, i=info: self._on_value_changed(r, i, val)
            )
            self._table.setCellWidget(row, _COL_VALUE, spin)

            # Output cell (read-only, updated on each spinbox change)
            out_item = QTableWidgetItem("0.00")
            out_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(row, _COL_OUTPUT, out_item)

            # Used-by cell
            short = ", ".join(
                u.split("/")[-1].split("(")[0].strip()
                for u in info.used_by
            )
            used_item = QTableWidgetItem(short)
            used_item.setToolTip("\n".join(info.used_by))
            self._table.setItem(row, _COL_USED_BY, used_item)

        self._table.resizeRowsToContents()

    # ── Spinbox callback ──────────────────────────────────────────────────

    def _on_value_changed(self, row: int, info: _DatarefInfo, value: float) -> None:
        # Update output column
        if info.table:
            output = lookup_piecewise(info.table, value)
            item = self._table.item(row, _COL_OUTPUT)
            if item is not None:
                item.setText(f"{output:.2f}")

        # Send to MockDataSource
        payload = json.dumps({info.dataref: value}).encode("utf-8")
        try:
            self._sock.sendto(payload, ("127.0.0.1", self._port))
        except Exception:
            pass

    # ── Reset ─────────────────────────────────────────────────────────────

    def _reset_all(self) -> None:
        for row in range(self._table.rowCount()):
            spin = self._table.cellWidget(row, _COL_VALUE)
            if spin is not None:
                spin.setValue(0.0)
