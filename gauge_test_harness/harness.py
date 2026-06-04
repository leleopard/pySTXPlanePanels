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
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
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

import gauge_core.convert as _convert_reg  # noqa: F401 — registers convert functions
from gauge_core.lookup import lookup_piecewise
from gauge_core.mock_source import DEFAULT_MOCK_PORT
from gauge_core.registry import get_convert


# ── Dataref descriptor ────────────────────────────────────────────────────────

@dataclass
class _DatarefInfo:
    dataref: str
    # first lookup table found (used for Output column)
    table: list[list[float]] = field(default_factory=list)
    # convert function name applied before the table (None = raw value goes in)
    convert_fn: str | None = None
    # human-readable uses: "InstrName / CompName (rotation)", …
    used_by: list[str] = field(default_factory=list)
    # spinbox range — derived from table inputs when no convert_fn; wide fallback otherwise
    input_min: float = 0.0
    input_max: float = 50000.0


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

    def _register(raw_dr: Any, table: list, label: str,
                  convert_fn: str | None = None) -> None:
        key = _dr_key(raw_dr)
        if key not in registry:
            if convert_fn is None:
                lo, hi = _table_range(table)
            else:
                lo, hi = 0.0, 50000.0  # raw range unknown; wide fallback
            registry[key] = _DatarefInfo(
                dataref=key,
                table=table,
                convert_fn=convert_fn,
                input_min=lo,
                input_max=hi,
            )
        else:
            info = registry[key]
            # If we previously stored a convert-fn entry, upgrade to a
            # direct table entry when we find one — gives a tighter range.
            if convert_fn is None and info.convert_fn is not None:
                lo, hi = _table_range(table)
                info.table = table
                info.convert_fn = None
                info.input_min = lo
                info.input_max = hi
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
                      f"{label_base}  (rotation)",
                      convert_fn=rot.get("convert_function"))

        if "translation" in comp:
            tr = comp["translation"]
            _register(tr["dataref"], tr.get("table", []),
                      f"{label_base}  (translation)",
                      convert_fn=tr.get("convert_function"))

        if "animation" in comp:
            anim = comp["animation"]
            _register(anim["dataref"], anim.get("table", []),
                      f"{label_base}  (animation)",
                      convert_fn=anim.get("convert_function"))

        if "scroll" in comp:
            scr = comp["scroll"]
            _register(scr["dataref"], scr.get("table", []),
                      f"{label_base}  (scroll)",
                      convert_fn=scr.get("convert_function"))

        if "visibility" in comp:
            vis = comp["visibility"]
            _register(vis["dataref"], [],
                      f"{label_base}  (visibility)")

        # Text component: dataref at the top level of the component dict
        if "dataref" in comp and not isinstance(comp["dataref"], dict):
            _register(comp["dataref"], [],
                      f"{label_base}  (text)",
                      convert_fn=comp.get("convert_function"))

        for band in comp.get("bands", []):
            for i, endpoint in enumerate(band.get("range", [])):
                if isinstance(endpoint, dict) and "dataref" in endpoint:
                    _register(endpoint["dataref"], endpoint.get("table", []),
                              f"{label_base}  (band range[{i}])",
                              convert_fn=endpoint.get("convert_function"))

        # Dict-valued fields that may contain a dataref+table
        # (Vector direction/length, CircularGauge needle_angle, …)
        for field in ("direction", "length", "needle_angle"):
            val = comp.get(field)
            if isinstance(val, dict) and "dataref" in val:
                _register(val["dataref"], val.get("table", []),
                          f"{label_base}  ({field})",
                          convert_fn=val.get("convert_function"))

        # Flat *_dataref keys: AttitudeIndicator uses pitch_dataref / roll_dataref
        # (plain strings at the component level, no nested table).
        for key, val in comp.items():
            if key.endswith("_dataref") and isinstance(val, str):
                convert_key = key.replace("_dataref", "_convert_function")
                _register(val, [],
                          f"{label_base}  ({key})",
                          convert_fn=comp.get(convert_key))


def _find_panels_project_root(yaml_path: Path) -> Path:
    """Walk up to the 'panels' ancestor and return its parent (project root)."""
    candidate = yaml_path.parent
    while candidate != candidate.parent:
        if candidate.name.lower() == "panels":
            return candidate.parent
        candidate = candidate.parent
    return yaml_path.parent


