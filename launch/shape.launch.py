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


"""Standalone launch for the LED shape flight.

Brings up the minimum stack the shape node needs, so it can replace the teleop
service on boot: MAVROS (setpoint + state topics) and shape_node. No cameras,
joy, mux, or gamepad. closed_loop mode reads the FCU pose
(/mavros/local_position/pose) directly, so no relay is launched. Set
mavros:=false to run only the shape node against a MAVROS that is already up
(e.g. under teleop or the simulator).
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_dir = get_package_share_directory('uav_neo_ros2_driver')
    launch_dir = os.path.join(pkg_dir, 'launch')

    fcu_url_arg = DeclareLaunchArgument(
        'fcu_url',
        default_value='/dev/ttyAMA0:921600',
        description='FCU connection URL (serial port:baud)')

    gcs_url_arg = DeclareLaunchArgument(
        'gcs_url',
        default_value='',
        description='GCS bridge URL (e.g. udp://:14550@ for QGroundControl)')

    mavros_arg = DeclareLaunchArgument(
        'mavros',
        default_value='true',
        description='Bring up MAVROS and the /position relay; set false when '
                    'MAVROS is already running (teleop or simulator)')

    shape_config_arg = DeclareLaunchArgument(
        'shape_config',
        default_value=os.path.join(pkg_dir, 'config', 'shape.yaml'),
        description='Path to shape node config YAML')

    mavros_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(launch_dir, 'mavros.launch.py')),
        launch_arguments={
            'fcu_url': LaunchConfiguration('fcu_url'),
            'gcs_url': LaunchConfiguration('gcs_url'),
        }.items(),
        condition=IfCondition(LaunchConfiguration('mavros')),
    )

    shape_node = Node(
        package='uav_neo_ros2_driver',
        executable='shape_node',
        name='shape_node',
        output='screen',
        parameters=[LaunchConfiguration('shape_config')],
    )

    return LaunchDescription([
        fcu_url_arg,
        gcs_url_arg,
        mavros_arg,
        shape_config_arg,
        mavros_launch,
        shape_node,
    ])
