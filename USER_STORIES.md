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
| C172-08 | As a user, `panels/c172_six_pack.yaml` composes all instruments into the Cessna panel layout (1540×920). | 🚧 Code path complete; visual verification pending. |
| C172-09 | As a user, `instruments/c172_oil_temp_pressure.yaml` renders oil temperature and pressure gauges. | 🚧 Code path complete; calibration tables may need tuning. |
| C172-10 | As a user, `instruments/c172_amp_vac.yaml` renders ammeter and vacuum/suction gauges. | 🚧 Code path complete; calibration tables may need tuning. |
| C172-11 | As a user, `instruments/c172_fuel_quantity.yaml` renders left and right tank fuel levels. | 🚧 Code path complete; calibration tables may need tuning. |
| C172-12 | As a user, `instruments/c172_fuel_flow.yaml` renders fuel flow and EGT gauges. | 🚧 Code path complete; calibration tables may need tuning. |
| C172-13 | As a user, `instruments/c172_rpm.yaml` renders the tachometer. | 🚧 Code path complete; visual verification pending. |
| C172-14 | As a user, `instruments/c172_vor1.yaml` renders VOR1 CDI with course needle, glideslope, TO/FROM, and OBS rose. | 🚧 Code path complete; datarefs corrected by user. |
| C172-15 | As a user, `instruments/c172_vor2.yaml` renders VOR2 CDI (identical layout, nav2 datarefs). | 🚧 Code path complete; datarefs may need tuning. |
| C172-16 | As a user, `instruments/c172_adf_indicator.yaml` renders an RMI-style ADF indicator with rotating compass card. | 🚧 Code path complete; visual verification pending. |
| C172-17 | As a user, `instruments/c172_compass.yaml` renders a simplified rotating-disc magnetic compass. | 🚧 Simplified version (no scrolling tape); UV-tape version deferred. |

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

---

## EPIC 8 — gauge_designer: Instrument Configuration GUI

| ID | Story | Status |
|----|-------|--------|
| DESIGN-01 | As a user, I can launch `python -m gauge_designer` to open a PySide6 desktop app. | ✅ |
| DESIGN-02 | As a user, I can open any instrument YAML (File→Open or recent files list) and see all components listed on the left. | ✅ |
| DESIGN-03 | As a user, clicking a component shows its full property tree (with nested sub-dicts expanded) on the right. | ✅ |
| DESIGN-04 | As a user, I can launch the Arcade preview of the current instrument in `--test` mode from a Preview button; the button disables while the window is open and re-enables when it closes. | ✅ |
| DESIGN-05 | As a user, I can edit component properties (position, origin, cliprect, table values, dataref) directly in the property tree without hand-editing YAML. | ✅ Note: save uses yaml.dump — header comments are not preserved on round-trip. |
| DESIGN-06 | As a user, I can add and reorder components in the list; changes are saved back to the YAML file (Ctrl+S / File→Save). | ✅ |
| DESIGN-07 | As a user, a WYSIWYG canvas renders the instrument at-size so I can see sprite positions while editing. The selected component is outlined in yellow; the preview updates live as property values are edited. | ✅ Note: sprites shown at nominal position with no rotation/translation applied (static preview only). |
| DESIGN-08 | As a user, I can click a sprite on the canvas to select it, and drag it to reposition it; the property tree and dirty flag update on release. | ✅ |
| DESIGN-09 | As a user, I can open and edit panel YAMLs in a Panel tab: instrument tree (plain + grid entries), PIL layout canvas, properties forms for each entry type, panel size controls, and ▲▼/+/− toolbar. | ✅ |
| DESIGN-10 | As a user, I can add a Grid Layout to the panel, configure its columns/rows/cell size, and drag instruments into/within the grid; tree order determines display order (first = top-left). | ✅ |
| DESIGN-11 | As a user, the Panel layout canvas shows a visual change when I reorder instruments inside a grid — each instrument keeps a consistent color tied to its file path, so swapping two cells produces a clearly different view. | ✅ |
| DESIGN-12 | As a user, no spinbox in the designer responds to the mouse wheel, so scrolling a form never accidentally changes a numeric value. All `QSpinBox` and `QDoubleSpinBox` instances are no-wheel subclasses imported from `gauge_designer.ui_utils`. | ✅ |
| DESIGN-13 | As a user, I can undo and redo edits in the instrument editor (Ctrl+Z / Ctrl+Y), so I can recover from accidental changes without reloading the file. | 🔲 |

