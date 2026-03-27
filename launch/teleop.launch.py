"""Launch MAVROS and RealSense D435i together for UAV Neo teleop."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    pkg_dir = get_package_share_directory('uav_neo_ros2_driver')
    launch_dir = os.path.join(pkg_dir, 'launch')

    # MAVROS arguments
    fcu_url_arg = DeclareLaunchArgument(
        'fcu_url',
        default_value='/dev/ttyAMA0:921600',
        description='FCU connection URL (serial port:baud)')

    gcs_url_arg = DeclareLaunchArgument(
        'gcs_url',
        default_value='',
        description='GCS bridge URL (e.g. udp://:14550@ for QGroundControl)')

    # RealSense arguments
    pointcloud_arg = DeclareLaunchArgument(
        'pointcloud_enable',
        default_value='false',
        description='Enable point cloud generation (CPU intensive on Pi 5)')

    align_depth_arg = DeclareLaunchArgument(
        'align_depth_enable',
        default_value='true',
        description='Align depth frames to color camera')

    depth_profile_arg = DeclareLaunchArgument(
        'depth_profile',
        default_value='640x480x30',
        description='Depth and infrared stream profile (widthxheightxfps)')

    color_profile_arg = DeclareLaunchArgument(
        'color_profile',
        default_value='640x480x30',
        description='Color stream profile (widthxheightxfps)')

    # Include MAVROS launch
    mavros_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(launch_dir, 'mavros.launch.py')),
        launch_arguments={
            'fcu_url': LaunchConfiguration('fcu_url'),
            'gcs_url': LaunchConfiguration('gcs_url'),
        }.items(),
    )

    # Include RealSense launch
    realsense_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(launch_dir, 'realsense.launch.py')),
        launch_arguments={
            'pointcloud_enable': LaunchConfiguration('pointcloud_enable'),
            'align_depth_enable': LaunchConfiguration('align_depth_enable'),
            'depth_profile': LaunchConfiguration('depth_profile'),
            'color_profile': LaunchConfiguration('color_profile'),
        }.items(),
    )

    return LaunchDescription([
        fcu_url_arg,
        gcs_url_arg,
        pointcloud_arg,
        align_depth_arg,
        depth_profile_arg,
        color_profile_arg,
        mavros_launch,
        realsense_launch,
    ])
