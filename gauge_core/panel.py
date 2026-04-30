"""Panel YAML schema and loader.

A panel composes one or more instruments at positions inside a single
window. The schema:

    name: C172 Six Pack
    size: [W, H]
    background_color: [r, g, b]   # optional, 0..255
    instruments:
      - file: instruments/c172_airspeed.yaml
        position: [px, py]        # bottom-left of the instrument in panel coords

Component-local positions inside each instrument are translated by the
instrument's panel position when the panel is loaded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from gauge_core.loader import Instrument, load_instrument


@dataclass
class Panel:
    name: str
    size: tuple[int, int]
    background_color: tuple[int, int, int] | None = None
    instruments: list[Instrument] = field(default_factory=list)

    def all_components(self) -> list[Any]:
        """Flat list of every component across every instrument, in order."""
        out: list[Any] = []
        for inst in self.instruments:
            out.extend(inst.components)
        return out


def _as_color(raw: Any) -> tuple[int, int, int] | None:
    if raw is None:
        return None
    return (int(raw[0]), int(raw[1]), int(raw[2]))


def load_panel(yaml_path: str | Path) -> Panel:
    yaml_path = Path(yaml_path).resolve()
    base_dir = yaml_path.parent

    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    panel = Panel(
        name=data["name"],
        size=tuple(data["size"]),
        background_color=_as_color(data.get("background_color")),
    )

    for entry in data.get("instruments", []):
        inst_path = (base_dir / entry["file"]).resolve()
        inst = load_instrument(inst_path)

        offset_x, offset_y = float(entry["position"][0]), float(entry["position"][1])
        for comp in inst.components:
            comp.apply_offset(offset_x, offset_y)

        panel.instruments.append(inst)

    return panel


def panel_from_instrument(inst: Instrument) -> Panel:
    """Wrap a single instrument in a synthetic Panel at origin.

    Lets the runner treat single-instrument and panel modes uniformly.
    """
    p = Panel(name=inst.name, size=inst.size, instruments=[inst])
    return p
