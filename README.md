# UAV Neo ROS2 Driver

**Version: v1.3.1**

A ROS2 (Jazzy) driver package for **UAV Neo**, an educational autonomous drone kit built on a Raspberry Pi 5 mission computer running Ubuntu 24.04 (Noble).

## Repository contents

- **Sensor stack**: RealSense D435i (depth + color + IMU), Arducam B0578 (downward global shutter), Coral EdgeTPU (object detection at ~26 ms/frame).
- **Flight controller link**: MAVROS over UART to a Pixhawk running PX4.
- **Two-pilot architecture**: RC safety pilot for emergency override (hardware-level via OFFBOARD switch); Xbox autonomy operator drives the mux node which arbitrates manual/auto velocity commands and enforces speed limits.
- **Image-topic relays**: a small QoS-matched [`image_relay.py`](scripts/image_relay.py) that fixes the silent `topic_tools/relay` BEST_EFFORT/RELIABLE mismatch for camera streams.
- **Standalone `mux.launch.py`**: used by the watchdog to restart the mux without re-spawning the entire teleop stack.
- **Watchdog**: five-second-poll process supervisor with topic+process liveness checks (the topic-only check gives false positives whenever any relay subscribes), per-node restart cooldown, FastRTPS shared-memory orphan cleanup, and Pi 5 PMIC under-voltage detection (`/sys/class/hwmon/hwmon5/in0_lcrit_alarm`).
- **Four systemd services**: `uav-teleop` (launches the full stack with EdgeTPU on by default), `uav-watchdog`, `uav-dashboard` (`:8080`), `uav-jupyter` (`:8888`). All start at boot.
- **Networking**: eth0 carries a static `192.168.52.200/24` (laptop tether) **and** a DHCP address (router) simultaneously; wlan0 runs as an isolated AP `uav-neo-0` (10.42.0.1/24, FORWARD blocked so clients reach the Pi's services but not the internet).
- **Setup automation**: `setup_all.sh` runs six phases (ROS2 -> Pixhawk/MAVROS -> RealSense -> Arducam + gscam patch + Coral -> services -> networking) idempotently.

## Release notes

### v1.3.1 (2026-07-05)

- Fixed the Pixhawk MAVLink link on Pi 5. A firmware/DTB update disabled the RP1 `serial0` node, so `/dev/ttyAMA0` disappeared and MAVROS looped on `serial:open: No such file or directory`. `setup_pixhawk.sh` now pins UART0 to GPIOs 14/15 with `dtoverlay=uart0-pi5`, restoring `/dev/ttyAMA0` (reboot required). On Pi 5 the GPIO-header UART is not guaranteed by `enable_uart=1` alone; this overlay makes it durable across firmware updates.
- Watchdog no longer restart-loops a healthy MAVROS: `mavros` liveness is now process-authoritative, so a transient `ros2 topic list` miss of `/mavros/state` no longer cycles a connected node.
- Corrected the `drone status` device-map note: the flight-controller UART is `/dev/ttyAMA0` (GPIOs 14/15, pinned by `dtoverlay=uart0-pi5`); `/dev/ttyAMA10` is the debug-connector PL011 (dead pins), not the FCU link.

### v1.3.0 (2026-07-05)

- Added the `drone` developer helper (`scripts/drone-tool.sh`), inherited from racecar-tool: a sourced `drone <subcommand>` shell function with tab completion for build/test/launch/service/library management and hardware checks. See [drone-tool](#drone-tool).
- New drone-only subcommands: `controller` (confirm the pad is in XInput mode and reinstall the `hid_nintendo` blacklist if it came up as the Switch spoof), `camera` (RealSense + Arducam hardware tests plus a pointer to confirm the 180 flip), and `mavros` (MAVROS link + PX4 state).
- `selftest` runs the hardware suite; `udev` reinstalls the camera + Coral rules and the controller blacklist; `library` manages `drone_student.pth` for the student library import path. `setup_services.sh` sources the tool from `~/.bashrc` so `drone` is available after setup.
- Not carried over from racecar-tool: the dot matrix commands, the Teensy/pit driver, and motor/ESC/lidar/ackermann controls.

### v1.2.0 (2026-07-05)

- Added a `gamepad_node` that normalizes the Xbox controller (`/joy`) into `/gamepad/cmd_vel`, so the drone can be flown manually (LB held) with no student-library code. The mux now consumes that topic for manual mode and keeps the LB/RB gating and speed limits.
- RealSense color and depth are rotated 180 degrees in the relay to correct the upside-down camera mount (toggle with `realsense_flip`); the downward Arducam is unaffected.
- Repo-wide syntax pass: all prose and code is ASCII (no em-dashes), README headings are noun-phrase and sentence case, and the table of contents anchors are verified.
- Lint: `ament_flake8`, `ament_pep257`, and `ament_copyright` tests pass. Added GPLv3 license headers, a `LICENSE` file, and `CONTRIBUTING.md`; set the package license to `GPL-3.0-or-later`.

### v1.1.0 (2026-07-05)

- Xbox controller button/axis to `/joy` index mapping moved into a single config
  file, `config/xbox_mapping.yaml`, read by both the mux node and the student
  library. Re-mapping a different controller is now a YAML edit, no code change.
- Standardized the kit's ESM-9110 pad on **XInput mode** (8 axes / 11 buttons,
  standard xpad layout). The pad is multi-mode and also enumerates as a Nintendo
  Switch Pro Controller (6 axes / 14 buttons) with off-center sticks and
  non-standard triggers; XInput mode rests sticks at 0 and triggers at +1, so the
  flight math and the student trigger/stick conversions are correct without extra
  calibration. The mapping records the expected report shape (`report:` block);
  the mux and student library now **reject a wrong-mode controller** (report-shape
  mismatch) with a one-time warning instead of mis-reading it or crashing.
- Added `scripts/setup_controller.sh` plus
  `scripts/modprobe.d/blacklist-hid-nintendo.conf` to blacklist `hid_nintendo`.
  On Pi 5 / kernel 6.x that driver otherwise claims the pad's Switch-Pro-spoof
  USB id (`057e:2009`) at boot and forces the wrong 6-axis mode; blacklisted, the
  pad falls back to `xpad` and comes up in XInput on every boot.

### v1.0.0 - initial release

- Full sensor + flight stack working with two-pilot operation
- EdgeTPU inference auto-starts at boot
- Watchdog detects node death even when relays keep topics in the DDS graph
- `mux.launch.py` prevents cascade-restart from a mux blip
- `launch_teleop.sh` cleans 0-byte FastRTPS SHM segments on each (re)start
- gscam patched for the appsink memory leak; build is shadowed in colcon overlay
- USB autosuspend disabled by udev rule for both cameras
- eth0 dual-IP + isolated wlan0 AP automated by `setup_networking.sh`

## Table of contents

- [Repository contents](#repository-contents)
- [Release notes](#release-notes)
- [Overview](#overview)
- [Hardware](#hardware)
- [Two-pilot operation](#two-pilot-operation)
- [Safety architecture](#safety-architecture)
- [Topic architecture](#topic-architecture)
- [Quick start (automated setup)](#quick-start-automated-setup)
- [Manual setup](#manual-setup)
  - [ROS2 Jazzy installation](#ros2-jazzy-installation)
  - [Pixhawk UART setup](#pixhawk-uart-setup)
  - [Serial console and SysRq deactivation (critical)](#serial-console-and-sysrq-deactivation-critical)
  - [Bluetooth-on-UART removal](#bluetooth-on-uart-removal)
  - [Serial port permissions](#serial-port-permissions)
  - [Pixhawk parameter configuration](#pixhawk-parameter-configuration)
  - [MAVROS installation](#mavros-installation)
  - [RealSense camera driver installation](#realsense-camera-driver-installation)
  - [Arducam global shutter camera driver installation](#arducam-global-shutter-camera-driver-installation)
  - [Coral EdgeTPU dependencies](#coral-edgetpu-dependencies)
- [Peripheral verification](#peripheral-verification)
- [Package build](#package-build)
- [Tests](#tests)
- [drone-tool](#drone-tool)
- [Launch commands](#launch-commands)
  - [MAVROS](#mavros)
  - [RealSense D435i](#realsense-d435i)
  - [Arducam B0578](#arducam-b0578)
  - [All sensors (teleop)](#all-sensors-teleop)
  - [Mux node](#mux-node)
  - [Gamepad node](#gamepad-node)
  - [EdgeTPU inference](#edgetpu-inference)
- [Services](#services)
  - [Teleop autostart](#teleop-autostart)
  - [Node watchdog](#node-watchdog)
  - [Web dashboard](#web-dashboard)
  - [JupyterLab](#jupyterlab)
  - [Service management](#service-management)
- [Network configuration](#network-configuration)
  - [eth0 dual-IP (static + DHCP)](#eth0-dual-ip-static--dhcp)
  - [wlan0 isolated access point](#wlan0-isolated-access-point)
  - [Setup](#setup)
- [Logs](#logs)

## Overview

UAV Neo is an educational autonomous drone platform. This ROS2 package provides the driver layer that interfaces with the onboard sensors, AI accelerator, and flight controller. The Raspberry Pi serves as the mission computer, handling perception, planning, and communication with the Pixhawk flight controller over MAVLink.

## Hardware

| Peripheral | Interface | Device Path | Description |
|---|---|---|---|
| Intel RealSense D435i | USB 3.0 | `/dev/video*` | RGBD + IMU camera for depth perception and SLAM |
| Arducam B0578 2.3MP | USB 2.0 | `/dev/video*` | Downward-facing global shutter camera for optical flow |
| Coral EdgeTPU USB Accelerator | USB 3.0 | N/A (via `libedgetpu`) | ML inference accelerator for onboard AI |
| Pixhawk 2.8.4 (clone) | UART (TELEM2) | `/dev/ttyAMA0` | Flight controller running PX4 |
| Xbox-compatible controller | USB (wireless dongle) | `/dev/input/js0` | Autonomy operator gamepad for student programs |

## Two-pilot operation

UAV Neo requires **two operators** for safe flight:

| Role | Controller | Responsibility |
|---|---|---|
| **Safety pilot** | RC transmitter (bound to Pixhawk) | Manual flight, takeoff/landing, emergency override. Has physical override via flight mode switch. |
| **Autonomy operator** | Xbox controller (connected to Pi) | Runs student programs, triggers autonomous behaviors via the student library API. |

**Safety pilot RC switch assignments:**

| Switch | Channel | Function |
|---|---|---|
| Switch A | CH5 | Arm / Disarm |
| Switch B | CH6 | Flight mode: Manual / Altitude / Stabilized |
| Switch C | CH7 | Loiter (position hold) |
| Switch D | CH8 | OFFBOARD (enables Pi control) |

**PX4 mode priority** (highest first): OFFBOARD > Loiter > Flight mode switch. Flipping Switch D off immediately returns control to the safety pilot regardless of what the Pi is doing.

**Autonomy operator Xbox controls:**

| Input | Function |
|---|---|
| **LB held** | Manual mode - Xbox sticks control the drone through the mux |
| **RB held** | Auto mode - student code controls the drone through the mux |
| **Neither bumper** | Idle - zero velocity (hover) |
| **Both bumpers** | Idle - zero velocity (hover) |
| START | Enter student program mode |
| BACK | Return to default mode |
| START + BACK | Exit program |

The Xbox controller has **no direct connection** to the flight controller. All commands pass through the mux node, which enforces speed limits from `config/mux.yaml`.

## Safety architecture

The system has multiple layers of safety to prevent uncontrolled flight:

**1. Mux node (`mux_node`)**: Arbitrates all velocity commands. Student code cannot send flight commands directly to MAVROS. The mux enforces:
- Speed limits (`max_speed` and `max_yaw_rate` from `config/mux.yaml`)
- Bumper gating (commands only pass through when LB or RB is held)
- Xbox controller disconnect detection (500ms timeout -> zero velocity)

**2. PX4 OFFBOARD timeout**: If the Pi stops sending setpoints for more than `COM_OF_LOSS_T` (1.0s), PX4 automatically exits OFFBOARD mode and reverts to the safety pilot's RC mode switch setting.

**3. RC transmitter override**: The safety pilot can switch out of OFFBOARD mode at any time via Switch D. This is a hardware-level override that cannot be blocked by software.

**4. Student code isolation**: The student library cannot:
- Arm or disarm the motors
- Change flight modes (OFFBOARD, STABILIZED, etc.)
- Set the speed limit (enforced by mux config, not student code)
- Publish directly to MAVROS velocity topics (all commands go through `/mux/cmd_vel`)

**5. Exception handling**: If student code crashes, the library catches the exception, logs it, and sends a stop command (zero velocity). The run loop continues operating.

**Required PX4 parameters** (set via QGroundControl):

| Parameter | Value | Purpose |
|---|---|---|
| `COM_OF_LOSS_T` | `1.0` | Seconds without setpoints before OFFBOARD failsafe |
| `COM_RCL_EXCEPT` | `4` | Allow OFFBOARD even if RC link drops |
| `RC_MAP_OFFB_SW` | `8` | Channel 8 (Switch D) controls OFFBOARD mode |

## Topic architecture

The driver publishes sensor data on standard ROS2 topic names. The teleop launch file creates topic relays that map these to simplified names used by the student library:

**Sensor topics (relay mapping):**

| Driver publishes | Relay name | Description |
|---|---|---|
| `/camera/color/image_raw` | `/camera/forward` | RealSense forward color image |
| `/camera/depth/image_rect_raw` | `/camera/depth` | RealSense depth image (16UC1, mm) |
| `/arducam/camera/image_raw` | `/camera/nadir` | Arducam downward-facing image |
| `/mavros/global_position/global` | `/nav` | GPS position (NavSatFix) |
| `/mavros/local_position/velocity_body` | `/velocity` | Body-frame velocity (TwistStamped) |

**Flight command flow:**

```
Student code            Xbox controller
     │                        │
 send_pcmd()              joy_node
     │                        │
     │                      /joy ───────────┐ (buttons: LB/RB gating)
     │                        │             │
     │                   gamepad_node       │
     │                        │             │
 /mux/cmd_vel        /gamepad/cmd_vel       │
     │                        │             │
     └──────────┬─────────────┴─────────────┘
                │
           mux_node (LB/RB gating + speed limit)
                │
  /mavros/setpoint_velocity/cmd_vel
                │
           MAVROS → MAVLink → Pixhawk
```

**Other topics:**

| Topic | Type | Description |
|---|---|---|
| `/mavros/imu/data` | `sensor_msgs/Imu` | Pixhawk EKF-fused IMU (used by student library) |
| `/mavros/state` | `mavros_msgs/State` | Flight mode, armed status, connection state |
| `/mavros/extended_state` | `mavros_msgs/ExtendedState` | Landed state (on ground, in air, etc.) |
| `/mavros/rc/in` | `mavros_msgs/RCIn` | Raw RC transmitter channels (for diagnostics) |
| `/edgetpu/inference` | `vision_msgs/Detection2DArray` | EdgeTPU object detection results |
| `/diagnostics` | `diagnostic_msgs/DiagnosticArray` | System health from all nodes |

## Quick start (automated setup)

Setup scripts are provided in `scripts/` that automate the entire installation. Run the all-in-one script:

```bash
cd ~/ros2_ws/src/uav_neo_ros2_driver
chmod +x scripts/setup_all.sh
./scripts/setup_all.sh
```

This runs five phases in series (Phase 4 has sub-phases):

| Phase | Script | What it does |
|---|---|---|
| 1 | `scripts/install_ros2_jazzy.sh` | Install ROS2 Jazzy (skipped if already installed) |
| 2 | `scripts/setup_pixhawk.sh` | Disable serial console/SysRq/Bluetooth, install MAVROS |
| 3 | `scripts/setup_realsense.sh` | Install RealSense driver + Pi 5 IMU permission fix |
| 4 | `scripts/setup_arducam.sh` | Install GStreamer + gscam driver |
| 4b | `scripts/patch_gscam.sh` | Patch gscam appsink memory leak (clone, fix, build) |
| 4c | `scripts/setup_coral.sh` | Install Coral EdgeTPU runtime, pycoral, tflite, udev rule |
| 5 | `scripts/setup_services.sh` | Install systemd services, JupyterLab, create log dirs |

> **Reboot required:** Phase 2 modifies UART and Bluetooth kernel settings that require a reboot. The script will detect this and prompt you. After rebooting, re-run `./scripts/setup_all.sh` - already-completed phases are skipped automatically.

After setup completes, the script builds the workspace. You can then verify everything works:

```bash
colcon test --packages-select uav_neo_ros2_driver --pytest-args -k hardware -v
```

The individual scripts can also be run standalone (e.g., `./scripts/setup_realsense.sh`) if you only need to set up one component.

> **Note:** Pixhawk parameters (MAV_1_CONFIG, SER_TEL2_BAUD, etc.) must still be configured manually via QGroundControl. See [Pixhawk Parameter Configuration](#pixhawk-parameter-configuration) below.

### After boot

All services start automatically on boot. Use these commands to manage them:

**Check status:**

```bash
systemctl status uav-teleop uav-watchdog uav-dashboard uav-jupyter
```

**Restart the teleop stack** (e.g., after changing a config file or updating code):

```bash
sudo systemctl restart uav-teleop
```

**EdgeTPU inference is enabled by default** in the systemd boot path (`launch_teleop.sh` passes `edgetpu_enable:=true`). To disable for a session, override on the command line:

```bash
sudo systemctl stop uav-teleop
~/ros2_ws/src/uav_neo_ros2_driver/scripts/launch_teleop.sh edgetpu_enable:=false
```

**Restart individual services:**

```bash
sudo systemctl restart uav-watchdog    # node health monitor
sudo systemctl restart uav-dashboard   # web dashboard on :8080
sudo systemctl restart uav-jupyter     # JupyterLab on :8888
```

**Stop everything:**

```bash
sudo systemctl stop uav-teleop uav-watchdog uav-dashboard uav-jupyter
```

**View live logs:**

```bash
journalctl -u uav-teleop -f          # teleop output
journalctl -u uav-watchdog -f        # watchdog events
tail -f ~/logs/latest/teleop.log     # same output, plain text
```

> **Tip:** After rebuilding the workspace (`colcon build`), restart the teleop service to pick up the new code. The watchdog will automatically restart any nodes that crash.

## Manual setup

The sections below document each setup step in detail. If you used the automated setup scripts above, these are already done - use this as a reference.

### ROS2 Jazzy installation

An install script is provided in `scripts/`. Run:

```bash
chmod +x scripts/install_ros2_jazzy.sh
./scripts/install_ros2_jazzy.sh
```

This script handles locale setup, adding the ROS2 apt repository, installing `ros-jazzy-ros-base` and `ros-dev-tools`, and sourcing ROS2 in your `~/.bashrc`.

Once complete, open a new terminal or run:

```bash
source ~/.bashrc
```

### Pixhawk UART setup

The Pixhawk connects to the Raspberry Pi via UART on GPIO 14 (TX) / GPIO 15 (RX) through the TELEM2 port.

1. Enable the serial port using `raspi-config`:

```bash
sudo raspi-config
# Navigate to: Interface Options -> Serial Port
# - Login shell over serial: No
# - Serial port hardware enabled: Yes
```

2. Reboot for changes to take effect:

```bash
sudo reboot
```

After reboot, `/dev/ttyAMA0` should be available.

### Serial console and SysRq deactivation (critical)

> **WARNING:** Do **not** connect the Pixhawk UART before completing **all** steps in this section and the next (Disable Bluetooth on UART). Ubuntu defaults to using the UART as a kernel boot console, login shell, and SysRq input. MAVLink data from the Pixhawk will be interpreted as system commands, causing two failure modes:
>
> 1. **Boot loop**: MAVLink data is interpreted as console/login input, preventing the Pi from booting. Can only be resolved by physically disconnecting the Pixhawk.
> 2. **System crash**: MAVLink byte sequences are interpreted as kernel SysRq commands (e.g., emergency remount read-only, sync, reboot), causing the filesystem to go read-only and the system to lock up.

1. Remove the serial console from the kernel command line:

```bash
sudo sed -i 's/ console=serial0,115200//' /boot/firmware/cmdline.txt
```

2. Disable the login shell on the serial port:

```bash
sudo systemctl stop serial-getty@ttyAMA0.service
sudo systemctl disable serial-getty@ttyAMA0.service
```

3. Disable the kernel SysRq handler so serial data cannot trigger kernel commands:

```bash
echo "kernel.sysrq = 0" | sudo tee /etc/sysctl.d/99-disable-sysrq.conf
sudo sysctl -p /etc/sysctl.d/99-disable-sysrq.conf
```

4. Reboot:

```bash
sudo reboot
```

5. Verify the changes after reboot:

```bash
# Should NOT contain "console=serial0"
cat /boot/firmware/cmdline.txt

# Should show "disabled"
sudo systemctl is-enabled serial-getty@ttyAMA0.service

# Should show "0"
cat /proc/sys/kernel/sysrq
```

### Bluetooth-on-UART removal

By default, the Pi's Bluetooth controller uses the PL011 UART (`/dev/ttyAMA0`) - the same port needed for the Pixhawk. Bluetooth must be moved off this UART to avoid conflicts.

1. Add the `disable-bt` overlay to `/boot/firmware/config.txt`:

```bash
echo -e "\n# Free PL011 UART for Pixhawk MAVLink\ndtoverlay=disable-bt" | sudo tee -a /boot/firmware/config.txt
```

2. Disable the Bluetooth service:

```bash
sudo systemctl disable bluetooth.service
```

3. Reboot:

```bash
sudo reboot
```

It is now safe to connect the Pixhawk UART to the Pi.

### Serial port permissions

Add your user to the `dialout` group to access the serial port without `sudo`:

```bash
sudo usermod -aG dialout $USER
```

Log out and back in (or reboot) for the group change to take effect.

### Pixhawk parameter configuration

The Pixhawk must be configured to output MAVLink on TELEM2. Connect to the Pixhawk using **QGroundControl** and set the following parameters:

| Parameter | Value | Description |
|---|---|---|
| `MAV_1_CONFIG` | `TELEM2` | Enable MAVLink on TELEM2 |
| `SER_TEL2_BAUD` | `921600` | UART baud rate |
| `MAV_1_RATE` | `0` (auto) or desired rate | MAVLink message rate (0 = auto) |
| `MAV_1_MODE` | `Onboard` | Companion computer mode (lower latency, includes position/attitude streams) |

After setting parameters, reboot the Pixhawk for changes to take effect.

**Wiring (TELEM2 to Raspberry Pi GPIO):**

| TELEM2 Pin | Pi GPIO | Description |
|---|---|---|
| TX | GPIO 15 (RXD) | Pixhawk transmit to Pi receive |
| RX | GPIO 14 (TXD) | Pi transmit to Pixhawk receive |
| GND | GND | Common ground |

> **Note:** TX and RX must be **crossed** (TX to RX, RX to TX). Do not connect the TELEM2 5V pin to the Pi.

### MAVROS installation

MAVROS provides a standard ROS2 interface to the Pixhawk over MAVLink, publishing sensor data as ROS2 topics and exposing services for arming, mode switching, and sending commands.

1. Install MAVROS and its dependencies:

```bash
sudo apt install -y ros-jazzy-mavros ros-jazzy-mavros-extras ros-jazzy-mavros-msgs ros-jazzy-joy ros-jazzy-topic-tools
```

2. Install the GeographicLib datasets (required for coordinate transforms):

```bash
sudo /opt/ros/jazzy/lib/mavros/install_geographiclib_datasets.sh
```

3. Verify MAVROS can connect to the Pixhawk:

```bash
source /opt/ros/jazzy/setup.bash
ros2 launch mavros px4.launch fcu_url:=/dev/ttyAMA0:921600
```

You should see `CON: Got HEARTBEAT, connected. FCU: PX4 Autopilot` in the output.

4. In a second terminal, verify topics are publishing:

```bash
ros2 topic echo /mavros/state --once
ros2 topic echo /mavros/imu/data --once
ros2 topic echo /mavros/rc/in --once
```

### RealSense camera driver installation

The Intel RealSense D435i provides depth, color, infrared, and IMU data over USB 3.0. The `realsense2_camera` ROS2 package publishes all streams as standard ROS2 topics.

1. Install the RealSense ROS2 packages:

```bash
sudo apt install -y ros-jazzy-realsense2-camera ros-jazzy-realsense2-camera-msgs ros-jazzy-realsense2-description
```

2. Verify the camera is detected:

```bash
rs-enumerate-devices --compact
```

You should see `Intel RealSense D435I` with a serial number and firmware version.

3. Fix IMU permissions (required on Raspberry Pi 5):

The D435i IMU uses HID-sensor IIO devices that default to root-only on the Pi 5. Install the permission fix script and udev rule:

```bash
# Create the fix script
sudo tee /usr/local/bin/fix-realsense-imu.sh > /dev/null << 'EOF'
#!/bin/bash
for dev in /sys/bus/iio/devices/iio:device*; do
    [ -d "$dev" ] || continue
    chmod 666 "$dev"/scan_elements/in_*_en 2>/dev/null
    chmod 666 "$dev"/buffer/enable 2>/dev/null
    chmod 666 "$dev"/buffer/length 2>/dev/null
    chmod 666 "$dev"/trigger/current_trigger 2>/dev/null
    chmod 666 "$dev"/in_*_sampling_frequency 2>/dev/null
    chmod 666 "$dev"/in_*_hysteresis 2>/dev/null
    [ -e /dev/"$(basename "$dev")" ] && chmod 666 /dev/"$(basename "$dev")"
done
EOF
sudo chmod +x /usr/local/bin/fix-realsense-imu.sh

# Create udev rule to fix permissions on device plug
echo 'SUBSYSTEM=="iio", KERNEL=="iio:device*", ACTION=="add", RUN+="/usr/local/bin/fix-realsense-imu.sh"' | sudo tee /etc/udev/rules.d/99-realsense-imu.rules
sudo udevadm control --reload-rules
```

4. Quick test (standalone, without the custom launch file):

```bash
source /opt/ros/jazzy/setup.bash
sudo /usr/local/bin/fix-realsense-imu.sh
ros2 launch realsense2_camera rs_launch.py camera_namespace:=/ camera_name:=camera enable_gyro:=true enable_accel:=true
```

5. In a second terminal, verify topics are publishing:

```bash
ros2 topic echo /camera/color/image_raw --once
ros2 topic echo /camera/depth/image_rect_raw --once
ros2 topic echo /camera/imu --once
```

### Arducam global shutter camera driver installation

The Arducam B0578 is a 2.3MP global shutter camera connected over USB 2.0. It outputs MJPEG which is decoded via GStreamer. The `gscam` ROS2 package bridges GStreamer pipelines to standard ROS2 image topics.

1. Install GStreamer (usually pre-installed on Ubuntu 24.04) and the gscam ROS2 package:

```bash
sudo apt install -y gstreamer1.0-tools gstreamer1.0-plugins-good ros-jazzy-gscam
```

2. **Patch gscam** to fix the appsink memory leak ([ros-drivers/gscam#63](https://github.com/ros-drivers/gscam/issues/63)):

```bash
./scripts/patch_gscam.sh
```

This clones the gscam source, applies a two-line fix that limits the appsink internal buffer (`max-buffers=1, drop=true`), and builds it as a colcon overlay. Without this patch, gscam leaks memory under CPU load and will be OOM-killed within minutes. See [docs/topic_bandwidth.md](docs/topic_bandwidth.md) for bandwidth and resource details.

> **Note:** The apt-installed `ros-jazzy-gscam` package remains installed but is shadowed by the overlay build. If you ever reinstall gscam from apt, re-run `patch_gscam.sh`.

3. Verify the camera is detected:

```bash
v4l2-ctl --list-devices
# Should show: Arducam-B0578-2.3MP-GS: Arducam (usb-xhci-hcd.1-2)
```

4. Quick test (standalone):

```bash
source ~/ros2_ws/install/setup.bash
ros2 run gscam gscam_node --ros-args \
  -p gscam_config:="v4l2src device=/dev/video0 ! image/jpeg,width=640,height=480,framerate=30/1 ! jpegdec ! videoconvert ! queue max-size-buffers=2 leaky=downstream" \
  -p camera_name:=arducam \
  -r __ns:=/arducam
```

5. In a second terminal, verify topics are publishing:

```bash
ros2 topic echo /arducam/camera/image_raw --once
```

### Coral EdgeTPU dependencies

The Coral EdgeTPU USB Accelerator is used for onboard ML inference. Pre-built packages for Ubuntu 24.04 (aarch64) are included in `depend/`.

> **Note:** The Coral USB device changes its USB ID after the runtime initializes it. It appears as `1a6e:089a` (Global Unichip) when first plugged in, then switches to `18d1:9302` (Google) after the EdgeTPU firmware is loaded. The udev rule covers both IDs.

1. Run the setup script:

```bash
chmod +x scripts/setup_coral.sh
./scripts/setup_coral.sh
```

This installs:
- `libedgetpu1-std` - EdgeTPU runtime library (`.deb`)
- `tflite_runtime` - TensorFlow Lite interpreter (`.whl`)
- `pycoral` - High-level Python API for EdgeTPU (`.whl`)
- Udev rule at `/etc/udev/rules.d/99-coral-edgetpu.rules` for non-root USB access

2. Verify the TPU is detected:

```bash
python3 -c "from pycoral.utils.edgetpu import list_edge_tpus; print(list_edge_tpus())"
```

You should see `[{'type': 'usb', 'path': '/sys/bus/usb/devices/...'}]`.

## Peripheral verification

Run the following commands to confirm all peripherals are visible to the Pi:

**USB devices (RealSense, Arducam, Coral):**

```bash
lsusb
```

Expected output should include:

| Device | USB ID |
|---|---|
| Intel RealSense D435i | `8086:0b3a` |
| Arducam B0578 | `0c45:0578` |
| Coral EdgeTPU | `1a6e:089a` (pre-init) or `18d1:9302` (post-init, after firmware load) |

**Pixhawk UART:**

```bash
ls -la /dev/ttyAMA0
```

Should show the device owned by the `dialout` group.

**Camera video devices:**

```bash
v4l2-ctl --list-devices
```

**Coral EdgeTPU:**

```bash
python3 -c "from pycoral.utils.edgetpu import list_edge_tpus; print(list_edge_tpus())"
```

Should show `[{'type': 'usb', 'path': '/sys/bus/usb/devices/...'}]`.

## Package build

```bash
source /opt/ros/jazzy/setup.bash
cd ~/ros2_ws
colcon build --packages-select uav_neo_ros2_driver
source install/setup.bash
```

## Tests

Hardware connectivity tests verify that all sensors are plugged in, detected, and accessible before launching any ROS2 nodes.

### Hardware test run

```bash
colcon test --packages-select uav_neo_ros2_driver --pytest-args -k hardware -v
```

### Test coverage

| Test Class | Tests | What it verifies |
|---|---|---|
| `TestPixhawk` | 6 | UART device exists, read/write permissions, dialout group, serial console disabled, SysRq disabled, Bluetooth overlay active |
| `TestRealSense` | 5 | USB device on bus, V4L2 devices registered, rs-enumerate finds D435i, USB 3.x connection, IMU IIO permissions |
| `TestArducam` | 4 | USB device on bus, V4L2 device listed, device node accessible, MJPEG format available |
| `TestCoralTPU` | 8 | USB device on bus (pre/post-init IDs), libedgetpu installed, tflite_runtime importable, pycoral importable, EdgeTPU runtime detects TPU, classification inference <100 ms, detection inference <50 ms, udev rule exists |
| `TestDependencies` | 5 | ROS2 packages installed (mavros, realsense2_camera, gscam - 3 parametrized cases), GeographicLib datasets, IMU fix script |

Each test assertion includes a human-readable error message with the exact command to fix the issue.

### Full test run (including linters)

```bash
colcon test --packages-select uav_neo_ros2_driver
colcon test-result --verbose
```

## drone-tool

`scripts/drone-tool.sh` defines a `drone <subcommand>` shell function (inherited from racecar-tool) that wraps the common build, launch, service, and hardware-check commands. It is sourced, not executed, so `drone cd`, `drone source`, and `drone build` mutate the current shell. `setup_services.sh` adds the source line to `~/.bashrc`; to enable it by hand:

```bash
source ~/ros2_ws/src/uav_neo_ros2_driver/scripts/drone-tool.sh
```

Tab completion covers subcommands, launch-file names, service actions, setup phases, and `library` flags.

| Command | Action |
|---|---|
| `drone build` | `colcon build --packages-select uav_neo_ros2_driver --symlink-install` and source the overlay. |
| `drone test` | Run the package test suite with verbose results. |
| `drone source` / `drone cd` | Source the overlay / cd to the package root in the current shell. |
| `drone teleop` | Launch the full stack via `launch_teleop.sh` (timestamped logs + SHM sweep). |
| `drone launch <name>` | `ros2 launch uav_neo_ros2_driver <name>.launch.py` (completes `arducam`, `edgetpu`, `mavros`, `mux`, `realsense`, `teleop`). |
| `drone watchdog` | Run the node watchdog in the foreground. |
| `drone udev` | Reinstall the camera + Coral udev rules and the `hid_nintendo` blacklist. |
| `drone controller` | Confirm the Xbox pad is in XInput mode (`2f24:00b7`, `js0`, 11/8); reinstall the blacklist if it came up as the Switch spoof (`057e:2009`). |
| `drone camera` | Run the RealSense + Arducam hardware tests and point to the live 180-flip check. |
| `drone mavros` | Show the MAVROS link + PX4 mode/arming state from `/mavros/state`. |
| `drone selftest` | Run the full hardware suite (Pixhawk / RealSense / Arducam / Coral + deps). |
| `drone setup <phase>` | Run a setup script: `all`, `pixhawk`, `realsense`, `arducam`, `coral`, `services`, `networking`, `controller`. |
| `drone service <action> [unit]` | systemd control for `uav-teleop`/`uav-watchdog`/`uav-dashboard`/`uav-jupyter`. |
| `drone library <action>` | Manage `drone_student.pth`: `--select <folder>`, `--list`, `--reset`, `--status`. |
| `drone cleanup` | List orphaned drone processes + FastRTPS SHM segments (dry-run; `--force` to remove). |
| `drone status` | USB peripherals, device nodes, and running ros2 nodes. |
| `drone help` | Command reference. |

## Launch commands

### MAVROS

A custom launch file is provided that starts MAVROS with the correct UART settings for the Pixhawk:

```bash
ros2 launch uav_neo_ros2_driver mavros.launch.py
```

To also bridge to QGroundControl over UDP:

```bash
ros2 launch uav_neo_ros2_driver mavros.launch.py gcs_url:=udp://:14550@
```

For the full list of available MAVROS topics, subscribers, and services, see [docs/mavros_topics.md](docs/mavros_topics.md).

### RealSense D435i

Launch the RealSense D435i with the UAV Neo configuration (640x480 @ 15 FPS, depth + color + IMU, depth filters enabled):

```bash
ros2 launch uav_neo_ros2_driver realsense.launch.py
```

To enable point cloud generation (CPU intensive):

```bash
ros2 launch uav_neo_ros2_driver realsense.launch.py pointcloud_enable:=true
```

For the full list of available RealSense topics, see [docs/realsense_topics.md](docs/realsense_topics.md).

### Arducam B0578

Launch the Arducam B0578 downward-facing global shutter camera (640x480 @ 30 FPS MJPEG, capped to 20 FPS output via GStreamer `videorate`):

```bash
ros2 launch uav_neo_ros2_driver arducam.launch.py
```

To use higher resolution (lower effective publish rate due to Pi 5 CPU limits):

```bash
ros2 launch uav_neo_ros2_driver arducam.launch.py image_width:=1280 image_height:=720
```

> **Note:** Requires the patched gscam build (`scripts/patch_gscam.sh`). The stock apt package will leak memory.

### All sensors (teleop)

Launch the full stack - MAVROS, RealSense, Arducam, joy node, mux (via `mux.launch.py`), topic relays, and (by default in the systemd boot path) EdgeTPU inference:

```bash
ros2 launch uav_neo_ros2_driver teleop.launch.py
```

The systemd service (`scripts/launch_teleop.sh`) passes `edgetpu_enable:=true` automatically. The launch file's own default is `false`, so calling `ros2 launch` directly leaves EdgeTPU off unless you opt in:

```bash
ros2 launch uav_neo_ros2_driver teleop.launch.py edgetpu_enable:=true
```

The launch also uses `image_relay.py` (a QoS-matched relay) for the three image topics rather than `topic_tools/relay`. The latter defaults to RELIABLE QoS, which silently drops from BEST_EFFORT image publishers like RealSense and gscam - see [`scripts/image_relay.py`](scripts/image_relay.py). The RealSense is mounted upside down, so its color (`/camera/forward`) and depth (`/camera/depth`) relays rotate the image 180 degrees; disable with `realsense_flip:=false`. The downward Arducam (`/camera/nadir`) is never rotated. The rotation flips pixels only; the camera intrinsics (`camera_info`) are not adjusted, so pixel-space use is correct but precise 3D deprojection would need the principal point mirrored.

**Available launch arguments:**

| Argument | Default | Description |
|---|---|---|
| `fcu_url` | `/dev/ttyAMA0:921600` | Pixhawk UART connection |
| `gcs_url` | (empty) | QGroundControl UDP bridge |
| `pointcloud_enable` | `false` | Enable point cloud (CPU intensive) |
| `depth_profile` | `640x480x15` | Depth stream resolution and FPS |
| `color_profile` | `640x480x15` | Color stream resolution and FPS |
| `realsense_flip` | `true` | Rotate RealSense color and depth 180 deg (camera mounted upside down) |
| `arducam_width` | `640` | Arducam image width |
| `arducam_height` | `480` | Arducam image height |
| `arducam_framerate` | `30` | Arducam framerate |
| `edgetpu_enable` | `false` (`true` via `launch_teleop.sh`) | Enable Coral EdgeTPU inference node |
| `edgetpu_config` | `config/edgetpu.yaml` | EdgeTPU configuration file |
| `mux_config` | `config/mux.yaml` | Mux node configuration file (consumed by `mux.launch.py`) |
| `joy_device` | `/dev/input/js0` | Xbox controller device path |

### Mux node

The mux node arbitrates between the manual gamepad command and the autonomous (student code) command. It is included automatically in the teleop launch. Both sources send a normalized `[-1, 1]` `TwistStamped`; the mux scales by `max_speed`/`max_yaw_rate` and forwards to MAVROS.

**Behavior:**
- **LB held**: manual mode: the gamepad node's command (`/gamepad/cmd_vel`) is scaled and forwarded
- **RB held**: auto mode: student code commands (from `/mux/cmd_vel`) are scaled and forwarded
- **Neither bumper**: idle: zero velocity published (drone hovers)
- **Controller disconnected**: if no `/joy` message for 500ms, zero velocity published
- **Stale source**: a manual or auto command older than 500ms holds zero (e.g. a dead gamepad node)

### Gamepad node

The gamepad node (`gamepad_node`) reads the Xbox controller (`/joy`), normalizes the sticks to `[-1, 1]` (deadzone from `config/gamepad.yaml`), and publishes `/gamepad/cmd_vel` for the mux. This lets a pilot fly manually (LB held) without running any student-library code. It reads the stick axis indices from `config/xbox_mapping.yaml` and ignores frames from a wrong-mode controller. The mux owns the LB/RB gating and the speed limits; the gamepad node only normalizes.

**Stick mapping (Mode 2):**

| Stick | Function |
|---|---|
| Left stick Y | Throttle (up/down) |
| Left stick X | Yaw (rotation) |
| Right stick Y | Pitch (forward/back) |
| Right stick X | Roll (left/right) |

**Controller index mapping** (`config/xbox_mapping.yaml`):

The button/axis to `/joy` array index mapping lives in one shared file read by
both the mux node and the student library, so a different controller can be
re-mapped without touching code. The kit standardizes on the ESM-9110 in
**XInput mode** (standard xpad layout, `8 axes / 11 buttons`):

| Control | `/joy` index | | Control | `/joy` index |
|---|---|---|---|---|
| A / B buttons | buttons 0 / 1 | | Back / Start | buttons 6 / 7 |
| X / Y buttons | buttons 2 / 3 | | LB / RB | buttons 4 / 5 |
| Left / right stick click | buttons 9 / 10 | | Guide | button 8 |
| Left stick X / Y | axes 0 / 1 | | Left / right trigger (analog) | axes 2 / 5 |
| Right stick X / Y | axes 3 / 4 | | D-pad X / Y | axes 6 / 7 |

The `report:` block (`11` buttons / `8` axes) records the expected shape; a
controller in a different mode is rejected rather than mis-read. To re-map, run
`ros2 topic echo /joy`, press each control to read its index, edit
`xbox_mapping.yaml`, then `colcon build` and restart the mux. A missing or
partial file falls back to the built-in defaults (the values above).

**Controller mode:** the ESM-9110 is multi-mode; press and **hold the "MODE"
button** to cycle modes. The mode is sticky (remembered across power cycles), so
set it once per pad. Use **XInput** (top + bottom LEDs lit):

| LED pattern | USB id | Enumerates as | Mode |
|---|---|---|---|
| **top + bottom** | `2f24:00b7` | "Generic X-Box pad" | **XInput (use this)** |
| center two | `0079:181c` | "ESM GAMEPAD" | DirectInput (wrong) |
| top + third | `2f24:00b6` | "ESM Controller" | ESM/other (wrong) |

If the student library or mux logs a "wrong controller mode" warning, the pad is
in one of the wrong modes; hold **MODE** until the **top + bottom** LEDs are
lit. Confirm with `lsusb | grep 2f24:00b7` or `ros2 topic echo /joy --once`
(should show 11 buttons / 8 axes).

**Boot-time fix (`hid_nintendo` blacklist):** the ESM-9110 also spoofs the
Nintendo Switch Pro VID:PID `057e:2009`. On Pi 5 / kernel 6.x the `hid_nintendo`
driver claims that spoof at enumeration and presents the wrong 6-axis / 14-button
Switch profile (no `js0`); this is the intermittent "1 LED at boot" symptom.
`scripts/setup_controller.sh` installs
`scripts/modprobe.d/blacklist-hid-nintendo.conf`, which blacklists `hid_nintendo`
so the pad falls back to the `xpad` driver and comes up in XInput mode
automatically on every boot, independent of the pad's remembered MODE state:

```bash
./scripts/setup_controller.sh
# then replug the controller or reboot
```

This is the fix to rely on for classroom use; the MODE button and the software
wrong-mode guard remain as fallbacks. (Tradeoff: a genuine Switch Pro controller
would also be blocked; the kit never uses one.)

**Configuration** (`config/mux.yaml`):

| Parameter | Default | Description |
|---|---|---|
| `max_speed` | `0.5` | Maximum velocity in m/s for all axes |
| `max_yaw_rate` | `0.5` | Maximum yaw rate in rad/s |
| `joystick_dead_zone` | `0.15` | Stick dead zone (fraction, 0.0-1.0) |
| `publish_rate` | `20.0` | Setpoint publish rate in Hz (must be >2 for PX4 OFFBOARD) |

### EdgeTPU inference

When enabled via `edgetpu_enable:=true`, the EdgeTPU node subscribes to `/camera/forward`, runs object detection on the Coral USB Accelerator, and publishes results to `/edgetpu/inference` (`vision_msgs/Detection2DArray`).

**Configuration** (`config/edgetpu.yaml`):

| Parameter | Default | Description |
|---|---|---|
| `model_path` | `models/efficientdet_lite0_generic_edgetpu.tflite` | Path to EdgeTPU-compiled model (relative to package share) |
| `labels_path` | `models/labels.txt` | Class label file |
| `score_threshold` | `0.5` | Minimum detection confidence |
| `max_detections` | `0` | Max detections per frame (0 = unlimited) |
| `image_timeout` | `5.0` | Seconds without input before diagnostic warning |

The default model runs at ~26ms per frame (~38 FPS) on USB 3.0.

## Services

Four systemd services are installed by `scripts/setup_services.sh` (or Phase 5 of `setup_all.sh`). All services start automatically on boot.

### Teleop autostart

The `uav-teleop` service launches the full stack (MAVROS + RealSense + Arducam + joy node + mux node + topic relays) on boot using `scripts/launch_teleop.sh`. This wrapper creates a timestamped log directory under `~/logs/` before launching.

```bash
sudo systemctl start uav-teleop    # start now
sudo systemctl stop uav-teleop     # stop
sudo systemctl restart uav-teleop  # restart (creates new log session)
```

### Node watchdog

The `uav-watchdog` service monitors the sensor nodes and mux node every 5 seconds. When a node disappears:

1. Determines liveness from **two checks**: the topic appears in `ros2 topic list` *and* the node binary is in `ps`. The process check is necessary because `ros2 topic list` includes subscriber-only topics - `image_relay` keeps the camera topics in the graph, and MAVROS keeps `/mavros/setpoint_velocity/cmd_vel`, so the topic check alone gives false positives. Each `NODES` entry supplies a `process_check` callable that pgreps for the binary path (e.g. `/install/gscam/lib/gscam/gscam_node`).
2. Checks if the underlying hardware is still connected (UART for Pixhawk, USB for cameras).
3. If connected: kills any stale matches of the `kill_pattern`, then relaunches the **node-specific** launch file (e.g. `arducam.launch.py` for arducam, `mux.launch.py` for mux). Mux uses a standalone launch file rather than `teleop.launch.py` to prevent a mux restart from cascade-respawning the entire stack.
4. If disconnected: logs a warning and waits for the device to reappear.
5. Enforces a 30-second cooldown between restarts of the same node.

The watchdog starts 15 seconds after teleop to allow all nodes to initialize. Log entries distinguish three failure modes: `topic not advertised`, `process not running`, `topic+process down`.

Two periodic background tasks also run from the watchdog:

- **FastRTPS shared-memory orphan cleanup**: every 60 s, removes 0-byte `/dev/shm/fastrtps_port*` segments and stranded `_el` / `sem.*_mutex` lock files left behind by ros2 processes killed mid-init. Without this, any future `rclpy.create_node()` that hashes to a poisoned port spins forever (the "Jupyter cell hangs at drone init" symptom). `launch_teleop.sh` runs the same cleanup once on each (re)start as defense-in-depth before any rclpy participants start.
- **Pi 5 under-voltage detection**: checks `/sys/class/hwmon/hwmon5/in0_lcrit_alarm` (sticky bit, set by the Pi PMIC on first 5V-rail dip below threshold). Logs `Pi under-voltage alarm armed (...)` at startup and a single `[WARNING] Pi under-voltage alarm tripped - ...` the moment the bit flips. After any flight, `grep under-voltage ~/logs/latest/watchdog.log` will tell you whether the BEC sagged. If it did, expect cascading USB device resets (gscam in particular dies with `Could not get gstreamer sample`); the fix is hardware (5V/5A+ BEC, bulk caps near the Pi, or a separate USB power injector).

### Web dashboard

The `uav-dashboard` service runs a web-based monitoring page on **port 8080**. Open in a browser:

```
http://<pi-ip>:8080
```

The dashboard shows:
- Green/red indicators for each node (MAVROS, RealSense, Arducam)
- Topic publish rates with stale/dead detection
- Recent watchdog restart events

The page auto-refreshes every 3 seconds. No additional dependencies are required - it uses Python's built-in HTTP server.

### JupyterLab

The `uav-jupyter` service runs JupyterLab on **port 8888** for interactive development:

```
http://<pi-ip>:8888
```

JupyterLab opens in the `~/jupyter_ws/` directory by default. ROS2 Python packages (`rclpy`, etc.) are available in notebooks.

**Dependencies:** JupyterLab is installed system-wide by `setup_services.sh`. No authentication is required (educational use on a private network).

To install JupyterLab manually (if not using the setup script):

```bash
pip3 install --break-system-packages jupyterlab nptyping==1.4.4 pandas matplotlib Pillow
mkdir -p ~/jupyter_ws
```

### Service management

**Check status of all services:**

```bash
systemctl status uav-teleop uav-watchdog uav-dashboard uav-jupyter
```

**Disable a service from starting on boot:**

```bash
sudo systemctl disable uav-teleop   # (or any service name)
```

**Re-enable:**

```bash
sudo systemctl enable uav-teleop
```

**View live logs via journald:**

```bash
journalctl -u uav-teleop -f         # teleop output
journalctl -u uav-watchdog -f       # watchdog events
journalctl -u uav-dashboard -f      # dashboard server
journalctl -u uav-jupyter -f        # JupyterLab server
```

## Network configuration

The Pi has two network interfaces, each configured for a specific role.

### eth0 dual-IP (static + DHCP)

eth0 carries both a fixed static address for direct laptop tethering **and** a DHCP-assigned address from any router it's plugged into, simultaneously. Either path reaches every service on the Pi.

| Address | Source | Use case |
|---|---|---|
| `192.168.52.200/24` | static | Laptop direct-connect (no router needed) |
| `10.0.0.x/24` (or whatever DHCP gives) | DHCP from connected router | Internet access for the Pi, easy network connectivity |

The default route comes from DHCP when present, so the Pi has internet access whenever it's on a router. Direct-tether keeps working at `192.168.52.200` regardless. Configuration lives in a single netplan file managed by NetworkManager (`/etc/netplan/90-NM-...yaml`) using `ipv4.method: auto`, `ipv4.addresses: [192.168.52.200/24]`, `optional: true`, and `ipv4.may-fail: true`. **Do not put network setup in launch scripts**: netplan is the source of truth.

> **Subnet caveat:** if your router happens to also be on `192.168.52.0/24`, you'll get an address collision. Pick a different static subnet for the Pi in that case.

### wlan0 isolated access point

wlan0 runs as an isolated Wi-Fi access point so laptops, tablets, and phones can connect directly to the drone for SSH / Jupyter / dashboard access without an external router.

| Setting | Value |
|---|---|
| SSID | `uav-neo-0` |
| PSK | `uavneo@mit` |
| Mode | WPA2-PSK, 2.4 GHz, channel 6 |
| Pi address | `10.42.0.1/24` |
| DHCP for clients | `10.42.0.10 - 10.42.0.254` (NM's internal dnsmasq, 1-hour leases) |
| Internet for clients | **blocked**: see isolation note below |

Once a client connects, it can reach `http://10.42.0.1:8080` (dashboard), `http://10.42.0.1:8888` (Jupyter), or SSH to `10.42.0.1`. It **cannot** route out to the internet through the Pi - even though the Pi itself has internet via eth0. The isolation is enforced by a NetworkManager dispatcher script at `/etc/NetworkManager/dispatcher.d/99-uav-ap-isolate` that inserts `iptables FORWARD ... -j REJECT` rules whenever the AP comes up and removes them on down. Rules are reinstalled by the dispatcher on every connection-up, so no separate persistence layer is needed.

### Setup

The networking setup is automated by `scripts/setup_networking.sh` (run by `setup_all.sh` phase 6, or standalone):

```bash
./scripts/setup_networking.sh
```

This installs the AP-isolation dispatcher, deletes any prior Wi-Fi client connection on wlan0 (the original `Duck` connection from a previous build), creates the `uav-neo-ap` NM connection, and rewrites the eth0 netplan file for the dual-IP behavior. `netplan apply` is invoked at the end to bring everything up. You can re-run the script idempotently - it skips work that's already done.

To verify after setup:

```bash
ip -br addr show eth0     # should show 192.168.52.200/24 + DHCP address
iw dev wlan0 info         # should show ssid uav-neo-0, type AP, channel 6
sudo iptables -L FORWARD -n | grep wlan0   # should show two REJECT rules
```

## Logs

Each time the teleop service starts (on boot or manual restart), a new timestamped directory is created:

```
~/logs/
├── latest -> 20260327_143000/    (symlink to current session)
├── 20260327_143000/
│   ├── teleop.log                (combined teleop stdout/stderr)
│   ├── watchdog.log              (watchdog events)
│   ├── dashboard.log             (dashboard server log)
│   ├── jupyter.log               (JupyterLab server log)
│   ├── restart_mavros_143512.log (rosout from restarted node)
│   └── ...                       (ROS2 internal logs via ROS_LOG_DIR)
└── 20260326_.../                 (previous sessions)
```

The `~/logs/latest` symlink always points to the most recent session. Logs are not automatically cleaned up - manage disk space manually by deleting old session directories.
