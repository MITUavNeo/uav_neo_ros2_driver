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
# affect the current environment). See docs/drone-tool-plan.md for the
# racecar -> drone command mapping.

drone() {
    local pkg="uav_neo_ros2_driver"
    local ws="$HOME/ros2_ws"
    local pkg_dir="$ws/src/$pkg"
    local cmd="${1:-help}"
    shift || true

    case "$cmd" in
        build)
            ( cd "$ws" && colcon build --packages-select "$pkg" --symlink-install "$@" ) \
                && source "$ws/install/setup.bash"
            ;;

        test)
            ( cd "$ws" \
                && colcon test --packages-select "$pkg" --event-handlers console_direct+ "$@" \
                && colcon test-result --verbose )
            ;;

        source)
            # shellcheck disable=SC1091
            source "$ws/install/setup.bash"
            ;;

        cd)
            # Hop to the package source dir. Has to be a shell function (not a
            # subprocess) so the cd sticks in the user's interactive shell.
            cd "$pkg_dir" || return 1
            ;;

        teleop)
            # Launch wrapper: timestamped ~/logs/<ts>/ + FastRTPS SHM sweep.
            # Extra args (e.g. `realsense_flip:=false`) forward to ros2 launch.
            bash "$pkg_dir/scripts/launch_teleop.sh" "$@"
            ;;

        launch)
            local name="$1"
            if [[ -z "$name" ]]; then
                echo "usage: drone launch <name>   # e.g. drone launch realsense" >&2
                return 2
            fi
            shift
            ros2 launch "$pkg" "${name}.launch.py" "$@"
            ;;

        watchdog)
            # Foreground node watchdog; logs to ~/logs/latest/watchdog.log.
            # When uav-watchdog.service is installed, prefer
            # `drone service start watchdog`.
            python3 "$pkg_dir/scripts/watchdog.py" "$@"
            ;;

        udev)
            # Reinstall the camera + Coral udev rules AND the hid_nintendo
            # blacklist that keeps the Xbox pad in XInput mode.
            local sdir="$pkg_dir/scripts"
            echo "=== Reinstalling camera + Coral udev rules ==="
            sudo install -m 0644 "$sdir/99-uav-cameras.rules" \
                /etc/udev/rules.d/99-uav-cameras.rules
            sudo install -m 0644 "$sdir/99-coral-edgetpu.rules" \
                /etc/udev/rules.d/99-coral-edgetpu.rules
            sudo udevadm control --reload-rules
            sudo udevadm trigger --subsystem-match=usb
            echo "Camera + Coral rules reloaded."
            echo
            echo "=== Controller (hid_nintendo blacklist) ==="
            bash "$sdir/setup_controller.sh"
            ;;

        controller)
            # Verify the Xbox pad is in XInput mode (2f24:00b7, js0, 11/8). If it
            # came up as the Nintendo Switch spoof (057e:2009), reinstall the
            # hid_nintendo blacklist so it falls back to xpad next enumeration.
            echo "=== Xbox controller mode ==="
            if lsusb | grep -q '2f24:00b7'; then
                echo "  XInput mode OK (2f24:00b7, 'ESM GAME FOR WINDOWS')"
            elif lsusb | grep -q '057e:2009'; then
                echo "  Switch-spoof mode (057e:2009); hid_nintendo has claimed it."
                echo "  Reinstalling the blacklist ..."
                echo
                bash "$pkg_dir/scripts/setup_controller.sh"
                echo
                echo "  Replug the controller (or reboot), then re-run 'drone controller'."
                return 0
            else
                echo "  No known controller on the USB bus." >&2
                echo "  Expected 2f24:00b7 (XInput) or 057e:2009 (Switch spoof)." >&2
                return 3
            fi
            if [[ -e /dev/input/js0 ]]; then
                echo "  /dev/input/js0 present"
            else
                echo "  /dev/input/js0 MISSING (xpad did not bind the pad)" >&2
            fi
            echo
            echo "  LEDs: top + bottom of the 4-LED column lit = player 1 (XInput)."
            echo "  Confirm the /joy report shape (11 buttons / 8 axes):"
            echo "    ros2 topic echo /joy --once"
            ;;

        camera)
            # Connectivity check for the RealSense + Arducam (hardware suite,
            # camera classes only), then a pointer to confirm the 180 flip live.
            echo "=== Camera hardware tests (RealSense + Arducam) ==="
            ( cd "$ws" \
                && colcon test --packages-select "$pkg" \
                    --event-handlers console_direct+ \
                    --pytest-args -k "RealSense or Arducam" "$@" \
                && colcon test-result --verbose )
            echo
            echo "=== 180 flip ==="
            echo "  Both feeds are rotated 180 (mount is inverted): the color +"
            echo "  depth images via realsense_flip, the Arducam via image_relay.py"
            echo "  rotate180. Orientation is visual; confirm in the dashboard or:"
            echo "    ros2 run rqt_image_view rqt_image_view"
            if command -v ros2 >/dev/null; then
                echo
                echo "  Active image topics:"
                ros2 topic list 2>/dev/null | grep -iE 'image|camera' \
                    | sed 's/^/    /' || echo "    (none; is teleop running?)"
            fi
            ;;

        mavros)
            # mavros_node running + /dev/ttyAMA0 present is the reliable liveness
            # signal. The /mavros/state read is best-effort: ros2 topic discovery
            # on this stack routinely takes >5s, so a short timeout false-reports
            # a healthy, connected MAVROS as down.
            echo "=== MAVROS ==="
            local mpid
            mpid=$(pgrep -x mavros_node | head -1)
            if [ -n "$mpid" ]; then
                echo "  mavros_node: running (pid $mpid)"
            else
                echo "  mavros_node: not running - start the stack with 'drone teleop'" >&2
                return 3
            fi
            if [ -e /dev/ttyAMA0 ]; then
                echo "  /dev/ttyAMA0: present"
            else
                echo "  /dev/ttyAMA0: MISSING - needs dtoverlay=uart0-pi5 (drone setup pixhawk)" >&2
            fi
            if ! command -v ros2 >/dev/null; then
                return 0
            fi
            echo "  reading /mavros/state (discovery can take ~10s) ..."
            local state
            state=$(timeout 15 ros2 topic echo /mavros/state --once 2>/dev/null)
            if [ -n "$state" ]; then
                echo "$state" | grep -E 'connected|armed|guided|mode|system_status' \
                    | sed 's/^/  /'
            else
                echo "  /mavros/state not read in 15s (ros2 discovery latency)."
                echo "  mavros_node is up with the serial link; retry, or check the FCU link:"
                echo "    journalctl -u uav-teleop -b | grep 'CON:'"
            fi
            ;;

        selftest)
            # Full hardware suite: Pixhawk / RealSense / Arducam / Coral +
            # ROS2 package deps (test/test_hardware.py).
            ( cd "$ws" \
                && colcon test --packages-select "$pkg" \
                    --event-handlers console_direct+ \
                    --pytest-args -k hardware "$@" \
                && colcon test-result --verbose )
            ;;

        service)
            local action="${1:-status}"
            shift || true
            local -a units=("uav-teleop" "uav-watchdog"
                            "uav-dashboard" "uav-jupyter")
            case "$action" in
                install)
                    bash "$pkg_dir/scripts/setup_services.sh"
                    ;;
                start)
                    if [[ -n "$1" ]]; then
                        sudo systemctl start "uav-$1"
                    else
                        sudo systemctl start uav-teleop
                    fi
                    ;;
                stop)
                    if [[ -n "$1" ]]; then
                        sudo systemctl stop "uav-$1"
                    else
                        sudo systemctl stop uav-teleop
                    fi
                    ;;
                restart)
                    if [[ -n "$1" ]]; then
                        sudo systemctl restart "uav-$1"
                    else
                        sudo systemctl restart uav-teleop
                    fi
                    ;;
                enable|disable)
                    local u
                    for u in "${units[@]}"; do
                        sudo systemctl "$action" "$u"
                    done
                    ;;
                logs)
                    local unit="${1:-teleop}"
                    sudo journalctl -u "uav-$unit" -f
                    ;;
                status|"")
                    local u
                    for u in "${units[@]}"; do
                        local state enabled
                        state=$(systemctl is-active "$u" 2>&1 || true)
                        enabled=$(systemctl is-enabled "$u" 2>&1 || true)
                        printf "  %-18s  active=%-12s enabled=%s\n" \
                            "$u" "$state" "$enabled"
                    done
                    ;;
                -h|--help|help)
                    cat <<'__DR_SVC_HELP__'
