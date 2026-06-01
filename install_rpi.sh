#!/usr/bin/env bash
# install_rpi.sh — Install pySTXPlanePanels on Raspberry Pi OS (Bookworm/Bullseye)
#
# Run as your normal user (not root). sudo is used only for apt.
# Tested against Raspberry Pi OS Desktop (64-bit) on Pi 4 / Pi 5.

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
REPO_URL="https://github.com/leleopard/pySTXPlanePanels.git"
INSTALL_DIR="$HOME/plane_gauges"
VENV_DIR="$INSTALL_DIR/.venv"
BIN="$VENV_DIR/bin"

# ── Colours ───────────────────────────────────────────────────────────────────
R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'; B='\033[0;34m'; N='\033[0m'
ok()      { echo -e "${G}  ✓  ${N}$*"; }
warn()    { echo -e "${Y}  !  ${N}$*"; }
err()     { echo -e "${R}  ✗  ${N}$*" >&2; }
section() { echo -e "\n${B}━━━  $*  ━━━${N}"; }

ask_yn() {   # ask_yn "Question" → returns 0=yes 1=no
    local answer
    while true; do
        read -rp "    $1 [y/n]: " answer
        case "$answer" in
            [Yy]) return 0 ;;
            [Nn]) return 1 ;;
            *)    echo "      Please enter y or n." ;;
        esac
    done
}

# ── Banner ────────────────────────────────────────────────────────────────────
echo -e "${B}"
echo "  ╔══════════════════════════════════════════╗"
echo "  ║   pySTXPlanePanels — Raspberry Pi Setup  ║"
echo "  ╚══════════════════════════════════════════╝"
echo -e "${N}"

# ── 1. Python version check ───────────────────────────────────────────────────
section "Python"
PY=$(command -v python3 || true)
if [ -z "$PY" ]; then
    err "python3 not found. Install it with:  sudo apt install python3"
    exit 1
