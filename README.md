# UAV Neo ROS2 Driver

A ROS2 (Jazzy) driver package for **UAV Neo**, an educational autonomous drone kit built on a Raspberry Pi 5 mission computer running Ubuntu 24.04 (Noble).

## Table of Contents

- [Overview](#overview)
- [Hardware](#hardware)
- [Prerequisites](#prerequisites)
  - [Install ROS2 Jazzy](#install-ros2-jazzy)
  - [Enable UART for Pixhawk](#enable-uart-for-pixhawk)
  - [Set Serial Port Permissions](#set-serial-port-permissions)
- [Verifying Peripherals](#verifying-peripherals)
- [Building the Package](#building-the-package)

## Overview

UAV Neo is an educational autonomous drone platform. This ROS2 package provides the driver layer that interfaces with the onboard sensors, AI accelerator, and flight controller. The Raspberry Pi serves as the mission computer, handling perception, planning, and communication with the Pixhawk flight controller over MAVLink.

## Hardware

| Peripheral | Interface | Device Path | Description |
|---|---|---|---|
| Intel RealSense D435i | USB 3.0 | `/dev/video*` | RGBD + IMU camera for depth perception and SLAM |
| Arducam B0578 2.3MP | USB 2.0 | `/dev/video*` | Global shutter camera for visual tasks |
| Coral EdgeTPU USB Accelerator | USB 3.0 | N/A (via `libedgetpu`) | ML inference accelerator for onboard AI |
| Pixhawk 2.8.4 (clone) | UART (TELEM2) | `/dev/ttyAMA0` | Flight controller running ArduPilot/PX4 |

## Prerequisites

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

After reboot, `/dev/ttyAMA0` should be available. The default TELEM2 baud rate is **921600**.

### Set Serial Port Permissions

Add your user to the `dialout` group to access the serial port without `sudo`:

```bash
sudo usermod -aG dialout $USER
```

Log out and back in (or reboot) for the group change to take effect.

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