usage: drone service <action> [unit]
actions:
  install        Drop unit files in /etc/systemd/system/ + daemon-reload + enable
  start [name]   Start uav-<name>; default = teleop
  stop [name]    Stop uav-<name>; default = teleop
  restart [name] Restart uav-<name>; default = teleop
  enable         Enable all uav-* units (auto-start on boot)
  disable        Disable all uav-* units
  logs [name]    journalctl -u uav-<name> -f; default = teleop
  status         active/enabled snapshot for all units (default)
units: teleop, watchdog, dashboard, jupyter
__DR_SVC_HELP__
                    ;;
                *)
                    echo "drone service: unknown action '$action'" >&2
                    return 2
                    ;;
            esac
            ;;

        setup)
            local phase="${1:-}"
            shift || true
            local sdir="$pkg_dir/scripts"
            case "$phase" in
                "")
                    echo "usage: drone setup <phase>" >&2
                    echo "  phases: all, pixhawk, realsense, arducam, coral, services, networking, controller" >&2
                    return 2
                    ;;
                all)         bash "$sdir/setup_all.sh" "$@" ;;
                pixhawk)     bash "$sdir/setup_pixhawk.sh" "$@" ;;
                realsense)   bash "$sdir/setup_realsense.sh" "$@" ;;
                arducam)     bash "$sdir/setup_arducam.sh" "$@" ;;
                coral)       bash "$sdir/setup_coral.sh" "$@" ;;
                services)    bash "$sdir/setup_services.sh" "$@" ;;
                networking)
                    if [ "${1:-}" = "--reset" ]; then
                        shift
                        bash "$sdir/reset_networking.sh" "$@"
                    else
                        bash "$sdir/setup_networking.sh" "$@"
                    fi
                    ;;
                controller)  bash "$sdir/setup_controller.sh" "$@" ;;
                *)
                    echo "drone setup: unknown phase '$phase'" >&2
                    echo "  phases: all, pixhawk, realsense, arducam, coral, services, networking, controller" >&2
                    return 2
                    ;;
            esac
            ;;

        library)
            # Manage which ~/jupyter_ws/<folder>/library/ is on Python's sys.path
            # by writing a .pth file into the user site-packages directory, so
            # labs can `import drone_core` without sys.path hacks. Ported from
            # racecar-tool (racecar_student.pth -> drone_student.pth,
            # racecar_core.py -> drone_core.py).
            local jws="$HOME/jupyter_ws"
            local site_pkgs
            site_pkgs=$(python3 -c 'import site; print(site.getusersitepackages())' 2>/dev/null)
            local pth_file="$site_pkgs/drone_student.pth"

            local action=""
            local select_target=""
            while [[ $# -gt 0 ]]; do
                local arg="$1"; shift
                case "$arg" in
                    --select)
                        action="select"
                        select_target="${1:-}"
                        [[ -n "$select_target" ]] && shift
                        ;;
                    --select=*)
                        action="select"
                        select_target="${arg#*=}"
                        ;;
                    --list)    action="list" ;;
                    --reset)   action="reset" ;;
                    --status)  action="status" ;;
                    --help|-h) action="help" ;;
                    *)
                        echo "drone library: unknown flag '$arg'" >&2
                        return 2
                        ;;
                esac
            done

            if [[ -z "$action" ]]; then
                echo "usage: drone library [--select <folder> | --list | --reset | --status]" >&2
                return 2
            fi

            if [[ "$action" == "help" ]]; then
                cat <<'__DR_LIB_HELP__'
