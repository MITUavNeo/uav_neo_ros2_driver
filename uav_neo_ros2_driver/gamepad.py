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


"""Gamepad teleop node for UAV Neo.

Reads the Xbox controller (/joy), normalizes the sticks into a [-1, 1]
body-velocity command, and publishes it to /gamepad/cmd_vel. The mux arbitrates
between this manual source (LB held) and the student autonomy source (RB held),
applies the speed limits, and forwards to MAVROS. This lets a pilot fly manually
without running any student-library code.

Stick mapping (Mode 2), each normalized to [-1, 1]:
    right stick Y -> pitch    (linear.x, forward +)
    right stick X -> roll     (linear.y, left +)
    left stick Y  -> throttle (linear.z, up +)
    left stick X  -> yaw      (angular.z)

The stick axis -> /joy index mapping and the expected report shape come from
config/xbox_mapping.yaml. This node only normalizes; the mux owns the LB/RB
gating and the speed limits.
"""

from geometry_msgs.msg import TwistStamped
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Joy

from uav_neo_ros2_driver.controller_mapping import (
    default_mapping_path, load_mapping,
)


class GamepadNode(Node):

    def __init__(self):
        super().__init__('gamepad_node')

        self.declare_parameter('joystick_dead_zone', 0.15)
        self.declare_parameter('mapping_config', default_mapping_path())
        self._dz = self.get_parameter('joystick_dead_zone').value

        mapping = load_mapping(self.get_parameter('mapping_config').value)
        ax = mapping['axes']
        self._LEFT_X = ax['left_x']
        self._LEFT_Y = ax['left_y']
        self._RIGHT_X = ax['right_x']
        self._RIGHT_Y = ax['right_y']
        self._exp_axes = mapping.get('report', {}).get('axes')
        self._min_axes = max(self._LEFT_X, self._LEFT_Y,
                             self._RIGHT_X, self._RIGHT_Y) + 1
        self._warned_mode = False

        self._pub = self.create_publisher(TwistStamped, '/gamepad/cmd_vel', 10)
        self.create_subscription(Joy, '/joy', self._joy_cb, 10)

        self.get_logger().info(
            f'Gamepad node started: sticks=axes['
            f'{self._LEFT_X},{self._LEFT_Y},{self._RIGHT_X},{self._RIGHT_Y}], '
            f'dead_zone={self._dz}, publishing /gamepad/cmd_vel'
        )

    def _joy_cb(self, msg: Joy):
        wrong = (self._exp_axes is not None and len(msg.axes) != self._exp_axes)
        if len(msg.axes) < self._min_axes or wrong:
            if not self._warned_mode:
                self._warned_mode = True
                self.get_logger().warn(
                    f'/joy has {len(msg.axes)} axes, expected {self._exp_axes} '
                    '(XInput mode); not publishing gamepad commands until the '
                    'controller is in the right mode.'
                )
            return

        out = TwistStamped()
        out.header.stamp = self.get_clock().now().to_msg()
        out.twist.linear.x = self._dead_zone(msg.axes[self._RIGHT_Y])
        out.twist.linear.y = self._dead_zone(-msg.axes[self._RIGHT_X])
        out.twist.linear.z = self._dead_zone(msg.axes[self._LEFT_Y])
        out.twist.angular.z = self._dead_zone(-msg.axes[self._LEFT_X])
        self._pub.publish(out)

    def _dead_zone(self, value: float) -> float:
        dz = self._dz
        if abs(value) < dz:
            return 0.0
        sign = 1.0 if value > 0 else -1.0
        return sign * (abs(value) - dz) / (1.0 - dz)


def main(args=None):
    rclpy.init(args=args)
    node = GamepadNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
