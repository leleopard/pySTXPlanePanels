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
| CORE-02 | As a developer, gauge_core exposes a typed component registry so new component types (sprite, vector, text) can be added without modifying the core loader. | ✅ |
| CORE-03 | As a developer, textures are interned by file path so loading the same atlas multiple times consumes one GPU texture. | ⚠️ Partial — atlas PIL Images are cached; per-region Arcade textures are not yet shared. |
| CORE-04 | As a developer, gauge_core uses relative texture paths resolved against a configurable asset root. | ⚠️ Partial — paths resolve relative to the YAML file. Configurable asset root TBD. |
| CORE-05 | As a developer, a piecewise-linear lookup table maps dataref values to angles/translations (port of `convertValueToTransformValue`). | ✅ |
| CORE-06 | As a developer, a conversion-function registry exposes the available data-shaping functions so the editor can pick from a known list. | ✅ |

---

## EPIC 2 — Instrument YAML Schema & Loader

| ID | Story | Status |
|----|-------|--------|
| INSTR-01 | As a user, I can define an instrument in a YAML file with `name`, `size`, and a typed `components` list. | ✅ |
| INSTR-02 | As a user, an `ImagePanel` component supports `texture`, `layer`, `position`, `cliprect`, `origin`, `resize_to_container`, `maintain_proportions`. | ⚠️ Partial — texture/position/cliprect/origin work; layer, resize_to_container, maintain_proportions deferred. |
| INSTR-03 | As a user, an `ImagePanel` can declare `rotation` driven by an X-Plane dataref with a piecewise-linear calibration table and optional convert function. | ✅ |
| INSTR-04 | As a user, an `ImagePanel` can declare `translation` driven by a dataref with a calibration table, optional translation angle, and optional add-angle-to-rotation. | ✅ |
| INSTR-05 | As a user, an `ImagePanel` can declare `visibility` driven by a dataref + toggle predicate so warning lights turn on/off. | ✅ |
| INSTR-06 | As a user, a `Text` component renders a static string OR a formatted dataref value with a configurable font and color. | ✅ |

---

## EPIC 3 — Panel YAML Schema & Loader

| ID | Story | Status |
|----|-------|--------|
| PANEL-01 | As a user, I can define a panel in a YAML file with `name`, `size`, `background_color`, and a list of instrument references with positions and scale. | ⚠️ Partial — name, size, background_color, instruments + positions all work. Per-instrument scale is deferred to a later commit. |
| PANEL-02 | As a user, a panel YAML can be loaded, opened in an Arcade window, and rendered live from X-Plane data. | ✅ |

---

## EPIC 4 — X-Plane UDP Integration

| ID | Story | Status |
|----|-------|--------|
| UDP-01 | As a user, the panel runtime starts `pyxpudpserver` from a YAML/INI config and exposes a `getData(ref)` interface to components. | ✅ `config.yaml` at project root sets listen/xplane host+port and optional xplane_name; CLI flags override. |
| UDP-02 | As a user, a "not receiving X-Plane data" overlay appears when UDP traffic stops. | ✅ |

---

## EPIC 5 — Panel Runtime

