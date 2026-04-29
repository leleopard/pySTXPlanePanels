"""YAML instrument loader.

Reads an instrument YAML and returns a list of components plus the
instrument's name and pixel size. Texture paths are resolved relative
to the YAML file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from gauge_core.component import ImagePanel


@dataclass
class Instrument:
    name: str
    size: tuple[int, int]
    components: list[ImagePanel]


def load_instrument(yaml_path: str | Path) -> Instrument:
    yaml_path = Path(yaml_path).resolve()
    base_dir = yaml_path.parent

    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    components: list[ImagePanel] = []
    for comp_def in data.get("components", []):
        ctype = comp_def.get("type")
        if ctype != "ImagePanel":
            raise ValueError(
                f"MVP0 only supports type=ImagePanel; got {ctype!r} in {yaml_path}"
            )

        atlas_path = (base_dir / comp_def["texture"]).resolve()
        origin = tuple(comp_def["origin"])
        cliprect = tuple(comp_def["cliprect"])
        position = tuple(comp_def["position"])

        panel = ImagePanel(
            name=comp_def["name"],
            atlas_path=atlas_path,
            origin_xy=origin,
            cliprect_wh=cliprect,
            position_xy=position,
        )

        if "rotation" in comp_def:
            rot = comp_def["rotation"]
            dataref = rot["dataref"]
            # Allow YAML list form for legacy (group, index) datarefs
            if isinstance(dataref, list):
                dataref = tuple(dataref)
            panel.set_rotation(dataref, rot["table"])

        components.append(panel)

    return Instrument(
        name=data["name"],
        size=tuple(data["size"]),
        components=components,
    )
