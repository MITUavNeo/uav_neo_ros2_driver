# Shape node

Fly a repeating shape so an LED strip on the drone draws it in a long-exposure or
timelapse photo. The node (`uav_neo_ros2_driver/shape_node.py`) streams setpoints
directly to MAVROS - it does not use the mux or the gamepad.

## Running

`shape.launch.py` is standalone: it brings up MAVROS and the shape node (no cameras,
joy, mux, or gamepad).

```bash
ros2 launch uav_neo_ros2_driver shape.launch.py                 # MAVROS + shape_node
ros2 launch uav_neo_ros2_driver shape.launch.py mavros:=false   # shape_node only (MAVROS already up)
ros2 launch uav_neo_ros2_driver shape.launch.py shape:=spiral
```

Override single parameters directly (against an already-running MAVROS or sim):

```bash
ros2 run uav_neo_ros2_driver shape_node --ros-args \
  -p control_mode:=closed_loop -p shape:=circle
```

Defaults live in `config/shape.yaml`.

## Flying it (safety pilot)

1. The safety pilot arms and switches to OFFBOARD on the RC transmitter. Software
   cannot arm or set OFFBOARD.
2. The node only advances the shape while armed and in OFFBOARD. Taking the drone
   out of OFFBOARD pauses the shape; switching back in resumes it where it paused,
   so the drawing is not skipped ahead.
3. Switching out of OFFBOARD is always the pilot's override.

## Two control modes

| Mode | Topic | Message | Behavior |
|---|---|---|---|
| `open_loop` | `/mavros/setpoint_velocity/cmd_vel` | `TwistStamped` | Body-frame velocity. Dead-reckoned, so the path drifts over time. |
| `closed_loop` | `/mavros/setpoint_position/local` | `PoseStamped` | Absolute position waypoints. PX4 flies to and holds each one, so the shape stays anchored in the world. |

Comparing the two is the point: open loop shows how commanding velocity without
feedback accumulates error, while closed loop shows PX4 closing the loop on position.
Each mode uses the MAVROS topic that fits it - velocity for open loop, position for
closed loop.

Closed-loop mode relies on `config/mavros_px4.yaml` setting
`setpoint_position: mav_frame: LOCAL_NED`, which makes waypoints absolute. With the
default `BODY_NED` they would be offsets from the current pose and the shape would
walk away each cycle. The velocity path keeps `setpoint_velocity: mav_frame: BODY_NED`.

## Built-in shapes

Open-loop shapes come in two forms, because velocity control is best for smooth
continuous motion and awkward for exact corners:

- `VELOCITY_SHAPES` - timed `(forward, left, up, yaw, seconds)` segments, for
  straight-line shapes: `square`, `triangle`.
- `VELOCITY_PATTERNS` - a function of time returning a normalized velocity, for
  smooth curves: `circle`, `spiral`, `figure8`, `wave`.

Closed-loop shapes are `(x, y, z)` waypoints in `WAYPOINT_SHAPES`: `square`,
`triangle`, `circle`.

## Sizing for your space

The default sizes are tuned to fit a ~6 x 3 m (20 x 10 ft) room, all footprints
<= 1.5 m; the 3 m width is the binding dimension.

- Center the drone in the space before engaging OFFBOARD. Closed-loop shapes are
  centered on the EKF origin (roughly where it booted); open-loop shapes grow from
  wherever the drone is when OFFBOARD engages.
- Open-loop drifts (no position feedback), so its real footprint wanders. In a tight
  space favor `closed_loop`, which is anchored and does not drift.
- `wave` travels forward continuously - it crosses the room rather than looping in
  place. Use it for a single pass, not in a small space.
- Sizes scale with the constants at the top of `shape_node.py` (`SHAPE_RADIUS_M`,
  the per-shape `*_PERIOD_S` and `*_SIDE_SECONDS`) and with the `max_speed`
  parameter.

## Frames and signs

Open-loop body-frame velocity, matching `gamepad.py`:

```
linear.x  forward +      linear.y  left +
linear.z  up +           angular.z yaw CCW +
```

Closed-loop waypoints are ENU meters: `x` east, `y` north, `z` up (altitude).

## Adding your own shape

Shapes are plain data at the top of `shape_node.py`. To add one named `diamond`:

1. Open-loop, as timed segments (straight lines) - add to `VELOCITY_SHAPES`. Each
   value is normalized to `[-1, 1]`; the node scales it by `max_speed` /
   `max_yaw_rate`. A diamond is a square rotated 45 degrees, so drive the diagonals:

   ```python
   'diamond': [
       (0.7, 0.7, 0.0, 0.0, 2.0),    # forward-left
       (-0.7, 0.7, 0.0, 0.0, 2.0),   # back-left
       (-0.7, -0.7, 0.0, 0.0, 2.0),  # back-right
       (0.7, -0.7, 0.0, 0.0, 2.0),   # forward-right
   ],
   ```

2. Open-loop, as a velocity pattern (smooth curve) - add a function of time to
   `VELOCITY_PATTERNS`. See `_spiral_pattern` for the idea. A rose/petal curve:

   ```python
   def _rose_pattern(t):
       w = 2.0 * math.pi / 10.0
       r = math.cos(3.0 * w * t)          # petal envelope
       return (r * math.cos(w * t), r * math.sin(w * t), 0.0, 0.0)

   VELOCITY_PATTERNS = {
       ...
       'rose': _rose_pattern,
   }
   ```

3. Closed-loop, as waypoints - add `(x, y, z)` meters to `WAYPOINT_SHAPES`:

   ```python
   'diamond': [
       (0.0, 0.75, 1.5),
       (-0.75, 0.0, 1.5),
       (0.0, -0.75, 1.5),
       (0.75, 0.0, 1.5),
   ],
   ```

Define a shape in whichever forms make sense. Select it with `-p shape:=diamond`.
The `_regular_polygon_velocity` and `_regular_polygon_waypoints` helpers build these
lists in code if you would rather generate a shape than type out its points.

After editing, rebuild:

```bash
colcon build --packages-select uav_neo_ros2_driver
source install/setup.bash
```

## Autostart on boot (swap for teleop)

After pulling the latest branch, one script builds the package, installs
`uav-shape.service`, disables teleop, and enables the shape service for boot:

```bash
cd ~/ros2_ws/src/uav_neo_ros2_driver
./scripts/setup_shape_service.sh          # enable for boot
./scripts/setup_shape_service.sh --start  # ...and start now (FCU connected)
```

Only one of `uav-teleop` / `uav-shape` can run at a time (both bind the FCU via
MAVROS). Revert with
`sudo systemctl disable --now uav-shape && sudo systemctl enable --now uav-teleop`.
See the README "Shape autostart" section for the manual equivalent.
