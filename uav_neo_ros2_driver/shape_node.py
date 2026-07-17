# Copyright 2026 MIT
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


"""Fly a repeating shape for an LED long-exposure / timelapse photo.

The node streams setpoints directly to MAVROS (no mux, no gamepad). It keeps
running while the drone is taken in and out of OFFBOARD: it only advances the
shape while armed and in OFFBOARD, so when the safety pilot hands control back
the shape resumes where it paused instead of jumping ahead.

Two control modes are provided so students can compare them:

  open_loop   -> publishes body-frame velocity to
                 /mavros/setpoint_velocity/cmd_vel. Dead-reckoned, so it drifts.
                 Best for smooth, continuously-varying motion that is natural to
                 command with velocity: a circle, spiral, figure eight, or weave.

  closed_loop -> publishes absolute position waypoints to
                 /mavros/setpoint_position/local. PX4 runs its own position
                 controller to reach and hold each point, so the shape stays
                 anchored in the world. Best for exact corners (polygons).

Body-velocity sign convention (open_loop), matching gamepad.py:
    linear.x  forward +      linear.y  left +
    linear.z  up +           angular.z yaw CCW +

Waypoint axes (closed_loop) are ENU meters: x east, y north, z up (altitude).

Open-loop shapes come in two forms:
  VELOCITY_SHAPES   - timed (forward, left, up, yaw, seconds) segments, for
                      straight-line shapes (square, triangle).
  VELOCITY_PATTERNS - f(t_seconds) -> normalized (forward, left, up, yaw), for
                      smooth curves (circle, spiral, figure8, wave).

------------------------------------------------------------------------------
ADD YOUR OWN SHAPE
------------------------------------------------------------------------------
1. Pick a name, e.g. 'diamond'.
2. For open_loop, either add timed segments to VELOCITY_SHAPES, or add a
   function of time to VELOCITY_PATTERNS (see _spiral_pattern for the idea).
   Values are normalized to [-1, 1]; the node scales by max_speed/max_yaw_rate.
3. For closed_loop, add a list of (x, y, z) waypoints in meters to
   WAYPOINT_SHAPES.
Define a shape in whichever forms make sense. Select it with the `shape`
parameter. The helpers above build shapes in code if you prefer that.
"""

import math

from geometry_msgs.msg import PoseStamped, TwistStamped
from mavros_msgs.msg import State
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data


# --- Defaults (overridable as ROS parameters) ---

# PX4 drops OFFBOARD if setpoints stop for longer than COM_OF_LOSS_T, so stream
# well above its 2 Hz floor.
DEFAULT_PUBLISH_RATE_HZ = 20.0
DEFAULT_MAX_SPEED = 0.5
DEFAULT_MAX_YAW_RATE = 0.5
DEFAULT_WAYPOINT_TOLERANCE_M = 0.2
DEFAULT_WAYPOINT_TIMEOUT_S = 12.0
DEFAULT_SHAPE = 'square'
DEFAULT_CONTROL_MODE = 'closed_loop'

# Closed-loop reads the FCU local pose directly for arrival detection; no relay
# needed. Override to /position if pointing at the teleop-relayed name.
DEFAULT_POSITION_TOPIC = '/mavros/local_position/pose'

OPEN_LOOP = 'open_loop'
CLOSED_LOOP = 'closed_loop'

# Normalized command magnitude cap for the open-loop velocity segments.
NORM_LIMIT = 1.0

# MAVROS local setpoint frame; the actual FCU frame comes from mav_frame in
# config/mavros_px4.yaml (LOCAL_NED so waypoints are absolute, not offsets).
SETPOINT_FRAME_ID = 'map'

# --- Shape geometry defaults used by the generators below ---

# Sizes are tuned to fit a ~6 x 3 m (20 x 10 ft) space with margin; the 3 m
# width is the binding dimension. Scale these up for a larger area.
SIDE_SPEED_NORM = 1.0
SQUARE_SIDE_SECONDS = 2.0
TRIANGLE_SIDE_SECONDS = 2.0

