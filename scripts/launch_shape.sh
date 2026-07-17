#!/bin/bash
# Launch wrapper for shape.launch.py with centralized logging.
#
# Mirrors launch_teleop.sh (same SHM cleanup and logging) but brings up the
# standalone LED-shape stack (MAVROS + /position relay + shape_node) instead of
# the full teleop stack. Swap uav-teleop for uav-shape to autostart it on boot.
#
# Usage:
#   ./scripts/launch_shape.sh [extra launch args...]
#   systemctl start uav-shape   (calls this script)

set -eo pipefail

# ---------------------------------------------------------------------------
# Log directory setup
# ---------------------------------------------------------------------------
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="$HOME/logs/$TIMESTAMP"
mkdir -p "$LOG_DIR"

# Atomic symlink update: create temp link then rename
ln -sfn "$LOG_DIR" "$HOME/logs/latest"

echo "=== UAV Neo Shape - $(date) ==="
echo "Log directory: $LOG_DIR"

# Remove FastRTPS shared-memory orphans left by processes killed mid-init
# (e.g. timeout-killed `ros2 topic hz`). A 0-byte fastrtps_port<N> segment
# causes any new rclpy participant that hashes to that port to spin forever
# in _rclpy.Node() - which masquerades as a Jupyter cell hang.
for f in /dev/shm/fastrtps_port*; do
    [ -e "$f" ] || continue
    case "$f" in *_el) continue ;; esac
    if [ ! -s "$f" ]; then
        base=$(basename "$f")
        rm -f "$f" "/dev/shm/${base}_el" "/dev/shm/sem.${base}_mutex"
        echo "Removed orphan SHM: $base"
    fi
done
for el in /dev/shm/fastrtps_port*_el; do
    [ -e "$el" ] || continue
    data="${el%_el}"
    if [ ! -e "$data" ]; then
        base=$(basename "$data")
        rm -f "$el" "/dev/shm/sem.${base}_mutex"
        echo "Removed orphan SHM lock: $(basename "$el")"
    fi
done

# Tell ROS2 to put its internal logs (rosout, launch.log) here too
export ROS_LOG_DIR="$LOG_DIR"
export ROS_HOME="$LOG_DIR"

# ---------------------------------------------------------------------------
# Source ROS2 environment. The workspace is derived from this script's location
# (<workspace>/src/uav_neo_ros2_driver/scripts) so no user or path is hardcoded.
# ---------------------------------------------------------------------------
# shellcheck source=/opt/ros/jazzy/setup.bash
source /opt/ros/jazzy/setup.bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS="$(cd "$SCRIPT_DIR/../../.." && pwd)"
if [ -f "$WS/install/setup.bash" ]; then
    # shellcheck disable=SC1091
    source "$WS/install/setup.bash"
fi

# ---------------------------------------------------------------------------
# Redirect stdout/stderr to both the log file and the console (journald)
# ---------------------------------------------------------------------------
exec &> >(tee -a "$LOG_DIR/shape.log")

# ---------------------------------------------------------------------------
# Launch - exec replaces this shell so systemd tracks the ros2 PID directly
# ---------------------------------------------------------------------------
exec ros2 launch uav_neo_ros2_driver shape.launch.py "$@"
