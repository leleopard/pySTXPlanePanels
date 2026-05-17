"""Shared UI helpers for gauge_designer widgets."""

from PySide6.QtWidgets import QLabel

_HEADER_STYLE = (
    "QLabel { background-color: #424abb; color: white; "
    "font-weight: bold; padding: 3px 6px; }"
)


def header_label(text: str) -> QLabel:
    """Return a QLabel styled as a pane section header."""
    lbl = QLabel(text)
    lbl.setStyleSheet(_HEADER_STYLE)
    return lbl