usage: drone library <action>
Manages the drone_student.pth file in user site-packages so Python scripts
(e.g. labs/test_core.py) can `import drone_core` without sys.path hacks.

Actions:
  --select <folder>  Point the .pth at ~/jupyter_ws/<folder>/library/.
                     <folder> must contain library/drone_core.py.
  --list             List all ~/jupyter_ws/ folders that look like valid
                     student libraries (contain library/drone_core.py).
                     The currently-selected folder is marked with *.
  --reset            Delete the .pth file (no library on sys.path).
  --status           Show the currently-selected library, or report none.

The .pth is written to:
  ~/.local/lib/pythonX.Y/site-packages/drone_student.pth
__DR_LIB_HELP__
                return 0
            fi

            if [[ -z "$site_pkgs" ]]; then
                echo "drone library: could not determine user site-packages directory" >&2
                return 1
            fi

            case "$action" in
                list)
                    if [[ ! -d "$jws" ]]; then
                        echo "No ~/jupyter_ws/ directory found."
                        return 0
                    fi
                    local current=""
                    if [[ -f "$pth_file" ]]; then
                        current=$(head -n 1 "$pth_file")
                    fi
                    local found=0
                    echo "Available libraries in $jws:"
                    local d
                    for d in "$jws"/*/; do
                        [[ -d "$d" ]] || continue
                        local libdir="${d}library"
                        if [[ -f "$libdir/drone_core.py" ]]; then
                            local name
                            name=$(basename "$d")
                            local marker="  "
                            if [[ "$current" == "${libdir%/}" ]]; then
                                marker=" *"
                            fi
                            printf "%s %s\n" "$marker" "$name"
                            found=1
                        fi
                    done
                    if [[ $found -eq 0 ]]; then
                        echo "  (none - no folder contains library/drone_core.py)"
                    fi
                    ;;

                select)
                    if [[ -z "$select_target" ]]; then
                        echo "drone library: --select requires a folder name" >&2
                        echo "  (run 'drone library --list' to see candidates)" >&2
                        return 2
                    fi
                    local target_dir="$jws/$select_target"
                    local target_lib="$target_dir/library"
                    if [[ ! -d "$target_dir" ]]; then
                        echo "drone library: '$select_target' is not a folder under $jws" >&2
                        return 2
                    fi
                    if [[ ! -f "$target_lib/drone_core.py" ]]; then
                        echo "drone library: '$target_lib/drone_core.py' not found" >&2
                        echo "  (folder must contain library/drone_core.py)" >&2
                        return 2
                    fi
                    mkdir -p "$site_pkgs"
                    echo "$target_lib" > "$pth_file"
                    echo "Selected library: $target_lib"
                    echo "  wrote $pth_file"
                    ;;

                reset)
                    if [[ -f "$pth_file" ]]; then
                        rm -f "$pth_file"
                        echo "Reset: removed $pth_file"
                    else
                        echo "Reset: no .pth file to remove ($pth_file)"
                    fi
                    ;;

                status)
                    if [[ -f "$pth_file" ]]; then
                        local current
                        current=$(head -n 1 "$pth_file")
                        echo "Current library: $current"
                        echo "  ($pth_file)"
                        if [[ ! -f "$current/drone_core.py" ]]; then
                            echo "  WARNING: drone_core.py not found at this path" >&2
                        fi
                    else
                        echo "No drone library is currently selected."
                        echo "  Run: drone library --select <folder>"
                        echo "  (or: drone library --list)"
                    fi
                    ;;
            esac
            ;;

        cleanup)
            # Find orphaned/stale drone processes + FastRTPS SHM segments.
            # Dry-run by default; pass --force to actually kill / remove.
            local force=0
            local arg
            for arg in "$@"; do
                case "$arg" in
                    -f|--force) force=1 ;;
                    -n|--dry-run) force=0 ;;
                    -h|--help)
                        cat <<'__DR_CLEANUP_HELP__'
usage: drone cleanup [--dry-run | --force]
  Lists drone processes and FastRTPS SHM orphans. Default is --dry-run.
  --force kills processes (uses sudo for root-owned ones) and removes SHM.
__DR_CLEANUP_HELP__
                        return 0
                        ;;
                    *) echo "drone cleanup: unknown flag '$arg'" >&2; return 2 ;;
                esac
            done

            # ----- Process inventory -----
            local pattern='uav_neo_ros2_driver|realsense2_camera_node|mavros_node|gscam_node|ros2 launch uav_neo'
            local matches
            matches=$(ps -eo pid,user,cmd --no-headers | grep -E "$pattern" | grep -v 'grep\|drone cleanup' || true)

            if [[ -z "$matches" ]]; then
                echo "No drone processes running."
            else
                echo "=== Drone processes ==="
                echo "$matches" | awk '{printf "  pid=%-6s user=%-8s cmd=%s\n", $1, $2, substr($0, index($0,$3))}' | head -30
                local user_pids root_pids
                user_pids=$(echo "$matches" | awk -v u="$USER" '$2 == u {print $1}' | tr '\n' ' ')
                root_pids=$(echo "$matches" | awk '$2 == "root" {print $1}' | tr '\n' ' ')
                if [[ $force -eq 1 ]]; then
                    if [[ -n "$user_pids" ]]; then
                        echo "Killing user-owned: $user_pids"
                        # shellcheck disable=SC2086
                        kill -9 $user_pids 2>/dev/null || true
                    fi
                    if [[ -n "$root_pids" ]]; then
                        echo "Killing root-owned (sudo): $root_pids"
                        # shellcheck disable=SC2086
                        sudo kill -9 $root_pids 2>/dev/null || \
                            echo "  (sudo failed; run: sudo kill -9 $root_pids)"
                    fi
                else
                    echo "(dry-run; pass --force to kill)"
                fi
            fi

            # ----- FastRTPS SHM orphans -----
            local shm_orphans=()
            local shm_locks=()
            local f el
            for f in /dev/shm/fastrtps_port*; do
                [ -e "$f" ] || continue
                case "$f" in *_el) continue ;; esac
                if [ ! -s "$f" ]; then
                    shm_orphans+=("$f")
                fi
            done
            for el in /dev/shm/fastrtps_port*_el; do
                [ -e "$el" ] || continue
                local data="${el%_el}"
                if [ ! -e "$data" ]; then
                    shm_locks+=("$el")
                fi
            done

            echo
            if [[ ${#shm_orphans[@]} -eq 0 && ${#shm_locks[@]} -eq 0 ]]; then
                echo "No FastRTPS SHM orphans in /dev/shm."
            else
                echo "=== FastRTPS SHM orphans ==="
                for f in "${shm_orphans[@]}"; do
                    echo "  zero-byte: $f"
                done
                for el in "${shm_locks[@]}"; do
                    echo "  stale lock: $el"
                done
                if [[ $force -eq 1 ]]; then
                    for f in "${shm_orphans[@]}"; do
                        local base
                        base=$(basename "$f")
                        rm -f "$f" "/dev/shm/${base}_el" "/dev/shm/sem.${base}_mutex"
                    done
                    for el in "${shm_locks[@]}"; do
                        local base
                        base=$(basename "${el%_el}")
                        rm -f "$el" "/dev/shm/sem.${base}_mutex"
                    done
                    echo "Removed."
                else
                    echo "(dry-run; pass --force to remove)"
                fi
            fi
            ;;

        status)
            echo "=== USB peripherals ==="
            lsusb | grep -iE "intel|global unichip|google|0c45|2f24|057e" \
                || echo "  (none of the expected USB devices found)"
            echo
            echo "=== Device nodes ==="
            # Pixhawk UART: the FC is on GPIO 14/15 = RP1 serial0 = /dev/ttyAMA0
            # (pinned by dtoverlay=uart0-pi5; see setup_pixhawk.sh). /dev/ttyAMA10
            # is the SoC PL011 on the debug connector (dead pins), not the FCU
            # link. List whichever the kernel presents.
            local uart
            uart=$(ls /dev/ttyAMA* 2>/dev/null | tr '\n' ' ')
            if [[ -n "$uart" ]]; then
                printf "  %-16s %s\n" "Pixhawk UART" "$uart"
            else
                printf "  %-16s %s\n" "Pixhawk UART" "MISSING (no /dev/ttyAMA*)"
            fi
            if [[ -e /dev/input/js0 ]]; then
                printf "  %-16s %s\n" "/dev/input/js0" "present (Xbox pad)"
            else
                printf "  %-16s %s\n" "/dev/input/js0" "MISSING (xpad not bound)"
            fi
            echo
            echo "=== ros2 nodes running ==="
            if command -v ros2 >/dev/null; then
                ros2 node list 2>/dev/null || echo "  (no ROS daemon / no nodes)"
            else
                echo "  ros2 not on PATH"
            fi
            ;;

        help|-h|--help|"")
            cat <<'__DR_HELP__'
drone - UAV Neo developer tool

Usage:
    drone <command> [args]

Commands:
    build               Build uav_neo_ros2_driver (--symlink-install) and source overlay.
    test                Run the package test suite with verbose results.
    source              Source the workspace overlay into the current shell.
    cd                  Change directory to the uav_neo_ros2_driver package root.
    teleop              Launch the full teleop stack via launch_teleop.sh wrapper
                        (timestamped ~/logs/<ts>/ + FastRTPS SHM cleanup).
                        Forwards args, e.g. `drone teleop realsense_flip:=false`.
    launch <name>       Shortcut for `ros2 launch uav_neo_ros2_driver <name>.launch.py`.
                        Examples: drone launch realsense
                                  drone launch mavros
                                  drone launch edgetpu
    watchdog            Run the node watchdog (restart-on-failure supervisor).
                        Logs to ~/logs/latest/watchdog.log. Assumes teleop runs
                        separately.
    udev                Reinstall the camera + Coral udev rules AND the
                        hid_nintendo blacklist (keeps the pad in XInput mode).
    controller          Verify the Xbox pad is in XInput mode (2f24:00b7, js0,
                        11/8); reinstall the blacklist if it came up as the
                        Nintendo Switch spoof (057e:2009).
    camera              Run the RealSense + Arducam hardware tests and point to
                        the live 180-flip confirmation.
    mavros              Show the MAVROS link + PX4 mode/arming state
                        (/mavros/state).
    selftest            Run the full hardware suite (Pixhawk / RealSense /
                        Arducam / Coral + ROS2 package deps).
    setup <phase>       Run a setup script. Phases:
                          all          - setup_all.sh (the 6-phase orchestrator)
                          pixhawk      - Pixhawk UART + MAVROS
                          realsense    - RealSense D435i
                          arducam      - Arducam B0578
                          coral        - Coral EdgeTPU
                          services     - systemd units + JupyterLab
                          networking   - eth0 dual-IP + wlan0 isolated AP
                                         (--reset reverts to stock, pre-imaging)
                          controller   - hid_nintendo blacklist (XInput fallback)
    service <action>    systemd service control. Actions:
                          install              setup_services.sh (drop + enable units)
                          start [name]         default: teleop
                          stop [name]          default: teleop
                          restart [name]       default: teleop
                          enable|disable       all units
                          logs [name]          journalctl -f for uav-<name>
                          status               active/enabled summary (default)
                        Units: teleop, watchdog, dashboard, jupyter
    library <action>    Manage drone_student.pth in user site-packages.
                          --select <folder>   point at ~/jupyter_ws/<folder>/library
                          --list              show valid folders in ~/jupyter_ws
                          --reset             delete the .pth file
                          --status            show current selection
    cleanup             List orphaned drone processes + FastRTPS SHM segments.
                        Defaults to a dry-run. Pass --force to actually kill/remove
                        (uses sudo for root-owned PIDs).
    status              Show USB peripherals, device nodes, and running ros2 nodes.
    help                Show this message.

Extra args are forwarded:
    drone build --cmake-args -DCMAKE_BUILD_TYPE=Release
    drone launch realsense realsense_flip:=false
__DR_HELP__
            ;;

        *)
            echo "drone: unknown command '$cmd'. Try 'drone help'." >&2
            return 2
            ;;
    esac
}

# Bash completion: subcommands at position 1, then per-command args.
_drone_complete() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"
    local sub="${COMP_WORDS[1]:-}"

    if [[ $COMP_CWORD -eq 1 ]]; then
        # shellcheck disable=SC2207
        COMPREPLY=( $(compgen -W "build test source cd teleop launch watchdog udev controller camera mavros selftest setup service library cleanup status help" -- "$cur") )
        return
    fi

    case "$sub" in
        launch)
            local launch_dir="$HOME/ros2_ws/src/uav_neo_ros2_driver/launch"
            if [[ -d "$launch_dir" ]]; then
                local names
                names=$(cd "$launch_dir" && ls ./*.launch.py 2>/dev/null | sed 's|.*/||; s/\.launch\.py$//')
                # shellcheck disable=SC2207
                COMPREPLY=( $(compgen -W "$names" -- "$cur") )
            fi
            ;;
        setup)
            if [[ "$prev" == "networking" ]]; then
                # shellcheck disable=SC2207
                COMPREPLY=( $(compgen -W "--reset" -- "$cur") )
            else
                # shellcheck disable=SC2207
                COMPREPLY=( $(compgen -W "all pixhawk realsense arducam coral services networking controller" -- "$cur") )
            fi
            ;;
        service)
            if [[ $COMP_CWORD -eq 2 ]]; then
                # shellcheck disable=SC2207
                COMPREPLY=( $(compgen -W "install start stop restart enable disable logs status help" -- "$cur") )
            elif [[ $COMP_CWORD -eq 3 ]]; then
                local action="${COMP_WORDS[2]}"
                case "$action" in
                    start|stop|restart|logs)
                        # shellcheck disable=SC2207
                        COMPREPLY=( $(compgen -W "teleop watchdog dashboard jupyter" -- "$cur") )
                        ;;
                esac
            fi
            ;;
        library)
            if [[ "$cur" == --select=* || "$prev" == "--select" ]]; then
                local jws="$HOME/jupyter_ws"
                local candidates=""
                if [[ -d "$jws" ]]; then
                    local d
                    for d in "$jws"/*/; do
                        [[ -d "$d" ]] || continue
                        if [[ -f "${d}library/drone_core.py" ]]; then
                            candidates+="$(basename "$d") "
                        fi
                    done
                fi
                if [[ "$cur" == --select=* ]]; then
                    local prefix="${cur#--select=}"
                    # shellcheck disable=SC2207
                    COMPREPLY=( $(compgen -W "$candidates" -- "$prefix") )
                else
                    # shellcheck disable=SC2207
                    COMPREPLY=( $(compgen -W "$candidates" -- "$cur") )
                fi
            else
                # shellcheck disable=SC2207
                COMPREPLY=( $(compgen -W "--select --select= --list --reset --status --help" -- "$cur") )
            fi
            ;;
        cleanup)
            # shellcheck disable=SC2207
            COMPREPLY=( $(compgen -W "--dry-run --force --help" -- "$cur") )
            ;;
    esac
}
complete -F _drone_complete drone