| ID | Story | Status |
|----|-------|--------|
| RUN-01 | As a user, the runtime opens a window sized per panel YAML, draws the panel at 25+ FPS, and shows an FPS counter. | ✅ |
| RUN-02 | As a user, ESC closes the window cleanly. | ✅ |
| RUN-03 | As a user, test mode (numpad +/-/*) drives all gauges with a simulated value when X-Plane is not running. | ✅ |
| RUN-04 | As a user, the runtime supports fullscreen and multi-monitor placement via panel YAML or CLI flags. | 🔲 |

---

## EPIC 6 — C172 Six-Pack Panel (MVP1 deliverable)

| ID | Story | Status |
|----|-------|--------|
| C172-01 | As a user, `instruments/c172_airspeed.yaml` renders a working airspeed indicator. | ✅ |
| C172-02 | As a user, `instruments/c172_altimeter.yaml` renders a working altimeter. | 🚧 Code path complete; visual verification pending. |
| C172-03 | As a user, `instruments/c172_vsi.yaml` renders a working vertical speed indicator. | 🚧 Code path complete; visual verification pending. |
| C172-04 | As a user, `instruments/c172_directional_gyro.yaml` renders a working DG. | 🚧 Code path complete; visual verification pending. |
| C172-05 | As a user, `instruments/c172_artificial_horizon.yaml` renders a working artificial horizon. | 🚧 Code path complete; visual verification pending. |
| C172-06 | As a user, `instruments/c172_turn_coordinator.yaml` renders a working turn coordinator. | 🚧 Code path complete; visual verification pending. |
| C172-07 | As a user, `instruments/c172_annunciator.yaml` renders the warning lights panel. | 🚧 Code path complete; visual verification pending. |
| C172-08 | As a user, `panels/c172_six_pack.yaml` composes the six instruments + annunciator into the Cessna panel layout. | 🚧 Code path complete; visual verification pending. |

---

## EPIC 7 — Bendix-King Radio Stack

**As a user, I want the five Bendix-King radios from `pyXPPanels/RadioStack.py` rendered as a YAML-driven panel, driven entirely by X-Plane datarefs (no Arduino input, no Python-side state machines).**

The original implementation mixed Arduino-input handling and a few Python-side state machines (e.g. ADF timer mode tracked by listening to X-Plane commands). For this rewrite the panel must be **display-only**: every visible state derived from a dataref X-Plane already publishes. Where the original used `registerXPCmdCallback`-style logic, we re-evaluate whether the underlying state has a dataref source before re-introducing any panel-side state.

| ID | Story | Status |
|----|-------|--------|
| RADIO-01 | As a user, `instruments/bk_navcomm_1.yaml` renders a working NAVCOMM #1 with COM/NAV active and standby frequencies. The whole instrument hides when com1 is unpowered. | 🚧 Code path + visuals OK at font_size 32. COM keeps 3 decimals (118.250) — visually differentiates COM vs NAV (which uses 2). Final precision/sizing may need re-tuning once the screen sits behind a hardware mockup of the radio stack. |
| RADIO-02 | As a user, `instruments/bk_navcomm_2.yaml` renders NAVCOMM #2 against com2/nav2 datarefs. | 🚧 Code path verified; visual verification pending (identical to NAVCOMM #1 modulo dataref indices). |
| RADIO-03 | As a user, `instruments/bk_dme.yaml` renders the DME (distance, speed, time). Whole instrument hides when `dme_power=0`. NAV1/2 source indicator deferred (no clear dataref in stock X-Plane). | 🚧 Code path complete; visual verification pending. |
| RADIO-04 | As a user, `instruments/bk_adf.yaml` renders the ADF. Timer mode (FRQ/FLT/ET) requires panel-side state machine — deferred per display-only design principle; panel always shows standby freq (FRQ mode). ANT/ADF/BFO indicators driven by `adf1_power` predicate. | 🚧 Code path complete; visual verification pending. |
| RADIO-05 | As a user, `instruments/bk_xpdr.yaml` renders the transponder. Mode indicators (SBY/ON/ALT/GND/R/FL) driven entirely by `transponder_mode` and `transponder_light` datarefs via equality predicates — no panel-side state. | 🚧 Code path complete; visual verification pending. |
| RADIO-06 | As a user, `panels/bk_radio_stack.yaml` composes all five radios into the original vertical-strip layout. | 🚧 Code path complete; visual verification pending. |
| RADIO-07 | As a developer, gauge_core supports **instrument-level visibility** so a single dataref can hide an entire composite instrument when unpowered. | ✅ |
| RADIO-08 | As a developer, the Text component supports custom TTF fonts loaded from a `font_file` path so radio readouts render in the correct LCD-style typeface (e.g. DS-Digital). | ✅ |
| RADIO-09 | As a developer, the convert-function registry includes `divideby100` so X-Plane's hundredths-of-MHz frequency datarefs render as 118.250 MHz. | ✅ |

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
- *2026-04-30* — fix: needle rotation direction. Arcade's `sprite.angle` already rotates clockwise for positive values, matching aircraft-gauge convention; removed the unnecessary negation that was inverting the needle direction. Visually confirmed by user.
- *2026-04-30* — feat(core): typed component + convert-function registries; ImagePanel gains translation, visibility, off-centre pivot, and convert-function support. Loader is now generic; new component types just register a factory. Convert functions ported from `pyXPPanels/lib/general/conversionFunctions.py`: return100s/1000s/10000s, convert_in_to_mb, add_compass_heading_to_value, calculate_turn_rate, true_if_over_zero, identity. Marks CORE-02, CORE-06, INSTR-03, INSTR-04, INSTR-05 ✅.
- *2026-04-30* — feat(component): Text component (arcade.Text) for static labels and dataref-driven readouts. Uniform `draw()` method introduced across components so the runner can mix sprite + text without isinstance checks. Marks INSTR-06 ✅.
- *2026-04-30* — feat(panel): panel YAML schema + loader; runner unified to handle either an instrument or a panel (single-instrument YAML is wrapped in a synthetic Panel of one). FPS counter shown in the window title. "Not receiving X-Plane data" overlay shown in UDP mode when pyxpudpserver.XPalive is False. Marks PANEL-02, RUN-01, UDP-02 ✅; PANEL-01 ⚠️ pending per-instrument scale.
- *2026-04-30* — feat(c172): all six instruments + annunciator + six-pack panel YAML. Each instrument YAML ports verbatim from `pyXPPanels/instruments/`: altimeter (3 needles + Hg/mb pressure wheels), VSI, directional gyro (heading card + bug), artificial horizon (rotation+translation), turn coordinator (off-centre ball pivot), annunciator (8 visibility-toggled warning lights). `panels/c172_six_pack.yaml` composes them at the original layout coords. Each YAML smoke-tested via `py -m gauge_core.runner ... --test`. Marks C172-02..C172-08 in progress (code path complete; visual verification pending).
- *2026-04-30* — fix(panel): six-pack instruments overlapped by 10 px because the 310-px bezels were placed on a 300-px grid (the original used zoom 0.97 to compensate; we deferred per-instrument scale). Switch to a 310-px grid: ASI stays at (170, 670), AH/ALT shift right by 10/20 px, bottom row drops by 10 px, annunciator recentres at (635, 860). Window grows from 950x920 to 960x920. Visually confirmed by user: instruments no longer overlap.
- *2026-04-30* — feat(radio MVP-0): Bendix-King NAVCOMM #1. New foundational gauge_core capabilities: `divideby100` convert function, instrument-level cascade visibility (`Instrument.visibility` predicate evaluated before drawing components, skipped in --test so all gauges show by default), and Text-component custom font loading via `font_file:` (cached load_font). DS-Digital-ItalicST.ttf and 2048_Radio_Stack_text.png copied into assets/. instruments/bk_navcomm.yaml renders the radio with 4 frequency readouts; whole instrument hides when com1_power=0 in UDP mode. Marks RADIO-01 in progress (code path verified; visual pending), RADIO-07/08/09 ✅. Adds new EPIC 7 with RADIO-02..06 still planned.
- *2026-04-30* — fix(radio): COM active/standby readouts overlapped at font_size 35 because arcade's natural-advance-width text rendering produces a 143-px wide "118.250" but the artwork's COM display windows are only 136 px apart. The original `GL_Font` used fixed-width per-char rendering with -4 px negative kerning (effective ~112 px); pyglet's high-level Text doesn't expose a letter-spacing knob, so we drop font_size from 35 to 32, scaling COM text to 131 px (5-px margin) and NAV to 110 px (10-px margin). User-confirmed the font/colour are right; only the size is the workaround.
- *2026-04-30* — feat(radio): NAVCOMM #2 (`bk_navcomm_2.yaml`). Identical layout to NAVCOMM #1 with com2/nav2 datarefs and com2_power as the cascade-visibility source. Renamed `bk_navcomm.yaml` -> `bk_navcomm_1.yaml` for symmetry (git mv preserves history). Marks RADIO-02 in progress.
- *2026-04-30* — refactor(c172): migrate flight instruments from legacy DATA(group, index) tuples to string datarefs. `pyxpudpserver.getData()` auto-subscribes string datarefs on first access (verified via source inspection), so no Data-Output configuration is required on the X-Plane side. Mappings: airspeed `(3,0)` -> `airspeed_kts_pilot`, altimeter pressure setting `(7,0)` -> `barometer_setting_in_hg_pilot`, VSI `(4,2)` -> `vvi_fpm_pilot`, DG bug `(118,1)` -> `autopilot/heading_dial_deg_mag_pilot`, art-horizon roll `(17,1)` -> `flightmodel/position/phi`, pitch `(17,0)` -> `flightmodel/position/theta`, turn-coord ball `(18,7)` -> `slip_deg`, turn-rate placeholder `(17,3)` -> `flightmodel/position/R`. `calculate_turn_rate` convert function rewritten to read `theta`, `phi`, `Q`, `R` strings.
- *2026-05-01* — feat(radio): DME, ADF, XPDR instruments + bk_radio_stack panel. New convert function `return_alt_hundreds` and 8 equality/range predicates (`true_if_zero`, `true_if_equals_1..5`, `true_if_over_1/2`). Text component gains dataref-driven visibility and lazy position application (fixes crash when Text.apply_offset() called before Arcade window exists). ADF timer mode deferred (display-only; always shows FRQ/standby freq). XPDR mode indicators driven purely by `transponder_mode` predicate — no state machine. Marks RADIO-03/04/05/06 🚧.
- *2026-05-01* — fix(runner): call pyxpudpserver.quit() on window close so sockets are released. Prevents "WinError 10048 address already in use" on relaunch.
- *2026-05-01* — fix(c172): turn coordinator bank angle 57× too large. `sim/flightmodel/position/Q` and `R` arrive in deg/s via RREF; the original DATA group 16 sent rad/s and needed `* 180/π`. Removed that factor from `calculate_turn_rate` so output stays in deg/s.
- *2026-05-01* — feat(config): `config.yaml` for X-Plane UDP settings. Runner auto-loads it from CWD; CLI flags override. Schema: `udp.listen_host/port`, `udp.xplane_host/port`, `udp.xplane_name`. Marks UDP-01 ✅.
- *2026-04-29* — refactor(c172): migrate annunciator panel from legacy tuples to string datarefs. All 8 warning lights now use canonical X-Plane annunciator datarefs: `low_voltage` (shared alternator+battery), `fuel_quantity`, `parking_brake_ratio`, `oil_pressure_low[0]`, `oil_temperature_high[0]`, `low_vacuum`, `autopilot_disconnect`. No DATA-Output group config needed in X-Plane. Dataref assignments documented in YAML header comment. All C172 instruments now fully migrated to string datarefs.
