# UAV Neo ROS2 Driver

A ROS2 (Jazzy) driver package for **UAV Neo**, an educational autonomous drone kit built on a Raspberry Pi 5 mission computer running Ubuntu 24.04 (Noble).

## Table of Contents

- [Overview](#overview)
- [Hardware](#hardware)
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
- [Verifying Peripherals](#verifying-peripherals)
- [Building the Package](#building-the-package)
- [Testing](#testing)
- [Launching](#launching)
  - [MAVROS](#mavros)
  - [RealSense D435i](#realsense-d435i)
  - [Arducam B0578](#arducam-b0578)
  - [All Sensors (Teleop)](#all-sensors-teleop)

## Overview

UAV Neo is an educational autonomous drone platform. This ROS2 package provides the driver layer that interfaces with the onboard sensors, AI accelerator, and flight controller. The Raspberry Pi serves as the mission computer, handling perception, planning, and communication with the Pixhawk flight controller over MAVLink.

## Hardware

| Peripheral | Interface | Device Path | Description |
|---|---|---|---|
| Intel RealSense D435i | USB 3.0 | `/dev/video*` | RGBD + IMU camera for depth perception and SLAM |
| Arducam B0578 2.3MP | USB 2.0 | `/dev/video*` | Downward-facing global shutter camera for optical flow |
| Coral EdgeTPU USB Accelerator | USB 3.0 | N/A (via `libedgetpu`) | ML inference accelerator for onboard AI |
| Pixhawk 2.8.4 (clone) | UART (TELEM2) | `/dev/ttyAMA0` | Flight controller running PX4 |

## Quick Start (Automated Setup)

Setup scripts are provided in `scripts/` that automate the entire installation. Run the all-in-one script:

```bash
cd ~/ros2_ws/src/uav_neo_ros2_driver
chmod +x scripts/setup_all.sh
./scripts/setup_all.sh
```

This runs four phases in series:

| Phase | Script | What it does |
|---|---|---|
| 1 | `scripts/install_ros2_jazzy.sh` | Install ROS2 Jazzy (skipped if already installed) |
| 2 | `scripts/setup_pixhawk.sh` | Disable serial console/SysRq/Bluetooth, install MAVROS |
| 3 | `scripts/setup_realsense.sh` | Install RealSense driver + Pi 5 IMU permission fix |
| 4 | `scripts/setup_arducam.sh` | Install GStreamer + gscam driver |

> **Reboot required:** Phase 2 modifies UART and Bluetooth kernel settings that require a reboot. The script will detect this and prompt you. After rebooting, re-run `./scripts/setup_all.sh` — already-completed phases are skipped automatically.

After setup completes, the script builds the workspace. You can then verify everything works:

```bash
colcon test --packages-select uav_neo_ros2_driver --pytest-args -k hardware -v
```

The individual scripts can also be run standalone (e.g., `./scripts/setup_realsense.sh`) if you only need to set up one component.

> **Note:** Pixhawk parameters (MAV_1_CONFIG, SER_TEL2_BAUD, etc.) must still be configured manually via QGroundControl. See [Pixhawk Parameter Configuration](#pixhawk-parameter-configuration) below.

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
sudo apt install -y ros-jazzy-mavros ros-jazzy-mavros-extras ros-jazzy-mavros-msgs
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

2. Verify the camera is detected:

```bash
v4l2-ctl --list-devices
# Should show: Arducam-B0578-2.3MP-GS: Arducam (usb-xhci-hcd.1-2)
```

3. Quick test (standalone):

```bash
source /opt/ros/jazzy/setup.bash
ros2 run gscam gscam_node --ros-args \
  -p gscam_config:="v4l2src device=/dev/video0 ! image/jpeg,width=1280,height=720,framerate=30/1 ! jpegdec ! videoconvert" \
  -p camera_name:=arducam \
  -r __ns:=/arducam
```

4. In a second terminal, verify topics are publishing:

```bash
ros2 topic echo /arducam/camera/image_raw --once
```

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
| Coral EdgeTPU | `1a6e:089a` (USB3 max performance) or `18d1:9302` (USB2) |

**Pixhawk UART:**

```bash
ls -la /dev/ttyAMA0
```

Should show the device owned by the `dialout` group.

**Camera video devices:**

```bash
v4l2-ctl --list-devices
```

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
| `TestDependencies` | 5 | MAVROS/realsense2_camera/gscam packages installed, GeographicLib datasets, IMU fix script |

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

Launch the RealSense D435i with the UAV Neo configuration (640x480 @ 30 FPS, depth + color + IMU, depth filters enabled):

```bash
ros2 launch uav_neo_ros2_driver realsense.launch.py
```

To enable point cloud generation (CPU intensive):

```bash
ros2 launch uav_neo_ros2_driver realsense.launch.py pointcloud_enable:=true
```

For the full list of available RealSense topics, see [docs/realsense_topics.md](docs/realsense_topics.md).

### Arducam B0578

Launch the Arducam B0578 downward-facing global shutter camera (1280x720 @ 30 FPS MJPEG, decoded to RGB via GStreamer):

```bash
ros2 launch uav_neo_ros2_driver arducam.launch.py
```

To use full resolution (higher CPU cost):

```bash
ros2 launch uav_neo_ros2_driver arducam.launch.py image_width:=1920 image_height:=1200 framerate:=60
```

### All Sensors (Teleop)

Launch MAVROS, RealSense D435i, and Arducam together:

```bash
ros2 launch uav_neo_ros2_driver teleop.launch.py
```
