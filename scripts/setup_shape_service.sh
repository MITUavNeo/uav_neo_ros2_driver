#!/bin/bash
# Swap the boot service from teleop to the LED shape flight.
#
# Builds the package, renders uav-shape.service for the CURRENT user (no
# hardcoded user or home), installs it, and enables it for boot in place of
# uav-teleop (they both bind the FCU via MAVROS, so only one runs). Run after
# pulling the latest branch:
#
#   ./scripts/setup_shape_service.sh            # build + install + enable for boot
#   ./scripts/setup_shape_service.sh --start    # also start now (FCU must be connected)
#
# Revert to teleop:
#   sudo systemctl disable --now uav-shape && sudo systemctl enable --now uav-teleop uav-watchdog

# No `-u`: ROS/colcon setup.bash reference unset vars under nounset and would abort
# the sourcing below.
set -eo pipefail

# All paths are derived from where this script lives, so the current user, home,
# and workspace name are picked up automatically.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WS="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SERVICE="uav-shape.service"

if [ ! -d "$WS/src" ]; then
    echo "ERROR: expected a colcon workspace at $WS (with a src/ dir)."
    echo "Put this repo at <workspace>/src/uav_neo_ros2_driver and re-run."
    exit 1
fi

START=false
[ "${1:-}" = "--start" ] && START=true

echo "============================================="
echo "  UAV Neo - Shape Service Setup"
echo "  user=$USER  home=$HOME  workspace=$WS"
echo "============================================="

# ---------------------------------------------------------------------------
# 1. Build so shape_node, shape.launch.py, config, and the mavros_px4.yaml
#    frame fix are installed into the workspace.
# ---------------------------------------------------------------------------
echo ""
echo "--- Building uav_neo_ros2_driver ---"
# shellcheck source=/opt/ros/jazzy/setup.bash
source /opt/ros/jazzy/setup.bash
( cd "$WS" && colcon build --packages-select uav_neo_ros2_driver --symlink-install )
# shellcheck disable=SC1091
source "$WS/install/setup.bash"

# ---------------------------------------------------------------------------
# 2. Render the service unit for the current user and install it.
# ---------------------------------------------------------------------------
echo ""
echo "--- Installing $SERVICE ---"
dst="/etc/systemd/system/$SERVICE"
rendered="$(mktemp)"
trap 'rm -f "$rendered"' EXIT
sed -e "/^#/d" \
    -e "s|__USER__|$USER|g" \
    -e "s|__GROUP__|$(id -gn)|g" \
    -e "s|__HOME__|$HOME|g" \
    -e "s|__WS__|$WS|g" \
    -e "s|__REPO_DIR__|$REPO_DIR|g" \
    "$SCRIPT_DIR/$SERVICE.in" > "$rendered"

if cmp -s "$rendered" "$dst" 2>/dev/null; then
    echo "$SERVICE: already installed (unchanged)"
else
    sudo cp "$rendered" "$dst"
    echo "$SERVICE: installed to $dst"
fi
sudo systemctl daemon-reload

# ---------------------------------------------------------------------------
# 3. Swap teleop -> shape. Disabling teleop stops it from autostarting and
#    winning the boot race for the FCU.
# ---------------------------------------------------------------------------
echo ""
echo "--- Enabling $SERVICE for boot ---"
# uav-watchdog BindsTo uav-teleop, so leaving it enabled re-activates teleop at boot
# (which conflicts with shape). Both are teleop-specific and unused in shape mode.
for unit in uav-teleop.service uav-watchdog.service; do
    if systemctl list-unit-files 2>/dev/null | grep -q "^$unit"; then
        sudo systemctl disable --now "$unit" 2>/dev/null || true
        echo "$unit: disabled and stopped"
    fi
done
sudo systemctl enable "$SERVICE"
echo "uav-shape: enabled (starts on next boot)"

if $START; then
    echo ""
    echo "--- Starting $SERVICE now ---"
    sudo systemctl restart "$SERVICE"
    echo "uav-shape: started"
fi

echo ""
echo "============================================="
echo "  Done."
echo "============================================="
echo "Pick the shape/mode in config/shape.yaml, then apply:"
echo "  sudo systemctl restart uav-shape"
echo "Check it:"
echo "  systemctl status uav-shape"
echo "  journalctl -u uav-shape -f"
echo "Revert to teleop:"
echo "  sudo systemctl disable --now uav-shape && sudo systemctl enable --now uav-teleop uav-watchdog"
