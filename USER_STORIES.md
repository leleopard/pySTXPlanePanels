# pySTXPlanePanels — User Stories & Epics

**Project:** pySTXPlanePanels
**Repo:** https://github.com/leleopard/pySTXPlanePanels (public)
**Version:** 0.0.0 (pre-MVP1)
**Status:** Planning & infrastructure setup

This file is the living changelog for the project. It is updated on every commit that adds, changes, or completes a feature.

---

## How this file works

- Each EPIC groups related user stories.
- Each story has a stable ID (e.g. `CORE-01`).
- Status icons: ✅ Done, 🚧 In progress, 🔲 Planned, ⚠️ Partial, ❌ Removed.
- When a feature is implemented, update the story status in the same commit that lands the implementation.
- Bugs are tracked in the "Known Defects" section at the bottom.
- Use `git log` for full commit detail; this file is the high-level index.

---

## EPIC 0 — Project Infrastructure

| ID | Story | Status |
|----|-------|--------|
| INFRA-01 | As a developer, I have a local git repository for pySTXPlanePanels so that all changes are version-controlled. | ✅ |
| INFRA-02 | As a developer, the repo is mirrored to GitHub at github.com/leleopard/pySTXPlanePanels so that changes are backed up and shareable. | ✅ |
| INFRA-03 | As a developer, every implementation change lands as a discrete commit with a clear message so that history is auditable. | 🚧 |
| INFRA-04 | As a developer, USER_STORIES.md tracks all features and their status so the project state is always visible. | ✅ |
| INFRA-05 | As a developer, CLAUDE.md preserves architectural context across sessions. | ✅ |

---

## EPIC 1 — gauge_core: Render Core (Arcade-based)

| ID | Story | Status |
|----|-------|--------|
| CORE-01 | As a developer, I have a `gauge_core` Python package skeleton with Arcade as the render dependency. | ✅ |
| CORE-02 | As a developer, gauge_core exposes a typed component registry so new component types (sprite, vector, text) can be added without modifying the core loader. | 🔲 |
| CORE-03 | As a developer, textures are interned by file path so loading the same atlas multiple times consumes one GPU texture. | ⚠️ Partial — atlas PIL Images are cached; per-region Arcade textures are not yet shared. |
| CORE-04 | As a developer, gauge_core uses relative texture paths resolved against a configurable asset root. | ⚠️ Partial — paths resolve relative to the YAML file. Configurable asset root TBD. |
| CORE-05 | As a developer, a piecewise-linear lookup table maps dataref values to angles/translations (port of `convertValueToTransformValue`). | ✅ |
| CORE-06 | As a developer, a conversion-function registry exposes the available data-shaping functions so the editor can pick from a known list. | 🔲 |

---

## EPIC 2 — Instrument YAML Schema & Loader

| ID | Story | Status |
|----|-------|--------|
| INSTR-01 | As a user, I can define an instrument in a YAML file with `name`, `size`, and a typed `components` list. | ✅ |
| INSTR-02 | As a user, an `ImagePanel` component supports `texture`, `layer`, `position`, `cliprect`, `origin`, `resize_to_container`, `maintain_proportions`. | ⚠️ Partial — texture/position/cliprect/origin work; layer, resize_to_container, maintain_proportions deferred. |
| INSTR-03 | As a user, an `ImagePanel` can declare `rotation` driven by an X-Plane dataref with a piecewise-linear calibration table and optional convert function. | ⚠️ Partial — dataref + table work; convert function not yet wired. |
| INSTR-04 | As a user, an `ImagePanel` can declare `translation` driven by a dataref with a calibration table, optional translation angle, and optional add-angle-to-rotation. | 🔲 |
| INSTR-05 | As a user, an `ImagePanel` can declare `visibility` driven by a dataref + toggle predicate so warning lights turn on/off. | 🔲 |
| INSTR-06 | As a user, a `Text` component renders a static string OR a formatted dataref value with a configurable font and color. | 🔲 |

---

## EPIC 3 — Panel YAML Schema & Loader

| ID | Story | Status |
|----|-------|--------|
| PANEL-01 | As a user, I can define a panel in a YAML file with `name`, `size`, `background_color`, and a list of instrument references with positions and scale. | 🔲 |
| PANEL-02 | As a user, a panel YAML can be loaded, opened in an Arcade window, and rendered live from X-Plane data. | 🔲 |

