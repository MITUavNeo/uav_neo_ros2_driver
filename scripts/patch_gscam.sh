#!/bin/bash
# patch_gscam.sh - Clone, patch, and build gscam with appsink memory-leak fix
#
# The stock ros-jazzy-gscam package has an unbounded appsink buffer that
# causes memory leaks under CPU load (ros-drivers/gscam#63).  This script
# clones the upstream source, applies a two-line fix (max-buffers=1,
# drop=true), and builds it as a colcon overlay that shadows the apt package.
#
# Usage:
#   ./scripts/patch_gscam.sh
#
# After running, rebuild any dependent packages and restart services:
#   colcon build --packages-select uav_neo_ros2_driver
#   sudo systemctl restart uav-teleop

set -eo pipefail

GSCAM_VERSION="2.0.2"
WS_DIR="$HOME/ros2_ws"
GSCAM_DIR="$WS_DIR/src/gscam"

echo "=== Patching gscam (appsink memory-leak fix) ==="
echo ""

# -----------------------------------------------
# Step 1: Clone source
# -----------------------------------------------
if [ -d "$GSCAM_DIR" ]; then
    echo "gscam source already exists at $GSCAM_DIR"
    echo "Checking version tag..."
    cd "$GSCAM_DIR"
    CURRENT_TAG=$(git describe --tags --exact-match 2>/dev/null || echo "unknown")
    if [ "$CURRENT_TAG" != "$GSCAM_VERSION" ]; then
        echo "WARNING: existing source is at $CURRENT_TAG, expected $GSCAM_VERSION"
        echo "Remove $GSCAM_DIR and re-run to start fresh, or continue at your own risk."
    fi
else
    echo "Cloning ros-drivers/gscam (tag $GSCAM_VERSION)..."
    git clone --depth 1 --branch "$GSCAM_VERSION" \
        https://github.com/ros-drivers/gscam.git "$GSCAM_DIR"
fi

cd "$GSCAM_DIR"

# -----------------------------------------------
# Step 2: Apply appsink patch
# -----------------------------------------------
GSCAM_CPP="$GSCAM_DIR/src/gscam.cpp"

if grep -q "gst_app_sink_set_max_buffers" "$GSCAM_CPP"; then
    echo "Patch already applied (gst_app_sink_set_max_buffers found). Skipping patch."
else
    echo "Applying appsink max-buffers patch..."

    # Insert the fix after gst_caps_unref(caps);
    # The patch adds two lines that limit the appsink internal queue to 1 buffer
    # and drop old frames when the ROS2 publish loop can't keep up.
    sed -i '/gst_caps_unref(caps);/a \
\
  // Limit appsink internal queue to prevent unbounded memory growth.\
  // Without this, frames accumulate when the ROS2 publish loop cant\
  // keep up with the GStreamer pipeline (ros-drivers/gscam#63).\
  gst_app_sink_set_max_buffers(GST_APP_SINK(sink_), 1);\
  gst_app_sink_set_drop(GST_APP_SINK(sink_), TRUE);' "$GSCAM_CPP"

    # Verify patch was applied
    if grep -q "gst_app_sink_set_max_buffers" "$GSCAM_CPP"; then
        echo "Patch applied successfully."
    else
        echo "ERROR: Patch failed - gst_app_sink_set_max_buffers not found in $GSCAM_CPP"
        exit 1
    fi
fi

# -----------------------------------------------
# Step 3: Build
# -----------------------------------------------
echo ""
echo "Building patched gscam..."
cd "$WS_DIR"
source /opt/ros/jazzy/setup.bash
colcon build --packages-select gscam

echo ""
echo "=== gscam patched and built ==="
echo ""
echo "The overlay binary at $WS_DIR/install/gscam/ now shadows the apt package."
echo "Verify with: source install/setup.bash && ros2 pkg prefix gscam"
echo ""
echo "To activate: restart the teleop service"
echo "  sudo systemctl restart uav-teleop"
