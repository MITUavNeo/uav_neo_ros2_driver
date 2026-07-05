"""Launch MAVROS for UAV Neo with PX4 Pixhawk over UART."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_dir = get_package_share_directory('uav_neo_ros2_driver')

    # Launch arguments
    fcu_url_arg = DeclareLaunchArgument(
        'fcu_url',
        default_value='/dev/ttyAMA0:921600',
        description='FCU connection URL (serial port:baud)'
    )

    gcs_url_arg = DeclareLaunchArgument(
        'gcs_url',
        default_value='',
        description='GCS bridge URL (e.g. udp://:14550@ for QGroundControl)'
    )

    tgt_system_arg = DeclareLaunchArgument(
        'tgt_system',
        default_value='1',
        description='MAVLink target system ID'
    )

    tgt_component_arg = DeclareLaunchArgument(
        'tgt_component',
        default_value='1',
        description='MAVLink target component ID'
    )

    # Config files
    config_yaml = os.path.join(pkg_dir, 'config', 'mavros_px4.yaml')
    pluginlists_yaml = os.path.join(pkg_dir, 'config', 'mavros_pluginlists.yaml')

    # MAVROS node
    mavros_node = Node(
        package='mavros',
        executable='mavros_node',
        namespace='mavros',
        output='screen',
        parameters=[
            config_yaml,
            pluginlists_yaml,
            {
                'fcu_url': LaunchConfiguration('fcu_url'),
                'gcs_url': LaunchConfiguration('gcs_url'),
                'tgt_system': LaunchConfiguration('tgt_system'),
                'tgt_component': LaunchConfiguration('tgt_component'),
                'fcu_protocol': 'v2.0',
            }
        ],
    )

    return LaunchDescription([
        fcu_url_arg,
        gcs_url_arg,
        tgt_system_arg,
        tgt_component_arg,
        mavros_node,
    ])
