#!/bin/bash
# Setup script for UAV Neo systemd services.
#
# Installs and enables:
#   - uav-teleop.service    (autostart teleop on boot)
#   - uav-watchdog.service  (node health monitoring)
#   - uav-dashboard.service (web dashboard on :8080)
#   - uav-jupyter.service   (JupyterLab on :8888)
#
# Also creates required directories and installs JupyterLab system-wide.
#
# Usage:
#   ./scripts/setup_services.sh
#   (or via ./scripts/setup_all.sh which calls this as Phase 5)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================="
echo "  UAV Neo — Service Setup"
echo "============================================="

# ---------------------------------------------------------------------------
# 1. Create directories
# ---------------------------------------------------------------------------
echo ""
echo "--- Creating directories ---"

if [ ! -d "$HOME/logs" ]; then
    mkdir -p "$HOME/logs"
    echo "Created ~/logs/"
else
    echo "~/logs/ already exists"
fi

if [ ! -d "$HOME/jupyter_ws" ]; then
    mkdir -p "$HOME/jupyter_ws"
    echo "Created ~/jupyter_ws/"
else
    echo "~/jupyter_ws/ already exists"
fi

# ---------------------------------------------------------------------------
# 2. Install JupyterLab and Python dependencies (system-wide)
# ---------------------------------------------------------------------------
echo ""
echo "--- Setting up JupyterLab ---"

if command -v jupyter &>/dev/null; then
    echo "JupyterLab already installed"
else
    echo "Installing JupyterLab (this may take a minute on Pi 5) ..."
    pip3 install --break-system-packages jupyterlab
    echo "JupyterLab installed"
fi

# Install Python dependencies required by the student library
echo "Installing student library Python dependencies ..."
pip3 install --break-system-packages --quiet pandas matplotlib Pillow ipywidgets luma.led_matrix luma.core spidev 2>/dev/null
echo "Student library dependencies installed"

# Verify
if jupyter --version &>/dev/null; then
    echo "JupyterLab version: $(jupyter lab --version 2>/dev/null || echo 'unknown')"
else
    echo "WARNING: jupyter command not found"
fi

# ---------------------------------------------------------------------------
# 3. Install udev rules (disable USB autosuspend for cameras)
# ---------------------------------------------------------------------------
echo ""
echo "--- Installing udev rules ---"

UDEV_SRC="$SCRIPT_DIR/99-uav-cameras.rules"
UDEV_DST="/etc/udev/rules.d/99-uav-cameras.rules"

if cmp -s "$UDEV_SRC" "$UDEV_DST" 2>/dev/null; then
    echo "Camera udev rules: already installed (unchanged)"
else
    sudo cp "$UDEV_SRC" "$UDEV_DST"
    echo "Camera udev rules: installed (USB autosuspend disabled for cameras)"
fi

CORAL_UDEV_SRC="$SCRIPT_DIR/99-coral-edgetpu.rules"
CORAL_UDEV_DST="/etc/udev/rules.d/99-coral-edgetpu.rules"

if cmp -s "$CORAL_UDEV_SRC" "$CORAL_UDEV_DST" 2>/dev/null; then
    echo "Coral udev rules: already installed (unchanged)"
else
    sudo cp "$CORAL_UDEV_SRC" "$CORAL_UDEV_DST"
    echo "Coral udev rules: installed (non-root access for pre/post-init USB IDs)"
fi

sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=usb

# ---------------------------------------------------------------------------
# 4. Make scripts executable
# ---------------------------------------------------------------------------
echo ""
echo "--- Setting script permissions ---"

chmod +x "$SCRIPT_DIR/launch_teleop.sh"
chmod +x "$SCRIPT_DIR/watchdog.py"
chmod +x "$SCRIPT_DIR/dashboard.py"
echo "Scripts marked executable"

# ---------------------------------------------------------------------------
# 5. Install systemd service files
# ---------------------------------------------------------------------------
echo ""
echo "--- Installing systemd services ---"

SERVICES=(
    uav-teleop.service
    uav-watchdog.service
    uav-dashboard.service
    uav-jupyter.service
)

for svc in "${SERVICES[@]}"; do
    src="$SCRIPT_DIR/$svc"
    dst="/etc/systemd/system/$svc"

    if [ ! -f "$src" ]; then
        echo "ERROR: $src not found"
        continue
    fi

    if cmp -s "$src" "$dst" 2>/dev/null; then
        echo "$svc: already installed (unchanged)"
    else
        sudo cp "$src" "$dst"
        echo "$svc: installed to $dst"
    fi
done

echo ""
echo "Reloading systemd daemon ..."
sudo systemctl daemon-reload

# ---------------------------------------------------------------------------
# 6. Enable services
# ---------------------------------------------------------------------------
echo ""
echo "--- Enabling services ---"

for svc in "${SERVICES[@]}"; do
    if systemctl is-enabled "$svc" &>/dev/null; then
        echo "$svc: already enabled"
    else
        sudo systemctl enable "$svc"
        echo "$svc: enabled"
    fi
done

# ---------------------------------------------------------------------------
# 7. Summary
# ---------------------------------------------------------------------------
echo ""
echo "============================================="
echo "  Service setup complete!"
echo "============================================="
echo ""
echo "Services installed and enabled for next boot:"
echo "  uav-teleop     — Teleop autostart (MAVROS + RealSense + Arducam)"
echo "  uav-watchdog   — Node health monitor and auto-restart"
echo "  uav-dashboard  — Web dashboard at http://<pi-ip>:8080"
echo "  uav-jupyter    — JupyterLab at http://<pi-ip>:8888"
echo ""
echo "Start now (without reboot):"
echo "  sudo systemctl start uav-teleop"
echo "  sudo systemctl start uav-dashboard"
echo "  sudo systemctl start uav-jupyter"
echo "  (watchdog starts automatically 15s after teleop)"
echo ""
echo "Check status:"
echo "  systemctl status uav-teleop uav-watchdog uav-dashboard uav-jupyter"
echo ""
echo "View logs:"
echo "  ls ~/logs/latest/"
echo "  journalctl -u uav-teleop -f"
echo ""
