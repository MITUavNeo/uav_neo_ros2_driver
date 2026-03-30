"""Launch MAVROS, RealSense D435i, and Arducam together for UAV Neo teleop.

Adds topic relays so the student library can use simplified names:
    /camera/forward  ← /camera/color/image_raw
    /camera/depth    ← /camera/depth/image_rect_raw
    /camera/nadir    ← /arducam/camera/image_raw
    /imu             ← fused by student library (RealSense + MAVROS)
    /nav             ← /mavros/global_position/global
    /velocity        ← /mavros/local_position/velocity_body
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, \
    TimerAction, ExecuteProcess
from launch.conditions import LaunchConfigurationEquals, LaunchConfigurationNotEquals
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
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
        default_value='false',
        description='Align depth frames to color camera')

    depth_profile_arg = DeclareLaunchArgument(
        'depth_profile',
        default_value='640x480x15',
        description='Depth and infrared stream profile (widthxheightxfps)')

    color_profile_arg = DeclareLaunchArgument(
        'color_profile',
        default_value='640x480x15',
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

    # Arducam arguments
    arducam_width_arg = DeclareLaunchArgument(
        'arducam_width',
        default_value='640',
        description='Arducam image width')

    arducam_height_arg = DeclareLaunchArgument(
        'arducam_height',
        default_value='480',
        description='Arducam image height')

    arducam_framerate_arg = DeclareLaunchArgument(
        'arducam_framerate',
        default_value='30',
        description='Arducam framerate')

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

    # EdgeTPU arguments
    edgetpu_enable_arg = DeclareLaunchArgument(
        'edgetpu_enable',
        default_value='false',
        description='Enable EdgeTPU inference node (true/false)')

    edgetpu_config_arg = DeclareLaunchArgument(
        'edgetpu_config',
        default_value=os.path.join(pkg_dir, 'config', 'edgetpu.yaml'),
        description='Path to EdgeTPU config YAML')

    # Include EdgeTPU launch (delayed 3s to allow RealSense to start publishing)
    edgetpu_launch = TimerAction(
        period=3.0,
        actions=[
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    os.path.join(launch_dir, 'edgetpu.launch.py')),
                launch_arguments={
                    'edgetpu_config': LaunchConfiguration('edgetpu_config'),
                }.items(),
            ),
        ],
        condition=LaunchConfigurationEquals('edgetpu_enable', 'true'),
    )

    # Include Arducam launch (delayed 5s to avoid USB contention with RealSense init)
    arducam_launch = TimerAction(
        period=5.0,
        actions=[
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    os.path.join(launch_dir, 'arducam.launch.py')),
                launch_arguments={
                    'image_width': LaunchConfiguration('arducam_width'),
                    'image_height': LaunchConfiguration('arducam_height'),
                    'framerate': LaunchConfiguration('arducam_framerate'),
                }.items(),
            ),
        ],
    )

    # -----------------------------------------------------------------
    # Joy node: external Xbox controller for autonomy operator
    # -----------------------------------------------------------------
    joy_device_arg = DeclareLaunchArgument(
        'joy_device',
        default_value='/dev/input/js0',
        description='Joystick device path')

    joy_node = Node(
        package='joy',
        executable='joy_node',
        name='joy_node',
        output='log',
        parameters=[{
            'device_id': 0,
            'deadzone': 0.05,
            'autorepeat_rate': 20.0,
        }],
    )

    # -----------------------------------------------------------------
    # Mux node: arbitrates manual/auto velocity commands
    # -----------------------------------------------------------------
    mux_config_arg = DeclareLaunchArgument(
        'mux_config',
        default_value=os.path.join(pkg_dir, 'config', 'mux.yaml'),
        description='Path to mux node config YAML')

    mux_node = Node(
        package='uav_neo_ros2_driver',
        executable='mux_node',
        name='mux_node',
        output='screen',
        parameters=[
            LaunchConfiguration('mux_config'),
        ],
    )

    # -----------------------------------------------------------------
    # Topic relays: map driver topics to simplified student library names
    # -----------------------------------------------------------------
    relay_forward = ExecuteProcess(
        cmd=['ros2', 'run', 'topic_tools', 'relay',
             '/camera/color/image_raw', '/camera/forward'],
        output='log',
    )
    relay_depth = ExecuteProcess(
        cmd=['ros2', 'run', 'topic_tools', 'relay',
             '/camera/depth/image_rect_raw', '/camera/depth'],
        output='log',
    )
    relay_nadir = ExecuteProcess(
        cmd=['ros2', 'run', 'topic_tools', 'relay',
             '/arducam/camera/image_raw', '/camera/nadir'],
        output='log',
    )
    relay_nav = ExecuteProcess(
        cmd=['ros2', 'run', 'topic_tools', 'relay',
             '/mavros/global_position/global', '/nav'],
        output='log',
    )
    relay_velocity = ExecuteProcess(
        cmd=['ros2', 'run', 'topic_tools', 'relay',
             '/mavros/local_position/velocity_body', '/velocity'],
        output='log',
    )

    return LaunchDescription([
        fcu_url_arg,
        gcs_url_arg,
        pointcloud_arg,
        align_depth_arg,
        depth_profile_arg,
        color_profile_arg,
        arducam_width_arg,
        arducam_height_arg,
        arducam_framerate_arg,
        edgetpu_enable_arg,
        edgetpu_config_arg,
        joy_device_arg,
        mux_config_arg,
        mavros_launch,
        joy_node,
        mux_node,
        realsense_launch,
        arducam_launch,
        edgetpu_launch,
        relay_forward,
        relay_depth,
        relay_nadir,
        relay_nav,
        relay_velocity,
    ])
