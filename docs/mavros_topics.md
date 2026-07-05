# MAVROS Topic Reference - UAV Neo

Reference of notable MAVROS published topics, subscribers, and services for the UAV Neo platform.

> **Note:** This system does not have a GPS module. GPS-related topics (`/mavros/global_position/*`, `/mavros/gpsstatus/*`) will not publish meaningful data. Position estimation relies on local/relative methods only.

---

## Table of Contents

- [Published Topics (Pixhawk to ROS2)](#published-topics-pixhawk-to-ros2)
  - [State and System](#state-and-system)
  - [IMU and Attitude](#imu-and-attitude)
  - [Local Position and Velocity](#local-position-and-velocity)
  - [Altitude](#altitude)
  - [Battery and Power](#battery-and-power)
  - [RC Input and Servo Output](#rc-input-and-servo-output)
  - [Flight Display (HUD)](#flight-display-hud)
  - [Estimator and Diagnostics](#estimator-and-diagnostics)
  - [Time Synchronization](#time-synchronization)
  - [Missions and Waypoints](#missions-and-waypoints)
- [Subscribed Topics (ROS2 to Pixhawk)](#subscribed-topics-ros2-to-pixhawk)
  - [Setpoint Position](#setpoint-position)
  - [Setpoint Velocity](#setpoint-velocity)
  - [Setpoint Attitude](#setpoint-attitude)
  - [Setpoint Raw](#setpoint-raw)
  - [Setpoint Acceleration](#setpoint-acceleration)
  - [Setpoint Trajectory](#setpoint-trajectory)
  - [RC Override](#rc-override)
  - [Obstacle Avoidance](#obstacle-avoidance)
  - [Vision Pose (External Estimation)](#vision-pose-external-estimation)
  - [Manual Control](#manual-control)
- [Services](#services)
  - [Command and Control](#command-and-control)
  - [Mode and State](#mode-and-state)
  - [Mission Management](#mission-management)
  - [Parameters](#parameters)

---

## Published Topics (Pixhawk to ROS2)

Rates measured on UAV Neo hardware (Pixhawk 2.8.4 over UART at 921600 baud).

### State and System

| Topic | Message Type | Rate | Description |
|---|---|---|---|
| `/mavros/state` | `mavros_msgs/msg/State` | 1 Hz | Connection status, armed state, flight mode, system status |
| `/mavros/extended_state` | `mavros_msgs/msg/ExtendedState` | 5 Hz | VTOL state, landed state detection |
| `/mavros/sys_status` | `mavros_msgs/msg/SysStatus` | 5 Hz | Onboard sensor health, CPU load, communication drop rate |
| `/mavros/statustext/recv` | `mavros_msgs/msg/StatusText` | Event | Text messages from the FCU (warnings, errors, info) |

### IMU and Attitude

| Topic | Message Type | Rate | Description |
|---|---|---|---|
| `/mavros/imu/data` | `sensor_msgs/msg/Imu` | 50 Hz | Fused orientation (quaternion) + angular velocity + linear acceleration |
| `/mavros/imu/data_raw` | `sensor_msgs/msg/Imu` | 50 Hz | Raw IMU data without orientation estimate |
| `/mavros/imu/mag` | `sensor_msgs/msg/MagneticField` | 13 Hz | Magnetometer reading (x, y, z) |
| `/mavros/imu/temperature_imu` | `sensor_msgs/msg/Temperature` | 18 Hz | IMU sensor temperature |
| `/mavros/imu/temperature_baro` | `sensor_msgs/msg/Temperature` | - | Barometer sensor temperature (not active on this hardware) |
| `/mavros/imu/static_pressure` | `sensor_msgs/msg/FluidPressure` | 18 Hz | Barometric pressure (absolute) |
| `/mavros/imu/diff_pressure` | `sensor_msgs/msg/FluidPressure` | - | Differential pressure (no airspeed sensor installed) |

### Local Position and Velocity

| Topic | Message Type | Rate | Description |
|---|---|---|---|
| `/mavros/local_position/pose` | `geometry_msgs/msg/PoseStamped` | 30 Hz | Local position (x, y, z) and orientation in NED frame |
| `/mavros/local_position/pose_cov` | `geometry_msgs/msg/PoseWithCovarianceStamped` | - | Local position with covariance (requires EKF covariance output) |
| `/mavros/local_position/velocity_local` | `geometry_msgs/msg/TwistStamped` | 30 Hz | Velocity in local NED frame |
| `/mavros/local_position/velocity_body` | `geometry_msgs/msg/TwistStamped` | 30 Hz | Velocity in body frame |
| `/mavros/local_position/velocity_body_cov` | `geometry_msgs/msg/TwistWithCovarianceStamped` | - | Body velocity with covariance (requires EKF covariance output) |
| `/mavros/local_position/odom` | `nav_msgs/msg/Odometry` | 30 Hz | Full odometry (pose + twist) in local frame |
| `/mavros/local_position/accel` | `geometry_msgs/msg/AccelWithCovarianceStamped` | - | Local acceleration estimate (not published in current PX4 config) |

### Altitude

| Topic | Message Type | Rate | Description |
|---|---|---|---|
| `/mavros/altitude` | `mavros_msgs/msg/Altitude` | 10 Hz | Multiple altitude references: monotonic, AMSL, local, relative, terrain, bottom clearance |

### Battery and Power

| Topic | Message Type | Rate | Description |
|---|---|---|---|
| `/mavros/battery` | `sensor_msgs/msg/BatteryState` | ~1 Hz | Voltage, current, cell voltages, charge remaining, temperature. Only publishes when a battery/power module is connected |

### RC Input and Servo Output

| Topic | Message Type | Rate | Description |
|---|---|---|---|
| `/mavros/rc/in` | `mavros_msgs/msg/RCIn` | 4 Hz | RC controller input - all channel PWM values (1000-2000 us) and RSSI |
| `/mavros/rc/out` | `mavros_msgs/msg/RCOut` | 10 Hz | Servo/motor output PWM values for all channels |
| `/mavros/manual_control/control` | `mavros_msgs/msg/ManualControl` | - | Normalized joystick inputs (requires `MAV_1_MODE` set to `Normal`) |

### Flight Display (HUD)

| Topic | Message Type | Rate | Description |
|---|---|---|---|
| `/mavros/vfr_hud` | `mavros_msgs/msg/VfrHud` | 10 Hz | Airspeed, groundspeed, heading, throttle %, altitude, climb rate |

### Estimator and Diagnostics

| Topic | Message Type | Rate | Description |
|---|---|---|---|
| `/mavros/estimator_status` | `mavros_msgs/msg/EstimatorStatus` | 1 Hz | EKF health flags and innovation ratios (velocity, position, mag, HAGL) |
| `/mavros/timesync_status` | `mavros_msgs/msg/TimesyncStatus` | 10 Hz | Time offset between FCU and companion computer |

> **Note:** The `vibration` plugin is disabled in the default UAV Neo config due to a MAVROS Jazzy namespace bug. The raw vibration data is still available via `/mavros/imu/data_raw` accelerometer readings.

### Time Synchronization

| Topic | Message Type | Rate | Description |
|---|---|---|---|
| `/mavros/time_reference` | `sensor_msgs/msg/TimeReference` | 1 Hz | FCU time reference for synchronizing sensor timestamps |

### Missions and Waypoints

| Topic | Message Type | Rate | Description |
|---|---|---|---|
| `/mavros/mission/waypoints` | `mavros_msgs/msg/WaypointList` | On change | Current mission waypoint list |
| `/mavros/mission/reached` | `mavros_msgs/msg/WaypointReached` | Event | Notification when a mission waypoint is reached |
| `/mavros/home_position/home` | `mavros_msgs/msg/HomePosition` | On change | Current home position |

---

## Subscribed Topics (ROS2 to Pixhawk)

These topics accept commands from your ROS2 nodes and send them to the Pixhawk.

### Setpoint Position

| Topic | Message Type | Description |
|---|---|---|
| `/mavros/setpoint_position/local` | `geometry_msgs/msg/PoseStamped` | Command a target position + orientation in local NED frame |
| `/mavros/setpoint_position/global` | `geographic_msgs/msg/GeoPoseStamped` | Command a target position in global lat/lon/alt |

### Setpoint Velocity

| Topic | Message Type | Description |
|---|---|---|
| `/mavros/setpoint_velocity/cmd_vel` | `geometry_msgs/msg/TwistStamped` | Command velocity in local frame (stamped) |
| `/mavros/setpoint_velocity/cmd_vel_unstamped` | `geometry_msgs/msg/Twist` | Command velocity in local frame (unstamped) |

### Setpoint Attitude

| Topic | Message Type | Description |
|---|---|---|
| `/mavros/setpoint_attitude/cmd_vel` | `geometry_msgs/msg/TwistStamped` | Command angular velocity (body rates) |
| `/mavros/setpoint_attitude/thrust` | `mavros_msgs/msg/Thrust` | Command thrust (0.0-1.0 normalized for PX4) |

### Setpoint Raw

| Topic | Message Type | Description |
|---|---|---|
| `/mavros/setpoint_raw/local` | `mavros_msgs/msg/PositionTarget` | Combined position/velocity/acceleration setpoint with type mask |
| `/mavros/setpoint_raw/global` | `mavros_msgs/msg/GlobalPositionTarget` | Combined global setpoint with type mask |
| `/mavros/setpoint_raw/attitude` | `mavros_msgs/msg/AttitudeTarget` | Combined attitude/thrust/body rate setpoint with type mask |

### Setpoint Acceleration

| Topic | Message Type | Description |
|---|---|---|
| `/mavros/setpoint_accel/accel` | `geometry_msgs/msg/Vector3Stamped` | Command acceleration in local frame |

### Setpoint Trajectory

| Topic | Message Type | Description |
|---|---|---|
| `/mavros/setpoint_trajectory/local` | `mavros_msgs/msg/Trajectory` | Multi-point trajectory setpoint |

### RC Override

| Topic | Message Type | Description |
|---|---|---|
| `/mavros/rc/override` | `mavros_msgs/msg/OverrideRCIn` | Override RC channel values (PWM). Use 0 to release a channel, 65535 to ignore |

### Obstacle Avoidance

| Topic | Message Type | Description |
|---|---|---|
| `/mavros/obstacle/send` | `sensor_msgs/msg/LaserScan` | Send obstacle distance data to PX4 for collision prevention |
| `/mavros/obstacle_distance_3d/send` | `mavros_msgs/msg/ObstacleDistance3D` | 3D obstacle distance data |

### Vision Pose (External Estimation)

| Topic | Message Type | Description |
|---|---|---|
| `/mavros/vision_pose/pose` | `geometry_msgs/msg/PoseStamped` | External pose estimate (e.g., from RealSense D435i VIO, SLAM) for EKF fusion |
| `/mavros/vision_pose/pose_cov` | `geometry_msgs/msg/PoseWithCovarianceStamped` | External pose estimate with covariance |
| `/mavros/vision_speed/speed_twist_cov` | `geometry_msgs/msg/TwistWithCovarianceStamped` | External velocity estimate with covariance |

### Manual Control

| Topic | Message Type | Description |
|---|---|---|
| `/mavros/manual_control/send` | `mavros_msgs/msg/ManualControl` | Send manual control inputs to the FCU (virtual joystick) |

---

## Services

### Command and Control

| Service | Type | Description |
|---|---|---|
| `/mavros/mavros_node/arming` | `mavros_msgs/srv/CommandBool` | Arm or disarm the vehicle |
| `/mavros/mavros_node/takeoff` | `mavros_msgs/srv/CommandTOL` | Command takeoff to a specified altitude |
| `/mavros/mavros_node/land` | `mavros_msgs/srv/CommandTOL` | Command landing |
| `/mavros/mavros_node/command` | `mavros_msgs/srv/CommandLong` | Send any MAV_CMD_* long command |
| `/mavros/mavros_node/command_int` | `mavros_msgs/srv/CommandInt` | Send any MAV_CMD_* int command |

### Mode and State

| Service | Type | Description |
|---|---|---|
| `/mavros/mavros/set_mode` | `mavros_msgs/srv/SetMode` | Change flight mode (e.g., OFFBOARD, POSITION, MANUAL, LAND) |
| `/mavros/home_position/req_update` | `std_srvs/srv/Trigger` | Request home position update from FCU |
| `/mavros/home_position/set` | `mavros_msgs/srv/CommandHome` | Set a new home position |

### Mission Management

| Service | Type | Description |
|---|---|---|
| `/mavros/mission/pull` | `mavros_msgs/srv/WaypointPull` | Pull the current mission from the FCU |
| `/mavros/mission/push` | `mavros_msgs/srv/WaypointPush` | Push a mission to the FCU |
| `/mavros/mission/clear` | `mavros_msgs/srv/WaypointClear` | Clear all mission waypoints on the FCU |
| `/mavros/mission/set_current` | `mavros_msgs/srv/WaypointSetCurrent` | Set the active mission waypoint index |

### Parameters

| Service | Type | Description |
|---|---|---|
| `/mavros/param/pull` | `mavros_msgs/srv/ParamPull` | Pull all parameters from the FCU |
| `/mavros/param/push` | `mavros_msgs/srv/ParamPush` | Push parameters to the FCU |
| `/mavros/param/get` | `mavros_msgs/srv/ParamGet` | Get a single FCU parameter |
| `/mavros/param/set` | `mavros_msgs/srv/ParamSet` | Set a single FCU parameter |