---

## EPIC 9 — Vector Primitive Components

Static and dataref-driven vector shapes rendered via Arcade's `draw_*` API.  Intended as building blocks for custom bezel artwork and for composite glass-cockpit instrument types.  All primitives support `visibility` (same predicate mechanism as `ImagePanel`) and `apply_scale` / `apply_offset` so they compose correctly inside a panel.

| ID | Story | Status |
|----|-------|--------|
| VEC-01 | As a user, a `Line` component draws a straight line between two points with configurable color and width. | ✅ |
| VEC-02 | As a user, an `Arc` component draws a circular arc segment with configurable center, radius, start/end angles, color, and line width. | ✅ |
| VEC-03 | As a user, a `FilledRect` component draws a solid rectangle with configurable position, size, and color. | ✅ |
| VEC-04 | As a user, a `Polygon` component draws an open or filled polygon from a list of points with configurable color. | ✅ |
| VEC-05 | As a developer, all vector primitives accept an optional `visibility` block (same schema as `ImagePanel`) so any shape can be shown/hidden via a dataref predicate. | ✅ |
| VEC-06 | As a user, a `Vector` component draws an arrow from a configurable position, in a configurable direction (degrees) and length (pixels). Both direction and length can be static values or driven by datarefs with lookup tables and optional convert functions, independently. Designer canvas shows a live preview; properties form exposes direction and length via a Static/Dataref selector. | ✅ |
| VEC-07 | As a user, a `Vector` component can optionally have a cap at its tip: a filled `triangle` arrowhead or a `bar` (perpendicular line), with a configurable `cap_width`. Cap type defaults to `none`. Designer canvas and runtime both render the cap. | ✅ |

---

## EPIC 10 — Glass Cockpit Instrument Types

High-level procedural instrument components for jetliner-style glass panels (B737, A320).  Unlike sprite-based components, these generate geometry in Python each frame from dataref values — no pre-rendered texture strips required.

| ID | Story | Status |
|----|-------|--------|
| GLASS-01 | As a user, a `VectorTape` component draws a scrolling tape (airspeed or altitude) with configurable tick intervals, label intervals, label format string, colored speed/altitude bands, and a scissor viewport — driven by a dataref + calibration table. | ✅ |
| GLASS-02 | As a user, a `TapeBug` component overlays a filled triangle marker on a `VectorTape` viewport at a position driven by a separate dataref (e.g. selected speed bug, selected altitude). | 🔲 |
| GLASS-03 | As a user, a `HeadingTape` component draws a horizontal scrolling compass tape with configurable tick/label intervals and a center lubber line — driven by a heading dataref. | 🔲 |
| GLASS-04 | As a user, an `AttitudeIndicator` component renders a full AI: sky/ground background, pitch ladder (lines + labels CPU-rotated by bank angle), bank angle arc with tick marks, and roll pointer — all clipped to a configurable rectangular viewport. | ✅ |
| GLASS-05 | As a user, a `FlightPathVector` component renders the FPV symbol (circle + wing stubs + tail) positioned from pitch/roll/FPA datarefs within the AI viewport. | 🔲 |
| GLASS-06 | As a user, an `ILSDeviation` component renders a two-axis dot-style deviation indicator (localizer + glideslope) driven by the relevant datarefs. | 🔲 |

---

## EPIC 11 — B737 PFD Panel

Full procedural Primary Flight Display modelled on the Boeing 737-800 NG layout (see `Primary_Flight_Display_of_a_Boeing_737-800.png` in project root).

| ID | Story | Status |
|----|-------|--------|
| B737-01 | As a user, `instruments/B737/b737_airspeed_tape.yaml` renders a working vector airspeed tape with VNO/VFE/stall colored bands and selected-speed bug. | ⚠️ YAML + runtime done; speed bug (TapeBug, GLASS-02) not yet implemented. |
| B737-02 | As a user, `instruments/B737/b737_altitude_tape.yaml` renders a working vector altitude tape with 20 ft minor / 100 ft major ticks and selected-altitude bug. | 🔲 |
| B737-03 | As a user, `instruments/B737/b737_heading_tape.yaml` renders a working horizontal heading tape with 5° minor / 10° major ticks and heading bug. | 🔲 |
| B737-04 | As a user, `instruments/B737/b737_attitude_indicator.yaml` renders a working AI with pitch ladder, bank scale, and roll pointer. | 🚧 |
| B737-05 | As a user, `instruments/B737/b737_vsi.yaml` renders a vertical speed indicator (vector scale + digital readout). | 🔲 |
| B737-06 | As a user, selected speed, altitude, and heading digital readout boxes render as `Text` components with colored borders (matching 737 magenta/cyan convention). | 🔲 |
| B737-07 | As a user, `panels/b737_pfd.yaml` composes all B737 instruments into the full PFD layout at the correct positions. | 🔲 |