---

## EPIC 4 — X-Plane UDP Integration

| ID | Story | Status |
|----|-------|--------|
| UDP-01 | As a user, the panel runtime starts `pyxpudpserver` from a YAML/INI config and exposes a `getData(ref)` interface to components. | ⚠️ Partial — runner accepts UDP via CLI flags (--listen, --xp, --xp-name); YAML/INI config TBD. |
| UDP-02 | As a user, a "not receiving X-Plane data" overlay appears when UDP traffic stops. | 🔲 |

---

## EPIC 5 — Panel Runtime

| ID | Story | Status |
|----|-------|--------|
| RUN-01 | As a user, the runtime opens a window sized per panel YAML, draws the panel at 25+ FPS, and shows an FPS counter. | ⚠️ Partial — single-instrument window opens and draws; FPS counter and panel YAML deferred. |
| RUN-02 | As a user, ESC closes the window cleanly. | ✅ |
| RUN-03 | As a user, test mode (numpad +/-/*) drives all gauges with a simulated value when X-Plane is not running. | ✅ |
| RUN-04 | As a user, the runtime supports fullscreen and multi-monitor placement via panel YAML or CLI flags. | 🔲 |

---

## EPIC 6 — C172 Six-Pack Panel (MVP1 deliverable)

| ID | Story | Status |
|----|-------|--------|
| C172-01 | As a user, `instruments/c172_airspeed.yaml` renders a working airspeed indicator. | 🚧 Code path complete and runs without errors; visual fidelity pending user verification. |
| C172-02 | As a user, `instruments/c172_altimeter.yaml` renders a working altimeter. | 🔲 |
| C172-03 | As a user, `instruments/c172_vsi.yaml` renders a working vertical speed indicator. | 🔲 |
| C172-04 | As a user, `instruments/c172_directional_gyro.yaml` renders a working DG. | 🔲 |
| C172-05 | As a user, `instruments/c172_artificial_horizon.yaml` renders a working artificial horizon. | 🔲 |
| C172-06 | As a user, `instruments/c172_turn_coordinator.yaml` renders a working turn coordinator. | 🔲 |
| C172-07 | As a user, `instruments/c172_annunciator.yaml` renders the warning lights panel. | 🔲 |
| C172-08 | As a user, `panels/c172_six_pack.yaml` composes the six instruments + annunciator into the Cessna panel layout. | 🔲 |

---

## Out of MVP1 (Backlog)

These are tracked here for visibility but are not in scope for MVP1:

- G1000-style UV-scrolling speed/altitude tapes
- Framebuffer-based rectangular clipping
- Vector primitives (`Line`, `Polygon`, `Arc`) for jetliner glass cockpits (737, A320)
- Frame-based animated images
- Standalone `gauge_designer` Qt app (WYSIWYG editor)
- Multi-panel / multi-monitor coordination
- Mouse interaction / draggable windows

---

## Status Legend

| Symbol | Meaning |
|--------|---------|
| ✅ Done | Implemented and verified |
| 🚧 In progress | Active work |
| 🔲 Planned | Scoped, not started |
| ⚠️ Partial | Partially implemented; gaps documented |
| ❌ Removed | Dropped from scope |

---

## Known Defects

(none yet — project is pre-implementation)

---

## Changelog Index

High-level pointer to recent commits. Use `git log` for full detail.

- *2026-04-30* — Project context bootstrap: CLAUDE.md, USER_STORIES.md, .gitignore, initial git repo.
- *2026-04-30* — GitHub repo created at github.com/leleopard/pySTXPlanePanels; project renamed pySTXPlanePanels; INFRA-01/02/04 marked done.
- *2026-04-30* — **MVP0 vertical slice**: gauge_core package (lookup, component, loader, runner), `instruments/c172_airspeed.yaml`, atlas asset, pyproject.toml. `python -m gauge_core.runner instruments/c172_airspeed.yaml --test` opens an Arcade window with the C172 airspeed indicator; numpad/arrows/PgUp-PgDn drive the needle; ESC quits. UDP path also wired (verified the listener binds without an X-Plane peer). Visual fidelity awaiting user check.
