# RealSense D435i Topic Reference — UAV Neo

Reference of ROS2 topics published by the Intel RealSense D435i using `realsense2_camera`.

> **Hardware:** Intel RealSense D435i (USB 3.2, serial 943222073786, firmware 5.11.1.100)

---

## Table of Contents

- [Depth](#depth)
- [Color (RGB)](#color-rgb)
- [Infrared](#infrared)
- [IMU](#imu)
- [Aligned Depth](#aligned-depth)
- [Point Cloud](#point-cloud)
- [Camera Info and Metadata](#camera-info-and-metadata)
- [TF Frames](#tf-frames)
- [Configuration Notes](#configuration-notes)

---

## Depth

| Topic | Message Type | Rate | Description |
|---|---|---|---|
| `/camera/depth/image_rect_raw` | `sensor_msgs/msg/Image` | 30 Hz | Rectified depth image (16UC1, values in mm) |
| `/camera/depth/camera_info` | `sensor_msgs/msg/CameraInfo` | 30 Hz | Depth camera intrinsics and distortion |

## Color (RGB)

| Topic | Message Type | Rate | Description |
|---|---|---|---|
| `/camera/color/image_raw` | `sensor_msgs/msg/Image` | 30 Hz | Raw color image (RGB8, 640x480) |
| `/camera/color/camera_info` | `sensor_msgs/msg/CameraInfo` | 30 Hz | Color camera intrinsics and distortion |

## Infrared

| Topic | Message Type | Rate | Description |
|---|---|---|---|
| `/camera/infra1/image_rect_raw` | `sensor_msgs/msg/Image` | 30 Hz | Left infrared camera (8UC1, 640x480) |
| `/camera/infra2/image_rect_raw` | `sensor_msgs/msg/Image` | 30 Hz | Right infrared camera (8UC1, 640x480) |

> Stereo infrared pair is useful for visual odometry (VIO) and feature tracking in low-light conditions.

## IMU

| Topic | Message Type | Rate | Description |
|---|---|---|---|
| `/camera/imu` | `sensor_msgs/msg/Imu` | 200 Hz | Fused gyroscope + accelerometer (linear interpolation) |
| `/camera/gyro/sample` | `sensor_msgs/msg/Imu` | 200 Hz | Raw gyroscope data only |
| `/camera/accel/sample` | `sensor_msgs/msg/Imu` | 63 Hz | Raw accelerometer data only |
| `/camera/gyro/imu_info` | `realsense2_camera_msgs/msg/IMUInfo` | Latched | Gyroscope noise and bias parameters |
| `/camera/accel/imu_info` | `realsense2_camera_msgs/msg/IMUInfo` | Latched | Accelerometer noise and bias parameters |

> The `unite_imu_method: 2` config interpolates accel data to match gyro timestamps, producing a unified `/camera/imu` topic at 200 Hz. This is the preferred input for VIO/SLAM pipelines.

## Aligned Depth

| Topic | Message Type | Rate | Description |
|---|---|---|---|
| `/camera/aligned_depth_to_color/image_raw` | `sensor_msgs/msg/Image` | 30 Hz | Depth image aligned to the color camera frame |
| `/camera/aligned_depth_to_color/camera_info` | `sensor_msgs/msg/CameraInfo` | 30 Hz | Camera info matching the aligned depth |

> Aligned depth maps each depth pixel to the corresponding color pixel. Essential for tasks that combine color and depth (object detection with distance, RGBD SLAM).

## Point Cloud

| Topic | Message Type | Rate | Description |
|---|---|---|---|
| `/camera/depth/color/points` | `sensor_msgs/msg/PointCloud2` | 30 Hz | Colored 3D point cloud (XYZRGB) |

> **Disabled by default** in the UAV Neo config — point cloud generation is CPU intensive on the Pi 5. Enable with: `ros2 launch uav_neo_ros2_driver realsense.launch.py pointcloud_enable:=true`

## Camera Info and Metadata

| Topic | Message Type | Description |
|---|---|---|
| `/camera/extrinsics/depth_to_color` | `realsense2_camera_msgs/msg/Extrinsics` | Extrinsic calibration between depth and color sensors |
| `/camera/depth/metadata` | `realsense2_camera_msgs/msg/Metadata` | Per-frame metadata (exposure, gain, timestamp) |
| `/camera/color/metadata` | `realsense2_camera_msgs/msg/Metadata` | Per-frame metadata for color stream |

## TF Frames

The RealSense node publishes static transforms between all sensor frames:

```
camera_link
├── camera_depth_frame
│   └── camera_depth_optical_frame
├── camera_color_frame
│   └── camera_color_optical_frame
├── camera_infra1_frame
│   └── camera_infra1_optical_frame
├── camera_infra2_frame
│   └── camera_infra2_optical_frame
├── camera_gyro_frame
│   └── camera_gyro_optical_frame
└── camera_accel_frame
    └── camera_accel_optical_frame
```

`camera_link` is the reference frame. Optical frames follow the ROS convention (Z forward, X right, Y down).

---

## Configuration Notes

### Resolution and Framerate

The default UAV Neo config runs at 640x480 @ 30 FPS for depth and color. Available profiles for D435i:

| Resolution | Max FPS (Depth) | Max FPS (Color) | Notes |
|---|---|---|---|
| 1280x720 | 30 | 30 | Higher quality, more CPU load |
| 640x480 | 90 | 60 | Good balance for Pi 5 |
| 424x240 | 90 | 60 | Lowest latency |

To change, edit `depth_module.depth_profile` and `rgb_camera.color_profile` in [config/realsense_d435i.yaml](../config/realsense_d435i.yaml).

### Depth Filters

The following post-processing filters are enabled by default:

| Filter | Purpose |
|---|---|
| Decimation | Reduces depth resolution for faster processing |
| Spatial | Edge-preserving smoothing to reduce noise |
| Temporal | Smoothing across frames to fill holes |

### Pi 5 Performance Considerations

- **Point cloud** is disabled by default — enable only when needed
- **640x480 @ 30 FPS** is the recommended starting resolution
- If CPU usage is too high, reduce to 424x240 or lower FPS
- The D435i is connected over **USB 3.2** which provides full bandwidth
