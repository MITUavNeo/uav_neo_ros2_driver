# UAV Neo - Topic Bandwidth and I/O Reference

Measured 2026-03-28 on Raspberry Pi 5 (8 GB) with full teleop stack running.
Configuration: MAVROS (nice 5) + RealSense D435i 640x480@15fps + Arducam B0578 640x480@30fps capped to 20fps (patched gscam).

## Bandwidth Chart

| Topic | Rate (Hz) | Bandwidth | Msg Size | Source |
|-------|-----------|-----------|----------|--------|
| `/arducam/camera/image_raw` | ~15-24 | **25.49 MB/s** | ~921 KB | Arducam B0578 (gscam, 20fps cap) |
| `/camera/depth/image_rect_raw` | ~10-15 | **12.92 MB/s** | ~600 KB | RealSense D435i depth |
| `/camera/color/image_raw` | ~10-15 | **1.52 MB/s** | ~307 KB | RealSense D435i color |
| `/camera/imu` | ~156-200 | **91.40 KB/s** | ~160 B | RealSense D435i IMU |
| `/mavros/imu/data` | ~45-50 | **17.33 KB/s** | ~440 B | Pixhawk via MAVROS |
| `/mavros/state` | ~1.0 | **39 B/s** | ~38 B | Pixhawk via MAVROS |

## Total Estimated Bandwidth

| Category | Bandwidth |
|----------|-----------|
| Arducam (raw RGB 640x480) | ~25.5 MB/s |
| RealSense (color + depth + IMU) | ~14.5 MB/s |
| MAVROS (state + IMU + all topics) | ~0.1 MB/s |
| **Total internal DDS traffic** | **~40.1 MB/s** |

## Process Resource Usage

| Process | CPU (% of 1 core) | RSS (MB) | Nice |
|---------|-------------------|----------|------|
| mavros_node | ~86-92% | ~231 | 5 |
| realsense2_camera_node | ~29-34% | ~129 | 0 |
| gscam_node | ~20-25% | ~99 | 0 |
| **Total** | **~140%** (of 400%) | **~459** | - |

## Notes

- Arducam dominates bandwidth due to raw RGB publishing at 640x480. At 1280x720 (~81 MB/s raw) the effective rate drops to ~7 Hz due to CPU saturation.
- RealSense streams are set to 15 FPS at the sensor level. Actual publish rates are ~10-15 Hz under full system load due to USB bus contention and CPU scheduling.
- MAVROS CPU is high (~86-92% of one core) because it handles serial protocol parsing, plugin processing, and TF broadcasting. Setting nice 5 reduces its scheduling priority without affecting its data rates.
- Rates fluctuate between measurements due to DDS scheduling on a loaded 4-core system. Rates are more stable with the 15fps RealSense cap and 20fps Arducam videorate cap than with uncapped 30fps.
- gscam RSS is stable at ~95-105 MB indefinitely after the appsink `max-buffers=1 drop=true` patch (see `scripts/patch_gscam.sh`).
- RealSense CPU dropped from ~55% to ~30% after reducing from 30fps to 15fps profiles, freeing headroom for other processing.
