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


"""Standalone launch for mux_node.

Used by the watchdog to restart the mux without re-spawning the rest of
the teleop stack (mavros/realsense/arducam/relays) which would duplicate
node instances fighting over the same USB devices.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_dir = get_package_share_directory('uav_neo_ros2_driver')

    mux_config_arg = DeclareLaunchArgument(
        'mux_config',
        default_value=os.path.join(pkg_dir, 'config', 'mux.yaml'),
        description='Path to mux node config YAML')

    mux_node = Node(
        package='uav_neo_ros2_driver',
        executable='mux_node',
        name='mux_node',
        output='screen',
        parameters=[LaunchConfiguration('mux_config')],
    )

    return LaunchDescription([mux_config_arg, mux_node])
