"""Shared YAML discovery + classification for the regression suite.

Both the pytest tiers and the change-impact selector (scripts/regress.py)
need the same answer to "what config files does this project have, and
which are panels vs instruments?" — so it lives here rather than being
duplicated.
"""

from __future__ import annotations

from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INSTRUMENTS_DIR = PROJECT_ROOT / "instruments"
PANELS_DIR = PROJECT_ROOT / "panels"


def _yaml_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*.yaml") if p.is_file())


def instrument_yamls() -> list[Path]:
    """Every YAML under instruments/, sorted for stable test ordering."""
    return _yaml_files(INSTRUMENTS_DIR)


def panel_yamls() -> list[Path]:
    """Every YAML under panels/, sorted for stable test ordering."""
    return _yaml_files(PANELS_DIR)


def is_panel_yaml(path: Path) -> bool:
    """A YAML is a panel if it has a top-level `instruments:` key.

    Mirrors the runner's own detection so the suite classifies files
    exactly the way the runtime will.
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return False
    return isinstance(data, dict) and "instruments" in data


def rel(path: Path) -> str:
    """Project-relative POSIX path — used for readable test IDs."""
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()
