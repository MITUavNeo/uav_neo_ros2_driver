#!/bin/bash
# setup_all.sh — Complete UAV Neo setup: ROS2 + Pixhawk + RealSense + Arducam + Services
#
# This script runs each component setup in series. The Pixhawk/UART setup
# requires a reboot before the flight controller can be connected, so this
# script will pause and prompt you to reboot at that point.
#
# Usage:
#   chmod +x scripts/setup_all.sh
#   ./scripts/setup_all.sh
#
# After completion, build the workspace:
#   cd ~/ros2_ws && colcon build --packages-select uav_neo_ros2_driver
#   source install/setup.bash
#   ros2 launch uav_neo_ros2_driver teleop.launch.py

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================"
echo "  UAV Neo — Full System Setup"
echo "============================================"
echo ""

# -----------------------------------------------
# Phase 1: ROS2 Jazzy
# -----------------------------------------------
echo ">>> Phase 1/5: ROS2 Jazzy"
echo "-------------------------------------------"
if command -v ros2 &>/dev/null; then
    echo "ROS2 already installed ($(ros2 --version 2>/dev/null || echo 'unknown version')). Skipping."
else
    bash "$SCRIPT_DIR/install_ros2_jazzy.sh"
fi
source /opt/ros/jazzy/setup.bash
echo ""

# -----------------------------------------------
# Phase 2: Pixhawk UART + MAVROS
# -----------------------------------------------
echo ">>> Phase 2/5: Pixhawk UART + MAVROS"
echo "-------------------------------------------"
bash "$SCRIPT_DIR/setup_pixhawk.sh"
echo ""

# Check if a reboot is needed. The Pixhawk script edits config files but the
# kernel won't pick up overlay changes until reboot. We check whether the
# Bluetooth UART is actually freed (hci0 absent = overlay active).
NEEDS_REBOOT=false
if hciconfig hci0 &>/dev/null; then
    # Bluetooth is still on the UART — overlay not yet active
    NEEDS_REBOOT=true
fi
if grep -q "console=serial0" /proc/cmdline 2>/dev/null; then
    # Kernel was booted with serial console still enabled
    NEEDS_REBOOT=true
fi

if [ "$NEEDS_REBOOT" = true ]; then
    echo "============================================"
    echo "  *** REBOOT REQUIRED ***"
    echo ""
    echo "  UART and Bluetooth changes need a reboot"
    echo "  to take effect before continuing."
    echo ""
    echo "  After reboot, re-run this script to"
    echo "  continue with Phases 3-5. Already-completed"
    echo "  phases will be skipped automatically."
    echo "============================================"
    echo ""
    read -rp "Reboot now? [Y/n] " answer
    if [[ "$answer" =~ ^[Nn] ]]; then
        echo "Skipping reboot. Re-run this script after you reboot manually."
        exit 0
    else
        sudo reboot
    fi
fi

# -----------------------------------------------
# Phase 3: RealSense D435i
# -----------------------------------------------
echo ">>> Phase 3/5: RealSense D435i"
echo "-------------------------------------------"
bash "$SCRIPT_DIR/setup_realsense.sh"
echo ""

# -----------------------------------------------
# Phase 4: Arducam B0578
# -----------------------------------------------
echo ">>> Phase 4/5: Arducam B0578"
echo "-------------------------------------------"
bash "$SCRIPT_DIR/setup_arducam.sh"
echo ""

# -----------------------------------------------
# Build the workspace
# -----------------------------------------------
echo ">>> Building ROS2 workspace..."
echo "-------------------------------------------"
cd ~/ros2_ws
source /opt/ros/jazzy/setup.bash
colcon build --packages-select uav_neo_ros2_driver
source install/setup.bash
echo ""

# -----------------------------------------------
# Phase 5: Services
# -----------------------------------------------
echo ">>> Phase 5/5: Services (teleop, watchdog, dashboard, JupyterLab)"
echo "-------------------------------------------"
bash "$SCRIPT_DIR/setup_services.sh"
echo ""

echo "============================================"
echo "  UAV Neo setup complete!"
echo ""
echo "  Launch all sensors:"
echo "    ros2 launch uav_neo_ros2_driver teleop.launch.py"
echo ""
echo "  Or reboot to start services automatically:"
echo "    sudo reboot"
echo ""
echo "  Don't forget to configure Pixhawk params"
echo "  via QGroundControl (see setup_pixhawk.sh"
echo "  header for parameter values)."
echo "============================================"
