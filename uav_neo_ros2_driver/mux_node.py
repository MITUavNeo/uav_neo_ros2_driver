"""Velocity command mux for UAV Neo.

Arbitrates between manual (Xbox controller) and auto (student code) velocity
commands based on the Xbox controller's bumper state:

    LB held  -> manual mode: Xbox sticks drive the drone
    RB held  -> auto mode:   student code drives the drone
    Neither  -> idle:        zero velocity (hover)

Publishes the selected command to /mavros/setpoint_velocity/cmd_vel
at a fixed rate. All commands are scaled by max_speed from config.

If the Xbox controller disconnects (no /joy message for >500ms), the mux
treats it as idle and publishes zero velocity regardless of the last
bumper state.

The button/axis -> /joy index mapping (LB, RB, and the four stick axes) is
loaded from config/xbox_mapping.yaml so it can be re-mapped for a different
controller without editing this file.

The safety pilot on the RC transmitter always has override authority at the
PX4 level by switching out of OFFBOARD mode.
"""

import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Joy
from geometry_msgs.msg import TwistStamped

from uav_neo_ros2_driver.controller_mapping import (
    default_mapping_path, load_mapping,
)


class MuxNode(Node):

    # If no Joy message received for this many seconds, treat as disconnected
    _JOY_TIMEOUT = 0.5

    def __init__(self):
        super().__init__('mux_node')

        # Parameters
        self.declare_parameter('max_speed', 0.5)
        self.declare_parameter('max_yaw_rate', 0.5)
        self.declare_parameter('joystick_dead_zone', 0.15)
        self.declare_parameter('publish_rate', 20.0)
        self.declare_parameter('mapping_config', default_mapping_path())

        self._max_speed = self.get_parameter('max_speed').value
        self._max_yaw_rate = self.get_parameter('max_yaw_rate').value
        self._joy_dz = self.get_parameter('joystick_dead_zone').value
        publish_rate = self.get_parameter('publish_rate').value

        # Controller button/axis -> /joy index mapping (shared config file)
        mapping_path = self.get_parameter('mapping_config').value
        mapping = load_mapping(mapping_path)
        btn, ax = mapping['buttons'], mapping['axes']
        self._LB = btn['lb']
        self._RB = btn['rb']
        self._LEFT_X = ax['left_x']
        self._LEFT_Y = ax['left_y']
        self._RIGHT_X = ax['right_x']
        self._RIGHT_Y = ax['right_y']

        # Expected /joy report shape for the standardized controller mode. A
        # frame that does not match is from a wrong-mode controller and is
        # treated as idle (zero velocity) rather than mis-read into flight
        # commands.
        report = mapping.get('report', {})
        self._exp_buttons = report.get('buttons')
        self._exp_axes = report.get('axes')
        self._warned_mode = False

        # Store latest raw Joy message and timestamp
        self._latest_joy = None
        self._joy_stamp = 0.0
        self._auto_cmd = TwistStamped()
        self._joy_connected = False

        # Subscribers
        self.create_subscription(Joy, '/joy', self._joy_cb, 10)
        self.create_subscription(
            TwistStamped, '/mux/cmd_vel', self._auto_cb, 10
        )

        # Publisher
        self._pub = self.create_publisher(
            TwistStamped,
            '/mavros/setpoint_velocity/cmd_vel',
            10,
        )

        # Timer
        self.create_timer(1.0 / publish_rate, self._publish)

        self.get_logger().info(
            f'Mux started: max_speed={self._max_speed} m/s, '
            f'max_yaw={self._max_yaw_rate} rad/s, '
            f'rate={publish_rate} Hz, '
            f'joy_timeout={self._JOY_TIMEOUT}s'
        )
        self.get_logger().info(
            f'Controller mapping: LB=btn{self._LB}, RB=btn{self._RB}, '
            f'sticks=axes[{self._LEFT_X},{self._LEFT_Y},'
            f'{self._RIGHT_X},{self._RIGHT_Y}] (from {mapping_path or "defaults"})'
        )

    def _joy_cb(self, msg: Joy):
        self._latest_joy = msg
        self._joy_stamp = time.monotonic()
        if not self._joy_connected:
            self._joy_connected = True
            self.get_logger().info('Xbox controller connected')

    def _auto_cb(self, msg: TwistStamped):
        self._auto_cmd.twist.linear.x = (
            max(-1.0, min(1.0, msg.twist.linear.x)) * self._max_speed
        )
        self._auto_cmd.twist.linear.y = (
            max(-1.0, min(1.0, msg.twist.linear.y)) * self._max_speed
        )
        self._auto_cmd.twist.linear.z = (
            max(-1.0, min(1.0, msg.twist.linear.z)) * self._max_speed
        )
        self._auto_cmd.twist.angular.z = (
            max(-1.0, min(1.0, msg.twist.angular.z)) * self._max_yaw_rate
        )

    def _publish(self):
        out = TwistStamped()
        out.header.stamp = self.get_clock().now().to_msg()

        joy = self._latest_joy

        # Check for controller disconnect
        if joy is None or (time.monotonic() - self._joy_stamp) > self._JOY_TIMEOUT:
            if self._joy_connected and joy is not None:
                self._joy_connected = False
                self.get_logger().warn('Xbox controller disconnected; publishing zero velocity')
            self._pub.publish(out)
            return

        # Reject a wrong-mode controller (report shape mismatch) as idle rather
        # than mis-reading its axes into flight commands.
        if ((self._exp_buttons is not None and len(joy.buttons) != self._exp_buttons)
                or (self._exp_axes is not None and len(joy.axes) != self._exp_axes)):
            if not self._warned_mode:
                self._warned_mode = True
                self.get_logger().warn(
                    f'Controller report {len(joy.buttons)} buttons / {len(joy.axes)} '
                    f'axes != expected {self._exp_buttons} / {self._exp_axes}; '
                    'wrong controller mode, holding zero velocity. '
                    'Set the controller to XInput mode (see config/xbox_mapping.yaml).'
                )
            self._pub.publish(out)
            return

        lb_held = (len(joy.buttons) > self._LB and bool(joy.buttons[self._LB]))
        rb_held = (len(joy.buttons) > self._RB and bool(joy.buttons[self._RB]))

        if lb_held and not rb_held:
            # Manual mode: build command from latest joy axes
            if len(joy.axes) > max(self._RIGHT_X, self._RIGHT_Y, self._LEFT_X, self._LEFT_Y):
                pitch = self._apply_dead_zone(joy.axes[self._RIGHT_Y]) * self._max_speed
                roll = self._apply_dead_zone(-joy.axes[self._RIGHT_X]) * self._max_speed
                throttle = self._apply_dead_zone(joy.axes[self._LEFT_Y]) * self._max_speed
                yaw = self._apply_dead_zone(-joy.axes[self._LEFT_X]) * self._max_yaw_rate

                out.twist.linear.x = pitch
                out.twist.linear.y = roll
                out.twist.linear.z = throttle
                out.twist.angular.z = yaw

        elif rb_held and not lb_held:
            # Auto mode: student code
            out.twist = self._auto_cmd.twist

        # else: neither or both -> zero velocity (hover)

        self._pub.publish(out)

    def _apply_dead_zone(self, value: float) -> float:
        dz = self._joy_dz
        if abs(value) < dz:
            return 0.0
        sign = 1.0 if value > 0 else -1.0
        return sign * (abs(value) - dz) / (1.0 - dz)


def main(args=None):
    rclpy.init(args=args)
    node = MuxNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