fi
PY_VER=$("$PY" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=${PY_VER%%.*}
PY_MINOR=${PY_VER#*.}
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    err "Python 3.10+ required, found $PY_VER."
    err "Raspberry Pi OS Bookworm ships Python 3.11 — please upgrade your OS."
    exit 1
fi
ok "Python $PY_VER"

# ── 2. System packages ────────────────────────────────────────────────────────
section "System packages"
PKGS=()
for pkg in python3-venv python3-pip git; do
    dpkg -s "$pkg" &>/dev/null || PKGS+=("$pkg")
done
if [ ${#PKGS[@]} -gt 0 ]; then
    echo "  Installing: ${PKGS[*]}"
    sudo apt-get install -y "${PKGS[@]}"
fi
ok "System packages ready"

# ── 3. Clone / update repo ────────────────────────────────────────────────────
section "Repository"
if [ -d "$INSTALL_DIR/.git" ]; then
    ok "Repo already at $INSTALL_DIR — pulling latest"
    git -C "$INSTALL_DIR" pull --ff-only
else
    echo "  Cloning into $INSTALL_DIR ..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    ok "Cloned"
fi

# ── 4. Virtual environment ────────────────────────────────────────────────────
section "Virtual environment"
if [ ! -d "$VENV_DIR" ]; then
    echo "  Creating venv at $VENV_DIR ..."
    "$PY" -m venv "$VENV_DIR"
fi
ok "Venv ready"
PIP="$BIN/pip"
"$PIP" install --upgrade pip --quiet

# ── 5. Core dependencies (always installed) ───────────────────────────────────
section "Core dependencies"
echo "  Installing arcade, pyyaml, pillow, pyxpudpserver ..."
echo "  (arcade is ~100 MB; this may take a few minutes on a Pi 4)"
"$PIP" install \
    "arcade>=3.3,<4" \
    "pyyaml>=6.0" \
    "pillow>=10.0" \
    "pyxpudpserver" \
    --quiet
ok "Core dependencies installed"

# ── 5a. Patch arcade GLES shaders for Raspberry Pi ───────────────────────────
# Arcade 3.3.x detects Pi and uses OpenGL ES mode, but its GLES geometry shaders
# omit required precision qualifiers for integer sampler types (isampler2D,
# usampler2D), causing shader compilation failures on Pi.  Two lines fix it.
section "Patching arcade GLES shaders for Pi"
GLSL_FILE="$("$BIN/python" -c "import arcade.gl.backends.opengl.glsl as m; import inspect; print(inspect.getfile(m))")"
if [ -f "$GLSL_FILE" ]; then
    python3 - "$GLSL_FILE" <<'PYEOF'
import sys, re
path = sys.argv[1]
with open(path) as f:
    src = f.read()
OLD = '            self._lines.insert(1, "precision mediump float;")\n'
NEW = (
    '            self._lines.insert(1, "precision mediump float;")\n'
    '            # Pi fix: GLSL ES requires explicit precision for integer samplers.\n'
    '            self._lines.insert(2, "precision highp isampler2D;")\n'
    '            self._lines.insert(3, "precision highp usampler2D;")\n'
)
if OLD in src and NEW not in src:
    with open(path, 'w') as f:
        f.write(src.replace(OLD, NEW))
    print("  Patched:", path)
else:
    print("  Already patched or pattern not found — skipping.")
PYEOF
    ok "arcade GLES shader patch applied"
else
    warn "Could not locate arcade glsl.py — skipping patch."
fi

# ── 6. Install this package ───────────────────────────────────────────────────
section "gauge_core"
echo "  Installing pySTXPlanePanels in editable mode ..."
"$PIP" install -e "$INSTALL_DIR" --quiet
ok "gauge_core installed"

# ── 7. Optional: gauge_designer (PySide6) ────────────────────────────────────
section "Optional: gauge_designer"
warn "PySide6 is ~700 MB. Only needed if you want the WYSIWYG editor on this Pi."
INSTALL_DESIGNER=false
if ask_yn "Install gauge_designer (PySide6)?"; then
    echo "  Installing PySide6 — this will take a while ..."
    "$PIP" install "PySide6>=6.5" --quiet
    ok "gauge_designer available (run: gauge-designer)"
    INSTALL_DESIGNER=true
else
    ok "Skipped — you can install it later with:  $PIP install PySide6"
fi

# ── 8. UDP config ─────────────────────────────────────────────────────────────
section "UDP / X-Plane network config"
CONFIG_FILE="$INSTALL_DIR/config.yaml"
echo "  Current config ($CONFIG_FILE):"
echo "  ─────────────────────────────────────────"
cat "$CONFIG_FILE" | sed 's/^/    /'
echo "  ─────────────────────────────────────────"
warn "Edit $CONFIG_FILE to set xplane_host to your X-Plane PC's IP address."
warn "The listen_host should be 0.0.0.0 if X-Plane is on a different machine."

# ── 9. Choose default panel ───────────────────────────────────────────────────
section "Default panel"
echo "  Available panels:"
PANELS=()
i=1
while IFS= read -r -d '' f; do
    rel="${f#$INSTALL_DIR/}"
    echo "    $i) $rel"
    PANELS+=("$f")
    ((i++))
done < <(find "$INSTALL_DIR/panels" -name "*.yaml" -print0 | sort -z)

DEFAULT_PANEL="${PANELS[0]}"
read -rp "    Pick a panel number [1]: " PANEL_CHOICE
PANEL_CHOICE="${PANEL_CHOICE:-1}"
if [[ "$PANEL_CHOICE" =~ ^[0-9]+$ ]] && [ "$PANEL_CHOICE" -ge 1 ] && [ "$PANEL_CHOICE" -le "${#PANELS[@]}" ]; then
    DEFAULT_PANEL="${PANELS[$((PANEL_CHOICE - 1))]}"
fi
ok "Default panel: ${DEFAULT_PANEL#$INSTALL_DIR/}"

# ── 10. Launcher script ───────────────────────────────────────────────────────
LAUNCHER="$INSTALL_DIR/start_panel.sh"
cat > "$LAUNCHER" <<LAUNCHER_EOF
#!/usr/bin/env bash
# Auto-generated by install_rpi.sh
# Edit PANEL and SSAA to taste.
PANEL="${DEFAULT_PANEL#$INSTALL_DIR/}"
SSAA=4   # Anti-aliasing: 0=off  2=light  4=default  8=heavy

cd "$INSTALL_DIR"
exec "$BIN/plane-gauge" "\$PANEL" --ssaa "\$SSAA"
LAUNCHER_EOF
chmod +x "$LAUNCHER"
ok "Launcher written: $LAUNCHER"

# ── 11. Optional: autostart on boot ──────────────────────────────────────────
section "Autostart on boot"
AUTOSTART_FILE="$HOME/.config/autostart/plane_gauges.desktop"

if ask_yn "Auto-start the panel when the desktop logs in?"; then
    mkdir -p "$HOME/.config/autostart"
    cat > "$AUTOSTART_FILE" <<DESKTOP_EOF
[Desktop Entry]
Name=Plane Gauges
Comment=X-Plane gauge panel
Exec=$LAUNCHER
Type=Application
X-GNOME-Autostart-enabled=true
DESKTOP_EOF
    ok "Autostart entry created: $AUTOSTART_FILE"
    warn "The panel will launch automatically on next desktop login."
    warn "To disable: rm $AUTOSTART_FILE"
else
    ok "Skipped — start manually with:  $LAUNCHER"
fi

# ── 12. Summary ───────────────────────────────────────────────────────────────
section "Done"
echo ""
echo "  Installation complete. Quick reference:"
echo ""
echo "  Run panel:       $LAUNCHER"
echo "  Run panel (cmd): $BIN/plane-gauge <panel.yaml>"
echo "  Test mode:       $BIN/plane-gauge <panel.yaml> --test"
if [ "$INSTALL_DESIGNER" = true ]; then
echo "  Designer:        $BIN/gauge-designer"
fi
echo "  UDP config:      $CONFIG_FILE"
echo "  Update repo:     git -C $INSTALL_DIR pull"
echo ""
warn "Remember to set xplane_host in config.yaml to your X-Plane PC's IP."
echo ""