def collect_datarefs(yaml_path: Path) -> list[_DatarefInfo]:
    """Return one _DatarefInfo per unique dataref found in a panel or instrument YAML."""
    yaml_path = Path(yaml_path).resolve()
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    registry: dict[str, _DatarefInfo] = {}

    if "instruments" in data:
        # Panel YAML: instrument paths are relative to the project root
        # (parent of the panels/ directory).
        base = _find_panels_project_root(yaml_path)
        for entry in data.get("instruments", []):
            inst_entries = (
                entry["grid"].get("instruments", [])
                if "grid" in entry
                else [entry]
            )
            for inst_entry in inst_entries:
                inst_path = (base / inst_entry["file"]).resolve()
                try:
                    with open(inst_path, encoding="utf-8") as f:
                        inst_data = yaml.safe_load(f)
                except Exception:
                    continue
                inst_name = inst_data.get("name", inst_path.stem)
                _collect_from_instrument(inst_data, inst_name, registry)
    else:
        # Single instrument YAML
        inst_name = data.get("name", yaml_path.stem)
        _collect_from_instrument(data, inst_name, registry)

    return list(registry.values())


# ── Digit-aware spinbox ───────────────────────────────────────────────────────

class _DigitSpinBox(QDoubleSpinBox):
    """Steps the digit at the cursor position rather than a fixed step size.

    Click on any digit in the displayed number, then press Up/Down (or click
    the arrows) to increment/decrement that digit's power of 10.
    """

    def wheelEvent(self, event):
        event.ignore()

    def stepBy(self, steps: int) -> None:
        le = self.lineEdit()
        text = le.text()
        cur = le.cursorPosition()

        sign_len = 1 if text.startswith('-') else 0
        dec_pos = text.find('.')
        if dec_pos == -1:
            dec_pos = len(text)

        # Digit immediately to the left of the cursor (clamped to first digit)
        idx = max(sign_len, cur - 1)
        # If cursor sits on the decimal point itself, use the units digit
        if idx < len(text) and text[idx] == '.':
            idx = max(sign_len, idx - 1)

        if idx < dec_pos:
            power = dec_pos - idx - 1      # e.g. hundreds=2, tens=1, units=0
        else:
            power = -(idx - dec_pos)       # e.g. tenths=-1, hundredths=-2

        step_size = (10.0 ** power) * steps
        self.setValue(round(self.value() + step_size, self.decimals()))
        # Restore cursor so repeated presses keep stepping the same digit
        le.setCursorPosition(cur)


# ── Main window ───────────────────────────────────────────────────────────────

_COL_DATAREF    = 0
_COL_VALUE      = 1
_COL_POST_CONV  = 2
_COL_OUTPUT     = 3
_COL_USED_BY    = 4


class TestHarnessWindow(QMainWindow):
    closed = Signal()

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

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
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Dataref", "Dataref value", "Value post conversion", "Output", "Used by"]
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setMinimumSectionSize(60)
        self._table.setColumnWidth(_COL_DATAREF,   280)
        self._table.setColumnWidth(_COL_VALUE,     120)
        self._table.setColumnWidth(_COL_POST_CONV, 150)
        self._table.setColumnWidth(_COL_OUTPUT,     80)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
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
            spin = _DigitSpinBox()
            spin.setRange(info.input_min, info.input_max)
            spin.setDecimals(6)
            spin.setValue(0.0)
            spin.setMinimumWidth(90)
            # capture row/info in closure
            spin.valueChanged.connect(
                lambda val, r=row, i=info: self._on_value_changed(r, i, val)
            )
            self._table.setCellWidget(row, _COL_VALUE, spin)

            # Value post conversion cell (read-only)
            pc_item = QTableWidgetItem("—" if info.convert_fn else "")
            pc_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(row, _COL_POST_CONV, pc_item)

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
        # Apply conversion function (if any) to get the post-conversion value
        post_conv = value
        if info.convert_fn:
            fn = get_convert(info.convert_fn)
            if fn is not None:
                post_conv = float(fn(value, lambda _: 0.0))

        # Update post-conversion column
        pc_item = self._table.item(row, _COL_POST_CONV)
        if pc_item is not None and info.convert_fn:
            pc_item.setText(f"{post_conv:.6g}")

        # Update output column (table lookup on post-conversion value)
        if info.table:
            output = lookup_piecewise(info.table, post_conv)
            out_item = self._table.item(row, _COL_OUTPUT)
            if out_item is not None:
                out_item.setText(f"{output:.2f}")

        # Send raw dataref value to MockDataSource
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
