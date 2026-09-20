"""What each golden case depends on.

A panel YAML pulls in instrument YAMLs, and those pull in textures and
fonts. Knowing that graph is what lets the change-impact selector
(`scripts/regress.py`) re-render only the cases a change can actually
affect: editing the C172 altimeter should not re-render the B737 PFD.

The same graph answers the related question of which panels break when an
instrument file moves — the selector only needs the forward direction
today, so that is all this builds.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Iterator

import yaml

from tests.discovery import PROJECT_ROOT, is_panel_yaml

# Suffixes that mark a YAML string value as a reference to an asset file
# rather than ordinary data. Asset paths are project-root relative, which
# the smoke tier separately enforces.
_ASSET_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".ttf", ".otf"}


def _walk_values(node: Any) -> Iterator[Any]:
    if isinstance(node, dict):
        for value in node.values():
            yield value
            yield from _walk_values(value)
    elif isinstance(node, list):
        for value in node:
            yield value
            yield from _walk_values(value)


def _read(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _asset_references(data: Any) -> set[Path]:
    """Every existing asset file referenced by string value in *data*."""
    assets: set[Path] = set()
    for value in _walk_values(data):
        if not isinstance(value, str):
            continue
        if Path(value).suffix.lower() not in _ASSET_SUFFIXES:
            continue
        candidate = (PROJECT_ROOT / value).resolve()
        if candidate.exists():
            assets.add(candidate)
    return assets


def _instrument_references(data: Any) -> set[Path]:
    """Every instrument YAML a panel's `instruments:` tree points at.

    Walks the raw tree rather than using the loader's own iterator so that
    grid and container nesting are followed without having to build the
    panel — the selector must work even when a config is mid-edit and
    would not load.
    """
    referenced: set[Path] = set()
    for value in _walk_values(data):
        if isinstance(value, dict) and isinstance(value.get("file"), str):
            candidate = (PROJECT_ROOT / value["file"]).resolve()
            if candidate.exists():
                referenced.add(candidate)
    return referenced


def yaml_dependencies(yaml_path: str | Path) -> set[Path]:
    """Every file *yaml_path* depends on, including itself.

    For an instrument: the YAML plus its textures and fonts. For a panel:
    that, plus every instrument it composes, transitively.
    """
    root = Path(yaml_path).resolve()
    if not root.exists():
        return set()

    dependencies: set[Path] = set()
    pending = [root]
    while pending:
        current = pending.pop()
        if current in dependencies:
            continue
        dependencies.add(current)

        try:
            data = _read(current)
        except Exception:
            # A config that does not parse still counts as a dependency —
            # it just cannot contribute any further edges.
            continue

        dependencies |= _asset_references(data)
        if is_panel_yaml(current):
            pending.extend(_instrument_references(data))

    return dependencies


def build_graph(cases: Iterable[dict[str, Any]]) -> dict[str, set[Path]]:
    """Map each case name to the set of files it depends on."""
    return {
        case["name"]: yaml_dependencies(PROJECT_ROOT / case["yaml"])
        for case in cases
    }


def cases_affected_by(
    changed: Iterable[str | Path],
    graph: dict[str, set[Path]],
) -> set[str]:
    """Names of the cases that depend on any of the *changed* paths."""
    changed_resolved = {
        (PROJECT_ROOT / path).resolve() if not Path(path).is_absolute()
        else Path(path).resolve()
        for path in changed
    }
    return {
        name
        for name, dependencies in graph.items()
        if dependencies & changed_resolved
    }
