#!/bin/bash
# Launch wrapper for teleop.launch.py with centralized logging.
#
# Creates a timestamped log directory under ~/logs/, updates the
# ~/logs/latest symlink, and redirects all output so that systemd
# journald AND a plain-text log file both capture rosout messages.
#
# Usage:
#   ./scripts/launch_teleop.sh [extra launch args...]
#   systemctl start uav-teleop   (calls this script)

set -eo pipefail

# ---------------------------------------------------------------------------
# Log directory setup
# ---------------------------------------------------------------------------
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="$HOME/logs/$TIMESTAMP"
mkdir -p "$LOG_DIR"

# Atomic symlink update: create temp link then rename
ln -sfn "$LOG_DIR" "$HOME/logs/latest"

echo "=== UAV Neo Teleop — $(date) ==="
echo "Log directory: $LOG_DIR"

# Tell ROS2 to put its internal logs (rosout, launch.log) here too
export ROS_LOG_DIR="$LOG_DIR"
export ROS_HOME="$LOG_DIR"

# ---------------------------------------------------------------------------
# Source ROS2 environment
# ---------------------------------------------------------------------------
# shellcheck source=/opt/ros/jazzy/setup.bash
source /opt/ros/jazzy/setup.bash

if [ -f "$HOME/ros2_ws/install/setup.bash" ]; then
    # shellcheck source=/home/uav/ros2_ws/install/setup.bash
    source "$HOME/ros2_ws/install/setup.bash"
fi

# ---------------------------------------------------------------------------
# Redirect stdout/stderr to both the log file and the console (journald)
# ---------------------------------------------------------------------------
exec &> >(tee -a "$LOG_DIR/teleop.log")

# ---------------------------------------------------------------------------
# Launch — exec replaces this shell so systemd tracks the ros2 PID directly
# ---------------------------------------------------------------------------
exec ros2 launch uav_neo_ros2_driver teleop.launch.py "$@"
