# Changelog

All notable changes to this package are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.0] - Unreleased

### Added

- (in progress) Coral Edge TPU M.2 (PCIe) support. Migrates the Coral path off
  the USB accelerator: gasket/apex DKMS kernel modules, an `apex` udev rule for
  `/dev/apex_0`, and a `setup_coral.sh` path for the PCIe card
  (`1ac1:089a`). Replaces the USB firmware-retry workaround.

## [1.3.1] - 2026-07-05

### Fixed

- Pixhawk MAVLink link on Pi 5. A firmware/DTB update left the RP1 `serial0`
  node disabled, so `/dev/ttyAMA0` disappeared and MAVROS looped on
  `serial:open: No such file or directory`; `/mavros/state` never published.
  `setup_pixhawk.sh` now pins UART0 to GPIOs 14/15 with `dtoverlay=uart0-pi5`,
  which restores `/dev/ttyAMA0` and survives future firmware updates. Requires a
  reboot. The device path in the launch/config/test is unchanged (`/dev/ttyAMA0`).
- Watchdog no longer restart-loops a healthy MAVROS. `mavros` liveness is now
  process-authoritative (`liveness: 'process'` in `watchdog.py`): it restarts
  only when `mavros_node` is actually gone, not when the `ros2 topic list` graph
  query transiently drops `/mavros/state`. MAVROS owns the FCU serial link and
  reconnects on its own, so the topic-based check was cycling a connected node
  every poll once `/dev/ttyAMA0` returned.
- Watchdog debounces topic-only failures for the topic-checked nodes
  (`arducam`/`realsense`/`mux`). `ros2 topic list` intermittently returns a
  partial graph under DDS discovery latency, which was restarting healthy,
  publishing nodes ~once a minute. A restart now requires `TOPIC_FAIL_THRESHOLD`
  (3) consecutive misses while the process is up; a dead process still restarts
  immediately.
- `drone mavros` no longer false-reports a connected MAVROS as down. It checks
  `mavros_node` and `/dev/ttyAMA0` first (reliable), then reads `/mavros/state`
  best-effort with a longer window instead of a 5s timeout that this stack's
  discovery latency routinely exceeds.
- `drone status` device-map comment corrected. The flight-controller UART is
  `/dev/ttyAMA0` (GPIOs 14/15, pinned by `dtoverlay=uart0-pi5`); `/dev/ttyAMA10`
  is the SoC PL011 on the debug connector (dead pins), not the FCU link. The
  earlier comment had these reversed.

## [1.3.0] - 2026-07-05

### Added

- `drone` shell helper (`scripts/drone-tool.sh`), inherited from racecar-tool: a
  sourced `drone <subcommand>` function with tab completion. Commands: `build
  test source cd teleop launch watchdog udev controller camera mavros selftest
  setup service library cleanup status help`.
- Drone-specific subcommands not in racecar-tool: `controller` (verify the Xbox
  pad is in XInput mode `2f24:00b7`; reinstall the `hid_nintendo` blacklist if it
  came up as the Switch spoof `057e:2009`), `camera` (RealSense + Arducam
  hardware tests plus a pointer to confirm the 180 flip), and `mavros` (MAVROS
  link + PX4 state from `/mavros/state`).
- `setup_services.sh` sources `drone-tool.sh` from `~/.bashrc` (idempotent), so
  `drone` is available after setup.
- `docs/drone-tool-plan.md`: the racecar -> drone command mapping and carry-over
  decisions.

### Changed

- `selftest` runs the hardware suite (`test/test_hardware.py`) instead of
  racecar's dot matrix patterns; `udev` reinstalls the camera + Coral rules AND
  the `hid_nintendo` blacklist; `library` manages `drone_student.pth` pointing at
  `~/jupyter_ws/<folder>/library/drone_core.py`.

### Removed

- Racecar-only features were not carried over: the dot matrix `clear`/`selftest`
  paths, the Teensy/pit driver, and motor/ESC/lidar/ackermann controls.

## [1.2.0] - 2026-07-05

### Added

- `gamepad_node` (`uav_neo_ros2_driver/gamepad.py`): normalizes `/joy` into
  `/gamepad/cmd_vel` so the drone can be flown manually without student code.
- `config/gamepad.yaml` for the gamepad node's dead zone.
- 180-degree rotation of the RealSense color and depth relays for the
  upside-down camera mount, toggled by the `realsense_flip` launch argument.
- GPLv3 license headers on all source files, a `LICENSE` file, and
  `CONTRIBUTING.md`.

### Changed

- `mux_node` consumes `/gamepad/cmd_vel` for manual mode instead of reading the
  `/joy` sticks directly; stick normalization moved to the gamepad node. A stale
  manual or auto command now holds zero velocity.
- Repo-wide ASCII syntax pass; README headings are noun-phrase and sentence case.
- Package license set to `GPL-3.0-or-later` in `package.xml` and `setup.py`.

### Fixed

- `ament_flake8`, `ament_pep257`, and `ament_copyright` tests now pass (import
  ordering, quotes, line length, docstring conventions, license headers).
- `dashboard.py` shutdown handler now declares `global _monitor_running`, so it
  actually stops the monitor loop instead of binding a dead local.

## [1.1.0] - 2026-07-05

### Added

- `config/xbox_mapping.yaml`: single source for the controller button/axis to
  `/joy` index mapping, read by both the mux node and the student library.
- `uav_neo_ros2_driver/controller_mapping.py`: shared loader that overlays the
  YAML onto built-in defaults so a missing or partial file cannot leave the mux
  without a mapping.
- `scripts/setup_controller.sh` and `scripts/modprobe.d/blacklist-hid-nintendo.conf`:
  blacklist `hid_nintendo` so the ESM-9110 pad falls back to the `xpad` driver
  and enumerates in XInput mode on every boot.
- `report:` block in the mapping and a wrong-mode guard in the mux and student
  library that rejects a controller whose `/joy` report shape does not match the
  standardized XInput mode.

### Changed

- Standardized the ESM-9110 gamepad on XInput mode (8 axes / 11 buttons). Its
  sticks rest at 0 and triggers rest at +1, so the flight math and student
  trigger/stick conversions are correct without extra calibration.
- `mux_node` loads its LB/RB and stick-axis indices from `xbox_mapping.yaml`
  instead of hardcoded constants.

### Fixed

- Boot-time enumeration: on Pi 5 / kernel 6.x `hid_nintendo` claimed the pad's
  Switch-Pro-spoof USB id (`057e:2009`) and forced a 6-axis / 14-button profile
  with no `js0` (the intermittent "1 LED at boot" state).
- Student library controller indices were wrong for this pad (Back/Start,
  stick-clicks, and a trigger axis that indexed past the end of the `/joy`
  array); the mapping now comes from the shared config.

## [1.0.0] - initial release

- Full sensor and flight stack with two-pilot operation.
- EdgeTPU inference auto-starts at boot.
- Watchdog detects node death even when relays keep topics in the DDS graph.
- `mux.launch.py` prevents a cascade restart from a mux blip.
- gscam patched for the appsink memory leak; build shadowed in the colcon overlay.
- USB autosuspend disabled by udev rule for both cameras.
- eth0 dual-IP and isolated wlan0 AP automated by `setup_networking.sh`.