SHAPE_CENTER = (0.0, 0.0)
SHAPE_RADIUS_M = 0.75
SHAPE_ALTITUDE_M = 1.5
CIRCLE_WAYPOINT_SIDES = 24

# --- Velocity pattern tuning (open-loop continuous shapes) ---
# The loop period sets how long one full pattern takes; the traced size scales
# with max_speed * period.
CIRCLE_PERIOD_S = 6.0
SPIRAL_PERIOD_S = 20.0
SPIRAL_TURNS = 4
FIGURE8_PERIOD_S = 8.0
FIGURE8_LEFT_SCALE = 0.8
WAVE_PERIOD_S = 5.0
WAVE_FORWARD_NORM = 0.25
WAVE_SIDE_NORM = 0.6


def _regular_polygon_velocity(sides, side_seconds, speed=SIDE_SPEED_NORM):
    """Velocity segments tracing a regular polygon at constant heading.

    Each side points at an evenly spaced angle in the body plane (forward=+x,
    left=+y). Equally spaced unit directions sum to zero, so the ideal path
    closes; real flight drifts, which is the point of the open-loop demo.
    """
    segments = []
    for k in range(sides):
        angle = k * (2.0 * math.pi / sides)
        fwd = speed * math.cos(angle)
        left = speed * math.sin(angle)
        segments.append((fwd, left, 0.0, 0.0, side_seconds))
    return segments


def _regular_polygon_waypoints(sides, radius, center, altitude,
                               start_angle=0.0):
    """Corner waypoints of a regular polygon in the ENU plane at `altitude`."""
    waypoints = []
    for k in range(sides):
        angle = start_angle + k * (2.0 * math.pi / sides)
        x = center[0] + radius * math.cos(angle)
        y = center[1] + radius * math.sin(angle)
        waypoints.append((x, y, altitude))
    return waypoints


def _circle_pattern(t):
    """Constant-speed velocity whose direction rotates: a smooth circle."""
    w = 2.0 * math.pi / CIRCLE_PERIOD_S
    return (math.cos(w * t), math.sin(w * t), 0.0, 0.0)


def _spiral_pattern(t):
    """Rotating velocity whose magnitude ramps up then down: spiral out and in.

    Natural to command with velocity; a waypoint list would need many points.
    """
    phase = (t % SPIRAL_PERIOD_S) / SPIRAL_PERIOD_S
    envelope = 1.0 - abs(2.0 * phase - 1.0)
    w = 2.0 * math.pi * SPIRAL_TURNS / SPIRAL_PERIOD_S
    return (envelope * math.cos(w * t), envelope * math.sin(w * t), 0.0, 0.0)


def _figure8_pattern(t):
    """Lissajous velocity (2:1 side-to-forward) that traces a figure eight."""
    w = 2.0 * math.pi / FIGURE8_PERIOD_S
    return (math.cos(w * t),
            FIGURE8_LEFT_SCALE * math.cos(2.0 * w * t), 0.0, 0.0)


def _wave_pattern(t):
    """Steady forward speed with a sinusoidal sideways weave: a snaking line."""
    w = 2.0 * math.pi / WAVE_PERIOD_S
    return (WAVE_FORWARD_NORM, WAVE_SIDE_NORM * math.sin(w * t), 0.0, 0.0)


# Open-loop segment shapes: timed body-frame velocity bursts, normalized to
# [-1, 1]. (forward, left, up, yaw, seconds). Straight-line shapes; these are
# the ones to compare against the closed-loop waypoint versions.
VELOCITY_SHAPES = {
    'square': _regular_polygon_velocity(4, SQUARE_SIDE_SECONDS),
    'triangle': _regular_polygon_velocity(3, TRIANGLE_SIDE_SECONDS),
}

# Open-loop velocity patterns: name -> f(t_seconds) returning a normalized
# (forward, left, up, yaw). Continuous motion that is natural to command with
# velocity but awkward as waypoints (a circle, spiral, figure eight, weave).
VELOCITY_PATTERNS = {
    'circle': _circle_pattern,
    'spiral': _spiral_pattern,
    'figure8': _figure8_pattern,
    'wave': _wave_pattern,
}

