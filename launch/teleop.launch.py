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


"""Launch MAVROS, RealSense D435i, and Arducam together for UAV Neo teleop.

Adds topic relays so the student library can use simplified names:
    /camera/forward  <- /camera/color/image_raw
    /camera/depth    <- /camera/depth/image_rect_raw
    /camera/nadir    <- /arducam/camera/image_raw
    /imu             <- fused by student library (RealSense + MAVROS)
    /nav             <- /mavros/global_position/global
    /velocity        <- /mavros/local_position/velocity_body
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, \
    IncludeLaunchDescription, TimerAction
from launch.conditions import LaunchConfigurationEquals
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


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

    # Include EdgeTPU launch (short stagger so the camera topics are up before
    # edgetpu_node subscribes). The M.2 Apex is bound at boot, so the old 10s
    # USB-firmware-enumeration wait is no longer needed.
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

    # Gamepad: normalizes /joy sticks into /gamepad/cmd_vel for the mux, so a
    # pilot can fly manually (LB held) without running student-library code.
    gamepad_node = Node(
        package='uav_neo_ros2_driver',
        executable='gamepad_node',
        name='gamepad_node',
        output='log',
        parameters=[os.path.join(pkg_dir, 'config', 'gamepad.yaml')],
    )

    # Mux: launched via standalone mux.launch.py so the watchdog can
    # restart it without re-spawning the rest of the teleop stack.
    mux_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(launch_dir, 'mux.launch.py')),
    )

    # RealSense is mounted upside down, so its color and depth relays rotate the
    # image 180 degrees. Toggle with realsense_flip (the downward Arducam is
    # never rotated).
    realsense_flip_arg = DeclareLaunchArgument(
        'realsense_flip',
        default_value='true',
        description='Rotate RealSense color and depth 180 deg (upside-down mount)')

    # Image relays: sensor-data QoS to match RealSense/gscam publishers
    # (topic_tools/relay defaults to RELIABLE and silently drops here).
    image_relay = os.path.join(pkg_dir, 'scripts', 'image_relay.py')
    image_relay_specs = [
        ('/camera/color/image_raw',       '/camera/forward', True),
        ('/camera/depth/image_rect_raw',  '/camera/depth',   True),
        ('/arducam/camera/image_raw',     '/camera/nadir',   False),
    ]
    image_relays = []
    for src, dst, flip in image_relay_specs:
        cmd = ['python3', image_relay, src, dst]
        if flip:
            cmd.append(LaunchConfiguration('realsense_flip'))
        image_relays.append(ExecuteProcess(cmd=cmd, output='log'))

    # MAVROS topics are published RELIABLE, so topic_tools/relay works fine.
    topic_tools_relays = [
        ExecuteProcess(
            cmd=['ros2', 'run', 'topic_tools', 'relay', src, dst],
            output='log',
        )
        for src, dst in [
            ('/mavros/global_position/global',       '/nav'),
            ('/mavros/local_position/velocity_body', '/velocity'),
        ]
    ]

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
        realsense_flip_arg,
        mavros_launch,
        joy_node,
        gamepad_node,
        mux_launch,
        realsense_launch,
        arducam_launch,
        edgetpu_launch,
        *image_relays,
        *topic_tools_relays,
    ])
