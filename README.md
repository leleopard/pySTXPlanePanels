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

## Project structure

```
gauge_core/          Arcade-based render engine; YAML loader; X-Plane data binding
gauge_designer/      PySide6 WYSIWYG editor for instrument and panel YAML files
instruments/         Instrument YAML definitions (C172, G1000, …)
panels/              Panel YAML files (compose instruments at positions)
assets/              Shared texture atlases
config.yaml          UDP network settings
```
