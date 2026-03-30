"""EdgeTPU inference node for UAV Neo.

Subscribes to a color image topic, runs object detection on the Coral EdgeTPU,
and publishes Detection2DArray results to /edgetpu/inference.
"""

import os
import time

import numpy as np
from pycoral.utils.edgetpu import list_edge_tpus, make_interpreter

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from ament_index_python.packages import get_package_share_directory
from cv_bridge import CvBridge
from sensor_msgs.msg import Image
from vision_msgs.msg import (
    BoundingBox2D,
    Detection2D,
    Detection2DArray,
    ObjectHypothesisWithPose,
    ObjectHypothesis,
    Pose2D,
    Point2D,
)
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue


class EdgeTPUNode(Node):

    def __init__(self):
        super().__init__('edgetpu_node')

        # Parameters
        self.declare_parameter('model_path', '')
        self.declare_parameter('labels_path', '')
        self.declare_parameter('score_threshold', 0.5)
        self.declare_parameter('max_detections', 0)
        self.declare_parameter('image_topic', '/camera/color/image_raw')
        self.declare_parameter('diagnostics_period', 1.0)
        self.declare_parameter('image_timeout', 5.0)

        model_path = self.get_parameter('model_path').value
        labels_path = self.get_parameter('labels_path').value
        self.score_threshold = self.get_parameter('score_threshold').value
        self.max_detections = self.get_parameter('max_detections').value
        image_topic = self.get_parameter('image_topic').value
        diag_period = self.get_parameter('diagnostics_period').value
        self.image_timeout = self.get_parameter('image_timeout').value

        if not model_path:
            self.get_logger().fatal('model_path parameter is required')
            raise SystemExit(1)

        # Resolve relative paths against the package share directory
        pkg_share = get_package_share_directory('uav_neo_ros2_driver')
        if not os.path.isabs(model_path):
            model_path = os.path.join(pkg_share, model_path)
        if labels_path and not os.path.isabs(labels_path):
            labels_path = os.path.join(pkg_share, labels_path)

        # Load labels
        self.labels = {}
        if labels_path:
            try:
                with open(labels_path) as f:
                    for i, line in enumerate(f):
                        line = line.strip()
                        if line:
                            self.labels[i] = line
            except FileNotFoundError:
                self.get_logger().warn(f'Labels file not found: {labels_path}')

        # Initialize EdgeTPU interpreter
        tpus = list_edge_tpus()
        if not tpus:
            self.get_logger().fatal('No EdgeTPU device detected')
            raise SystemExit(1)

        self.get_logger().info(
            f'EdgeTPU found: {tpus[0]["type"]} at {tpus[0]["path"]}'
        )

        self.interpreter = make_interpreter(model_path)
        self.interpreter.allocate_tensors()

        self.input_details = self.interpreter.get_input_details()[0]
        self.output_details = self.interpreter.get_output_details()
        _, self.model_h, self.model_w, _ = self.input_details['shape']

        # Identify output tensors by shape
        self._map_outputs()

        self.get_logger().info(
            f'Model loaded: {model_path} '
            f'(input {self.model_w}x{self.model_h}, '
            f'{len(self.labels)} label(s), '
            f'threshold {self.score_threshold})'
        )

        self.bridge = CvBridge()

        # Diagnostics state
        self._inference_count = 0
        self._detection_count = 0
        self._last_inference_ms = 0.0
        self._avg_inference_ms = 0.0
        self._last_image_time = None
        self._tpu_ok = True

        # Publishers
        self.det_pub = self.create_publisher(
            Detection2DArray, '/edgetpu/inference', 10
        )
        self.diag_pub = self.create_publisher(
            DiagnosticArray, '/diagnostics', 10
        )

        # Subscriber
        self.create_subscription(
            Image, image_topic, self._image_cb, qos_profile_sensor_data
        )

        # Diagnostics timer
        self.create_timer(diag_period, self._publish_diagnostics)

        self.get_logger().info(
            f'Subscribed to {image_topic}, publishing to /edgetpu/inference'
        )

    def _map_outputs(self):
        """Identify which output index is boxes, scores, count, classes."""
        self._idx_boxes = None
        self._idx_scores = None
        self._idx_count = None
        self._idx_classes = None

        for i, od in enumerate(self.output_details):
            shape = tuple(od['shape'])
            if len(shape) == 3 and shape[-1] == 4:
                self._idx_boxes = i
            elif shape == (1,):
                self._idx_count = i
            elif len(shape) == 2 and self._idx_scores is None:
                self._idx_scores = i
            elif len(shape) == 2:
                self._idx_classes = i

        if self._idx_boxes is None or self._idx_scores is None:
            self.get_logger().fatal(
                'Cannot identify model output layout (boxes/scores). '
                f'Output shapes: {[tuple(od["shape"]) for od in self.output_details]}'
            )
            raise SystemExit(1)

    def _image_cb(self, msg: Image):
        self._last_image_time = self.get_clock().now()

        try:
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='rgb8')
        except Exception as e:
            self.get_logger().warn(f'cv_bridge conversion failed: {e}')
            return

        img_h, img_w = cv_image.shape[:2]

        # Resize to model input
        import cv2
        resized = cv2.resize(cv_image, (self.model_w, self.model_h))
        input_tensor = np.expand_dims(resized, axis=0).astype(np.uint8)

        # Run inference
        try:
            self.interpreter.set_tensor(
                self.input_details['index'], input_tensor
            )
            t0 = time.monotonic()
            self.interpreter.invoke()
            elapsed_ms = (time.monotonic() - t0) * 1000
        except Exception as e:
            self.get_logger().error(f'EdgeTPU inference failed: {e}')
            self._tpu_ok = False
            return

        self._tpu_ok = True
        self._last_inference_ms = elapsed_ms
        self._inference_count += 1
        # Exponential moving average (alpha=0.1)
        if self._avg_inference_ms == 0.0:
            self._avg_inference_ms = elapsed_ms
        else:
            self._avg_inference_ms = 0.9 * self._avg_inference_ms + 0.1 * elapsed_ms

        # Extract outputs
        scores = self.interpreter.get_tensor(
            self.output_details[self._idx_scores]['index']
        ).flatten()
        boxes = self.interpreter.get_tensor(
            self.output_details[self._idx_boxes]['index']
        ).reshape(-1, 4)

        if self._idx_classes is not None:
            classes = self.interpreter.get_tensor(
                self.output_details[self._idx_classes]['index']
            ).flatten().astype(int)
        else:
            classes = np.zeros(len(scores), dtype=int)

        if self._idx_count is not None:
            count = int(
                self.interpreter.get_tensor(
                    self.output_details[self._idx_count]['index']
                ).flatten()[0]
            )
        else:
            count = len(scores)

        # Build Detection2DArray
        det_array = Detection2DArray()
        det_array.header = msg.header

        n_det = 0
        max_det = self.max_detections if self.max_detections > 0 else count
        for i in range(min(count, len(scores))):
            if scores[i] < self.score_threshold:
                continue
            if n_det >= max_det:
                break

            det = Detection2D()
            det.header = msg.header

            # Hypothesis
            hyp = ObjectHypothesisWithPose()
            hyp.hypothesis = ObjectHypothesis()
            class_id = int(classes[i])
            hyp.hypothesis.class_id = self.labels.get(class_id, str(class_id))
            hyp.hypothesis.score = float(scores[i])
            det.results.append(hyp)

            # Bounding box — model outputs normalized [ymin, xmin, ymax, xmax]
            ymin, xmin, ymax, xmax = boxes[i]
            cx = float((xmin + xmax) / 2.0 * img_w)
            cy = float((ymin + ymax) / 2.0 * img_h)
            w = float((xmax - xmin) * img_w)
            h = float((ymax - ymin) * img_h)

            det.bbox = BoundingBox2D()
            det.bbox.center = Pose2D()
            det.bbox.center.position = Point2D(x=cx, y=cy)
            det.bbox.center.theta = 0.0
            det.bbox.size_x = w
            det.bbox.size_y = h

            det_array.detections.append(det)
            n_det += 1

        self._detection_count += n_det
        self.det_pub.publish(det_array)

    def _publish_diagnostics(self):
        msg = DiagnosticArray()
        msg.header.stamp = self.get_clock().now().to_msg()

        status = DiagnosticStatus()
        status.name = 'EdgeTPU Inference'
        status.hardware_id = 'coral_edgetpu_usb'

        if not self._tpu_ok:
            status.level = DiagnosticStatus.ERROR
            status.message = 'EdgeTPU inference failed'
        elif self._last_image_time is None:
            status.level = DiagnosticStatus.WARN
            status.message = 'No images received yet'
        else:
            age = (self.get_clock().now() - self._last_image_time).nanoseconds / 1e9
            if age > self.image_timeout:
                status.level = DiagnosticStatus.WARN
                status.message = f'No image for {age:.1f}s'
            else:
                status.level = DiagnosticStatus.OK
                status.message = f'Running ({self._avg_inference_ms:.1f} ms avg)'

        status.values = [
            KeyValue(key='inference_count', value=str(self._inference_count)),
            KeyValue(key='detection_count', value=str(self._detection_count)),
            KeyValue(key='last_inference_ms', value=f'{self._last_inference_ms:.1f}'),
            KeyValue(key='avg_inference_ms', value=f'{self._avg_inference_ms:.1f}'),
            KeyValue(key='model_input', value=f'{self.model_w}x{self.model_h}'),
            KeyValue(key='score_threshold', value=str(self.score_threshold)),
            KeyValue(key='tpu_ok', value=str(self._tpu_ok)),
        ]

        msg.status.append(status)
        self.diag_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = EdgeTPUNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
