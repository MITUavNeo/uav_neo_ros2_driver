#!/usr/bin/env bash

# Copyright 2026 MIT
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# drone-tool: a `drone <subcommand>` helper for the UAV Neo kit, inherited from
# racecar-tool. Source this file from ~/.bashrc so `drone` is available as a
# shell function (it runs in the calling shell so `drone cd`/`drone source`
# affect the current environment).
#
# SCAFFOLD ONLY. Command bodies are stubs; see docs/drone-tool-plan.md for the
# racecar -> drone command mapping and the carry-over decisions still open.

DRONE_PKG="uav_neo_ros2_driver"
DRONE_WS="$HOME/ros2_ws"
DRONE_PKG_DIR="$DRONE_WS/src/$DRONE_PKG"

_drone_stub() {
    echo "drone $1: not implemented yet (scaffold; see docs/drone-tool-plan.md)" >&2
    return 2
}

_drone_help() {
    cat <<'EOF'
drone <command> [args]  -  UAV Neo kit helper (SCAFFOLD; commands not yet implemented)

Development:
  build                 colcon build the driver, source the overlay
  test                  colcon test + results
  source                source the workspace overlay
  cd                    cd into the driver package source

Launch and control:
  teleop                start the full teleop stack (launch_teleop.sh)
  launch <name>         ros2 launch uav_neo_ros2_driver <name>.launch.py
  watchdog              run the node watchdog

Hardware and system:
  udev                  reinstall udev rules + hid_nintendo blacklist
  controller            verify/fix the Xbox pad XInput mode
  selftest              run the hardware test suite (test_hardware.py)
  status                lsusb, device nodes, ros2 node list
  setup <phase>         run setup_*.sh (all|networking|realsense|...)

Services and library:
  service <action> [u]  systemd for uav-teleop/uav-watchdog/uav-dashboard/uav-jupyter
  library <action>      switch the student library import path
  cleanup               remove orphan processes + FastRTPS shm segments

  help                  this text
EOF
}

drone() {
    local cmd="$1"; shift 2>/dev/null
    case "$cmd" in
        build)      _drone_stub build ;;
        test)       _drone_stub test ;;
        source)     _drone_stub source ;;
        cd)         _drone_stub cd ;;
        teleop)     _drone_stub teleop ;;
        launch)     _drone_stub launch ;;
        watchdog)   _drone_stub watchdog ;;
        udev)       _drone_stub udev ;;
        controller) _drone_stub controller ;;
        selftest)   _drone_stub selftest ;;
        status)     _drone_stub status ;;
        setup)      _drone_stub setup ;;
        service)    _drone_stub service ;;
        library)    _drone_stub library ;;
        cleanup)    _drone_stub cleanup ;;
        help|-h|--help|"") _drone_help ;;
        *) echo "drone: unknown command '$cmd' (try 'drone help')" >&2; return 2 ;;
    esac
}

_drone_complete() {
    local cmds="build test source cd teleop launch watchdog udev controller \
selftest status setup service library cleanup help"
    local cur="${COMP_WORDS[COMP_CWORD]}"
    if [ "$COMP_CWORD" -eq 1 ]; then
        # shellcheck disable=SC2207
        COMPREPLY=($(compgen -W "$cmds" -- "$cur"))
    fi
    # TODO(v1.3.0): per-command completion (launch names, service actions).
}
complete -F _drone_complete drone
