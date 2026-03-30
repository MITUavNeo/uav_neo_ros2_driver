#!/bin/bash
# setup_arducam.sh — Install Arducam B0578 global shutter camera driver (gscam + GStreamer)
#
# This script:
#   1. Installs GStreamer tools and plugins
#   2. Installs the gscam ROS2 package
#   3. Verifies camera detection
#
# No reboot required.

set -e

echo "=== Arducam B0578 Setup ==="

# --- 1. Install GStreamer ---
echo "[1/2] Installing GStreamer and gscam..."
sudo apt install -y gstreamer1.0-tools gstreamer1.0-plugins-good ros-jazzy-gscam

# --- 2. Verify camera detection ---
echo "[2/2] Verifying Arducam detection..."
if command -v v4l2-ctl &>/dev/null; then
    echo ""
    v4l2-ctl --list-devices 2>/dev/null || echo "  WARNING: No V4L2 devices found. Is the Arducam plugged in?"
else
    echo "  v4l2-ctl not found. Installing v4l-utils..."
    sudo apt install -y v4l-utils
    v4l2-ctl --list-devices 2>/dev/null || echo "  WARNING: No V4L2 devices found. Is the Arducam plugged in?"
fi

echo ""
echo "=== Arducam B0578 setup complete! ==="
echo "No reboot required."
echo "Verify: ros2 launch uav_neo_ros2_driver arducam.launch.py"
