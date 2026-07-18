"""Panel YAML schema and loader.

A panel composes one or more instruments at positions inside a single
window. Three entry types are supported in the `instruments` list:

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

Container (a positioned/sized box that groups instruments, each positioned
relative to the container's own origin instead of absolute panel coords).
Unlike Grid, a Container renders an actual background box at runtime when
`background_color` is set (reuses the FilledRect vector component):
    - container:
        name: "Radio Stack"       # optional label
        position: [px, py]        # bottom-left, y-up, absolute panel coords.
                                   # Omitted when nested as a grid cell (the
                                   # grid computes it, like plain grid-child
                                   # instruments never store position).
        size: [w, h]
        background_color: [r, g, b, a]  # optional, 0-255; omit = no box
        instruments:
          - file: instruments/c172_vor1.yaml
            position: [px, py]    # relative to the container's own origin
            scale: 0.9            # optional

A Container may itself be a grid cell (`grid.instruments[j]` can be either a
plain `{file, ...}` entry or a `{container: {...}}` entry) — no other
nesting is supported (no Container-in-Container, no Grid-in-Container/Grid).

Panel-level layout transform (optional, top-level keys, sibling of `instruments`):
    layout_scale: 1.0        # uniformly rescales the WHOLE arrangement of
                              # already-positioned instruments (pivoting
                              # around panel origin (0,0)), on top of each
                              # instrument's own individual `scale` —
                              # shrinks/grows the whole cluster as a unit
                              # without touching any instrument's own
                              # position/scale values in the YAML
    layout_offset: [0, 0]    # translates the (possibly rescaled) whole
                              # cluster, applied after layout_scale — lets
                              # the user reposition where the cluster shows
                              # up in the panel without moving instruments
                              # individually

Window placement (optional, top-level `window:` key):
    window:
      fullscreen: true        # default false
      screen: 1                # monitor index (as enumerated by the OS), 0-based
      position: [x, y]         # windowed mode only, ignored when fullscreen.
                                # Top-left of the window, offset from the
                                # top-left of `screen` above, in OS desktop
                                # pixels (Y-down) — NOT the panel's own
                                # Y-up coordinate system used everywhere
                                # else in this schema. Omit for the OS's
                                # own default window placement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import yaml

from gauge_core.loader import Instrument, load_instrument
from gauge_core.vector_primitives import FilledRect
from gauge_core.vector_primitives import _as_color as _vp_as_color


@dataclass
class Panel:
    name: str
    size: tuple[int, int]
    background_color: tuple[int, int, int] | None = None
    instruments: list[Instrument] = field(default_factory=list)
    udp_listen_port: int | None = None  # overrides config.yaml when set
    fullscreen: bool = False
    screen_index: int = 0
    window_position: tuple[int, int] | None = None  # windowed-mode only; None = OS default
    hit_padding_multiplier: float = 1.5
    layout_scale: float = 1.0
    layout_offset: tuple[float, float] = (0.0, 0.0)

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
    win_pos = win_cfg.get("position")
    panel = Panel(
        name=data["name"],
        size=tuple(data["size"]),
        background_color=_as_color(data.get("background_color")),
        udp_listen_port=udp_cfg.get("listen_port"),
        fullscreen=bool(win_cfg.get("fullscreen", False)),
        screen_index=int(win_cfg.get("screen", 0)),
        window_position=(int(win_pos[0]), int(win_pos[1])) if win_pos else None,
        hit_padding_multiplier=float(data.get("hit_padding_multiplier", 1.5)),
    )

    for entry in data.get("instruments", []):
        if "grid" in entry:
            _load_grid(entry["grid"], base_dir, panel)
        elif "container" in entry:
            _load_container(entry["container"], base_dir, panel)
        else:
            _load_instrument(entry, base_dir, panel)

    # Global layout transform — rescales and repositions the whole arrangement
    # of already-loaded instruments as a single unit, on top of each
    # instrument's own scale/position. Applied last, uniformly, regardless of
    # how deeply an instrument was nested in a grid/container, since every
    # loading path above has already resolved each component to its final
    # panel-space position by this point (scale first so it pivots around
    # panel origin (0,0), same convention as everywhere else in this file,
    # then offset to reposition the whole scaled cluster).
    panel.layout_scale = float(data.get("layout_scale", 1.0))
    layout_offset_raw = data.get("layout_offset", [0.0, 0.0])
    panel.layout_offset = (float(layout_offset_raw[0]), float(layout_offset_raw[1]))
    if panel.layout_scale != 1.0 or panel.layout_offset != (0.0, 0.0):
        for comp in panel.all_components():
            if panel.layout_scale != 1.0:
                comp.apply_scale(panel.layout_scale)
            if panel.layout_offset != (0.0, 0.0):
                comp.apply_offset(*panel.layout_offset)

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
        if "container" in inst_entry:
            c_cfg = inst_entry["container"]
            iw = float(c_cfg["size"][0])
            ih = float(c_cfg["size"][1])
            ox = gx + col * cw + (cw - iw) / 2
            oy = gy + (rows - 1 - row) * ch + (ch - ih) / 2
            _load_container(c_cfg, base_dir, panel, position=(ox, oy))
            continue
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


def _load_container(
    container_cfg: dict,
    base_dir: Path,
    panel: "Panel",
    position: tuple[float, float] | None = None,
) -> None:
    if position is None:
        position = (float(container_cfg["position"][0]), float(container_cfg["position"][1]))
    cx, cy = position
    cw = float(container_cfg["size"][0])
    ch = float(container_cfg["size"][1])

    bg = container_cfg.get("background_color")
    if bg is not None:
        bg_rect = FilledRect(
            name=f"{container_cfg.get('name', 'container')}_bg",
            position=(cx + cw / 2, cy + ch / 2),
            size=(cw, ch),
            color=_vp_as_color(bg),
        )
        panel.instruments.append(
            Instrument(name="__container_bg__", size=(int(cw), int(ch)), components=[bg_rect])
        )

    for entry in container_cfg.get("instruments", []):
        inst_path = (base_dir / entry["file"]).resolve()
        inst = load_instrument(inst_path)
        scale = float(entry.get("scale", 1.0))
        ox = cx + float(entry["position"][0])
        oy = cy + float(entry["position"][1])
        for comp in inst.components:
            if scale != 1.0:
                comp.apply_scale(scale)
            comp.apply_offset(ox, oy)
        panel.instruments.append(inst)


def iter_leaf_instrument_entries(entries: list[dict]) -> Iterator[dict]:
    """Recursively unwrap grid/container wrappers and yield every leaf
    ({file, ...}) instrument entry reachable from a top-level `instruments:`
    list, in document order.
    """
    for entry in entries:
        if "grid" in entry:
            yield from iter_leaf_instrument_entries(entry["grid"].get("instruments", []))
        elif "container" in entry:
            yield from iter_leaf_instrument_entries(entry["container"].get("instruments", []))
        else:
            yield entry


def panel_from_instrument(inst: Instrument) -> Panel:
    """Wrap a single instrument in a synthetic Panel at origin.

    Lets the runner treat single-instrument and panel modes uniformly.
    """
    p = Panel(name=inst.name, size=inst.size, instruments=[inst])
    return p
