"""Panel YAML schema and loader.

A panel composes one or more instruments at positions inside a single
window. Two entry types are supported in the `instruments` list:

Plain instrument:
    - file: instruments/c172_airspeed.yaml
      position: [px, py]          # bottom-left in panel coords (y-up)
      scale: 0.9                  # optional

Grid layout (cells computed from col/row + cell size):
    - grid:
        name: "Nav Radios"        # optional label
        position: [px, py]        # bottom-left of the grid origin
        columns: 2
        rows: 1
        cell_width: 310
        cell_height: 310
        instruments:
          - file: instruments/c172_vor1.yaml
            col: 0
            row: 0
            scale: 0.9            # optional
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
    udp_listen_port: int | None = None  # overrides config.yaml when set
    fullscreen: bool = False
    screen_index: int = 0

    def all_components(self) -> list[Any]:
        """Flat list of every component across every instrument, in order."""
        out: list[Any] = []
        for inst in self.instruments:
            out.extend(inst.components)
        return out


def _as_color(raw: Any) -> tuple[int, int, int] | None:
    if raw is None:
        return None
    return (int(round(raw[0] * 255)), int(round(raw[1] * 255)), int(round(raw[2] * 255)))


def _find_project_root(yaml_path: Path) -> Path:
    """Walk up to the 'panels' ancestor and return its parent (project root).

    Instrument paths in panel YAMLs are relative to this root so that
    moving a panel YAML to any sub-folder within panels/ never breaks them.
    Falls back to yaml_path.parent if no 'panels' ancestor is found.
    """
    candidate = yaml_path.parent
    while candidate != candidate.parent:
        if candidate.name.lower() == "panels":
            return candidate.parent
        candidate = candidate.parent
    return yaml_path.parent


def load_panel(yaml_path: str | Path) -> Panel:
    yaml_path = Path(yaml_path).resolve()
    base_dir = _find_project_root(yaml_path)

    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    udp_cfg = data.get("udp", {}) or {}
    win_cfg = data.get("window", {}) or {}
    panel = Panel(
        name=data["name"],
        size=tuple(data["size"]),
        background_color=_as_color(data.get("background_color")),
        udp_listen_port=udp_cfg.get("listen_port"),
        fullscreen=bool(win_cfg.get("fullscreen", False)),
        screen_index=int(win_cfg.get("screen", 0)),
    )

    for entry in data.get("instruments", []):
        if "grid" in entry:
            _load_grid(entry["grid"], base_dir, panel)
        else:
            _load_instrument(entry, base_dir, panel)

    return panel


def _load_instrument(entry: dict, base_dir: Path, panel: "Panel") -> None:
    inst_path = (base_dir / entry["file"]).resolve()
    inst = load_instrument(inst_path)
    scale = float(entry.get("scale", 1.0))
    ox, oy = float(entry["position"][0]), float(entry["position"][1])
    for comp in inst.components:
        if scale != 1.0:
            comp.apply_scale(scale)
        comp.apply_offset(ox, oy)
    panel.instruments.append(inst)


def _load_grid(grid: dict, base_dir: Path, panel: "Panel") -> None:
    gx = float(grid["position"][0])
    gy = float(grid["position"][1])
    cols = int(grid.get("columns", 1))
    rows = int(grid.get("rows", 1))
    cw = float(grid.get("cell_width", 310))
    ch = float(grid.get("cell_height", 310))
    for idx, inst_entry in enumerate(grid.get("instruments", [])):
        col = idx % cols
        row = idx // cols
        inst_path = (base_dir / inst_entry["file"]).resolve()
        inst = load_instrument(inst_path)
        scale = float(inst_entry.get("scale", 1.0))
        iw = inst.size[0] * scale
        ih = inst.size[1] * scale
        ox = gx + col * cw + (cw - iw) / 2
        # Row 0 = top row; in y-up coords the top of the grid is gy+rows*ch.
        oy = gy + (rows - 1 - row) * ch + (ch - ih) / 2
        for comp in inst.components:
            if scale != 1.0:
                comp.apply_scale(scale)
            comp.apply_offset(ox, oy)
        panel.instruments.append(inst)


def panel_from_instrument(inst: Instrument) -> Panel:
    """Wrap a single instrument in a synthetic Panel at origin.

    Lets the runner treat single-instrument and panel modes uniformly.
    """
    p = Panel(name=inst.name, size=inst.size, instruments=[inst])
    return p
