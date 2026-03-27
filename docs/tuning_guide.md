# PX4 Tuning Guide — UAV Neo (F450 Quadcopter)

Guide for tuning the UAV Neo F450 frame quadcopter running PX4 on a Pixhawk 2.8.4. All parameter changes are made in QGroundControl (Vehicle Setup > Parameters).

---

## Table of Contents

- [Pre-Tuning Checklist](#pre-tuning-checklist)
- [1. Sensor Calibration](#1-sensor-calibration)
- [2. Physical Setup](#2-physical-setup)
- [3. Motor and ESC Verification](#3-motor-and-esc-verification)
- [4. Flight Mode Progression](#4-flight-mode-progression)
- [5. PID Tuning](#5-pid-tuning)
  - [Rate Controller (Inner Loop)](#rate-controller-inner-loop)
  - [Attitude Controller (Outer Loop)](#attitude-controller-outer-loop)
  - [Autotune](#autotune)
- [6. Position and Velocity Tuning](#6-position-and-velocity-tuning)
- [7. Common Symptoms and Fixes](#7-common-symptoms-and-fixes)
- [Useful MAVROS Topics for Tuning](#useful-mavros-topics-for-tuning)

---

## Pre-Tuning Checklist

Before any tuning flight, verify:

- [ ] All props are undamaged, correctly oriented (CW/CCW), and tightened
- [ ] Battery is fully charged
- [ ] Pixhawk firmware is up to date
- [ ] RC transmitter is calibrated in QGroundControl (Radio Setup)
- [ ] Kill switch is assigned and tested
- [ ] Flight area is clear and open (outdoor, no wind for first flights)

---

## 1. Sensor Calibration

Poor sensor calibration is the most common cause of drift and instability. Redo these any time the payload changes.

### Accelerometer Calibration

In QGroundControl: **Sensors > Accelerometer**

- Place the drone on a truly flat, level surface
- Complete the 6-side calibration (level, nose up, nose down, left, right, upside down)
- Keep the drone perfectly still during each step

### Level Horizon Calibration (Critical)

In QGroundControl: **Sensors > Level Horizon**

- Place the drone on a level surface **with all payload installed** (Pi, RealSense, Coral, battery)
- This sets the 0-degree reference for attitude control
- If this is wrong, PX4 will actively hold a tilted attitude, causing constant drift

> **This is the single most common cause of a drone drifting to one side in stabilized flight.** If the drone requires constant stick correction to hover in place, redo this calibration first.

### Gyroscope Calibration

In QGroundControl: **Sensors > Gyroscope**

- Place the drone on a stable surface and do not touch it
- Takes a few seconds — sets the zero-rate reference

### Compass Calibration

In QGroundControl: **Sensors > Compass**

- Rotate the drone in all orientations as prompted
- Perform outdoors, away from metal structures and electronics
- Note: compass is less critical for UAV Neo since there is no GPS, but it still feeds into the EKF

---

## 2. Physical Setup

### Center of Gravity

The CG must be at the geometric center of the F450 frame (where the motor axes cross). With the UAV Neo payload:

- **Raspberry Pi 5** — mount centrally on the top or bottom plate
- **Intel RealSense D435i** — mount forward-facing, as close to center as practical
- **Coral EdgeTPU** — lightweight, mount wherever convenient
- **Battery** — use battery position as the primary CG adjustment. Slide it forward/back until the drone balances level when lifted from the center

If CG is off-center, one or two motors will work harder to compensate, reducing flight time and causing asymmetric handling.

### Motor Mount Alignment

- All 4 motor mounts must be perpendicular to the frame
- Even 1-2 degrees of tilt causes persistent drift
- Check by placing a straight edge across each motor mount

### Prop Direction

F450 standard X-configuration (viewed from above):

```
   CW (1)     CCW (2)
      \       /
       \_____/
       /     \
      /       \
  CCW (3)     CW (4)
```

Verify motor order matches PX4 airframe configuration. In QGroundControl: **Airframe > Quadrotor X** (typically Generic Quadrotor or DJI F450).

---

## 3. Motor and ESC Verification

### Check Motor Spin Direction

In QGroundControl: **Motors** tab (with props removed!)

- Spin each motor individually and verify correct CW/CCW direction
- Swap any two of the three ESC-to-motor wires to reverse a motor

### Check Motor Balance

Monitor motor outputs during a hover using MAVROS:

```bash
ros2 topic echo /mavros/rc/out
```

In a stable hover, all 4 motor PWM values should be roughly equal (within ~50 PWM of each other). If one motor is significantly higher:

- CG is shifted toward the opposite side, or
- That motor/ESC/prop is less efficient

### ESC Calibration

Follow PX4 ESC calibration procedure if motor outputs are inconsistent. This ensures all ESCs map the same PWM range to the same throttle percentage.

---

## 4. Flight Mode Progression

Tune and test in this order, each mode builds on the previous:

| Order | Mode | What It Tests | Requirements |
|---|---|---|---|
| 1 | **Manual/Acro** | Raw motor response | Experience required — skip if not comfortable |
| 2 | **Stabilized** | Attitude hold (roll/pitch/yaw) | Accelerometer + Level Horizon calibration |
| 3 | **Altitude** | Throttle hold + attitude | Barometer calibration |
| 4 | **Position** | Full position hold | Requires position estimation (e.g., VIO from RealSense) |

> **Start tuning in Stabilized mode.** Altitude mode removes throttle management and makes it easier to focus on roll/pitch behavior.

---

## 5. PID Tuning

Only tune PIDs after sensor calibration and physical checks are complete. If the drone still doesn't fly well after calibration, PIDs are the next step.

### Rate Controller (Inner Loop)

Controls how quickly the drone corrects angular rate errors. Tune this first.

| Parameter | Default | Description | Tuning Direction |
|---|---|---|---|
| `MC_ROLLRATE_P` | 0.15 | Roll rate proportional gain | Increase for faster response |
| `MC_ROLLRATE_I` | 0.2 | Roll rate integral gain | Increase to eliminate steady-state error |
| `MC_ROLLRATE_D` | 0.003 | Roll rate derivative gain | Increase to dampen oscillation |
| `MC_PITCHRATE_P` | 0.15 | Pitch rate proportional gain | Same as roll for symmetric frame |
| `MC_PITCHRATE_I` | 0.2 | Pitch rate integral gain | Same as roll for symmetric frame |
| `MC_PITCHRATE_D` | 0.003 | Pitch rate derivative gain | Same as roll for symmetric frame |
| `MC_YAWRATE_P` | 0.2 | Yaw rate proportional gain | Increase if yaw is sluggish |

**Tuning procedure:**

1. Hover in Stabilized or Altitude mode
2. Make small, sharp stick inputs on roll/pitch
3. Increase `MC_ROLLRATE_P` and `MC_PITCHRATE_P` by 10-20% at a time
4. **Too low:** drone feels sluggish, slow to respond, wobbles back and forth (low-frequency oscillation)
5. **Too high:** drone vibrates or oscillates rapidly (high-frequency buzz)
6. If high-frequency oscillation appears, increase `MC_ROLLRATE_D` slightly before reducing P
7. For F450, typical good values are P=0.15-0.22, D=0.003-0.006

### Attitude Controller (Outer Loop)

Controls how aggressively the drone corrects angle errors. Tune after rate gains are stable.

| Parameter | Default | Description |
|---|---|---|
| `MC_ROLL_P` | 6.5 | Roll angle proportional gain |
| `MC_PITCH_P` | 6.5 | Pitch angle proportional gain |
| `MC_YAW_P` | 2.8 | Yaw angle proportional gain |

- **Too low:** drone is slow to level out, feels mushy
- **Too high:** drone overshoots target angle, oscillates
- Default 6.5 is usually fine for F450 — only adjust if rate gains are already tuned and response is still poor

### Autotune

PX4 has a built-in autotuner that works well for standard quads like the F450:

1. Set the following parameters:

| Parameter | Value | Description |
|---|---|---|
| `MC_AT_EN` | 1 | Enable autotune |
| `MC_AT_APPLY` | 1 | Automatically apply tuned gains |

2. Fly in **Altitude mode** with plenty of space
3. Switch to the autotune flight mode (assign to an RC switch)
4. The drone will make small twitching movements on each axis
5. When complete, the new gains are applied automatically
6. Land and verify the new parameters in QGroundControl

> **Autotune is the recommended approach** unless you have specific tuning requirements. It typically produces better results than manual tuning.

---

## 6. Position and Velocity Tuning

Position mode requires a position source. On UAV Neo (no GPS), this means external estimation such as VIO from the RealSense D435i fed through `/mavros/vision_pose/pose`.

| Parameter | Default | Description |
|---|---|---|
| `MPC_XY_P` | 0.95 | Horizontal position proportional gain |
| `MPC_XY_VEL_P_ACC` | 1.8 | Horizontal velocity proportional gain |
| `MPC_Z_P` | 1.0 | Vertical position proportional gain |
| `MPC_Z_VEL_P_ACC` | 4.0 | Vertical velocity proportional gain |

These only matter once position estimation is working. Leave at defaults until then.

---

## 7. Common Symptoms and Fixes

| Symptom | Likely Cause | Fix |
|---|---|---|
| Drifts to one side in stabilized hover | Level Horizon calibration off | Redo Level Horizon with full payload |
| Requires constant stick input to hover | Accelerometer calibration off or CG offset | Redo accel cal, check CG |
| Slow/mushy response to stick input | Rate P gains too low | Increase `MC_ROLLRATE_P` / `MC_PITCHRATE_P` |
| High-frequency vibration/buzz | Rate P too high or D too low | Reduce P or increase D |
| Low-frequency wobble (toilet bowl) | Compass interference or attitude P too high | Recalibrate compass away from electronics, reduce `MC_ROLL_P` |
| One motor much hotter than others | CG offset or motor/ESC issue | Rebalance CG, check motor/prop |
| Yaw drifts slowly | Compass calibration or yaw I gain | Recalibrate compass, check `MC_YAWRATE_I` |
| Drone flips on takeoff | Motor order or prop direction wrong | Verify motor spin directions with props removed |
| Altitude oscillation | Barometer noise or Z gains too high | Check barometer is shielded from prop wash, reduce `MPC_Z_P` |

---

## Useful MAVROS Topics for Tuning

Monitor these topics during tuning flights to diagnose issues:

| Topic | What to Look For |
|---|---|
| `/mavros/imu/data` | Orientation stability, angular rates during hover |
| `/mavros/rc/out` | Motor PWM balance — all 4 should be similar in hover |
| `/mavros/local_position/pose` | Position drift rate |
| `/mavros/vfr_hud` | Groundspeed (should be near 0 in hover), climb rate |
| `/mavros/estimator_status` | EKF health flags — all should be healthy |
| `/mavros/rc/in` | Verify stick inputs are reaching the FCU correctly |
| `/mavros/state` | Confirm armed state and flight mode |

Example — record motor outputs during a hover for analysis:

```bash
ros2 topic echo /mavros/rc/out --csv > motor_log.csv
```
