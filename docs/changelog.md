# Changelog

All notable changes to this package are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.2] - 2026-07-06

### Added

- `scripts/reset_networking.sh` and the `drone setup networking --reset` flag,
  which revert the networking config to stock for imaging or porting a unit to a
  new machine. The script deletes the `uav-neo-ap` connection (removing the SSID
  and plaintext WPA2 PSK), deletes `netplan-eth0` and `99-uav-eth0.yaml` so eth0
  returns to plain DHCP with no static IP or MAC lock, removes the AP-isolation
  dispatcher, flushes the wlan0 FORWARD rules, and runs `netplan apply`. It is
  idempotent, touches only what `setup_networking.sh` created, and takes `--yes`
  to skip the connectivity-loss prompt for scripted runs.

### Fixed

- Closed a networking leak in cloned images. On this build NetworkManager stores
  connections in netplan (`/etc/netplan/90-NM-<uuid>.yaml`), not in
  `/etc/NetworkManager/system-connections/`, so a per-unit `.nmconnection` wipe
  left the AP PSK, the static `192.168.52.200`, and the eth0 MAC lock in the
  image. `reset_networking.sh` removes them via `nmcli`, which keeps the netplan
  store consistent. `pre-image-wipe.sh` now documents the reset as the pre-imaging
  networking step.

## [1.4.1] - 2026-07-06

### Fixed

- JupyterLab could not import `uav_neo_ros2_driver` (e.g. the student library's
  `controller_real.py`), failing with `ModuleNotFoundError`. `uav-jupyter.service`
  set a static `PYTHONPATH`, which does not resolve the develop egg-link that a
  `--symlink-install` build writes into the overlay. The service now sources the
  ROS 2 and workspace overlays (matching `uav-dashboard.service`), so the driver
  package is importable regardless of copy vs symlink install.

## [1.4.0] - 2026-07-06

### Added

- Coral Edge TPU M.2 (PCIe) support. `setup_coral.sh` auto-detects the Apex card
  (`1ac1:089a`) and installs the full PCIe path: the gasket/apex driver via DKMS
  (`depend/gasket-dkms_*.deb`), the `coral-msi` device-tree overlay
  (`scripts/coral-msi.dts`), and the `apex` access group for non-root
  `/dev/apex_0`. `edgetpu_node` uses the M.2 with no code change (it auto-detects
  `pci` at `/dev/apex_0`). Deployed and verified on uav-neo. See
  `docs/coral-m2-migration.md`.
- `coral-msi` device-tree overlay. Repoints the Pi 5 external PCIe `msi-parent`
  from the small `mip1` peripheral to `pcie1`'s own MSI controller, which has
  enough vectors for the Apex's 13 interrupts. Without it apex fails with
  `Couldn't initialize interrupts: -28`. The overlay resolves `pcie1` by symbol,
  so it applies on any Pi 5 without per-board edits (portable to cloned images).
- Kernel-update resilience for the M.2 driver. `setup_coral.sh` installs the
  `linux-headers-raspi` meta package so DKMS auto-rebuilds `apex`/`gasket` after
  a kernel update. `setup_coral.sh` is idempotent and safe to re-run; all M.2
  state (overlay, DKMS module, udev rule, group) lives on disk, so a cloned
  image detects the Coral the same on another Pi 5.

### Changed

- gasket/apex driver is the feranick fork (builds on kernel 6.8 arm64) plus
  `scripts/gasket-msi-fallback.patch`, which allocates interrupts with
  `pci_alloc_irq_vectors(MSI-X | MSI)` so it falls back to MSI on the Pi 5 (whose
  external PCIe controller supplies MSI, not MSI-X).
- `teleop.launch.py` EdgeTPU start delay cut from 10s to 3s: the M.2 Apex is
  bound at boot, so the old USB-firmware-enumeration wait is unneeded.

### Removed

- USB firmware-retry workaround in `edgetpu_node.py` (the one-shot
  `make_interpreter` retry for the USB accelerator's `1a6e:089a -> 18d1:9302`
  re-enumeration). The M.2 Apex loads on the first try.

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
