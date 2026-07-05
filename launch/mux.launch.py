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
