"""Shared UI helpers for gauge_designer widgets."""

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QLabel, QSizePolicy,
    QSpinBox as _QSpinBox, QDoubleSpinBox as _QDoubleSpinBox,
)


class QSpinBox(_QSpinBox):
    """QSpinBox that ignores mouse-wheel events to prevent accidental edits."""
    def wheelEvent(self, event):
        event.ignore()


class QDoubleSpinBox(_QDoubleSpinBox):
    """QDoubleSpinBox that ignores mouse-wheel events to prevent accidental edits."""
    def wheelEvent(self, event):
        event.ignore()
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtCore import QByteArray, Qt, QSettings

_HEADER_COLOR = "#6682c5"

_HEADER_STYLE = (
    f"QLabel {{ background-color: {_HEADER_COLOR}; color: white; "
    "font-weight: bold; padding: 3px 6px; }"
)

_ICONS_DIR = Path(__file__).parent / "icons"


def header_label(text: str) -> QLabel:
    """Return a QLabel styled as a pane section header."""
    lbl = QLabel(text)
    lbl.setStyleSheet(_HEADER_STYLE)
    lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return lbl


def get_python_cmd() -> str:
    """Return the Python command to embed in generated launch scripts.

    Falls back to a platform default when the user has not set a preference.
    """
    default = "py" if sys.platform == "win32" else "python3"
    return QSettings().value("preferences/pythonCommand", default)


def get_ssaa_args() -> list[str]:
    """Return the runner.py --ssaa CLI arg for the current SSAA preference."""
    ssaa = QSettings().value("preferences/ssaa", 4, type=int)
    return ["--ssaa", str(ssaa)]


def is_y_down() -> bool:
    """Return True when the user has chosen the top-left / y-down convention."""
    return QSettings().value("preferences/coordSystem", "y_up") == "y_down"


def flip_y(y: int | float, height: int | float) -> int:
    """Convert a Y coordinate between y-up and y-down conventions.

    Self-inverse: flip_y(flip_y(y, h), h) == y.
    When y-up is active the value is returned unchanged.
    """
    return int(height - y) if is_y_down() else int(y)


def make_svg_icon(name: str, color: str = _HEADER_COLOR, size: int = 20) -> QIcon:
    """Load an MDI SVG from the icons directory, recolored to `color`."""
    try:
        with open(_ICONS_DIR / f"{name}.svg", encoding="utf-8") as f:
            svg = f.read()
        svg = svg.replace("<path ", f'<path fill="{color}" ')
        renderer = QSvgRenderer(QByteArray(svg.encode()))
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return QIcon(pixmap)
    except Exception:
        return QIcon()
