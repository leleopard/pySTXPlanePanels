"""YAML instrument loader.

Reads an instrument YAML and returns its components plus name and pixel
size. Texture paths in the YAML are resolved relative to the YAML file.
Component types are looked up from the registry — adding `Text`, `Line`,
etc. is a matter of registering a factory; this loader doesn't change.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# Importing for side effects: the modules below register themselves with
# the component / convert registries at import time.
from gauge_core import component as _component  # noqa: F401
from gauge_core import convert as _convert  # noqa: F401
from gauge_core import text_component as _text_component  # noqa: F401
from gauge_core.registry import get_component_factory


@dataclass
class Instrument:
    name: str
    size: tuple[int, int]
    components: list[Any]


def load_instrument(yaml_path: str | Path) -> Instrument:
    yaml_path = Path(yaml_path).resolve()
    base_dir = yaml_path.parent

    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    components: list[Any] = []
    for comp_def in data.get("components", []):
        ctype = comp_def.get("type")
        if not ctype:
            raise ValueError(f"Component is missing `type:` in {yaml_path}")
        factory = get_component_factory(ctype)
        components.append(factory(comp_def, base_dir))

    return Instrument(
        name=data["name"],
        size=tuple(data["size"]),
        components=components,
    )
