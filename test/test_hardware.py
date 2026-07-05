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


"""Hardware connectivity tests for UAV Neo sensors.

Verifies that all peripherals are physically connected, detected by the OS,
and accessible to the current user. These tests do NOT launch ROS2 nodes -
they check the prerequisites that the driver layer depends on.

Run with:
    colcon test --packages-select uav_neo_ros2_driver --pytest-args -k hardware
"""

import grp
import importlib
import os
import subprocess

import pytest


# ---------------------------------------------------------------------------
# Pixhawk (UART)
# ---------------------------------------------------------------------------

class TestPixhawk:
    """Pixhawk flight controller over UART (/dev/ttyAMA0)."""

    UART_DEVICE = '/dev/ttyAMA0'

    def test_uart_device_exists(self):
        """UART device node must be present (raspi-config serial enabled)."""
        assert os.path.exists(self.UART_DEVICE), (
            f'{self.UART_DEVICE} not found. '
            'Enable serial via: sudo raspi-config > Interface Options > Serial Port'
        )

    def test_uart_permissions(self):
        """Current user must have read/write access (dialout group)."""
        assert os.access(self.UART_DEVICE, os.R_OK | os.W_OK), (
            f'No read/write access to {self.UART_DEVICE}. '
            'Fix: sudo usermod -aG dialout $USER  (then re-login)'
        )

    def test_user_in_dialout_group(self):
        """User must be in the dialout group for serial access."""
        user_groups = [grp.getgrgid(g).gr_name for g in os.getgroups()]
        assert 'dialout' in user_groups, (
            'User is not in the dialout group. '
            'Fix: sudo usermod -aG dialout $USER  (then re-login)'
        )

    def test_serial_console_disabled(self):
        """Kernel must not use serial0 as console (MAVLink would be misread)."""
        with open('/proc/cmdline') as f:
            cmdline = f.read()
        assert 'console=serial0' not in cmdline, (
            'Serial console is still active on the kernel command line. '
            "Fix: sudo sed -i 's/ console=serial0,[0-9]*//' /boot/firmware/cmdline.txt "
            '&& sudo reboot'
        )

    def test_sysrq_disabled(self):
        """Verify SysRq is disabled so MAVLink bytes can't trigger kernel commands."""
        with open('/proc/sys/kernel/sysrq') as f:
            value = f.read().strip()
        assert value == '0', (
            f'kernel.sysrq = {value} (must be 0). '
            'Fix: echo "kernel.sysrq = 0" | sudo tee /etc/sysctl.d/99-disable-sysrq.conf '
            '&& sudo sysctl -p /etc/sysctl.d/99-disable-sysrq.conf'
        )

    def test_bluetooth_overlay_active(self):
        """Bluetooth must be disabled on the PL011 UART (dtoverlay=disable-bt)."""
        # If hci0 exists, Bluetooth is still using the UART
        result = subprocess.run(
            ['hciconfig', 'hci0'],
            capture_output=True, timeout=5,
        )
        assert result.returncode != 0, (
            'Bluetooth controller hci0 is still active on the UART. '
            'Fix: add "dtoverlay=disable-bt" to /boot/firmware/config.txt '
            '&& sudo systemctl disable bluetooth.service && sudo reboot'
        )


# ---------------------------------------------------------------------------
# RealSense D435i (USB 3.0)
# ---------------------------------------------------------------------------

