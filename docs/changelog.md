# Changelog

All notable changes to this package are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
