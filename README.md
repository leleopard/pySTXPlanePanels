# pySTXPlanePanels

A cross-platform application that displays fully functional 2D aircraft instrument panels driven by live X-Plane flight simulator data over UDP.

## Requirements

### Operating System

| Platform | Minimum version | Notes |
|---|---|---|
| Ubuntu / Debian | Ubuntu 22.04 LTS | Earlier releases (e.g. 16.04, 18.04, 20.04) are not supported |
| Raspberry Pi OS | Bookworm (12) | 64-bit desktop image; Pi 4 or Pi 5 |
| Windows | Windows 10 (64-bit) | Windows 11 recommended |
| macOS | macOS 12 Monterey | OpenGL is deprecated on Apple Silicon but still functional |

### Python

| Requirement | Minimum |
|---|---|
| Python | **3.10** |
| pip | 21.0 |

Ubuntu 22.04 ships Python 3.10. Ubuntu 24.04 ships Python 3.12. Both are supported.

### Python dependencies (installed automatically)

| Package | Version |
|---|---|
| arcade | ≥ 3.3, < 4 |
| PySide6 | ≥ 6.5 (designer only) |
| PyYAML | ≥ 6.0 |
| Pillow | ≥ 10.0 |
| pyxpudpserver | latest |

### X-Plane

| Requirement | Minimum |
|---|---|
| X-Plane | 11 or 12 |
| UDP output | Must be enabled in X-Plane network settings |

The panel machine and the X-Plane machine must be on the same local network (or the same machine).

---

## Installation

### Ubuntu (PC / x86-64)

```bash
wget https://raw.githubusercontent.com/leleopard/pySTXPlanePanels/main/install_ubuntu.sh
bash install_ubuntu.sh
```

### Raspberry Pi OS (Bookworm)

```bash
wget https://raw.githubusercontent.com/leleopard/pySTXPlanePanels/main/install_rpi.sh
bash install_rpi.sh
```

### Windows (manual)

```bat
git clone https://github.com/leleopard/pySTXPlanePanels.git
cd pySTXPlanePanels
python -m venv .venv
.venv\Scripts\activate
pip install -e .
pip install "PySide6>=6.5"
```

---

## Quick start

```bash
# Run a panel (replace with your panel YAML path)
plane-gauge panels/c172_six_pack.yaml

# Run in test mode (no X-Plane needed — use numpad keys to drive gauges)
plane-gauge panels/c172_six_pack.yaml --test

# Open the instrument/panel designer
gauge-designer
```

---

## Configuration

Edit `config.yaml` to point at your X-Plane machine:

```yaml
udp:
  listen_host: 0.0.0.0       # 0.0.0.0 = accept from any interface
  listen_port: 49008
  xplane_host: 192.168.1.x   # IP address of your X-Plane PC
  xplane_port: 49000
```

In X-Plane: **Settings → Network → UDP → Send data to IP** — set the panel machine's IP and port to match `listen_port` above.

---

## Tests

The suite is tiered, so that running it is never a reason not to.

| Tier | What it does | Cost |
|---|---|---|
| `smoke` | Builds every instrument and panel YAML through the real loaders, with no GL context. Catches missing textures, dangling instrument references, unknown component types, renamed convert functions and absolute paths. | ~4s, 136 tests |
| `render` | Renders golden cases offscreen at fixed dataref values and compares them pixel-by-pixel against committed baselines in `tests/goldens/`. Catches anything that visibly moves. | ~6s, 11 tests, needs a GPU |

Normally you do not pick a tier by hand — the selector works it out from
what you changed:

```bash
python scripts/regress.py            # tier chosen from the working tree
python scripts/regress.py --dry-run  # show the plan, run nothing
python scripts/regress.py --base main
python scripts/regress.py --all      # force the whole suite
```

A docs change runs nothing. A `gauge_designer/` change runs smoke only. A
`gauge_core/` change runs everything. Editing one instrument YAML runs
smoke plus only the golden cases that actually contain that instrument —
so touching the C172 altimeter does not re-render the B737 PFD.

### Pre-commit hook

The suite can run automatically on every commit. Enable it once per clone:

```bash
git config core.hooksPath .githooks
```

From then on `git commit` runs the tier your **staged** change warrants.
A docs commit runs nothing; a YAML tweak runs smoke plus the one or two
golden cases that contain it; a `gauge_core` change runs everything.

The hook tests a snapshot of the index, not your working tree, so what
gets checked is the commit itself — unrelated work in progress neither
hides a failure nor causes a spurious one. Because that snapshot contains
only tracked files, it also catches a commit that references a file you
forgot to `git add`.

Failing tests abort the commit. A machine with no Python or no pytest
(a Pi that only runs panels) warns loudly and commits anyway. To bypass
it for one commit:

```bash
git commit --no-verify
```

Running the tiers directly, if you want to:

```bash
python -m pytest                 # smoke only (the default)
python -m pytest -m render       # golden images
python -m pytest -m "smoke or render"
```

### Golden images

When a visual change is intentional, regenerate the baselines and **look
at them** before committing:

```bash
python -m pytest -m render --update-goldens
```

When a case fails, the rendered frame and an amplified difference map are
written to `tests/_artifacts/` (gitignored) so you can see what moved
rather than infer it from a pixel count.

Add a case by adding an entry to `tests/cases.yaml` and regenerating.

---

## Project structure

```
gauge_core/          Arcade-based render engine; YAML loader; X-Plane data binding
gauge_designer/      PySide6 WYSIWYG editor for instrument and panel YAML files
instruments/         Instrument YAML definitions (C172, G1000, …)
panels/              Panel YAML files (compose instruments at positions)
assets/              Shared texture atlases
tests/               Tiered regression suite (smoke + golden images)
scripts/regress.py   Runs the tier that your change warrants
config.yaml          UDP network settings
```
