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
| INSTR-05 | As a user, an `ImagePanel` can declare `visibility` driven by a dataref + toggle predicate so warning lights turn on/off. | ✅ Any component's `visibility:` block also accepts an inline threshold comparison (`operator: <\|<=\|==\|!=\|>\|>=` + `value:`) as an alternative to `predicate:`, so simple thresholds don't need a new `convert.py` function. Editable from the designer's shared Visibility section (Mode: Named predicate / Compare value). |
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
| DESIGN-14 | As a user, every color picker button in the designer shows the current color as a small swatch (not as the button's own background, which fights the OS theme and makes the hex/alpha readout hard to read); any custom colors I pick in the "Custom colors" palette are still there the next time I open the app; and clicking "Add to Custom Colors" repeatedly fills the palette left-to-right instead of always overwriting the first slot. | ✅ |

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
| GLASS-07 | As a developer, digit-drum smooth rollover (the odometer effect where a higher digit blends toward its next value as the drum below it approaches wraparound) is configurable from YAML instead of requiring a new hardcoded `convert.py` function per drum resolution. | 🔲 Backlog — see note below. |
| GLASS-08 | As a user, a `VectorCompassRose` component renders a rotating HSI compass card: circle (background/line configurable), independently configurable 5°/10° heading ticks (size/color/width/inside-or-outside), and periodic heading labels (configurable interval/offset/inside-or-outside/font/color/format, with an optional bigger/smaller font on a coarser interval e.g. every 30°) — the whole rose rotates as a rigid body from a heading dataref, keeping the current heading at the top. | ✅ `gauge_core/vector_compass_rose.py`; designer preview + full properties form (`gauge_designer/canvas.py`, `properties_form.py`). |

**GLASS-07 note:** the altitude tape (B737-02) needed three near-identical convert functions — `return_hundreds_digit_20ft`, `return_thousands_digit_20ft`, `return_ten_thousands_digit_20ft` — each hardcoding a blend window (80→100, 980→1000, 9980→10000) tied to one specific instrument's drum resolution. A fourth drum at a different resolution means a fourth hardcoded function. Worth exploring a generic mechanism (e.g. a `digit_rollover` convert function that takes its place-value and blend-window-width as YAML parameters instead of being baked into the function name/body) so this scales without growing `convert.py` per instrument.

---

## EPIC 11 — B737 PFD Panel

Full procedural Primary Flight Display modelled on the Boeing 737-800 NG layout (see `Primary_Flight_Display_of_a_Boeing_737-800.png` in project root).

| ID | Story | Status |
|----|-------|--------|
| B737-01 | As a user, `instruments/B737/b737_airspeed_tape.yaml` renders a working vector airspeed tape with VNO/VFE/stall colored bands and selected-speed bug. | ⚠️ YAML + runtime done; speed bug (TapeBug, GLASS-02) not yet implemented. |
| B737-02 | As a user, `instruments/B737/b737_altitude_tape.yaml` renders a working vector altitude tape with 20 ft minor / 100 ft major ticks and selected-altitude bug. | 🚧 Built as `instruments/B737 PFD/Altitude_Tape.yaml` (converted from Speed_Tape) and wired into `panels/B737.yaml`. Main scale + selected-altitude bug done; sub-hundred drum (00/20/40/60/80) plus synced hundreds/thousands/ten-thousands digit tapes done. Ticks are 100 ft minor / 500 ft major, not 20 ft/100 ft as originally scoped. |
| B737-03 | As a user, `instruments/B737/b737_heading_tape.yaml` renders a working horizontal heading tape with 5° minor / 10° major ticks and heading bug. | 🔲 |
| B737-04 | As a user, `instruments/B737/b737_attitude_indicator.yaml` renders a working AI with pitch ladder, bank scale, and roll pointer. | 🚧 |
| B737-05 | As a user, `instruments/B737/b737_vsi.yaml` renders a vertical speed indicator (vector scale + digital readout). | 🔲 |
| B737-06 | As a user, selected speed, altitude, and heading digital readout boxes render as `Text` components with colored borders (matching 737 magenta/cyan convention). | 🔲 |
| B737-07 | As a user, `panels/b737_pfd.yaml` composes all B737 instruments into the full PFD layout at the correct positions. | 🔲 |

---

## EPIC 12 — Interactive Panel Controls

Adds mouse and touchscreen interactivity to the panel. The panel remains a UDP consumer for dataref data; it additionally sends X-Plane commands via `pyxpudpserver.sendXPCmd()` (already implemented in the library). Visual state of all controls is driven by datarefs — no local state. Interactive components are **invisible overlays**; appearance is handled by companion visual components (ImagePanel, FilledRect, etc.) driven by datarefs as normal.

### Architecture decisions

| Decision | Choice |
|---|---|
| Send mechanism | `pyxpudpserver.sendXPCmd()` / `sendXPDref()` — already in the library, no new sender needed |
| State truth | X-Plane datarefs only. Controls read state; they never own it |
| Optimistic UI | Short-lived pending flag set on press, cleared when confirming dataref arrives or after 600 ms timeout |
| Visual rendering | Separate from interaction. Interactive components are invisible at runtime; designer shows dashed hit-zone overlays |
| Input model | `on_mouse_press/drag/release/scroll` as primary path (Pi touchscreen emulates mouse for single touch); `on_touch_*` handlers as thin pass-throughs to the same gesture dispatcher |
| Rotary gesture | Tap left half = CCW step · tap right half = CW step · drag up = CW continuous · drag down = CCW continuous · mouse scroll = 1 step/notch |
| Hit target size | `component.size × hit_padding_multiplier` (panel-level YAML key, default 1.5) |
| `send_cmd` wiring | A `Callable[[str], None]` is passed to interactive components at panel-load time alongside the existing `get_data`. No-op in `--test` mode |

### YAML schemas

```yaml
# Momentary button — fires command on press, optional command_end on release
- type: Momentary_Button
  name: ap_engage_btn
  position: [150, 200]
  size: [50, 30]
  command: sim/autopilot/autopilot_on
  command_end: sim/autopilot/autopilot_off   # optional: sent on release

# Switch — reads state_dataref to choose which command to send on tap
- type: Switch
  name: landing_light_sw
  position: [80, 150]
  size: [40, 60]
  command_on: sim/lights/landing_lights_on
  command_off: sim/lights/landing_lights_off
  state_dataref: sim/cockpit/electrical/landing_lights_on
  # or single toggle: command: sim/lights/landing_lights_on_off_toggle

# Rotary encoder — tap halves or drag
- type: RotaryEncoder
  name: heading_bug_knob
  position: [200, 300]
  size: [60, 60]
  command_cw: sim/autopilot/heading_up
  command_ccw: sim/autopilot/heading_down
  drag_px_per_step: 5   # pixels of drag before firing one command step

# Panel-level hit padding (top-level key in panel YAML)
hit_padding_multiplier: 1.5   # default if absent
```

### Stories

| ID | Story | Status |
|----|-------|--------|
| CTRL-01 | As a developer, `PanelWindow` routes `on_mouse_press/drag/release/scroll` and `on_touch_begin/motion/end` through a single gesture dispatcher that hit-tests interactive components in panel coordinates, so both mouse and touchscreen share one code path. | 🔲 |
| CTRL-02 | As a developer, each interactive component exposes a `hit_rect` (position + size × `hit_padding_multiplier` read from the panel YAML, default 1.5) used exclusively for hit-testing, so touch targets are generously sized without affecting rendering. | 🔲 |
| CTRL-03 | As a user, I can place a `Momentary_Button` component on an instrument that fires an X-Plane command (`command`) on press and optionally a second command (`command_end`) on release, so I can implement both single-press and hold-to-activate controls. | 🔲 |
| CTRL-04 | As a user, I can place a `Switch` component that reads a `state_dataref` to decide which command to send (`command_on` or `command_off`) when tapped. A single `command` field is also accepted for instruments that expose a dedicated toggle command. | 🔲 |
| CTRL-05 | As a user, I can place a `RotaryEncoder` component where tapping the left half sends `command_ccw` and tapping the right half sends `command_cw` (one step each), and dragging up fires continuous CW steps while dragging down fires continuous CCW steps at a rate of one command per `drag_px_per_step` pixels (default 5). Mouse scroll wheel fires one step per notch. | 🔲 |
| CTRL-06 | As a developer, interactive components support optimistic pending state: on press a `pending` flag is set with a timestamp; when the confirming dataref value arrives the flag clears; if no confirmation arrives within 600 ms the flag times out and the dataref value takes over, preventing permanent divergence from X-Plane state. | 🔲 |
| CTRL-07 | As a user, I can configure `Momentary_Button`, `Switch`, and `RotaryEncoder` components in the gauge designer with a dedicated properties form for each type. | 🔲 |
| CTRL-08 | As a user, the designer canvas preview shows interactive components with a dashed hit-zone outline and a type icon (button / switch / encoder) so I can see interactive areas while editing. These overlays are not rendered at runtime. | 🔲 |

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
- *2026-07-01* — fix(core+designer): font names with a baked-in style word (e.g. `ST_Boeing_PFD Bold`) failed to render in both preview and runtime once the font moved from a single TTC to separate per-weight TTF files (`ST_Boeing_PFD-Regular.ttf` / `ST_Boeing_PFD_Bold.ttf`). Root cause: pyglet's DirectWrite backend matches loaded fonts by base family + weight flag, not by an exact "Family Style" name, so `font_name="ST_Boeing_PFD Bold"` was an unregistered family and silently fell back to a default font. `gauge_core/font_utils.py` adds `strip_style_suffix()`, called from `resolve_font_for_arcade()` for plain TTF/OTF files so the style word is dropped and the separate `bold`/`italic` flags do the matching instead. The designer's three "Choose font" pickers (`_pick_label_font`, `_pick_ai_ladder_font`, `_pick_txt_font` in `properties_form.py`) also strip the suffix from `QFontDialog`'s returned family name before writing it to the YAML field, since that dialog is what produced the bad names in the first place.
- *2026-07-01* — fix(core): `_find_font_file()` always returned the first alphabetically-sorted file matching a font name, ignoring the requested bold/italic — so the base name `ST_Boeing_PFD` (used with a separate `bold: true` flag) only ever registered `ST_Boeing_PFD-Regular.ttf` with pyglet (`-` sorts before `_`, beating `ST_Boeing_PFD_Bold.ttf`), and a bold request against that incomplete registration fell back to synthetic/faux-bold on the Regular face. Now collects all filename matches per directory and picks the one whose filename-inferred style (Bold/Regular/Italic suffix) best matches the requested `bold`/`italic`, mirroring the selection logic the designer's canvas preview (`_pil_font` in `canvas.py`) already used. Same underlying bug as the previous entry, different code path (file selection vs. name resolution).
- *2026-07-01* — fix(assets): the ST_Boeing_PFD Regular/Bold TTFs still rendered as the same weight in the runtime even after both prior fixes, because the font files themselves were malformed — `ST_Boeing_PFD-Regular.ttf` and `ST_Boeing_PFD_Bold.ttf` each declared their own style word baked into the OpenType family name (name ID 1 = "ST_Boeing_PFD Regular" / "ST_Boeing_PFD Bold" rather than a shared "ST_Boeing_PFD"), and neither set the OS/2 `fsSelection` REGULAR/BOLD bits nor `head.macStyle`. Windows' DirectWrite (pyglet's font backend) auto-merges same-named files into a group under a stripped base family, but this merge doesn't reliably select the correct face by weight, so a `bold=True` request silently rendered the Regular outlines faux-bolded rather than the true Bold glyphs — confirmed by pixel-diffing a rendered "88888" (895 px lit vs. 1525 px lit before/after the fix). Patched both TTFs' `name` table (IDs 1/2/4/6/16/17) to a proper shared family "ST_Boeing_PFD" with correct Regular/Bold subfamily names, and set `OS/2.fsSelection`/`usWeightClass` and `head.macStyle` per the OpenType RIBBI convention, using `fontTools`. This is the actual root cause; the two previous font_utils.py fixes were necessary but not sufficient without correcting the underlying font metadata.
- *2026-07-01* — feat(convert): `return_hundreds_digit_20ft`, a 20-foot-resolution counterpart to `return_hundreds_digit`. The B737 altitude tape's sub-hundred drum (`units_speed_tape` in `Altitude_Tape.yaml`) only shows values in 20 ft steps (0/20/40/60/80, via `return_sub_hundred`), so the existing `return_hundreds_digit` — which only starts blending in the final 1-unit window (99→100) — made the hundreds digit above it snap late and out of sync with the drum's continuous scroll. The new function starts the blend as soon as the sub-hundred value enters its last visible step (80→100), matching the drum's actual resolution. Wired into `hundredsDigit_alti_tape`'s `convert_function` (B737-02, still 🔲 overall but progressing).
- *2026-07-01* — feat(convert): `return_thousands_digit_100ft`, same fix one digit up. The hundreds-place digit below it (`hundredsDigit_alti_tape`) only changes once every 100 ft, so `return_thousands_digit`'s final-1-unit blend window (999→1000) made the thousands digit roll over far too quickly relative to the drum it sits above. The new function blends across the last 100 ft (900→1000) instead. Wired into `thousands_Digit_alti_tape`'s `convert_function`.
- *2026-07-01* — fix(convert): corrected the above — testing in the sim showed every digit drum on the real B737 tape blends over the same fixed final 20 ft, driven by the sub-hundred drum's own 20 ft resolution, not a window scaled to each digit's place value. Renamed `return_thousands_digit_100ft` → `return_thousands_digit_20ft` (blend window 980→1000, was 900→1000) and added `return_ten_thousands_digit_20ft` (blend window 9980→10000) for the same reason. Wired into `thousands_Digit_alti_tape` and `10Kdigit_alti_tape` respectively. All three altitude digit tapes (hundreds/thousands/ten-thousands) now share the same 20 ft blend window as `return_sub_hundred`.
- *2026-07-01* — feat(designer): VectorTape properties form gains a "Label format" field. `labels.format` (e.g. `'{:02.0f}'` for zero-padded sub-hundred altitude readouts) previously round-tripped correctly through the designer's save/load cycle but had no widget to actually set it from the GUI — you had to hand-edit the YAML. Added a `QLineEdit` next to the other label fields in `properties_form.py`; `format` is now excluded from `_vt_labels_cache`'s passthrough set (like `interval`/`font_size`/etc.) and instead read/written explicitly, same pattern as the other form-controlled label fields. Verified with a headless `QT_QPA_PLATFORM=offscreen` load/get_data round-trip.
- *2026-07-01* — fix(core): VectorTape labels popped into view only once mostly visible, instead of fading in as a growing sliver from the viewport edge. Root cause: `_draw_labels_y`/`_draw_labels_x` decide which label values are candidates for drawing this frame using a window of `val ± (half_range + 1)`, where the `+1` is a flat one-*value-unit* margin meant to catch labels just outside the visible edge. For a low-`pixels_per_unit` tape (e.g. the altitude sub-hundred drum: ppu=1.2, so 1 value unit = 1.2 px) that margin is far smaller than the ~11–15 px half-height of a 22 px-tall glyph, so a label was excluded from the candidate set — and therefore never even had an `arcade.Text` created/drawn for it — until it had already scrolled well past the edge into clear view; GL scissor clipping itself was working correctly the whole time. Changed the margin to `max(1.0, label_font_size / ppu)`, converting the font size into value-space so the candidate window is always at least as generous as one glyph height. No effect on tapes with large ppu (e.g. the single-digit drums, ppu=35, where `22/35 < 1` keeps the original flat-1 margin).
- *2026-07-02* — feat(B737): land `instruments/B737 PFD/Altitude_Tape.yaml`, converted from `Speed_Tape.yaml` over the preceding several commits (font fixes, `return_*_20ft` convert functions, label format, label-candidate margin fix) and now committed as a whole. Main altitude scale (100 ft minor / 500 ft major ticks, 200 ft labels) with selected-altitude bug (`autopilot/altitude_dial_ft`); a 4-tape digit odometer (sub-hundred drum at `return_sub_hundred` + hundreds/thousands/ten-thousands via the new `_20ft`-suffixed convert functions, all sharing the same 20 ft blend window); GS readout; bold selected-altitude readout. Wired into `panels/B737.yaml` alongside Speed_Tape and HSI. Marks B737-02 🔲 → 🚧.
- *2026-07-02* — docs: add GLASS-07 backlog story — digit-drum smooth rollover currently requires a new hardcoded `convert.py` function per drum resolution (`return_hundreds_digit_20ft`, `return_thousands_digit_20ft`, `return_ten_thousands_digit_20ft` for the altitude tape alone). Flagged for a more elegant, YAML-configurable mechanism before the next instrument that needs a digit drum.
- *2026-07-02* — feat(core+designer): inline threshold comparisons for `visibility:` blocks (INSTR-05). Previously every visibility condition needed a named predicate registered in `convert.py` (e.g. `true_if_zero`, `nav_gsflg_visible`) — a new threshold meant a new hardcoded function. `visibility:` now also accepts `operator: <|<=|==|!=|>|>=` plus `value: <number>` as an alternative to `predicate:`. `gauge_core/registry.py` adds `resolve_predicate_name(block)`, which returns the named predicate as-is, or for the inline form synthesizes and registers (memoized by operator+value) a comparison convert function on first use — so every component's existing `set_visibility(dataref, predicate_name)` call keeps its signature. Updated all 10 call sites across `component.py`, `text_component.py`, `vector_tape.py`, `vector_primitives.py` (×5), `attitude_indicator.py`, `circular_gauge.py`, plus instrument-level visibility in `loader.py`. Designer's shared Visibility section (`properties_form.py`) gains a Mode combo (Named predicate / Compare value) with a stacked Operator+Value page, mirroring the existing Text Static/Dataref mode pattern; round-trips correctly for both forms. Also closes part of the GLASS-07 concern for the visibility case specifically (digit-drum rollover itself is still open).
- *2026-07-03* — fix(designer): `Text` component's `anchor_y` selection had no effect on the canvas preview. `_render_text()` in `canvas.py` built its PIL anchor string as `{"left":"la","center":"ma","right":"ra"}[anchor_x]` — the vertical half of the anchor code was hardcoded to `"a"` (ascender) regardless of the `anchor_y` property, so choosing baseline/center/top/bottom in the properties form never changed where text landed in the preview (only the runtime, via `arcade.Text`, respected it). Now builds the horizontal and vertical PIL anchor characters independently (`baseline→"s"`, `center→"m"`, `top→"a"`, `bottom→"d"`) and concatenates them, matching PIL's two-character anchor convention. Verified by rendering two labels at the same position with `anchor_y: top` vs `bottom` and confirming visibly distinct placement.
- *2026-07-03* — feat(designer): tooltip explaining Python format-spec syntax on both format-string entry fields — VectorTape's "Label format" and Text's "Custom fmt" override. Shared `_FORMAT_SPEC_TOOLTIP` constant with worked examples (`{:.0f}`, `{:02.0f}`, `{:5.0f}`, `{:+.0f}`) since the syntax isn't self-evident and both fields previously only had a terse placeholder.
- *2026-07-03* — feat(core+designer): VectorTape labels gain a `justify` option (GLASS-01). Previously the label anchor was entirely implied by `side` — text always flushed against the spine (left-of-spine labels right-justified, right-of-spine labels left-justified), with no way to center a label on its offset point or reverse the justification independently of which side it's on. `labels.justify: left|center|right` (y-axis tapes) or `top|center|bottom` (x-axis tapes) now overrides the anchor without moving the offset point. `gauge_core/vector_tape.py`: new `label_justify` param on `VectorTape`, applied in `_draw_labels_y`/`_draw_labels_x` as `self._label_justify or default_justify`; parsed from YAML in the factory. `gauge_designer/canvas.py`'s static preview mirrors the same override. `properties_form.py` adds a "Label justify" combo (auto / left / center / right / top / bottom) next to "Label side". Verified the runtime change by rendering the same label under `justify=None/left/center/right` and confirming three distinct, correctly-offset pixel ranges.
- *2026-07-03* — feat(core+designer): split-font-size numeric emphasis for VectorTape labels (GLASS-01) and the `Text` component (INSTR-06) — the glass-cockpit altimeter convention of rendering leading digits above a place value in a bigger size, e.g. "30" big + "000" small for 30,000 ft, or "1" big + "000" small for 1,000 ft. New shared `gauge_core/emphasize.py::split_at_place(value, place)` returns `(hi_text, lo_text)`: `hi_text` is the plain int string of `value // place`, `lo_text` is `value % place` zero-padded to the digit width implied by `place`. Both consumers add `emphasize_place` (the split point) and `emphasize_font_size` (size for the leading part; the existing `font_size` stays the size for the remainder): `Text` creates a second `arcade.Text` (`label_hi`), measures both parts' `content_width` each update, and lays them out adjacently so the pair aligns as if it were one run anchored per the original `anchor_x`; `VectorTape` mirrors this per-label with a parallel `_label_hi_pool`, using a new axis-agnostic `_pair_start()` helper for the width-based positioning math (reading direction is always horizontal, even on an x-axis/horizontal tape, since digits read left-to-right regardless of tape scroll direction). `gauge_designer/canvas.py` mirrors both in the static PIL preview — for the dataref-driven `Text` case, which has no live value at design time, it renders a representative sample (`place * 12.345`) so the split is visible while editing. `properties_form.py` adds "Emphasize place" / "Emphasize font size" controls to both the VectorTape label section and the Text component's dataref page. Verified end-to-end: runtime renders for 30,000 and 1,005 matched the spec exactly; designer preview (both Text and VectorTape) matched the runtime pixel-for-pixel in a side-by-side check.
- *2026-07-03* — fix(core): `emphasize_place: 1` (or any single-digit place) appended a spurious trailing "0" — e.g. altitude 8400 rendered as "84000" with the last zero small. `split_at_place()`'s remainder formatting is `f"{lo:0{digits}d}"` where `digits` is the zero-count implied by `place`; for `place=1`, `digits=0`, but Python's format spec still renders a lone `"0"` for zero-width integer formatting rather than nothing. `lo_text` is now forced empty when `digits <= 0`, so the whole value renders as the emphasized part — matching what "split at the ones place" should mean.
- *2026-07-03* — fix(core): redefined `emphasize_place`/`split_at_place()` — testing surfaced that treating it as a place *value* (a power of ten, e.g. 1000) broke for anything else: `emphasize_place: 2` on altitude 8400 rendered "4200" (it was literally computing `8400 // 2`) instead of splitting into "84"+"00". `emphasize_place` is now a *count* of trailing digits to keep at the regular size — `place=1` -> ("840","0"), `place=2` -> ("84","00"), `place=3` -> ("8","400") — which works correctly for any non-negative integer, not just clean powers of ten, and matches the intuitive reading of the parameter. Internally `split_at_place(value, digits)` computes `place = 10**digits` and proceeds as before. Fixed the designer's Text-preview sample generator in `canvas.py` (`sample = place * 12.345`, which assumed the old value semantics and produced nonsense for small digit counts — now `sample = 10**digits * 12.345`) and tightened the "Emphasize place" spinbox range in `properties_form.py` from 0–1,000,000 to 0–8 (a sane digit-count range) with corrected tooltips on both the VectorTape and Text fields. No YAML migration needed — the key name is unchanged, so already-authored `emphasize_place` values just started meaning something more useful (and, for the one in-progress `Altitude_Tape.yaml` test case, correct).
- *2026-07-04* — fix(core): VectorTape bugs (the selected-speed/altitude triangle markers) now clip to the tape's viewport scissor rectangle, same as ticks/bands/labels. Previously `_draw_bugs_y`/`_draw_bugs_x` ran outside the scissor block by design — the intent was letting the bug polygon extend past the tape edge into the surrounding panel artwork — but in practice that let an out-of-range bug (anchor clamped to the viewport boundary) spill its polygon into neighboring panel elements uncontrolled. Moved the `_draw_bugs_y`/`_draw_bugs_x` calls inside the same `ctx.scissor = scissor` block as bands/ticks. Verified with a bug clamped to the top-left corner with points extending well past the viewport in both directions: only the portion inside the clip rectangle now renders.
- *2026-07-04* — feat(core+designer): VectorTape ticks gain an independent `y_offset` alongside the renamed `offset` -> `x_offset` (GLASS-01). Previously a tick def's `offset` only nudged the tick in the spine-to-tick direction (x for a y-axis tape, y for an x-axis tape) — there was no way to nudge a tick level along the tape's scroll axis for fine visual alignment. `x_offset`/`y_offset` are now plain screen-space pixel nudges applied uniformly regardless of tape axis: on a y-axis tape, `x_offset` reproduces the old spine-gap behavior and `y_offset` is the new along-tape nudge; the roles swap on an x-axis tape. Updated `_draw_ticks_y`/`_draw_ticks_x`, `apply_scale()`, and the YAML factory in `gauge_core/vector_tape.py`; mirrored in `canvas.py`'s static preview (careful with the y-axis case, since PIL's y is flipped relative to Arcade's y-up — `y_off` is subtracted there, not added, to match direction). `properties_form.py`'s ticks `_TableEditor` gains a 5th "Y Offset" column alongside the renamed "X Offset". Migrated the only two VectorTape instruments in the repo (`Speed_Tape.yaml`, `Altitude_Tape.yaml`) from `offset:` to `x_offset:` under `ticks:` so their existing tick positions aren't silently lost — verified both still produce identical `x_offset` values (with `y_offset` defaulting to 0) after the loader parses them.
- *2026-07-04* — feat(core+designer): VectorTape bands gain an `offset` (gap in px from the spine), matching the concept ticks already had before their `x_offset`/`y_offset` split. Previously a band always sat flush against whichever viewport edge its `side` implied (`bx = vx` or `vx + vw - bw`, no gap) — no way to inset a band from the tape edge. `offset` now shifts the band's near edge away from the spine in the same direction ticks extend: `bx = vx + offset` (side=left) / `vx + vw - bw - offset` (side=right) for `_draw_bands_y`, and the y-axis equivalent for `_draw_bands_x`. Added to the band dict construction in `VectorTape.__init__` and the factory, scaled in `apply_scale()`, mirrored in `canvas.py`'s static preview, and exposed as an "Offset px" spinbox in the `_BandsEditor`'s per-band edit panel (next to Width/Side), omitted from the YAML when 0 to keep existing bands unchanged. Verified both axes render bands at the expected shifted position via direct pixel-range checks.
- *2026-07-04* — feat(core+designer): AttitudeIndicator flight director H-bar/V-bar visibility gains inline threshold comparisons, same as the shared `visibility:` block (INSTR-05). Previously FD visibility was flat `fd_h_vis_dataref`/`fd_h_vis_predicate` (and `fd_v_*`) keys supporting only a named `convert.py` predicate — no comparison operator, and unused by any committed instrument, so migrated cleanly with no back-compat shim. Replaced with nested `fd_h_visibility`/`fd_v_visibility` dicts (`{dataref, predicate}` or `{dataref, operator, value}`), resolved via the existing `resolve_predicate_name()` in the factory — `set_fd_h_dataref`/`set_fd_v_dataref` themselves are unchanged, since they already just took a resolved predicate name string. Designer's FD H/V bar sections each gain a Mode combo (Named predicate / Compare value) with a stacked Operator+Value page, mirroring the shared Visibility section's UI exactly (also upgraded the predicate field from a free-text `QLineEdit` to the same `_PREDICATES`-populated combo used elsewhere, for consistency). Added `_SubSection.row_widget()` (existing on `_Section` but missing on `_SubSection`, needed to embed the stacked widget in the FD sub-section). Verified round-trip for both modes plus the no-visibility-configured case through the actual form.
- *2026-07-05* — feat(core+designer): new `VectorCompassRose` component (GLASS-08) — a rotating HSI compass card. `gauge_core/vector_compass_rose.py`: circle (optional background fill, optional outline with configurable color/width), independently configurable 5°/10° heading ticks (length/color/width/inside-or-outside), and periodic heading labels (interval/offset/inside-or-outside/font/size/color/format, default `"{:02.0f}"` applied to heading/10 — the standard two-digit aviation convention, e.g. 030° → "03"). The whole rose rotates as a rigid body from a `heading:` dataref: each element's neutral screen angle is `90 - heading_value`, and the current aircraft heading is simply added to that (`90 - heading_value + current_heading`) — mathematically identical to rotating the whole static dial, so no rotation matrix is needed; turning right (heading increases) correctly rotates the card counter-clockwise, matching a real rotating HSI. Verified: neutral orientation (heading=0) lays out headings clockwise like a real compass face; heading=45 moves "06" near the top and "00" to the upper-left, matching physical expectation exactly. Labels/ticks use a pooled `arcade.Text` list like `VectorTape`, recomputed every frame since rotation changes every element's position. Registered via `register_component`, module imported for side effects in `loader.py`. Designer integration: `canvas.py` gets a `_render_compassrose` static (heading=0) PIL preview plus hit-testing/drag/selection-highlight support (reusing the `Arc` component's `center`-based handling, extended to also cover `VectorCompassRose`); `properties_form.py` gets a full "Compass Rose" section (added to `_COMP_TYPES`) covering every field, verified via a headless round-trip through the actual Qt form and a full YAML→loader→factory→update→draw pipeline test. Design decisions confirmed with the user up front: rotation is driven by a heading dataref now (not deferred), and label format defaults to the two-digit `/10` convention (still overridable via `label_format`).
- *2026-07-05* — feat(core+designer): `VectorCompassRose` labels gain an optional bigger/smaller font on a coarser interval (GLASS-08), e.g. label every 10° but a bigger size every 30° — matching a real HSI rose's cardinal/major headings standing out from the in-between ones. New `label_emphasize_interval` (must be a multiple of `label_interval`) + `label_emphasize_font_size`; a heading's label uses the emphasized size when `heading % label_emphasize_interval == 0`, else the regular `label_font_size`. Implemented by mutating `arcade.Text.font_size` per label per frame (confirmed mutable post-construction, unlike some other Text properties) rather than a second label pool — simpler than the `Text`/`VectorTape` digit-emphasis feature since this is a size switch, not a two-part split render. Mirrored in `canvas.py`'s static preview (two `_pil_font` instances, picked per label by the same modulo check) and exposed as "Emphasize interval °" / "Emphasize font size" in the designer's Compass Rose section. Verified: labels every 10° render at the base size except 00/03/06/.../33 (multiples of 30), which render distinctly larger, in both the runtime and the designer preview.
- *2026-07-05* — feat(core+designer): `VectorCompassRose` labels now render radially — baseline perpendicular to the radius, "up" pointing outward — instead of always upright, matching a real rotating compass card/ship's compass rose. Each label's rotation is `heading - h` (Arcade's CCW-degrees convention, same as `arcade.Sprite`/`arcade.Text`'s `rotation` param): confirmed empirically that positive `arcade.Text.rotation` rotates CCW as viewed (a horizontal baseline swings up-and-right for a small positive angle), derived from `point_at()`'s neutral angle formula (`90 - h + heading`) minus the 90° "already upright" offset. At the top the label stays upright (rotation 0); at the sides it reads vertically; at the bottom it's upside-down relative to a fixed viewer — all correct and expected for a literal radial/perpendicular-to-radius layout (the same convention real compass cards use, since the whole rose rotates and only the top is meant to be read normally at any instant). `gauge_designer/canvas.py`'s static preview has no built-in rotated-text draw call, so added `_paste_rotated_text()`: renders each label to a small transparent tile, rotates it with `Image.rotate()` (confirmed empirically to match Arcade's rotation sign directly, no conversion needed — both send a rightward vector to up-and-right for a positive angle, despite PIL's y-down vs. Arcade's y-up pixel convention, because PIL's `rotate()` is deliberately defined in on-screen/visual terms), then alpha-pastes it onto the composite centered at the label's position. `_render_compassrose()`'s signature gained a `composite: Image.Image` param for this (paste target), updated at its one call site. Verified the designer preview is pixel-equivalent to the runtime's rendering at heading=0.
- *2026-07-05* — fix(core): flipped `VectorCompassRose` label rotation in the runtime — user confirmed the live app renders labels mirrored versus the intended radial orientation, even though the designer's PIL preview (added the same session) already looked correct. Changed `t.rotation` from `heading - h` to `h - heading` in `gauge_core/vector_compass_rose.py`; `canvas.py`'s preview is untouched since it wasn't affected. Root cause not fully isolated (plausibly a handedness flip somewhere in the runtime's Arcade/OpenGL render pipeline — e.g. an SSAA/FBO y-flip — that doesn't apply to the PIL-based static preview), but the fix directly addresses the reported symptom and was verified to reverse the tilt direction as expected.
- *2026-07-05* — feat(core+designer): `VectorCompassRose` labels gain a configurable vertical anchor (GLASS-08) — which part of the glyph sits at the offset point (radius ± `label_offset`), in the label's own radial/rotated orientation. New `label_anchor_y: baseline | center (default) | top | bottom`, passed straight through to `arcade.Text`'s own `anchor_y` at label-pool creation time (static per-instrument config, so set once like `anchor_x` already was, not re-applied per frame). Verified at the unrotated top position: `top` anchor puts the glyph's ascender at the offset point (rows 100–114 for a 24px offset at radius 180, extending inward from there); `bottom` puts the descender there instead (rows 71–85, extending outward) — precise pixel-range measurements, not just visual inspection. `gauge_designer/canvas.py`'s `_paste_rotated_text()` gained a matching `anchor_y` param (PIL vertical anchor code): draws the label into a generously oversized transparent tile with the requested anchor point placed at the tile's own centre (so `Image.rotate(expand=True)`, which always pivots on the image centre, correctly pivots on the anchor point), verified to match the runtime's pixel rows within font-metric differences. Exposed as a "Label anchor" combo (baseline/center/top/bottom, matching the `Text` component's existing wording) in the designer's Compass Rose section, omitted from the YAML at the default "center" to keep existing instruments unchanged.
- *2026-07-05* — feat(designer): reorganized the Compass Rose properties section into collapsible `_SubSection` groups (GLASS-08), matching `AttitudeIndicator`'s established style instead of one long flat list of rows: Layout (Center/Radius, open by default), Circle (background/line/segments), 5° Ticks, 10° Ticks, Heading Labels, and Heading Rotation (all collapsed by default). Pure UI reorganization — every widget keeps its existing attribute name and `load()`/`get_data()`/`clear()` logic is untouched, since those reference the widgets directly rather than through the section. Verified the full round-trip and the all-14-component-types smoke test still pass unchanged.
- *2026-07-05* — feat(core+designer): `VectorCompassRose` gains a Track Indicator (GLASS-08) — a line from the rose centre with an optional perpendicular tick, both driven by their own `track:` dataref (independent of `heading:`). Rotates *with* the rose (same `90 - angle + heading` convention as ticks/labels), so it shows track relative to the rotating card — i.e. crab angle — matching a real HSI, not an independent screen-fixed needle. New nested `track:` dict (`dataref`, `convert_function`, `color`, `width`, `start`/`end` in px from centre, optional `tick_position`/`tick_length` for the perpendicular mark, which shares the line's color/width per the request). `gauge_core/vector_compass_rose.py`: `set_track()` enables the feature (mirrors how `heading:`'s presence alone enables rotation — no separate show flag); `_draw_track()` computes the perpendicular tick via the line's own screen angle ± 90°. Verified visually: a 45° track line lands exactly between the "03" and "06" ticks with the perpendicular cross-tick at the configured distance. `canvas.py`'s static preview (no live dataref value) shows a representative 45° angle, verified pixel-equivalent to the runtime. `properties_form.py` adds a "Track Indicator" `_SubSection` (dataref, convert fn, color/width, start/end, tick position/length), enabled by a non-empty dataref like Heading Rotation, verified round-tripping including the no-track-configured case.
- *2026-07-05* — feat(designer): every color picker button (`_ColorButton` in `properties_form.py`, used by ~25 component color fields, plus the Panel tab's background-color button) now shows the current color as a small 16×16 swatch icon next to a hex/alpha text readout, instead of setting the button's own `background-color` via stylesheet (DESIGN-14) — the old styling fought the OS theme and made the readout text illegible against light or saturated colors. Also, `QColorDialog`'s 16-slot "Custom colors" palette is process-static and previously reset every app restart; `_ColorButton` now lazily loads it from `QSettings` (`colorPicker/customColor{0..15}`, stored as `QColor.HexArgb` strings) the first time any color button is constructed, and saves it back after every pick (even if the user cancels the dialog, since `QColorDialog` still records swatches added along the way). The Panel tab had a second, independent color-picker implementation (`_pick_bg_color`/`_update_bg_swatch` in `panel_view.py`) with the identical background-styling bug and no persistence; replaced it outright with a `_ColorButton` instance rather than duplicating the fix, removing ~20 lines and the now-unused `QColorDialog`/`QColor` imports from that file. Verified via a headless `QT_QPA_PLATFORM=offscreen` test: swatch has no `background-color` in its stylesheet, a custom color saved in one `_ColorButton`/`QSettings` round-trip is recovered after clearing Qt's in-memory palette and reloading, and the Panel tab's background-color get/set/clear cycle still round-trips correctly through `PanelView`.
- *2026-07-05* — fix(designer): `QColorDialog`'s "Add to Custom Colors" button always overwrote slot 0 instead of filling the palette left-to-right, because each pick opens a brand-new dialog instance (via the static `QColorDialog.getColor()` convenience call) whose internal "next slot" pointer resets every time. `_ColorButton._reslot_custom_colors(before)` now snapshots all 16 custom-color slots before opening the dialog and diffs against them after it closes: any slot the dialog overwrote gets restored to its prior value, and the newly-added color is instead written into our own tracked `_next_custom_slot` (persisted in `QSettings` alongside the colors themselves, wrapping back to slot 0 after 15). Initial version of this diff-and-relocate logic had a same-loop read-after-write bug — writing the relocated color into `_next_custom_slot` while still iterating over `before` could plant a value at a not-yet-visited index, which the loop then mistook for a second native change and re-relocated; fixed by splitting into two passes (detect all changes against the pre-dialog snapshot first, then restore, then relocate) so a write is never re-read as a change. Verified headlessly by simulating three consecutive "Add" clicks that all write to slot 0, confirming each lands in slots 0/1/2 respectively (not all colliding in slot 0), plus a 16-slot wraparound case.
