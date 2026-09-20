"""Tier 1 — smoke tests.

Pure Python, no OpenGL context, no window. Every instrument and panel YAML
in the project is parsed and fully built through the real loaders, so any
schema drift, renamed convert function, moved instrument file or missing
texture fails here in about a second.

This is the tier that runs on every change.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator

import pytest
import yaml

from gauge_core.loader import load_instrument
from gauge_core.panel import load_panel, iter_leaf_instrument_entries
from gauge_core.registry import known_components, known_converts

from tests.discovery import (
    PROJECT_ROOT,
    instrument_yamls,
    panel_yamls,
    rel,
)

pytestmark = pytest.mark.smoke

INSTRUMENTS = instrument_yamls()
PANELS = panel_yamls()

INSTRUMENT_IDS = [rel(p) for p in INSTRUMENTS]
PANEL_IDS = [rel(p) for p in PANELS]
ALL_YAMLS = INSTRUMENTS + PANELS
ALL_IDS = INSTRUMENT_IDS + PANEL_IDS

# Windows drive letters, POSIX home/user roots, and UNC shares. Texture and
# instrument references must be relative so the project stays portable —
# absolute paths leaking back into configs is a regression this project has
# already had once (see CLAUDE.md, "Issues to fix during the port").
_ABSOLUTE_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|[\\/]{2}|/home/|/Users/)")

# YAML keys whose value names a convert function or visibility predicate.
_CONVERT_KEYS = {"convert_function", "predicate"}


def _walk(node: Any, path: str = "") -> Iterator[tuple[str, Any, Any]]:
    """Yield (dotted_path, key, value) for every mapping entry in a YAML tree."""
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else str(key)
            yield here, key, value
            yield from _walk(value, here)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            here = f"{path}[{index}]"
            yield from _walk(value, here)


def _read_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# -- Loading ---------------------------------------------------------------


@pytest.mark.parametrize("yaml_path", INSTRUMENTS, ids=INSTRUMENT_IDS)
def test_instrument_builds(yaml_path: Path) -> None:
    """Every instrument YAML builds: components construct, textures resolve."""
    instrument = load_instrument(yaml_path)

    assert instrument.name, f"{rel(yaml_path)}: instrument has an empty name"
    width, height = instrument.size
    assert width > 0 and height > 0, (
        f"{rel(yaml_path)}: non-positive size {instrument.size}"
    )


@pytest.mark.parametrize("yaml_path", PANELS, ids=PANEL_IDS)
def test_panel_builds(yaml_path: Path) -> None:
    """Every panel YAML builds, including all instruments it references."""
    panel = load_panel(yaml_path)

    assert panel.name, f"{rel(yaml_path)}: panel has an empty name"
    width, height = panel.size
    assert width > 0 and height > 0, f"{rel(yaml_path)}: non-positive size {panel.size}"
    assert panel.instruments, f"{rel(yaml_path)}: panel composes no instruments"


# -- Structural invariants the loaders do not enforce ----------------------


@pytest.mark.parametrize("yaml_path", PANELS, ids=PANEL_IDS)
def test_panel_instrument_references_exist(yaml_path: Path) -> None:
    """Each `file:` in a panel points at a file that is actually on disk.

    load_panel() would also fail on a dangling reference, but with a bare
    FileNotFoundError from deep inside the loader. Checking here names the
    panel, the entry and the missing path — which matters because moving an
    instrument between folders is a known way to break panels silently.
    """
    data = _read_yaml(yaml_path)
    missing = []
    for entry in iter_leaf_instrument_entries(data.get("instruments", []) or []):
        ref = entry.get("file")
        if not ref:
            continue
        if not (PROJECT_ROOT / ref).exists():
            missing.append(ref)

    assert not missing, (
        f"{rel(yaml_path)} references instrument files that do not exist:\n  "
        + "\n  ".join(missing)
    )


@pytest.mark.parametrize("yaml_path", ALL_YAMLS, ids=ALL_IDS)
def test_no_absolute_paths(yaml_path: Path) -> None:
    """No config hard-codes a machine-specific absolute path."""
    offenders = [
        f"{dotted} = {value!r}"
        for dotted, _key, value in _walk(_read_yaml(yaml_path))
        if isinstance(value, str) and _ABSOLUTE_PATH_RE.match(value)
    ]

    assert not offenders, (
        f"{rel(yaml_path)} contains absolute paths (must be project-relative):\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("yaml_path", ALL_YAMLS, ids=ALL_IDS)
def test_convert_functions_are_registered(yaml_path: Path) -> None:
    """Every named convert function / predicate exists in the registry.

    Covers components the loader skips (`hidden: true`), which would
    otherwise carry a dangling function name until the day they are unhidden.
    """
    known = set(known_converts())
    unknown = sorted(
        {
            value
            for _dotted, key, value in _walk(_read_yaml(yaml_path))
            if key in _CONVERT_KEYS
            and isinstance(value, str)
            and value not in ("", "(none)")
            and value not in known
        }
    )

    assert not unknown, (
        f"{rel(yaml_path)} references unregistered convert functions: "
        f"{', '.join(unknown)}"
    )


# -- Registry sanity -------------------------------------------------------


def test_component_registry_is_populated() -> None:
    """Importing the loader registers the component types it advertises."""
    components = known_components()
    assert "ImagePanel" in components
    assert "Text" in components


def test_project_has_configs_to_test() -> None:
    """Guard against the discovery globs silently matching nothing."""
    assert INSTRUMENTS, "no instrument YAMLs discovered under instruments/"
    assert PANELS, "no panel YAMLs discovered under panels/"