class TestRealSense:
    """Intel RealSense D435i depth camera over USB."""

    USB_ID = '8086:0b3a'

    def _lsusb_ids(self):
        """Return set of 'vendor:product' strings from lsusb."""
        result = subprocess.run(
            ['lsusb'], capture_output=True, text=True, timeout=5,
        )
        ids = set()
        for line in result.stdout.splitlines():
            # Bus 003 Device 002: ID 8086:0b3a Intel Corp. ...
            parts = line.split('ID ')
            if len(parts) >= 2:
                ids.add(parts[1].split()[0].lower())
        return ids

    def test_usb_device_detected(self):
        """Verify the RealSense appears on the USB bus."""
        ids = self._lsusb_ids()
        assert self.USB_ID in ids, (
            f'RealSense D435i (USB ID {self.USB_ID}) not detected on USB bus. '
            'Check the USB 3.0 cable and port.'
        )

    def test_video_devices_exist(self):
        """Verify the RealSense registers V4L2 video devices."""
        result = subprocess.run(
            ['v4l2-ctl', '--list-devices'],
            capture_output=True, text=True, timeout=5,
        )
        assert 'RealSense' in result.stdout, (
            'No RealSense V4L2 devices found. '
            'Check USB connection and try: rs-enumerate-devices --compact'
        )

    def test_rs_enumerate(self):
        """Verify rs-enumerate-devices finds the D435i."""
        result = subprocess.run(
            ['rs-enumerate-devices', '--compact'],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, (
            'rs-enumerate-devices failed. '
            'Install: sudo apt install ros-jazzy-realsense2-camera'
        )
        assert 'D435I' in result.stdout or 'D435i' in result.stdout, (
            f'D435i not found in rs-enumerate-devices output:\n{result.stdout}'
        )

    def test_usb3_connection(self):
        """Verify the RealSense is on USB 3.x for full bandwidth."""
        result = subprocess.run(
            ['rs-enumerate-devices', '--compact'],
            capture_output=True, text=True, timeout=10,
        )
        output = result.stdout
        # rs-enumerate-devices --compact includes "Usb Type Descriptor: 3.2"
        # Full enumeration shows it too. Check for USB 3.x
        if 'Usb Type Descriptor' in output:
            assert '3.' in output.split('Usb Type Descriptor')[1].split('\n')[0], (
                'RealSense is not on a USB 3.x port. '
                'Depth + color + IMU at full rate requires USB 3.0+.'
            )

    def test_imu_permissions(self):
        """IIO devices for the D435i IMU must be user-accessible on Pi 5."""
        iio_base = '/sys/bus/iio/devices'
        if not os.path.isdir(iio_base):
            pytest.skip('No IIO subsystem (not running on Pi 5?)')

        iio_devices = [
            os.path.join(iio_base, d)
            for d in os.listdir(iio_base)
            if d.startswith('iio:device')
        ]
        if not iio_devices:
            pytest.skip('No IIO devices found (RealSense IMU may not be enumerated yet)')

        bad = []
        for dev in iio_devices:
            buf_enable = os.path.join(dev, 'buffer', 'enable')
            if os.path.exists(buf_enable) and not os.access(buf_enable, os.W_OK):
                bad.append(buf_enable)

        assert not bad, (
            f'IMU IIO permissions not fixed ({len(bad)} file(s) not writable). '
            'Fix: sudo /usr/local/bin/fix-realsense-imu.sh\n'
            'Or run: scripts/setup_realsense.sh'
        )


# ---------------------------------------------------------------------------
# Arducam B0578 (USB 2.0)
# ---------------------------------------------------------------------------

class TestArducam:
    """Arducam B0578 2.3MP global shutter camera over USB."""

    USB_ID = '0c45:0578'

    def _lsusb_ids(self):
        result = subprocess.run(
            ['lsusb'], capture_output=True, text=True, timeout=5,
        )
        ids = set()
        for line in result.stdout.splitlines():
            parts = line.split('ID ')
            if len(parts) >= 2:
                ids.add(parts[1].split()[0].lower())
        return ids

    def test_usb_device_detected(self):
        """Arducam must appear on the USB bus."""
        ids = self._lsusb_ids()
        assert self.USB_ID in ids, (
            f'Arducam B0578 (USB ID {self.USB_ID}) not detected on USB bus. '
            'Check the USB cable and port.'
        )

    def test_v4l2_device_listed(self):
        """Arducam must register V4L2 video devices."""
        result = subprocess.run(
            ['v4l2-ctl', '--list-devices'],
            capture_output=True, text=True, timeout=5,
        )
        assert 'Arducam' in result.stdout or 'B0578' in result.stdout, (
            'No Arducam V4L2 device found. '
            'Check USB connection and try: v4l2-ctl --list-devices'
        )

    def test_v4l2_device_accessible(self):
        """The V4L2 device node must be readable by the current user."""
        result = subprocess.run(
            ['v4l2-ctl', '--list-devices'],
            capture_output=True, text=True, timeout=5,
        )
        # Parse device paths under the Arducam entry
        lines = result.stdout.splitlines()
        arducam_devs = []
        in_arducam = False
        for line in lines:
            if 'Arducam' in line or 'B0578' in line:
                in_arducam = True
                continue
            if in_arducam:
                stripped = line.strip()
                if stripped.startswith('/dev/video'):
                    arducam_devs.append(stripped)
                elif stripped == '' or not stripped.startswith('/dev/'):
                    # Next device block or non-device line
                    if not stripped.startswith('/dev/'):
                        break

        assert arducam_devs, 'Could not parse Arducam /dev/video* paths'

        # Check the first video device (capture node)
        dev = arducam_devs[0]
        assert os.access(dev, os.R_OK | os.W_OK), (
            f'No read/write access to {dev}. '
            'Check udev rules or try: sudo chmod 666 ' + dev
        )

    def test_mjpeg_format_available(self):
        """Arducam must support MJPEG format (needed by gscam pipeline)."""
        # Find the Arducam's video device
        result = subprocess.run(
            ['v4l2-ctl', '--list-devices'],
            capture_output=True, text=True, timeout=5,
        )
        lines = result.stdout.splitlines()
        dev = None
        in_arducam = False
        for line in lines:
            if 'Arducam' in line or 'B0578' in line:
                in_arducam = True
                continue
            if in_arducam:
                stripped = line.strip()
                if stripped.startswith('/dev/video'):
                    dev = stripped
                    break

        if dev is None:
            pytest.skip('Arducam device not found for format check')

        fmt_result = subprocess.run(
            ['v4l2-ctl', '-d', dev, '--list-formats'],
            capture_output=True, text=True, timeout=5,
        )
        assert 'MJPG' in fmt_result.stdout or 'Motion-JPEG' in fmt_result.stdout, (
            f'MJPEG format not available on {dev}. '
            'The gscam pipeline requires MJPEG. Check camera firmware.'
        )


# ---------------------------------------------------------------------------
# Coral EdgeTPU (USB 3.0)
# ---------------------------------------------------------------------------

class TestCoralTPU:
    """Coral EdgeTPU USB Accelerator for ML inference."""

    # Pre-init and post-init USB IDs
    USB_ID_PRE = '1a6e:089a'   # Global Unichip (before firmware load)
    USB_ID_POST = '18d1:9302'  # Google (after firmware load)

    def _lsusb_ids(self):
        result = subprocess.run(
            ['lsusb'], capture_output=True, text=True, timeout=5,
        )
        ids = set()
        for line in result.stdout.splitlines():
            parts = line.split('ID ')
            if len(parts) >= 2:
                ids.add(parts[1].split()[0].lower())
        return ids

    def test_usb_device_detected(self):
        """Coral TPU must appear on USB bus (pre-init or post-init ID)."""
        ids = self._lsusb_ids()
        assert self.USB_ID_PRE in ids or self.USB_ID_POST in ids, (
            f'Coral EdgeTPU not detected on USB bus. '
            f'Expected {self.USB_ID_PRE} (pre-init) or {self.USB_ID_POST} (post-init). '
            'Check the USB cable and port.'
        )

    def test_libedgetpu_installed(self):
        """The libedgetpu runtime library must be installed."""
        result = subprocess.run(
            ['dpkg', '-l', 'libedgetpu1-std'],
            capture_output=True, text=True, timeout=5,
        )
        assert result.returncode == 0 and 'ii' in result.stdout, (
            'libedgetpu1-std not installed. '
            'Fix: sudo dpkg -i depend/libedgetpu1-std_*.deb  '
            'or run: scripts/setup_coral.sh'
        )

    def test_tflite_runtime_importable(self):
        """tflite_runtime Python package must be importable."""
        try:
            importlib.import_module('tflite_runtime.interpreter')
        except ImportError:
            pytest.fail(
                'tflite_runtime not installed. '
                'Fix: pip3 install --break-system-packages depend/tflite_runtime-*.whl  '
                'or run: scripts/setup_coral.sh'
            )

    def test_pycoral_importable(self):
        """Coral Python package (pycoral) must be importable."""
        try:
            importlib.import_module('pycoral.utils.edgetpu')
        except ImportError:
            pytest.fail(
                'pycoral not installed. '
                'Fix: pip3 install --break-system-packages depend/pycoral-*.whl  '
                'or run: scripts/setup_coral.sh'
            )

    def test_edgetpu_runtime_detects_tpu(self):
        """The EdgeTPU must be visible to pycoral via libedgetpu."""
        try:
            from pycoral.utils.edgetpu import list_edge_tpus
        except ImportError:
            pytest.skip('pycoral not installed')

        tpus = list_edge_tpus()
        assert len(tpus) > 0, (
            'pycoral cannot detect any EdgeTPU devices. '
            'The Coral is on the USB bus but libedgetpu cannot communicate with it. '
            'Check: 1) libedgetpu1-std is installed, '
            '2) udev rule exists at /etc/udev/rules.d/99-coral-edgetpu.rules, '
            '3) try unplugging and replugging the Coral.'
        )

    def test_edgetpu_inference(self):
        """Run a single inference on the EdgeTPU to verify the full stack works."""
        try:
            from pycoral.utils.edgetpu import make_interpreter
            import numpy as np
            import time
        except ImportError:
            pytest.skip('pycoral or numpy not installed')

        model_path = os.path.join(
            os.path.dirname(__file__), 'test_data',
            'mobilenet_v2_1.0_224_quant_edgetpu.tflite',
        )
        if not os.path.isfile(model_path):
            pytest.skip(f'Test model not found at {model_path}')

        interpreter = make_interpreter(model_path)
        interpreter.allocate_tensors()

        input_details = interpreter.get_input_details()
        output_details = interpreter.get_output_details()

        input_data = np.random.randint(
            0, 256, size=input_details[0]['shape'],
            dtype=np.uint8,
        )
        interpreter.set_tensor(input_details[0]['index'], input_data)

        # Warm-up invoke (first call loads firmware)
        interpreter.invoke()

        # Timed invoke
        start = time.monotonic()
        interpreter.set_tensor(input_details[0]['index'], input_data)
        interpreter.invoke()
        elapsed_ms = (time.monotonic() - start) * 1000

        output = interpreter.get_tensor(output_details[0]['index'])

        assert output.shape[-1] == 1001, (
            f'Expected 1001-class output, got shape {output.shape}. '
            'The EdgeTPU model may be corrupt - re-download the test model.'
        )
        assert output.sum() > 0, (
            'Inference output is all zeros. '
            'The EdgeTPU delegate may not be running correctly.'
        )
        assert elapsed_ms < 100, (
            f'Inference took {elapsed_ms:.1f} ms (expected <100 ms for MobileNet V2). '
            'The model may be running on CPU instead of the EdgeTPU. '
            'Check that the Coral is plugged into a USB 3.0 port.'
        )

    def test_edgetpu_detection_inference(self):
        """Run object detection on the EdgeTPU with EfficientDet-Lite0."""
        try:
            from pycoral.utils.edgetpu import make_interpreter
            import numpy as np
            import time
        except ImportError:
            pytest.skip('pycoral or numpy not installed')

        model_path = os.path.join(
            os.path.dirname(__file__), 'test_data',
            'efficientdet_lite0_generic_edgetpu.tflite',
        )
        if not os.path.isfile(model_path):
            pytest.skip(f'Test model not found at {model_path}')

        interpreter = make_interpreter(model_path)
        interpreter.allocate_tensors()

        input_details = interpreter.get_input_details()
        output_details = interpreter.get_output_details()

        # EfficientDet-Lite0: 320x320 RGB input
        assert list(input_details[0]['shape']) == [1, 320, 320, 3], (
            f'Unexpected input shape {input_details[0]["shape"]}. '
            'The EfficientDet-Lite0 model may be corrupt - re-download it.'
        )

        # 4 outputs: boxes, class IDs, scores, detection count
        assert len(output_details) == 4, (
            f'Expected 4 detection outputs, got {len(output_details)}. '
            'The EfficientDet-Lite0 model may be corrupt - re-download it.'
        )

        input_data = np.random.randint(
            0, 256, size=input_details[0]['shape'],
            dtype=np.uint8,
        )
        interpreter.set_tensor(input_details[0]['index'], input_data)

        # Warm-up invoke
        interpreter.invoke()

        # Timed invoke
        start = time.monotonic()
        interpreter.set_tensor(input_details[0]['index'], input_data)
        interpreter.invoke()
        elapsed_ms = (time.monotonic() - start) * 1000

        # Verify outputs are retrievable - output order varies by model export,
        # so identify by shape rather than index.
        output_shapes = [
            tuple(interpreter.get_tensor(od['index']).shape)
            for od in output_details
        ]
        has_boxes = any(s[-1] == 4 and len(s) == 3 for s in output_shapes)
        has_count = any(s == (1,) for s in output_shapes)

        assert has_boxes, (
            f'No bounding box output (shape [1,N,4]) found. Shapes: {output_shapes}'
        )
        assert has_count, (
            f'No detection count output (shape [1]) found. Shapes: {output_shapes}'
        )
        # EfficientDet-Lite0 runs ~26 ms on USB 3.0 Coral.
        # 50 ms threshold catches CPU fallback (~300+ ms) without false alarms.
        assert elapsed_ms < 50, (
            f'Detection took {elapsed_ms:.1f} ms (expected <50 ms for EfficientDet-Lite0). '
            'The model may be running on CPU instead of the EdgeTPU. '
            'Check that the Coral is plugged into a USB 3.0 port.'
        )

    def test_udev_rule_exists(self):
        """Udev rule must exist for non-root Coral access on both USB IDs."""
        rule_path = '/etc/udev/rules.d/99-coral-edgetpu.rules'
        assert os.path.isfile(rule_path), (
            f'{rule_path} not found. '
            'Fix: run scripts/setup_coral.sh to install the udev rule.'
        )
        with open(rule_path) as f:
            content = f.read()
        assert '1a6e' in content and '18d1' in content, (
            f'{rule_path} is missing one or both Coral USB IDs '
            '(1a6e:089a pre-init, 18d1:9302 post-init). '
            'Fix: run scripts/setup_coral.sh'
        )


# ---------------------------------------------------------------------------
# ROS2 package dependencies
# ---------------------------------------------------------------------------

class TestDependencies:
    """Verify that required ROS2 packages are installed."""

    REQUIRED_PACKAGES = [
        ('mavros', 'ros-jazzy-mavros'),
        ('realsense2_camera', 'ros-jazzy-realsense2-camera'),
        ('gscam', 'ros-jazzy-gscam'),
    ]

    @pytest.mark.parametrize('pkg_name,apt_name', REQUIRED_PACKAGES)
    def test_ros2_package_installed(self, pkg_name, apt_name):
        """Each required ROS2 package must be findable."""
        result = subprocess.run(
            ['ros2', 'pkg', 'prefix', pkg_name],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, (
            f'ROS2 package "{pkg_name}" not found. '
            f'Install: sudo apt install {apt_name}'
        )

    def test_geographiclib_datasets(self):
        """Verify that GeographicLib datasets are installed for MAVROS."""
        # Each tuple: (directory that must exist, glob hint for what's inside)
        datasets = [
            '/usr/share/GeographicLib/geoids',
            '/usr/share/GeographicLib/gravity',
            '/usr/share/GeographicLib/magnetic',
        ]
        missing = [d for d in datasets if not os.path.isdir(d) or not os.listdir(d)]
        assert not missing, (
            'Missing GeographicLib dataset(s):\n' +
            '\n'.join(f'  {d}/' for d in missing) +
            '\nFix: sudo /opt/ros/jazzy/lib/mavros/install_geographiclib_datasets.sh'
        )

    def test_imu_fix_script_installed(self):
        """Verify the RealSense IMU permission fix script is installed."""
        script = '/usr/local/bin/fix-realsense-imu.sh'
        assert os.path.isfile(script), (
            f'{script} not found. Run: scripts/setup_realsense.sh'
        )
        assert os.access(script, os.X_OK), (
            f'{script} is not executable. Fix: sudo chmod +x {script}'
        )
