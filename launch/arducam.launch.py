"""Launch Arducam B0578 2.3MP global shutter camera for UAV Neo.

Uses GStreamer via gscam for hardware-accelerated MJPG decode.
Default 1280x720 @ 30 FPS for optical flow. Full res (1920x1200) available via launch args.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def generate_launch_description():
    video_device_arg = DeclareLaunchArgument(
        'video_device',
        default_value='/dev/video0',
        description='V4L2 video device path for the Arducam')

    image_width_arg = DeclareLaunchArgument(
        'image_width',
        default_value='640',
        description='Image width (1920, 1280, 960, 640, 320)')

    image_height_arg = DeclareLaunchArgument(
        'image_height',
        default_value='480',
        description='Image height (1200, 1080, 720, 600, 480, 240)')

    framerate_arg = DeclareLaunchArgument(
        'framerate',
        default_value='30',
        description='Camera framerate as integer (max depends on resolution)')

    # Build GStreamer pipeline string from launch arguments.
    # The leaky queue decouples decode from the appsink so the pipeline
    # doesn't stall under CPU load.  The actual memory-leak fix
    # (ros-drivers/gscam#63) is in our patched gscam build which sets
    # appsink max-buffers=1 drop=true.
    gscam_config = PythonExpression([
        "'v4l2src device=", LaunchConfiguration('video_device'),
        ' ! image/jpeg,width=', LaunchConfiguration('image_width'),
        ',height=', LaunchConfiguration('image_height'),
        ',framerate=', LaunchConfiguration('framerate'),
        '/1 ! jpegdec ! videoconvert'
        ' ! queue max-size-buffers=2 leaky=downstream'
        " ! videorate ! video/x-raw,framerate=20/1'"
    ])

    arducam_node = Node(
        package='gscam',
        executable='gscam_node',
        namespace='/arducam',
        name='gscam_publisher',
        output='screen',
        parameters=[{
            'gscam_config': gscam_config,
            'camera_name': 'arducam',
            'frame_id': 'arducam_optical_frame',
        }],
    )

    return LaunchDescription([
        video_device_arg,
        image_width_arg,
        image_height_arg,
        framerate_arg,
        arducam_node,
    ])
