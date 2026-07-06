# drone-tool plan (v1.3.0)

Plan for `drone-tool`, a `drone <subcommand>` shell helper for the UAV Neo kit,
inherited from racecar-tool. Status: scaffold only; commands are stubs pending a
decision on which racecar features to carry over.

## Source

MITRacecarNeo/racecar_neo_ros2_driver, branch `feature/pit-teensy-driver`, file
`scripts/racecar-tool.sh` (plus `test/test_racecar_tool.py`). It is one bash
`case` dispatch, sourced into the interactive shell as a function via `~/.bashrc`,
with a tab-completion function. The `pit_*` files on that branch are a separate
Teensy-driver feature and are not part of this tool.

racecar-tool subcommands: `build test source cd teleop launch clear udev
watchdog service setup library cleanup selftest status help`.

## Command inheritance

| racecar-tool | drone-tool | Disposition |
|---|---|---|
| `build` | `build` | Carry. `colcon build --packages-select uav_neo_ros2_driver` + source overlay. |
| `test` | `test` | Carry. `colcon test` + `colcon test-result`. |
| `source` | `source` | Carry. Source the workspace overlay. |
| `cd` | `cd` | Carry. cd to `~/ros2_ws/src/uav_neo_ros2_driver`. |
| `launch <name>` | `launch <name>` | Carry. `ros2 launch uav_neo_ros2_driver <name>.launch.py`. |
| `teleop` | `teleop` | Carry. Run `scripts/launch_teleop.sh` (timestamped logs). |
| `watchdog` | `watchdog` | Carry. Run `scripts/watchdog.py`. |
| `service <action> [unit]` | `service <action> [unit]` | Carry. systemd for `uav-teleop`/`uav-watchdog`/`uav-dashboard`/`uav-jupyter`. |
| `cleanup` | `cleanup` | Carry. Orphan process + FastRTPS `/dev/shm` cleanup (logic already in `watchdog.py`/`launch_teleop.sh`). |
| `status` | `status` | Carry. `lsusb`, device nodes, `ros2 node list`. |
| `library <action>` | `library <action>` | Carry (decision needed). Student-library import-path switching under `jupyter_ws`. |
| `setup all\|networking\|realsense` | `setup all\|networking\|...` | Carry. Wrap `scripts/setup_*.sh`. |
| `help` | `help` | Carry. Command reference. |
| `udev` | `udev` | Adapt. Reinstall camera + Coral rules AND the `hid_nintendo` blacklist (`scripts/setup_controller.sh`). |
| `selftest --dmatrix` | `selftest` | Adapt. Run the hardware suite (`test/test_hardware.py`: Pixhawk / RealSense / Arducam / Coral) instead of a dot matrix. |
| `clear --dmatrix` | (drop) | Drop. No dot matrix display on the drone. |

## New drone commands (candidates)

- `controller` — verify the Xbox pad is in XInput mode (`2f24:00b7`, `js0`,
  11/8), report LED guidance, and reinstall the `hid_nintendo` blacklist if the
  pad came up as Switch-spoof (`057e:2009`).
- `camera` — preview or confirm the RealSense 180 flip and Arducam feeds.
- `mavros` / `px4` — MAVROS connection and PX4 mode/arming status.

## Open questions

- Keep `library` (student import-path switching), or is that jupyter_ws-only?
- Add `controller` and `camera` drone commands, or keep the tool minimal?
- Any display/indicator equivalent to the racecar dot matrix?
- Include a `sim` command, or is the drone hardware-only?

## Scaffold contents

- `scripts/drone-tool.sh` — the `drone()` function, dispatch `case` with stubbed
  branches, `help` text, and a `_drone_complete` skeleton. No command bodies yet.
- This plan.

## Installation (planned)

Source it from `~/.bashrc` (`source ~/ros2_ws/src/uav_neo_ros2_driver/scripts/drone-tool.sh`),
matching how racecar-tool is installed. `scripts/setup_services.sh` would add the
line during setup once implemented.
