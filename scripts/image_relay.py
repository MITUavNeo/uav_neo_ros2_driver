#!/usr/bin/env python3
"""QoS-matched image relay with optional 180-degree rotation.

topic_tools/relay uses RELIABLE QoS by default, which does not match
BEST_EFFORT image publishers, so messages never flow. This relay matches
sensor-data QoS.

The RealSense is mounted upside down on the airframe, so its color and depth
streams are rotated 180 degrees here (pass "rotate180" as the third argument)
to present an upright image to the student library and downstream nodes.

Usage: image_relay.py <input_topic> <output_topic> [rotate180]
"""

import sys

import numpy as np
import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image


def rotate_180(msg):
    """Rotate an Image message 180 degrees (reverse rows and columns).

    Operates on the raw byte buffer, so it works for any packed encoding
    (rgb8/bgr8 color and 16UC1 depth). Returns the message untouched if the row
    is padded (step does not divide evenly into pixels).
    """
    h, w, step = msg.height, msg.width, msg.step
    if w == 0 or step % w != 0:
        return msg
    bpp = step // w
    arr = np.frombuffer(msg.data, dtype=np.uint8).reshape(h, w, bpp)
    # Reverse rows and columns; keep each pixel's bytes in order.
    msg.data = arr[::-1, ::-1, :].tobytes()
    return msg


def main():
    if len(sys.argv) < 3:
        print('usage: image_relay.py <input_topic> <output_topic> [rotate180]',
              file=sys.stderr)
        sys.exit(2)

    in_topic, out_topic = sys.argv[1], sys.argv[2]
    rotate = len(sys.argv) > 3 and sys.argv[3].lower() in ('1', 'true', 'rotate180')

    rclpy.init()
    node = rclpy.create_node('image_relay_' + out_topic.strip('/').replace('/', '_'))

    pub = node.create_publisher(Image, out_topic, qos_profile_sensor_data)
    if rotate:
        node.create_subscription(
            Image, in_topic, lambda m: pub.publish(rotate_180(m)),
            qos_profile_sensor_data)
        node.get_logger().info(f'relaying {in_topic} -> {out_topic} (rotated 180)')
    else:
        node.create_subscription(Image, in_topic, pub.publish,
                                 qos_profile_sensor_data)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