# Closed-loop: absolute ENU waypoints in meters. (x east, y north, z up)
WAYPOINT_SHAPES = {
    'square': _regular_polygon_waypoints(
        4, SHAPE_RADIUS_M, SHAPE_CENTER, SHAPE_ALTITUDE_M,
        start_angle=math.pi / 4.0),
    'triangle': _regular_polygon_waypoints(
        3, SHAPE_RADIUS_M, SHAPE_CENTER, SHAPE_ALTITUDE_M,
        start_angle=math.pi / 2.0),
    'circle': _regular_polygon_waypoints(
        CIRCLE_WAYPOINT_SIDES, SHAPE_RADIUS_M, SHAPE_CENTER, SHAPE_ALTITUDE_M),
}


class ShapeNode(Node):

    def __init__(self):
        super().__init__('shape_node')

        self.declare_parameter('control_mode', DEFAULT_CONTROL_MODE)
        self.declare_parameter('shape', DEFAULT_SHAPE)
        self.declare_parameter('publish_rate', DEFAULT_PUBLISH_RATE_HZ)
        self.declare_parameter('max_speed', DEFAULT_MAX_SPEED)
        self.declare_parameter('max_yaw_rate', DEFAULT_MAX_YAW_RATE)
        self.declare_parameter('require_offboard', True)
        self.declare_parameter('waypoint_tolerance',
                               DEFAULT_WAYPOINT_TOLERANCE_M)
        self.declare_parameter('waypoint_timeout', DEFAULT_WAYPOINT_TIMEOUT_S)
        self.declare_parameter('position_topic', DEFAULT_POSITION_TOPIC)

        self._mode = self.get_parameter('control_mode').value
        shape_name = self.get_parameter('shape').value
        publish_rate = self.get_parameter('publish_rate').value
        self._max_speed = self.get_parameter('max_speed').value
        self._max_yaw_rate = self.get_parameter('max_yaw_rate').value
        self._require_offboard = self.get_parameter('require_offboard').value
        self._waypoint_tol = self.get_parameter('waypoint_tolerance').value
        self._waypoint_timeout = self.get_parameter('waypoint_timeout').value

        self._dt = 1.0 / publish_rate

        # FCU state, read from /mavros/state for the freeze/resume gate.
        self._armed = False
        self._fcu_mode = ''
        self.create_subscription(State, '/mavros/state', self._state_cb, 10)

        # Open-loop shape progress. Advances only while active so a pause in
        # OFFBOARD resumes on the same segment.
        self._shape_clock = 0.0

        # Closed-loop shape progress.
        self._waypoint_index = 0
        self._waypoint_dwell = 0.0
        self._position = None

        if self._mode == OPEN_LOOP:
            self._pattern = VELOCITY_PATTERNS.get(shape_name)
            self._segments = VELOCITY_SHAPES.get(shape_name)
            if self._pattern is None and self._segments is None:
                available = sorted(set(VELOCITY_SHAPES) | set(VELOCITY_PATTERNS))
                raise ValueError(
                    f"shape '{shape_name}' not defined for open_loop; "
                    f'available: {available}')
            self._total_duration = (
                sum(seg[4] for seg in self._segments) if self._segments else 0.0)
            self._pub = self.create_publisher(
                TwistStamped, '/mavros/setpoint_velocity/cmd_vel', 10)
            self.create_timer(self._dt, self._tick_open_loop)
        elif self._mode == CLOSED_LOOP:
            self._waypoints = WAYPOINT_SHAPES.get(shape_name)
            if not self._waypoints:
                self._fatal_shape(shape_name, WAYPOINT_SHAPES)
            self._pub = self.create_publisher(
                PoseStamped, '/mavros/setpoint_position/local', 10)
            position_topic = self.get_parameter('position_topic').value
            # MAVROS publishes the local pose BEST_EFFORT; a RELIABLE sub gets no
            # messages. Sensor QoS is BEST_EFFORT and also accepts a RELIABLE relay.
            self.create_subscription(
                PoseStamped, position_topic, self._position_cb,
                qos_profile_sensor_data)
            self.create_timer(self._dt, self._tick_closed_loop)
        else:
            raise ValueError(
                f"control_mode must be '{OPEN_LOOP}' or '{CLOSED_LOOP}', "
                f"got '{self._mode}'")

        self.get_logger().info(
            f'Shape node started: mode={self._mode}, shape={shape_name}, '
            f'rate={publish_rate} Hz, require_offboard={self._require_offboard}')

    def _fatal_shape(self, name, registry):
        raise ValueError(
            f"shape '{name}' not defined for {self._mode}; "
            f'available: {sorted(registry)}')

    def _state_cb(self, msg: State):
        self._armed = msg.armed
        self._fcu_mode = msg.mode

    def _position_cb(self, msg: PoseStamped):
        self._position = msg.pose.position

    def _is_active(self) -> bool:
        # When require_offboard is False the shape runs unconditionally (bench
        # testing without an FCU). Otherwise it only runs under pilot control.
        if not self._require_offboard:
            return True
        return self._armed and self._fcu_mode == 'OFFBOARD'

    def _tick_open_loop(self):
        out = TwistStamped()
        out.header.stamp = self.get_clock().now().to_msg()
        if self._is_active():
            self._shape_clock += self._dt
            if self._pattern is not None:
                fwd, left, up, yaw = self._pattern(self._shape_clock)
            else:
                fwd, left, up, yaw = self._velocity_at(self._shape_clock)
            out.twist.linear.x = _clamp(fwd) * self._max_speed
            out.twist.linear.y = _clamp(left) * self._max_speed
            out.twist.linear.z = _clamp(up) * self._max_speed
            out.twist.angular.z = _clamp(yaw) * self._max_yaw_rate
        # Inactive holds zero velocity and freezes the shape clock.
        self._pub.publish(out)

    def _velocity_at(self, t: float):
        if self._total_duration <= 0.0:
            return (0.0, 0.0, 0.0, 0.0)
        phase = t % self._total_duration
        elapsed = 0.0
        for fwd, left, up, yaw, seconds in self._segments:
            elapsed += seconds
            if phase < elapsed:
                return (_clamp(fwd), _clamp(left), _clamp(up), _clamp(yaw))
        last = self._segments[-1]
        return (_clamp(last[0]), _clamp(last[1]), _clamp(last[2]),
                _clamp(last[3]))

    def _tick_closed_loop(self):
        if self._is_active():
            self._waypoint_dwell += self._dt
            if self._reached_target() or self._dwell_timed_out():
                self._advance_waypoint()
        # Always publish the current target so a valid setpoint stream exists
        # for PX4 to accept OFFBOARD on re-entry.
        target = self._waypoints[self._waypoint_index]
        out = PoseStamped()
        out.header.stamp = self.get_clock().now().to_msg()
        out.header.frame_id = SETPOINT_FRAME_ID
        out.pose.position.x = float(target[0])
        out.pose.position.y = float(target[1])
        out.pose.position.z = float(target[2])
        # Identity quaternion holds a fixed heading so the shape does not spin.
        out.pose.orientation.w = 1.0
        self._pub.publish(out)

    def _reached_target(self) -> bool:
        if self._position is None:
            return False
        target = self._waypoints[self._waypoint_index]
        dx = self._position.x - target[0]
        dy = self._position.y - target[1]
        dz = self._position.z - target[2]
        return math.sqrt(dx * dx + dy * dy + dz * dz) <= self._waypoint_tol

    def _dwell_timed_out(self) -> bool:
        return self._waypoint_dwell >= self._waypoint_timeout

    def _advance_waypoint(self):
        self._waypoint_index = (self._waypoint_index + 1) % len(self._waypoints)
        self._waypoint_dwell = 0.0


def _clamp(value: float) -> float:
    return max(-NORM_LIMIT, min(NORM_LIMIT, value))


def main(args=None):
    rclpy.init(args=args)
    node = ShapeNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
