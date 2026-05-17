"""Shared UI helpers for gauge_designer widgets."""

from pathlib import Path

from PySide6.QtWidgets import QLabel, QSizePolicy
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtCore import QByteArray, Qt

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