---

## Out of MVP1 (Backlog)

- G1000-style UV-scrolling speed/altitude tapes (superseded by EPIC 10 vector approach)
- Framebuffer-based rectangular clipping (not needed if AI uses CPU-side rotation)
- Frame-based animated images
- Multi-panel / multi-monitor coordination
- Mouse interaction / draggable windows
- Instrument properties form: disable mouse-wheel on all QSpinBox / QDoubleSpinBox widgets (same pattern as `_NoScrollComboBox` already in `properties_form.py`)

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
- *2026-05-02* — feat(c172): engine gauges, RPM, nav indicators, compass. Added 9 instruments to complete the full C172 panel: oil temp/pressure, ammeter/vacuum, fuel quantity, fuel flow/EGT, tachometer (RPM), VOR1 CDI, VOR2 CDI, ADF RMI, magnetic compass (simplified rotating-disc). Panel size expanded to 1540×920. New convert functions: `convert_lbs_to_gallons`, `convert_suction`, `nav_gsflg_visible`. Marks C172-09..C172-17 🚧.
- *2026-05-02* — feat(designer): MVP-D4 — interactive canvas. Click any sprite to select it (highlights in yellow, syncs list + property tree). Drag a sprite to reposition it: position updates live in the canvas during drag; on release the property tree reflects the new [x, y] and the file is marked dirty. Cursor changes to SizeAllCursor while dragging. Hit-test iterates components in reverse draw order so the topmost sprite wins on overlap.
- *2026-05-02* — feat(designer): MVP-D3 — WYSIWYG canvas preview. PIL composites all ImagePanel sprites at their nominal positions into a QScrollArea. Selecting a component highlights its cliprect in yellow; editing any value (position, origin, cliprect) redraws the canvas immediately. Non-ImagePanel components (Text) get a crosshair marker at their position. Atlas textures are cached per path so switching components doesn't reload the PNG. Window widened to 1060×620 for three-pane layout. Marks DESIGN-07 ✅.
- *2026-05-02* — feat(designer): MVP-D2 — editable property tree + add/reorder/remove components + save. Double-click any leaf value in the property tree to edit it in-place (int/float/bool coercion applied on commit). ▲▼ buttons reorder components in draw order; + adds a new blank ImagePanel; − removes with confirmation. Ctrl+S saves back to the YAML (via yaml.dump — header comments are not preserved on round-trip). Title shows `*` when unsaved; closing with unsaved changes prompts to discard or cancel. Marks DESIGN-05/06 ✅.
- *2026-05-02* — feat(designer): MVP-D1 gauge_designer PySide6 app. `python -m gauge_designer` opens a read-only instrument viewer: component list (left) + key/value property tree with nested expansion (right) + Preview button that launches the Arcade `--test` window via subprocess (button re-enables when window closes). File→Open YAML, recent-files menu (QSettings), status bar shows path + component count + size. Marks DESIGN-01..04 ✅.
- *2026-05-16* — feat(panel-designer): Panel tab with PIL layout canvas, instrument tree, three-page stacked properties form (plain instrument / grid header / grid instrument), panel size spinboxes, and Preview/Save support. Marks DESIGN-09 ✅.
- *2026-05-16* — fix(panel-designer): instrument scale spinbox widened and now drives visual scale in the layout canvas and at runtime (apply_scale/apply_offset in gauge_core). Fixed Arcade 3 Vec2 scale type error (use scale_x/scale_y).
- *2026-05-16* — feat(panel-designer): Grid Layout containers with drag-and-drop. +Grid button adds a grid entry; instruments can be dragged into grids or reordered within them; tree order determines cell position (first item = top-left, fills left-to-right). Marks DESIGN-10 ✅.
- *2026-05-16* — fix(panel-designer): grid instruments no longer disappear on drag-reorder (DragDrop mode + IgnoreAction); all children now visible (setExpanded after blockSignals); tree order matches grid display order. Marks DESIGN-10 improvements ✅.
- *2026-05-17* — fix(panel-designer): layout canvas colors now follow the instrument (file-path hash) rather than the cell position, so reordering instruments inside a grid produces a visually obvious change. Also defensive .get() for grid instruments list in tree rebuild. Marks DESIGN-11 ✅.
- *2026-05-23* — feat(designer): instrument file tree shows YAML `name` field instead of filename stem; label updates live when the Name field is edited; filename shown as tooltip. Added `_update_tree_label()` helper in `InstrumentView`.
- *2026-05-23* — feat(core): vector primitive components — `Line`, `Arc`, `FilledRect`, `Polygon`. All registered in the component registry via `gauge_core/vector_primitives.py`; imported for side-effects in `loader.py`. All four support `visibility` blocks. Added EPIC 9 (vector primitives), EPIC 10 (glass cockpit instrument types), EPIC 11 (B737 PFD panel) to USER_STORIES.md. Marks VEC-01..05 ✅.
- *2026-05-23* — feat(core+designer): `VectorTape` procedural scrolling tape component. `gauge_core/vector_tape.py` provides the runtime: scissor-clipped tick marks (configurable intervals / lengths / widths / per-level colour override), coloured bands, and unscissored labels — for both vertical (y) and horizontal (x) axes. Designer canvas shows a static tick-mark preview with band colour strips and viewport border. Designer properties form exposes axis, pixels-per-unit, tick side, tick colour, and scroll dataref/table; ticks/labels/bands round-trip transparently via `_extra`. `instruments/B737/b737_airspeed_tape.yaml` created as reference instrument. Marks GLASS-01 ✅, B737-01 ⚠️.
- *2026-05-30* — feat(core+designer): `Vector` component. Draws an arrow from a `position` in a given `direction` (degrees, Arcade convention: 0=right/east, CCW) for a given `length` (pixels). Both `direction` and `length` accept either a static float or a `{dataref, table, convert_function}` dict, independently. Runtime in `gauge_core/vector_primitives.py`; designer canvas preview + hit-test + drag; properties form uses `_BandEndpointWidget` for both scalars so the dataref+table path is fully functional. Test harness collects datarefs for both fields. Marks VEC-06 ✅.
- *2026-05-30* — fix(designer): canvas Y convention and vector-primitive drag. Coordinate label now respects the y-down/y-up preference (`is_y_down()`), matching the values shown in the properties form. Drag-to-reposition now works for `Line` (updates `start`/`end`), `Arc` (updates `center`), and `Polygon` (updates all `points`) instead of incorrectly writing a spurious `position` key; all three types move visually during drag and emit the correct anchor on release. DESIGN-08 fully extended to vector primitives.
- *2026-05-30* — feat(core+designer): `Vector` cap. A `cap` field (`none` / `triangle` / `bar`) and `cap_width` (px) can be added to any `Vector` component. `triangle` draws a filled arrowhead; `bar` draws a perpendicular line centred on the tip. Both are rendered in the runtime (`vector_primitives.py`) and in the designer canvas preview. Properties form adds Cap combo + Cap width spinbox (spinbox enabled only when cap ≠ none). Marks VEC-07 ✅.
- *2026-05-30* — feat(core+designer): `AttitudeIndicator` component. Full glass-cockpit AI with scissor-clipped viewport, sky/ground background, pitch ladder (lines + labels, CPU-rotated by bank), bank arc with ±10/20/30/45/60° ticks, roll pointer triangle, and fixed aircraft reference. Runtime in `gauge_core/attitude_indicator.py`; registered in loader. Designer canvas shows a static preview (bank=0, pitch=0) with the full geometry. Properties form exposes all visual parameters plus pitch/roll datarefs. Example instrument at `instruments/B737/b737_attitude_indicator.yaml`. Fixes canvas.py `half` → `half_w` NameError in vector bar-cap preview. Marks GLASS-04 ✅, B737-04 🚧.

- *2026-05-31* — fix(designer): all spinboxes now ignore mouse-wheel events (DESIGN-12). `QSpinBox` and `QDoubleSpinBox` subclasses that override `wheelEvent` to call `event.ignore()` exported from `gauge_designer.ui_utils`; all six files that used spinboxes updated to import from there instead of PySide6 directly.
