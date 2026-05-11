#!/usr/bin/env python3
"""QoS-matched image relay. topic_tools/relay uses RELIABLE QoS by default,
which does not match BEST_EFFORT image publishers, so messages never flow."""

import sys

import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image


def main():
    if len(sys.argv) < 3:
        print("usage: image_relay.py <input_topic> <output_topic>", file=sys.stderr)
        sys.exit(2)

    in_topic, out_topic = sys.argv[1], sys.argv[2]

    rclpy.init()
    node = rclpy.create_node("image_relay_" + out_topic.strip("/").replace("/", "_"))

    pub = node.create_publisher(Image, out_topic, qos_profile_sensor_data)
    node.create_subscription(Image, in_topic, pub.publish, qos_profile_sensor_data)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
