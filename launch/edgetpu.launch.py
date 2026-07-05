"""Launch EdgeTPU inference node for UAV Neo.

By default, loads parameters from config/edgetpu.yaml. Launch arguments
override individual parameters from the config file.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_dir = get_package_share_directory('uav_neo_ros2_driver')
    default_config = os.path.join(pkg_dir, 'config', 'edgetpu.yaml')

    config_arg = DeclareLaunchArgument(
        'edgetpu_config',
        default_value=default_config,
        description='Path to EdgeTPU node config YAML')

    score_threshold_arg = DeclareLaunchArgument(
        'score_threshold',
        default_value='-1.0',
        description='Override score threshold (-1 = use config file value)')

    image_topic_arg = DeclareLaunchArgument(
        'image_topic',
        default_value='',
        description='Override image topic (empty = use config file value)')

    edgetpu_node = Node(
        package='uav_neo_ros2_driver',
        executable='edgetpu_node',
        name='edgetpu_node',
        output='screen',
        parameters=[
            LaunchConfiguration('edgetpu_config'),
        ],
    )

    return LaunchDescription([
        config_arg,
        score_threshold_arg,
        image_topic_arg,
        edgetpu_node,
    ])
