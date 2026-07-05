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


"""Velocity command mux for UAV Neo.

Arbitrates between manual (gamepad node) and auto (student code) velocity
commands based on the Xbox controller's bumper state:

    LB held  -> manual mode: /gamepad/cmd_vel drives the drone
    RB held  -> auto mode:   /mux/cmd_vel (student code) drives the drone
    Neither  -> idle:        zero velocity (hover)

Both sources send a normalized [-1, 1] TwistStamped; the mux scales by
max_speed/max_yaw_rate and publishes to /mavros/setpoint_velocity/cmd_vel at a
fixed rate. A source whose command is older than the timeout holds zero.

If the Xbox controller disconnects (no /joy message for >500ms), the mux
treats it as idle and publishes zero velocity regardless of the last
bumper state.

Only the LB/RB button indices are read here, from config/xbox_mapping.yaml; the
gamepad node reads the stick axes from the same file. Re-mapping a different
controller is a YAML edit, no code change.

The safety pilot on the RC transmitter always has override authority at the
PX4 level by switching out of OFFBOARD mode.
"""

import time

from geometry_msgs.msg import TwistStamped
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Joy

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
        self.declare_parameter('publish_rate', 20.0)
        self.declare_parameter('mapping_config', default_mapping_path())

        self._max_speed = self.get_parameter('max_speed').value
        self._max_yaw_rate = self.get_parameter('max_yaw_rate').value
        publish_rate = self.get_parameter('publish_rate').value

        # LB/RB gating uses the shared controller mapping. Manual stick values
        # are normalized by the gamepad node (/gamepad/cmd_vel), not read here.
        mapping_path = self.get_parameter('mapping_config').value
        mapping = load_mapping(mapping_path)
        btn = mapping['buttons']
        self._LB = btn['lb']
        self._RB = btn['rb']

        # Expected /joy report shape for the standardized controller mode. A
        # frame that does not match is from a wrong-mode controller and is
        # treated as idle (zero velocity) rather than mis-read into flight
        # commands.
        report = mapping.get('report', {})
        self._exp_buttons = report.get('buttons')
        self._exp_axes = report.get('axes')
        self._warned_mode = False

        # Latest inputs. _auto_cmd is the student autonomy command
        # (/mux/cmd_vel); _gamepad_cmd is the manual command from the gamepad
        # node (/gamepad/cmd_vel). Both are stored already scaled to m/s.
        self._latest_joy = None
        self._joy_stamp = 0.0
        self._auto_cmd = TwistStamped()
        self._gamepad_cmd = TwistStamped()
        self._gamepad_stamp = 0.0
        self._joy_connected = False

        # Subscribers
        self.create_subscription(Joy, '/joy', self._joy_cb, 10)
        self.create_subscription(
            TwistStamped, '/mux/cmd_vel', self._auto_cb, 10
        )
        self.create_subscription(
            TwistStamped, '/gamepad/cmd_vel', self._gamepad_cb, 10
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
            f'Controller mapping: LB=btn{self._LB}, RB=btn{self._RB} '
            f'(from {mapping_path or "defaults"}); manual from /gamepad/cmd_vel'
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

    def _gamepad_cb(self, msg: TwistStamped):
        self._gamepad_cmd.twist.linear.x = (
            max(-1.0, min(1.0, msg.twist.linear.x)) * self._max_speed
        )
        self._gamepad_cmd.twist.linear.y = (
            max(-1.0, min(1.0, msg.twist.linear.y)) * self._max_speed
        )
        self._gamepad_cmd.twist.linear.z = (
            max(-1.0, min(1.0, msg.twist.linear.z)) * self._max_speed
        )
        self._gamepad_cmd.twist.angular.z = (
            max(-1.0, min(1.0, msg.twist.angular.z)) * self._max_yaw_rate
        )
        self._gamepad_stamp = time.monotonic()

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
            # Manual mode: gamepad node's normalized command (scaled to m/s in
            # _gamepad_cb). A stale command (dead gamepad node) holds zero.
            if (time.monotonic() - self._gamepad_stamp) <= self._JOY_TIMEOUT:
                out.twist = self._gamepad_cmd.twist

        elif rb_held and not lb_held:
            # Auto mode: student code
            out.twist = self._auto_cmd.twist

        # else: neither or both -> zero velocity (hover)

        self._pub.publish(out)


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
