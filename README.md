# UAV Neo ROS2 Driver

A ROS2 (Jazzy) driver package for **UAV Neo**, an educational autonomous drone kit built on a Raspberry Pi 5 mission computer running Ubuntu 24.04 (Noble).

## Table of Contents

- [Overview](#overview)
- [Hardware](#hardware)
- [Two-Pilot Operation](#two-pilot-operation)
- [Safety Architecture](#safety-architecture)
- [Topic Architecture](#topic-architecture)
- [Quick Start (Automated Setup)](#quick-start-automated-setup)
- [Manual Setup](#manual-setup)
  - [Install ROS2 Jazzy](#install-ros2-jazzy)
  - [Enable UART for Pixhawk](#enable-uart-for-pixhawk)
  - [Disable Serial Console and SysRq (Critical)](#disable-serial-console-and-sysrq-critical)
  - [Disable Bluetooth on UART](#disable-bluetooth-on-uart)
  - [Set Serial Port Permissions](#set-serial-port-permissions)
  - [Pixhawk Parameter Configuration](#pixhawk-parameter-configuration)
  - [Install MAVROS](#install-mavros)
  - [Install RealSense Camera Driver](#install-realsense-camera-driver)
  - [Install Arducam Global Shutter Camera Driver](#install-arducam-global-shutter-camera-driver)
  - [Install Coral EdgeTPU Dependencies](#install-coral-edgetpu-dependencies)
- [Verifying Peripherals](#verifying-peripherals)
- [Building the Package](#building-the-package)
- [Testing](#testing)
- [Launching](#launching)
  - [MAVROS](#mavros)
  - [RealSense D435i](#realsense-d435i)
  - [Arducam B0578](#arducam-b0578)
  - [All Sensors (Teleop)](#all-sensors-teleop)
  - [Mux Node](#mux-node)
  - [EdgeTPU Inference](#edgetpu-inference)
- [Services](#services)
  - [Teleop Autostart](#teleop-autostart)
  - [Node Watchdog](#node-watchdog)
  - [Web Dashboard](#web-dashboard)
  - [JupyterLab](#jupyterlab)
  - [Managing Services](#managing-services)
- [Logging](#logging)

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

## Two-Pilot Operation

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
| **LB held** | Manual mode — Xbox sticks control the drone through the mux |
| **RB held** | Auto mode — student code controls the drone through the mux |
| **Neither bumper** | Idle — zero velocity (hover) |
| **Both bumpers** | Idle — zero velocity (hover) |
| START | Enter student program mode |
| BACK | Return to default mode |
| START + BACK | Exit program |

The Xbox controller has **no direct connection** to the flight controller. All commands pass through the mux node, which enforces speed limits from `config/mux.yaml`.

## Safety Architecture

The system has multiple layers of safety to prevent uncontrolled flight:

**1. Mux node (`mux_node`)** — Arbitrates all velocity commands. Student code cannot send flight commands directly to MAVROS. The mux enforces:
- Speed limits (`max_speed` and `max_yaw_rate` from `config/mux.yaml`)
- Bumper gating (commands only pass through when LB or RB is held)
- Xbox controller disconnect detection (500ms timeout → zero velocity)

**2. PX4 OFFBOARD timeout** — If the Pi stops sending setpoints for more than `COM_OF_LOSS_T` (1.0s), PX4 automatically exits OFFBOARD mode and reverts to the safety pilot's RC mode switch setting.

**3. RC transmitter override** — The safety pilot can switch out of OFFBOARD mode at any time via Switch D. This is a hardware-level override that cannot be blocked by software.

**4. Student code isolation** — The student library cannot:
- Arm or disarm the motors
- Change flight modes (OFFBOARD, STABILIZED, etc.)
- Set the speed limit (enforced by mux config, not student code)
- Publish directly to MAVROS velocity topics (all commands go through `/mux/cmd_vel`)

**5. Exception handling** — If student code crashes, the library catches the exception, logs it, and sends a stop command (zero velocity). The run loop continues operating.

**Required PX4 parameters** (set via QGroundControl):

| Parameter | Value | Purpose |
|---|---|---|
| `COM_OF_LOSS_T` | `1.0` | Seconds without setpoints before OFFBOARD failsafe |
| `COM_RCL_EXCEPT` | `4` | Allow OFFBOARD even if RC link drops |
| `RC_MAP_OFFB_SW` | `8` | Channel 8 (Switch D) controls OFFBOARD mode |

## Topic Architecture

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
Student code                Xbox controller
     │                            │
 send_pcmd()                  joy_node
     │                            │
 /mux/cmd_vel              /joy (buttons + axes)
     │                            │
     └──────────┬─────────────────┘
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

## Quick Start (Automated Setup)

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

> **Reboot required:** Phase 2 modifies UART and Bluetooth kernel settings that require a reboot. The script will detect this and prompt you. After rebooting, re-run `./scripts/setup_all.sh` — already-completed phases are skipped automatically.

After setup completes, the script builds the workspace. You can then verify everything works:

```bash
colcon test --packages-select uav_neo_ros2_driver --pytest-args -k hardware -v
```

The individual scripts can also be run standalone (e.g., `./scripts/setup_realsense.sh`) if you only need to set up one component.

> **Note:** Pixhawk parameters (MAV_1_CONFIG, SER_TEL2_BAUD, etc.) must still be configured manually via QGroundControl. See [Pixhawk Parameter Configuration](#pixhawk-parameter-configuration) below.

### After Boot

All services start automatically on boot. Use these commands to manage them:

**Check status:**

```bash
systemctl status uav-teleop uav-watchdog uav-dashboard uav-jupyter
```

**Restart the teleop stack** (e.g., after changing a config file or updating code):

```bash
sudo systemctl restart uav-teleop
```

**Restart with EdgeTPU inference enabled:**

```bash
sudo systemctl stop uav-teleop
~/ros2_ws/src/uav_neo_ros2_driver/scripts/launch_teleop.sh edgetpu_enable:=true
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

## Manual Setup

The sections below document each setup step in detail. If you used the automated setup scripts above, these are already done — use this as a reference.

### Install ROS2 Jazzy

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

### Enable UART for Pixhawk

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

### Disable Serial Console and SysRq (Critical)

> **WARNING:** Do **not** connect the Pixhawk UART before completing **all** steps in this section and the next (Disable Bluetooth on UART). Ubuntu defaults to using the UART as a kernel boot console, login shell, and SysRq input. MAVLink data from the Pixhawk will be interpreted as system commands, causing two failure modes:
>
> 1. **Boot loop** — MAVLink data is interpreted as console/login input, preventing the Pi from booting. Can only be resolved by physically disconnecting the Pixhawk.
> 2. **System crash** — MAVLink byte sequences are interpreted as kernel SysRq commands (e.g., emergency remount read-only, sync, reboot), causing the filesystem to go read-only and the system to lock up.

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

### Disable Bluetooth on UART

By default, the Pi's Bluetooth controller uses the PL011 UART (`/dev/ttyAMA0`) — the same port needed for the Pixhawk. Bluetooth must be moved off this UART to avoid conflicts.

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

### Set Serial Port Permissions

Add your user to the `dialout` group to access the serial port without `sudo`:

```bash
sudo usermod -aG dialout $USER
```

Log out and back in (or reboot) for the group change to take effect.

### Pixhawk Parameter Configuration

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

### Install MAVROS

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

### Install RealSense Camera Driver

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

### Install Arducam Global Shutter Camera Driver

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

### Install Coral EdgeTPU Dependencies

The Coral EdgeTPU USB Accelerator is used for onboard ML inference. Pre-built packages for Ubuntu 24.04 (aarch64) are included in `depend/`.

> **Note:** The Coral USB device changes its USB ID after the runtime initializes it. It appears as `1a6e:089a` (Global Unichip) when first plugged in, then switches to `18d1:9302` (Google) after the EdgeTPU firmware is loaded. The udev rule covers both IDs.

1. Run the setup script:

```bash
chmod +x scripts/setup_coral.sh
./scripts/setup_coral.sh
```

This installs:
- `libedgetpu1-std` — EdgeTPU runtime library (`.deb`)
- `tflite_runtime` — TensorFlow Lite interpreter (`.whl`)
- `pycoral` — High-level Python API for EdgeTPU (`.whl`)
- Udev rule at `/etc/udev/rules.d/99-coral-edgetpu.rules` for non-root USB access

2. Verify the TPU is detected:

```bash
python3 -c "from pycoral.utils.edgetpu import list_edge_tpus; print(list_edge_tpus())"
```

You should see `[{'type': 'usb', 'path': '/sys/bus/usb/devices/...'}]`.

## Verifying Peripherals

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

## Building the Package

```bash
source /opt/ros/jazzy/setup.bash
cd ~/ros2_ws
colcon build --packages-select uav_neo_ros2_driver
source install/setup.bash
```

## Testing

Hardware connectivity tests verify that all sensors are plugged in, detected, and accessible before launching any ROS2 nodes.

### Run all hardware tests

```bash
colcon test --packages-select uav_neo_ros2_driver --pytest-args -k hardware -v
```

### What the tests check

| Test Class | Tests | What it verifies |
|---|---|---|
| `TestPixhawk` | 6 | UART device exists, read/write permissions, dialout group, serial console disabled, SysRq disabled, Bluetooth overlay active |
| `TestRealSense` | 5 | USB device on bus, V4L2 devices registered, rs-enumerate finds D435i, USB 3.x connection, IMU IIO permissions |
| `TestArducam` | 4 | USB device on bus, V4L2 device listed, device node accessible, MJPEG format available |
| `TestCoralTPU` | 8 | USB device on bus (pre/post-init IDs), libedgetpu installed, tflite_runtime importable, pycoral importable, EdgeTPU runtime detects TPU, classification inference <100 ms, detection inference <50 ms, udev rule exists |
| `TestDependencies` | 5 | ROS2 packages installed (mavros, realsense2_camera, gscam — 3 parametrized cases), GeographicLib datasets, IMU fix script |

Each test assertion includes a human-readable error message with the exact command to fix the issue.

### Run all tests (including linters)

```bash
colcon test --packages-select uav_neo_ros2_driver
colcon test-result --verbose
```

## Launching

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

### All Sensors (Teleop)

Launch the full stack — MAVROS, RealSense, Arducam, joy node, mux node, and topic relays:

```bash
ros2 launch uav_neo_ros2_driver teleop.launch.py
```

With EdgeTPU inference enabled:

```bash
ros2 launch uav_neo_ros2_driver teleop.launch.py edgetpu_enable:=true
```

**Available launch arguments:**

| Argument | Default | Description |
|---|---|---|
| `fcu_url` | `/dev/ttyAMA0:921600` | Pixhawk UART connection |
| `gcs_url` | (empty) | QGroundControl UDP bridge |
| `pointcloud_enable` | `false` | Enable point cloud (CPU intensive) |
| `depth_profile` | `640x480x15` | Depth stream resolution and FPS |
| `color_profile` | `640x480x15` | Color stream resolution and FPS |
| `arducam_width` | `640` | Arducam image width |
| `arducam_height` | `480` | Arducam image height |
| `arducam_framerate` | `30` | Arducam framerate |
| `edgetpu_enable` | `false` | Enable Coral EdgeTPU inference node |
| `edgetpu_config` | `config/edgetpu.yaml` | EdgeTPU configuration file |
| `mux_config` | `config/mux.yaml` | Mux node configuration file |
| `joy_device` | `/dev/input/js0` | Xbox controller device path |

### Mux Node

The mux node arbitrates between manual (Xbox sticks) and autonomous (student code) velocity commands. It is included automatically in the teleop launch.

**Behavior:**
- **LB held** — manual mode: Xbox stick inputs are scaled by `max_speed` and forwarded to MAVROS
- **RB held** — auto mode: student code commands (from `/mux/cmd_vel`) are scaled and forwarded
- **Neither bumper** — idle: zero velocity published (drone hovers)
- **Controller disconnected** — if no `/joy` message for 500ms, zero velocity published

**Stick mapping (Mode 2):**

| Stick | Function |
|---|---|
| Left stick Y | Throttle (up/down) |
| Left stick X | Yaw (rotation) |
| Right stick Y | Pitch (forward/back) |
| Right stick X | Roll (left/right) |

**Configuration** (`config/mux.yaml`):

| Parameter | Default | Description |
|---|---|---|
| `max_speed` | `0.5` | Maximum velocity in m/s for all axes |
| `max_yaw_rate` | `0.5` | Maximum yaw rate in rad/s |
| `joystick_dead_zone` | `0.15` | Stick dead zone (fraction, 0.0–1.0) |
| `publish_rate` | `20.0` | Setpoint publish rate in Hz (must be >2 for PX4 OFFBOARD) |

### EdgeTPU Inference

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

### Teleop Autostart

The `uav-teleop` service launches the full stack (MAVROS + RealSense + Arducam + joy node + mux node + topic relays) on boot using `scripts/launch_teleop.sh`. This wrapper creates a timestamped log directory under `~/logs/` before launching.

```bash
sudo systemctl start uav-teleop    # start now
sudo systemctl stop uav-teleop     # stop
sudo systemctl restart uav-teleop  # restart (creates new log session)
```

### Node Watchdog

The `uav-watchdog` service monitors the sensor nodes and mux node every 5 seconds. When a node disappears:

1. Checks if the underlying hardware is still connected (UART for Pixhawk, USB for cameras)
2. If connected: restarts the individual node's launch file and logs rosout to `~/logs/latest/restart_<node>_<time>.log`
3. If disconnected: logs a warning and waits for the device to reappear
4. Enforces a 30-second cooldown between restarts of the same node

The watchdog starts 15 seconds after teleop to allow all nodes to initialize.

### Web Dashboard

The `uav-dashboard` service runs a web-based monitoring page on **port 8080**. Open in a browser:

```
http://<pi-ip>:8080
```

The dashboard shows:
- Green/red indicators for each node (MAVROS, RealSense, Arducam)
- Topic publish rates with stale/dead detection
- Recent watchdog restart events

The page auto-refreshes every 3 seconds. No additional dependencies are required — it uses Python's built-in HTTP server.

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

### Managing Services

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

## Logging

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

The `~/logs/latest` symlink always points to the most recent session. Logs are not automatically cleaned up — manage disk space manually by deleting old session directories.
