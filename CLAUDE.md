# Plane Gauges — Project Context

## Project Goal

Cross-platform (Linux, Windows, ideally macOS) application that displays a 2D panel of fully functional aircraft gauges. The gauges receive data from the X-Plane flight simulator over the local network via UDP, and animate accordingly.

## Performance Target

25+ FPS on aging / moderate PC hardware. **Current Python+OpenGL implementation already meets this target comfortably** — performance is not the driver for any rewrite.

## Existing Assets

- **`pyxpudpserver`** — Python package (published, on user's GitHub) that handles X-Plane UDP protocol. Well documented, well structured. Easily portable to C++ if ever needed. **Status: keep as-is, dependency for new project.**
- **`pySTGraphics`** — pip package at `C:\Users\stephane\Desktop\pySTGraphics`, installed editable. Extracted version of the old `lib/graphics` from `pyXPPanels`, with added XML config loading (`PanelFileConfig` class) that builds `Container`s from XML at runtime. **Status: to be retired** — the user has opted to rewrite the render core on top of a higher-level abstraction (Arcade) rather than maintain the hand-rolled GL/shader code.
- **`pyXPPanels`** — original demo project at `C:\Users\stephane\Desktop\pyXPPanels`. Working C172 6-pack panel + various other panels (still scripted in Python). **Status: reference only**, not the target codebase.
- **`pyXPArduino`** — Arduino-config Qt app at `C:\Users\stephane\Desktop\pyXPArduino`. Includes a partial in-app instrument editor that produces XML configs and previews them via `pySTGraphics`. **Status: stays focused on Arduino → sim** (display-only scope, see Architectural Boundaries). The instrument editor is to be extracted into a separate standalone application.
- **Working XML schema** for instrument definitions, designed and tested in `pyXPArduino`. Lifts cleanly to YAML. See "Instrument schema reference" below.

## User Profile

- Occasional programmer.
- Low-level OpenGL code written years ago is now obscure to revisit.
- Comfortable in Python; UDP library is well within their wheelhouse.

## Real Pain Points (the actual drivers for this project)

1. **Maintainability / readability** of the low-level GL rendering code.
2. **Documentation** is lacking.
3. **Clean separation** of core libraries from application code is missing.
4. NOT performance — that's already solved.

## Working Process / Git Workflow

This project is version-controlled and mirrored to GitHub. The following rules apply for every change going forward — the user has pre-authorized routine commit + push so do NOT ask permission for each one:

1. **Every implementation change is a commit.** Each completed feature, bug fix, refactor, or doc update lands as a discrete commit covering exactly that change.
2. **Push every commit immediately** to the GitHub remote so the user's online mirror is always current.
3. **Update USER_STORIES.md in the same commit** that lands the implementation. Update the relevant story status (`🔲 → 🚧 → ✅`) and append the change to the Changelog Index at the bottom.
4. **Commit message style**: short headline (under 70 chars), then bullets explaining what changed and why. Reference the relevant USER_STORIES.md story ID where applicable (e.g. `CORE-02`).
5. **Documentation-only changes** (CLAUDE.md, USER_STORIES.md updates, memory edits) are committed too, with a `docs:` prefix on the headline.
6. **Do not bundle unrelated changes** in one commit. One feature/fix per commit.
7. **Do not commit secrets**. The `.gitignore` covers standard cases; verify before staging.
8. **Do not force-push or rewrite history** without explicit user authorization.
9. **Do not skip hooks** (`--no-verify`) without explicit user authorization. If a hook fails, fix the underlying issue and create a new commit.
10. **Do still confirm before destructive operations** — branch deletion, force-push, history rewrite, large reverts. Pre-authorization covers routine commit + push only.

## Architectural Boundaries (scope decisions)

**The rewrite is display-only. The panel is a one-way UDP consumer.**

- The panel application **MUST NOT** accept hardware inputs (Arduino, USB, etc.) and forward them to the simulator. Hardware → sim is handled by separate, dedicated software the user already maintains.
- Data flow is unidirectional: `hardware → (separate software) → X-Plane → UDP → panel display`.
- The simulator is the single source of truth. The panel renders what the sim broadcasts; it never assumes a hardware action took effect.
- The existing `pyXPPanels` codebase has a `RadioStack.py` with Arduino-driven inputs (an early experiment) — this design is **explicitly rejected** for the new project.

Rationale: avoid state divergence between hardware-side optimistic state and sim-side authoritative state, keep the panel app narrowly scoped to rendering, and respect existing tooling boundaries.

## Architecture Discussion Summary

### Dimensions considered

- **Language**: Python (current), C++, Rust, hybrid (Python core + C extension)
- **Rendering stack**: raw OpenGL+GLFW (current), SDL2+GL, Skia, Dear ImGui, wgpu/Vulkan (overkill), Arcade, Pyglet, raylib, SFML, moderngl
- **Threading**: UDP receive thread vs render thread; GIL considerations

### Key insight

For 2D textured-sprite gauge compositing, GPU is never the bottleneck on any hardware from the last ~15 years. Real risks are draw-call overhead, CPU compositing, GIL contention, and texture upload patterns — all already handled in the user's existing implementation.

### Three options on the table

**Option A — Python, replace only the render layer (RECOMMENDED)**
- Keep `pyxpUDPserver` unchanged.
- Swap raw GL for **Arcade** (built on pyglet/OpenGL): built-in `SpriteList` batching, sprite rotation/translation, PNG alpha — all native, well documented, cross-platform.
- Alternative: **raylib** via `pyray` bindings — even more readable, C-inspired API.
- Alternative: **moderngl** — cleaner OpenGL wrapper if more control is wanted.
- Tradeoff: lose easy custom-shader control (not needed here).

**Option B — Python data layer + C++/Rust render layer**
- Render process as separate executable, communicates via shared memory / local socket.
- **SFML** (C++) is the most readable 2D C++ graphics library.
- Justified only if Python hits a ceiling (not currently the case) or if a standalone redistributable render binary is wanted.

**Option C — Refactor existing code, no framework change**
- Clean up, document, extract packages. Stay on raw GL.
- Tradeoff: still maintaining code the user already finds obscure.

### Confirmed target architecture

Decisions (locked in):

1. **Retire the old hand-rolled GL render core** (`pySTGraphics`, `pyXPPanels/lib/graphics`). Build a new render core on Arcade. The legacy code is reference-only.
2. **Both instruments AND panels are config-driven** (YAML). The runtime composes a panel from a panel YAML which references instrument YAMLs.
3. **Format is YAML, not XML.** Lists like `[[0,0],[1.0,360]]` are first-class; no regex parsing layer; easier hand-editing.
4. **Components are typed and extensible.** Sprite-based (`ImagePanel`) and vector primitives (`Line`, `Polygon`, `Arc`, `Text`, etc.) coexist as different `type:` entries. A registry in `gauge_core` maps types to YAML loaders + Arcade render calls. Long-term goal: sprite C172-style + vector 737/A320-style panels in the same engine. Arcade's high-level API (`draw_line`, `draw_polygon_*`, `draw_arc_*`, `draw_text`, `ShapeElementList` batching) covers the vector primitive set with no render-stack change.

Five-component layout:

```
pyxpudpserver        (existing pip pkg, unchanged)         X-Plane UDP layer
─────────────────────────────────────────────────────────────────────────────
pyXPArduino          (existing app)                        Arduino → sim only
                                                           (instrument editor extracted out)
─────────────────────────────────────────────────────────────────────────────
gauge_core           (NEW pip pkg — successor to pySTGraphics)
                     Arcade-based render core; YAML loader for instrument
                     and panel configs; calibration lookup tables;
                     X-Plane data binding.

gauge_designer       (NEW Qt app)
                     Standalone WYSIWYG editor for instrument YAML files.
                     Lifts the existing pyXPArduino instrument editor logic
                     (~200 lines) and finishes the translation/rotation tabs.

gauge_panel_runtime  (NEW app)
                     Reads a panel YAML (composing N instruments at positions),
                     opens an Arcade window, drives gauges from UDP.
                     Replaces hand-written panel scripts like C172_Panel.py.
```

Data flow:

```
hardware → pyXPArduino → X-Plane → UDP → gauge_panel_runtime → Arcade window
                                          (reads panel.yaml +
                                           instrument YAMLs)
```

### Instrument schema reference (working XML, to be ported to YAML)

Lifted from `pyXPArduino/instruments/C172_Altimeter.xml` — the schema covers everything the C172 panel needs (sprite-space transforms with calibration tables):

```yaml
# instrument: c172_altimeter.yaml
name: C172 Altimeter
size: [500, 500]
position: [0, 0]
components:
  - type: ImagePanel
    name: black_background
    texture: textures/c172_text_standard6.png   # relative path, NOT absolute
    layer: 0
    position: [250, 250]
    cliprect: [300, 300]
    origin: [300, 1448]
    resize_to_container: true
    maintain_proportions: true

  - type: ImagePanel
    name: hundreds_needle
    texture: textures/c172_text_standard6.png
    layer: 0
    position: [250, 250]
    cliprect: [40, 300]
    origin: [430, 248]
    rotation:
      dataref: sim/cockpit2/gauges/indicators/altitude_ft_pilot
      table: [[0, 0], [1.0, 360]]
      convert_function: return100s
```

Translation, visibility-toggle, and texture-space transforms (G1000-only) extend the same shape. Conversion functions are referenced by string name and resolved from a registry the editor can introspect for autocomplete.

### Panel schema (NEW — was missing in current implementations)

```yaml
# panel: c172_six_pack.yaml
name: C172 Six Pack
size: [1600, 900]
background_color: [0.05, 0.05, 0.05]
instruments:
  - file: instruments/c172_airspeed.yaml
    position: [170, 670]
    scale: 0.97
  - file: instruments/c172_artificial_horizon.yaml
    position: [470, 670]
    scale: 0.97
  - file: instruments/c172_altimeter.yaml
    position: [770, 670]
    scale: 0.97
  # ... etc
```

### Issues to fix during the port (carried over from existing implementations)

- **Absolute texture paths** in current XML configs (e.g. `C:\Users\stephane\...`) — must be relative to the YAML file or to a configured asset root.
- **Texture deduplication**: the current `Container` loader instantiates a new `GL_Texture` per ImagePanel even when they share an atlas. New loader must intern textures by path.
- **Translation/rotation tabs** in `pyXPArduino` instrument editor are UI-only — the Python wiring to read/write those fields is not implemented. New editor must complete this.
- **Conversion-function registry** needs to be discoverable by the editor (so the GUI can offer a dropdown, not free-text).
- **Class-level mutable defaults** in legacy `ImagePanel` (latent bug) — fix in the rewrite.

## Existing Project Audit (`C:\Users\stephane\Desktop\pyXPPanels`)

The existing implementation was reviewed in detail. Key files:
- `C172_Panel.py` — working main script, working Cessna 6-pack + warning lights.
- `lib/general/pyXPPanel.py` — main `pyXPPanel` class: GLFW init, config.ini loader, X-Plane UDP server bootstrap, main loop, FPS counter, key/mouse callback dispatch, "no XP data" overlay.
- `lib/graphics/OpenGL3lib.py` — the "hardcore" layer: `GL_Texture`, `GL_BatchImageRenderer` (per-layer / per-texture buffers, 140 images max per buffer, model+text matrix uniform arrays), `GL_Image` (per-image quad with rotation/translation matrices), `GL_Font` (PIL-rendered character atlas), `GL_rectangle`/`GL_Filled_Rectangle`. ~1100 lines including a deprecated `GL_Image_OLD`.
- `lib/graphics/graphicsGL3.py` — higher-level: `Panel`, `Container` (hierarchy + cascading position/visibility/test mode + mouse hover/drag), `Window`, `TextField`, `TextBox`, `InputTextField`, `ImagePanel` (the workhorse — wraps `GL_Image` with dataref-driven rotation/translation/visibility), `AnimatedImage`. The 130-line `ImagePanel.draw()` includes the per-frame "refresh only if delta > threshold" optimization.
- `instruments/` — 25+ instrument classes, each subclasses `Container` and composes `ImagePanel`s on a shared 2048×2048 texture atlas (`c172_text_standard6.png`).

### Capabilities used (categorized)

**Sprite-space transforms** (used everywhere, including the entire C172 panel):
- Position translation
- Rotation around an arbitrary pivot point (`rotationCenter`)
- Resize, visibility toggle (annunciator lights)
- Sprite translation along a direction tied to rotation angle

**Texture-space transforms** (used by G1000 instruments only, NOT by C172):
- UV translation for scrolling tapes (`enableTextureTranslation` / `setTranslateTexture`)
- UV rotation (`textureRotation`)
- UV zoom (`textureZoom`)
- Sub-region clipping from the atlas (`cliprect` / `cliprect_origin`) — used everywhere

**Higher-level features:**
- Layered batched rendering (per-layer, per-texture VAO/VBO grouping)
- `Container` hierarchy with cascading transforms / visibility / test-mode
- `ClippingPanel` (glScissor) for rectangular clip windows — used in G1000 speed tapes
- Piecewise-linear value→angle/translation lookup tables (`convertValueToTransformValue`) — the gauge calibration mechanism
- Per-frame "refresh only if delta > threshold" gating
- Bitmap-font atlas via PIL (`GL_Font`) with `TextField` driven from datarefs
- Frame-based animation (`AnimatedImage`)

**Plumbing:**
- GLFW window/input/multi-monitor/fullscreen
- Config.ini for window/network settings
- Test mode with numpad keyboard for offline calibration
- `pyxpudpserver` integration with a "not receiving XP data" overlay text
- *(Existing code also has optional Arduino serial input — explicitly OUT OF SCOPE for the rewrite, see Architectural Boundaries below.)*

### Gap analysis vs Arcade

| Capability | Arcade fit | Notes |
|---|---|---|
| Texture atlas + sub-region | Native | `arcade.load_spritesheet()` |
| Sprite position / rotation / scale | Native | `Sprite.position`, `.angle`, `.scale` |
| Pivot-point rotation | Workaround (standard pattern) | Needle = sprite whose own center is on the pivot — same model the existing code uses |
| Visibility toggle | Native | `Sprite.visible` |
| Sprite translation along direction | Native | Position arithmetic |
| Layering / batched draw | Native | One `SpriteList` per layer, GPU-batched |
| PNG with alpha | Native | |
| GLFW windowing | Replaced by pyglet (Arcade dep) | Multi-monitor/fullscreen exist; API differs — worth verifying for home-cockpit setups |
| Bitmap font atlas | Native | `arcade.Text` |
| Frame-based animation | Native | `AnimatedTimeBasedSprite` |
| Container hierarchy | User-built (~50 lines) | Trivial Python wrapper |
| Calibration lookup tables | Pure Python | Port `convertValueToTransformValue` as-is |
| Per-frame refresh gating | Partly obviated | Arcade only re-uploads dirty sprites; user-side gating still useful for skipping per-frame UDP-read+lookup |
| **UV translation (texture scrolling)** | **GAP** — not exposed by high-level API |
| **UV rotation** | **GAP** — not exposed by high-level API |
| **UV zoom** | **GAP** — not exposed by high-level API |
| **Rectangular clip (glScissor)** | **GAP** — not exposed by high-level API |
| ~~Arduino serial~~ | Out of scope | See Architectural Boundaries — the rewrite is display-only |

### What this means in practice

- **C172 panel (the working reference):** uses ZERO texture-space transforms and ZERO clipping panels. Even the artificial horizon is implemented entirely in sprite-space (`enableRotation` + `enableTranslation`, no `enableTextureTranslation`/`enableTextureRotation`). **Arcade covers 100% of what the C172 panel needs natively.** Estimated swap: ~1500 lines of `OpenGL3lib` + `graphicsGL3` → ~300 lines of Arcade-flavored equivalents, plus calibration/lookup logic ported as-is.

- **G1000 panel (separate code):** uses UV translation for rolling speed/altitude tapes and `ClippingPanel` for the speed bug. Three viable mitigations:
  1. **Re-model tapes as tall sprites** (e.g., 1000-knot tape = 4600px-tall sprite) translated vertically and clipped — pure sprite-space, matches Arcade's grain.
  2. **Drop into `arcade.gl`** (Arcade's thin moderngl layer) for a small ~30-line custom shader, used only on tape sprites.
  3. **Framebuffer-based clipping**: render a SpriteList into an offscreen FBO, draw the FBO with the clip region.
  None of these break the rest of the architecture — they're isolated to a few G1000 instruments.

### Other observations from the audit

- Texture path resolution is fragile: `os.path.join(os.path.dirname(__file__), '../../', imagefile)` won't survive packaging. Worth fixing in any rewrite — Arcade's resource resolver is cleaner.
- `graphicsGL3.ImagePanel` has class-level mutable defaults (`valueToRotAnglesTable = [[0,0]]` declared at class level rather than `__init__`) — these become shared state if not explicitly overridden. Latent bug worth fixing in port.
- `ImagePanel.draw()` is ~130 lines with many flags; refactoring into smaller composable transform classes is a good opportunity during the port.
- No tests, no type hints, sparse docstrings — confirms the user's stated pain.
- Tabs are used for indentation throughout — preserve in any new code if patching the existing project; new project can pick its own style.
- Deprecated `GL_Image_OLD` class still present in `OpenGL3lib.py` — drop in port.

## MVP1 Scope

**MVP1 = working C172 six-pack panel, sprite-based, end-to-end YAML-driven.**

In scope:
- Component types: `ImagePanel` (textured PNG layer), `Text` (status overlay / labels)
- Transforms: position, rotation around pivot, sprite translation, visibility toggle, calibration lookup tables (all sprite-space)
- Panel YAML composes N instrument YAMLs at positions
- Window/input via Arcade defaults; FPS counter; "no XP data" overlay
- Test mode (numpad keys to drive gauge values) — preserved from the original

Out of MVP1 (deferred):
- G1000 UV-scrolling tapes / `arcade.gl` shaders
- Framebuffer-based rectangular clipping
- Vector primitives (`Line`, `Polygon`, `Arc`, etc.) — schema must accept them, but no implementations yet
- Frame-based animated images (`AnimatedImage`)
- Mouse-draggable windows / `Container` mouse interaction
- Multi-panel / multi-monitor coordination
- Standalone `gauge_designer` GUI (post-MVP1; YAML hand-editing is fine for MVP1)

## Resolved Decisions

- ✅ Render stack: **Arcade** (Python). Old hand-rolled GL/shader code retired; `pySTGraphics` not migrated, replaced clean.
- ✅ Config format: **YAML**.
- ✅ Both instruments and panels are config-driven; no more scripted panels like `C172_Panel.py`.
- ✅ Component schema is **typed + extensible** so vector primitives can be added later without disrupting MVP1 sprite components.
- ✅ Long-term direction: support both sprite (C172-style six-packs) and vector (737/A320-style glass cockpits) in the same engine.
- ✅ MVP1 = C172 panel only. Sprite + Text components only.
- ✅ Instrument editor is **separate from** `pyXPArduino` (extracted as `gauge_designer`, post-MVP1).
- ✅ Panel app is **display-only** — no hardware-to-sim input paths.
- ✅ Reuse `pyxpudpserver` as-is.

## Open Questions / Pending Decisions

- macOS support: OpenGL is deprecated by Apple (frozen at GL 4.1) but still functional. Acceptable today; long-term Metal/wgpu would be the path forward.
- **G1000 panel scope** — confirm whether the rewrite needs to cover G1000 from day one. C172 is gap-free against Arcade; G1000 needs framebuffer-clipping or an `arcade.gl` shader for the rolling tapes. Recommendation: ship C172 first, defer G1000.
- **Project bootstrap location** — `c:\Users\stephane\Desktop\plane_gauges\` is empty today. Confirm that's the home for `gauge_core` + `gauge_designer` + `gauge_panel_runtime`, or whether each gets its own repo (favoring separate repos given they will be reusable packages).
- **Backwards compatibility with existing XML configs** — should the new YAML loader also accept the existing XML schema (one-time migration), or is a clean break OK? Only one real XML file exists (`pyXPArduino/instruments/C172_Altimeter.xml`), so a clean break is cheap.
- **Asset root convention** — texture paths in YAML should be relative; need to decide whether they're relative to the instrument YAML, to the panel YAML, or to a configured asset directory.
- **Where do calibration lookup tables live for shared instruments?** Same instrument used on different aircraft may need different calibration. Options: per-aircraft YAML overrides, parameterized instruments, or just duplicate.

## Conversation History — Key Quotes

- User: "current implementation meets the FPS targets easily."
- User: "I have implemented GL batch rendering which seems quite efficient but is a bit 'hardcore'."
- User: "Documentation and clean separation of 'core libraries' from the rest of the project is an issue."
- User: "I am an occasional programmer so low level GL code rendering I wrote a bunch of years ago is now obscure to me."
- User: "My UDP library I am sure would easily be rewritten in c++ and is fairly well documented / coded."
- User: "we need to retire the old architecture and rewrite a new GL piece" — on the decision to drop `pySTGraphics` rather than migrate it.
- User: "we should definitely have panels based on config files" — extending data-driven design from instruments to whole panels.
