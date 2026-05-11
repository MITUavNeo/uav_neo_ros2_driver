# UAV Neo — Robotics Features

A categorized index of the startup, setup, and safety mechanisms in this repository, written with portability to other ROS2 robots in mind. Each section notes what is **generic** (drop-in reusable) vs. **platform-specific** (rewrite for your hardware).

## Table of Contents

- [1. Setup Automation](#1-setup-automation)
- [2. Boot-Time Startup (systemd)](#2-boot-time-startup-systemd)
- [3. Safety Architecture](#3-safety-architecture)
- [4. Watchdog & Recovery](#4-watchdog--recovery)
- [5. DDS / Middleware Reliability](#5-dds--middleware-reliability)
- [6. Power & Hardware Health](#6-power--hardware-health)
- [7. Networking](#7-networking)
- [8. Logging & Observability](#8-logging--observability)
- [9. Pre-Flight Verification](#9-pre-flight-verification)
- [Migration Checklist](#migration-checklist)

---

## 1. Setup Automation

| Feature | Description | Implementation | Portability |
|---|---|---|---|
| `setup_all.sh` orchestrator | Runs six idempotent phases (ROS2 → FCU → sensors → AI accel → services → network). Skips completed phases on re-run; detects reboot points. | Bash script with per-phase existence guards; prompts for reboot when kernel/UART settings change, then resumes when re-run. | **Generic pattern** — replace per-phase scripts for your robot. |
| Per-component setup scripts | Each peripheral (`setup_pixhawk.sh`, `setup_realsense.sh`, `setup_arducam.sh`, `setup_coral.sh`) is standalone and re-runnable. | Bash scripts in `scripts/` invoked by the orchestrator or directly; use `apt install`, kernel-cmdline edits via `sed`, and `.deb`/`.whl` installs from `depend/`. | **Generic pattern.** |
| Driver patching (`patch_gscam.sh`) | Clones, patches, and overlay-builds a third-party driver to fix an upstream memory leak. | `git clone` upstream into `~/ros2_ws/src/`, apply edits, `colcon build` — the overlay shadows the apt-installed package on each `source install/setup.bash`. | **Generic pattern** — wrap any upstream driver with known defects. |
| udev rules | Non-root device access for Coral, RealSense IIO, cameras; disables USB autosuspend. | `.rules` files installed to `/etc/udev/rules.d/99-*.rules`, applied with `udevadm control --reload-rules && udevadm trigger`. | Rule contents are device-specific; mechanism is generic. |

## 2. Boot-Time Startup (systemd)

| Feature | Description | Implementation | Portability |
|---|---|---|---|
| `uav-teleop.service` | Launches full ROS2 stack via [launch_teleop.sh](../scripts/launch_teleop.sh). `Type=exec`, `Restart=on-failure`, `KillMode=control-group` so child nodes die with the unit. | systemd unit in `/etc/systemd/system/`, enabled via `systemctl enable`. `ExecStart` points at the launch wrapper script; `User=`/`Group=` drop privileges. | **Generic** — rename and re-point `ExecStart`. |
| `uav-watchdog.service` | `BindsTo=uav-teleop.service` so the watchdog stops when teleop stops; `ExecStartPre=sleep 15` gives nodes time to initialize. | systemd unit with `BindsTo=` + `After=`; `ExecStart` sources ROS2, then `exec`s `python3 watchdog.py`. | **Generic pattern.** |
| `uav-dashboard.service` | Web status page on `:8080` using Python's built-in HTTP server (no extra deps). | systemd unit running `python3 dashboard.py`; binds to `:8080` and serves rendered HTML. | **Generic.** |
| `uav-jupyter.service` | JupyterLab on `:8888` for in-field development. | systemd unit running `jupyter lab --no-browser --ip=0.0.0.0 --port=8888` in `~/jupyter_ws/`. | **Generic.** |
| Launch wrapper (`launch_teleop.sh`) | Creates timestamped log dir, updates `~/logs/latest` symlink atomically, cleans DDS SHM orphans pre-launch, sets `ROS_LOG_DIR`/`ROS_HOME`, `exec`s ros2 launch so systemd tracks the real PID. | Bash script invoked by `ExecStart=`. Uses `exec` (not backgrounding) so systemd cgroups capture the entire ROS2 launch tree. | **Generic pattern.** |
| `After=network-online.target` | Defers launch until networking is up (matters for MAVROS UDP bridges and remote topics). | One line in the `[Unit]` section; requires `NetworkManager-wait-online.service` (or `systemd-networkd-wait-online`) to be enabled. | **Generic.** |

## 3. Safety Architecture

The robot has **five independent safety layers**. The first one to trigger wins.

| Layer | Mechanism | Implementation | Portability |
|---|---|---|---|
| **L1 — Mux node** | All velocity commands pass through [mux_node.py](../uav_neo_ros2_driver/mux_node.py). Enforces speed/yaw caps from `config/mux.yaml`, gates commands behind a held controller bumper, and zeros output if the joystick disconnects (500 ms timeout). | ROS2 Python node; subscribes to `/joy` and `/mux/cmd_vel`, publishes the gated output at fixed rate to `/mavros/setpoint_velocity/cmd_vel`. Limits and dead-zone loaded from YAML at startup. | **Generic pattern** — adapt topic names/limits. |
| **L2 — FCU offboard timeout** | PX4 param `COM_OF_LOSS_T=1.0` reverts to RC if setpoints stop. | Set via QGroundControl (or `mavlink param set`); stored persistently on the FCU. | PX4-specific; ArduPilot and others have equivalents. |
| **L3 — Hardware RC override** | Safety pilot's Switch D (CH8) drops OFFBOARD mode at the FCU level — software cannot block it. | RC channel mapped via PX4 param `RC_MAP_OFFB_SW=8`; the FCU's mode switcher reads RC directly, bypassing the companion computer entirely. | UAV-specific (RC + FCU). Ground robots need an analogous E-stop. |
| **L4 — Privilege isolation** | Student/user code cannot arm, change modes, or publish directly to FCU velocity topics. All commands go through `/mux/cmd_vel`. | API boundary in the student library — exposes only `send_pcmd()` and similar high-level methods; FCU services (`/mavros/cmd/arming`, `/mavros/set_mode`) are not re-exported. | **Generic pattern** — API boundary, not hardware. |
| **L5 — Exception trap** | User code crashes are caught; library publishes zero velocity and continues the run loop. | `try`/`except` around the user-code invocation in the library's run loop; on except, publishes a zero `TwistStamped` to `/mux/cmd_vel`. | **Generic pattern.** |

> Required PX4 params (`COM_OF_LOSS_T`, `COM_RCL_EXCEPT`, `RC_MAP_OFFB_SW`) are documented in the README. Replace with FCU-equivalent for non-PX4 platforms.

## 4. Watchdog & Recovery

[scripts/watchdog.py](../scripts/watchdog.py) — a 5-second-poll process supervisor.

| Feature | Description | Implementation | Portability |
|---|---|---|---|
| **Two-signal liveness check** | A node is alive iff (a) its topic appears in `ros2 topic list` **and** (b) its binary path is in `pgrep -f`. The process check is required because subscribers (relays, MAVROS) keep dead-publisher topics in the DDS graph. | Python loop: `subprocess.run(['ros2','topic','list'])` parsed into a set, plus `pgrep -f <binary-path>` per node — both must succeed. Configured by a `NODES` dict. | **Generic pattern** — high-value, often missed. |
| **Hardware-aware restart** | Before relaunching, the watchdog verifies the underlying device exists (UART path / USB VID:PID). Skips restart if hardware is unplugged. | Per-node `device_check` callable in `NODES` — e.g. `os.path.exists('/dev/ttyAMA0')` for UART, `lsusb` substring match for USB devices. | Per-node `device_check` lambda — rewrite for your devices. |
| **Per-node launch files** | Watchdog restarts individual launch files (`mavros.launch.py`, `arducam.launch.py`, `mux.launch.py`) instead of the full stack, preventing cascade-restart. Mux gets a dedicated [mux.launch.py](../launch/mux.launch.py) for this reason. | One `.launch.py` per node in `launch/`; watchdog calls `subprocess.Popen(['ros2','launch',PACKAGE,launch_file])`. The full stack composes them with `IncludeLaunchDescription`. | **Generic pattern.** |
| **TERM-then-KILL escalation** | `pkill -f <pattern>` (SIGTERM) → 2 s grace → `pkill -9 -f <pattern>` (SIGKILL). Frees device handles cleanly. | `subprocess.run(['pkill','-f',pattern])` → `time.sleep(2)` → `subprocess.run(['pkill','-9','-f',pattern])`. | **Generic pattern.** |
| **Restart cooldown** | 30 s minimum between restarts of the same node prevents thrash. | Dict keyed by node name storing the last-restart `time.time()` value; compared against `RESTART_COOLDOWN` before any relaunch. | **Generic** — tune per platform. |
| **USB settle delay** | Arducam gets a 5 s `restart_delay` to avoid bus contention with the RealSense re-enumeration. | Optional `restart_delay` field per node in `NODES`; `time.sleep(delay)` between kill and relaunch. | USB-bus-specific; pattern is generic. |
| **Process renicing** | MAVROS is reniced to `+5` at watchdog startup so the cameras get more scheduling time (raises publish rates from ~15 Hz to ~30 Hz on the Pi 5). | `pgrep -f mavros_node` → `renice 5 -p <pid>` invoked once at watchdog start. | Useful on any CPU-constrained SBC. |
| **Failure-mode logging** | Logs distinguish `topic not advertised`, `process not running`, and `topic+process down` for postmortems. | Conditional string assembled from `topic_alive`/`proc_alive` booleans, written via `logging.warning(...)` to both stderr (journald) and the log file. | **Generic.** |

## 5. DDS / Middleware Reliability

| Feature | Description | Implementation | Portability |
|---|---|---|---|
| **FastRTPS SHM orphan cleanup** | A killed-mid-init rclpy process leaves 0-byte `/dev/shm/fastrtps_port*` segments; new participants hashing to that port spin forever (the "Jupyter cell hang" symptom). The watchdog sweeps these every 60 s, and [launch_teleop.sh](../scripts/launch_teleop.sh) cleans them once at start. | `pathlib.Path('/dev/shm').glob('fastrtps_port*')` → `stat().st_size == 0` → `unlink()` for the port, its `_el` partner, and `sem.*_mutex` lock. Same logic mirrored in bash inside the launch wrapper. | **Generic** — applies to any ROS2 + FastRTPS deployment. |
| **QoS-matched image relay** | [scripts/image_relay.py](../scripts/image_relay.py) replaces `topic_tools/relay`, which defaults to RELIABLE and silently drops from BEST_EFFORT publishers like camera drivers. | 30-line ROS2 Python node: create publisher with `QoSProfile(reliability=BEST_EFFORT, history=KEEP_LAST, depth=1)` and republish in the subscription callback. Launched once per image topic in `teleop.launch.py`. | **Generic** — drop-in for any ROS2 stack with image topics. |
| **Standalone restart launch files** | Each node has its own launch file so the watchdog can restart it in isolation. | One `.launch.py` per node in `launch/`; the full stack composes them via `IncludeLaunchDescription` so per-node launches stay reusable. | **Generic pattern.** |

## 6. Power & Hardware Health

| Feature | Description | Implementation | Portability |
|---|---|---|---|
| **Under-voltage sticky-bit watch** | The watchdog reads the Pi 5 PMIC's `in0_lcrit_alarm` (resolved by `hwmon` name, not index). Logs a single WARN the moment the 5 V rail dips. Survives until reboot. Critical for diagnosing in-flight BEC sag, which manifests as cascading USB resets. | Iterate `/sys/class/hwmon/hwmon*/name`, find one equal to `rpi_volt`, then poll `in0_lcrit_alarm` once per watchdog tick; latch on first `1`. | Pi 5 specific; the **sticky-bit / hwmon pattern** is generic for any SBC exposing PMIC alarms. |
| **USB autosuspend disable** | udev rule keeps both cameras awake — autosuspend was killing the Arducam mid-flight. | udev rule matching the camera USB VID:PID sets `ATTR{power/autosuspend_delay_ms}="-1"` and `ATTR{power/control}="on"`. | **Generic** — applies wherever USB cameras hang. |
| **gscam memory-leak patch** | Stock `gscam` leaks under CPU load and gets OOM-killed; overlay build applies `max-buffers=1, drop=true`. | `patch_gscam.sh` clones gscam into `~/ros2_ws/src/`, edits the appsink properties, `colcon build`s — the overlay shadows the apt build on every `source install/setup.bash`. | gscam-specific; documents the pattern of overlaying patched upstream drivers. |
| **Hardware-aware restart skip** | (Cross-listed from §4) Watchdog will not respawn a node whose device is missing — avoids burning restart budget on a permanent fault. | Per-node `device_check` callable returns `False` if device absent; watchdog logs `device NOT connected, skipping restart` and continues. | **Generic pattern.** |

## 7. Networking

| Feature | Description | Implementation | Portability |
|---|---|---|---|
| **Dual-IP eth0** | Static `192.168.52.200/24` for direct laptop tether **plus** DHCP from any router, simultaneously. Configured in netplan; `optional: true` + `may-fail: true` so boot never blocks on the cable. | Single netplan YAML at `/etc/netplan/90-NM-…yaml` with `ipv4.method: auto`, `ipv4.addresses: [192.168.52.200/24]`, plus the `optional`/`may-fail` flags; applied via `netplan apply`. NetworkManager renderer. | **Generic pattern.** |
| **Isolated wlan0 AP** | Pi acts as an AP (`uav-neo-0`, WPA2-PSK). Clients reach onboard services but **cannot** route to the internet — an iptables `FORWARD … REJECT` rule is reinstalled by a NetworkManager dispatcher on every AP-up. | NetworkManager connection in AP mode (built-in dnsmasq for client DHCP) + dispatcher script at `/etc/NetworkManager/dispatcher.d/99-uav-ap-isolate` that runs `iptables -I FORWARD …` on up and removes on down. | **Generic pattern** — desirable on any field robot. |
| **Netplan as single source of truth** | Network setup explicitly NOT in launch scripts; one netplan file owns the config. | All eth0/wlan0 IP config lives in `/etc/netplan/*.yaml`; launch scripts never call `ip`/`ifconfig`. Re-applied with `netplan apply` after edits. | **Generic discipline.** |

## 8. Logging & Observability

| Feature | Description | Implementation | Portability |
|---|---|---|---|
| **Per-session timestamped log dirs** | Each teleop start creates `~/logs/<YYYYMMDD_HHMMSS>/` containing `teleop.log`, `watchdog.log`, dashboard/jupyter logs, per-restart logs, and ROS2 internals (`ROS_LOG_DIR` set). | `mkdir -p ~/logs/$(date +%Y%m%d_%H%M%S)` in `launch_teleop.sh`; `export ROS_LOG_DIR=$LOG_DIR` so ROS2 internals land in the same directory. | **Generic.** |
| **`~/logs/latest` symlink** | Atomic symlink update points to the current session; tools and the watchdog resolve through it. | `ln -sfn "$LOG_DIR" "$HOME/logs/latest"` — `-n` makes the rename atomic when `latest` is already a symlink to a directory. | **Generic.** |
| **Dual sink (file + journald)** | `exec &> >(tee -a teleop.log)` so `journalctl -u uav-teleop` and the plain-text file both have output. | One line of bash redirection in `launch_teleop.sh` before the final `exec ros2 launch`. | **Generic.** |
| **Web dashboard** | `uav-dashboard` on `:8080` shows node liveness, topic rates, and recent watchdog restarts. Uses stdlib HTTP server — no deps. | Python `http.server` in `dashboard.py`, started by `uav-dashboard.service`; renders HTML by parsing `ros2 topic list`/`hz` output and tailing `watchdog.log`. Polls every 3 s. | **Generic.** |

## 9. Pre-Flight Verification

| Feature | Description | Implementation | Portability |
|---|---|---|---|
| **Hardware connectivity test suite** | `test/test_hardware.py` runs via `colcon test`. Each peripheral has a class (`TestPixhawk`, `TestRealSense`, `TestArducam`, `TestCoralTPU`, `TestDependencies`) that asserts USB presence, V4L2 enumeration, kernel-flag state (serial console off, SysRq off), permission groups, and even an inference-latency budget for the TPU. | pytest classes; assertions call `lsusb`, `v4l2-ctl --list-devices`, read `/proc/sys/...`, check `dialout` group membership, and time-bound the TPU inference call. Each assertion's failure message embeds the fix command. | **Generic pattern** — write equivalent tests for your hardware. Each assertion carries a human-readable fix hint. |

---

## Migration Checklist

When porting these features to another robot, address them in this order:

1. **Layered safety first** (§3). Decide your equivalent of OFFBOARD-mode override, command mux, and user-code privilege boundary before any autonomy is written.
2. **Setup orchestrator** (§1). Wrap installation as idempotent, reboot-aware phases — saves hours every time a fresh image is flashed.
3. **systemd unit set** (§2). Use `BindsTo=` to bind watchdog to the main stack and `KillMode=control-group` to avoid zombie nodes.
4. **Watchdog with two-signal liveness** (§4). The topic-only check is a trap; combine it with a process check. Rewrite the `NODES` dict for your nodes and devices.
5. **DDS SHM cleanup** (§5). Free for any ROS2 + FastRTPS robot — copy [scripts/watchdog.py](../scripts/watchdog.py)'s `_clean_fastrtps_orphans()` verbatim.
6. **Power health monitor** (§6). Find your platform's PMIC sticky-bit (or analogous voltage sensor) — flight-time BEC sag is otherwise invisible.
7. **Pre-flight test suite** (§9). Don't rely on "it ran last time"; assert every peripheral every boot.
8. **Networking last** (§7). Dual-IP and AP-isolation are quality-of-life; the robot works without them.

**Files most worth copying directly:**
- [scripts/watchdog.py](../scripts/watchdog.py) — pattern for two-signal liveness + hardware-aware restart
- [scripts/launch_teleop.sh](../scripts/launch_teleop.sh) — log-dir + SHM cleanup wrapper
- [scripts/image_relay.py](../scripts/image_relay.py) — QoS-aware relay
- `scripts/uav-*.service` — systemd unit templates
- `test/test_hardware.py` — pre-flight assertions
