"""Launch Intel RealSense D435i for UAV Neo."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    pkg_dir = get_package_share_directory('uav_neo_ros2_driver')
    realsense_dir = get_package_share_directory('realsense2_camera')

    # Launch arguments
    pointcloud_arg = DeclareLaunchArgument(
        'pointcloud_enable',
        default_value='false',
        description='Enable point cloud generation (CPU intensive on Pi 5)'
    )

    align_depth_arg = DeclareLaunchArgument(
        'align_depth_enable',
        default_value='true',
        description='Align depth frames to color camera'
    )

    config_yaml = os.path.join(pkg_dir, 'config', 'realsense_d435i.yaml')

    # Include the stock realsense launch with our config overlay
    realsense_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(realsense_dir, 'launch', 'rs_launch.py')
        ),
        launch_arguments={
            'config_file': config_yaml,
            'pointcloud.enable': LaunchConfiguration('pointcloud_enable'),
            'align_depth.enable': LaunchConfiguration('align_depth_enable'),
            'camera_namespace': '',
            'camera_name': 'camera',
        }.items(),
    )

    return LaunchDescription([
        pointcloud_arg,
        align_depth_arg,
        realsense_launch,
    ])
