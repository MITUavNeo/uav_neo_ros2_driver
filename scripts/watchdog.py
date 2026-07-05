#!/usr/bin/env python3

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


"""UAV Neo node watchdog - monitors ROS2 nodes and restarts on failure.

Watches for the MAVROS, RealSense, and Arducam nodes.  When a node
disappears, checks whether the underlying hardware is still connected
and, if so, relaunches the individual launch file.  All events are
logged to ~/logs/latest/watchdog.log.

Designed to run as a systemd service (uav-watchdog.service).
"""

from datetime import datetime
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

POLL_INTERVAL = 5            # seconds between health checks
RESTART_COOLDOWN = 30        # minimum seconds between restarts of the same node
STARTUP_GRACE = 15           # seconds to wait before first check (set in systemd too)
SHM_CLEANUP_INTERVAL = 60    # seconds between FastRTPS shm orphan sweeps

PACKAGE = 'uav_neo_ros2_driver'

# Executable-path substrings used by `process_check`. Specific enough to
# distinguish the running node binary from `ros2 launch` wrappers in pgrep -f.
MAVROS_EXECUTABLE_PATH = '/lib/mavros/mavros_node'
REALSENSE_EXECUTABLE_PATH = '/realsense2_camera/realsense2_camera_node'
GSCAM_EXECUTABLE_PATH = '/install/gscam/lib/gscam/gscam_node'
MUX_EXECUTABLE_PATH = '/lib/uav_neo_ros2_driver/mux_node'


def _is_running(path_substring: str):
    """Return a process_check callable that pgreps for the given path substring.

    Topic-based liveness gives false positives whenever another node on the
    same Pi subscribes to the same topic - image_relay.py keeps the camera
    topics alive after their publishers die, MAVROS holds /mavros/state and
    /mavros/setpoint_velocity/cmd_vel. process_check closes that gap.
    """
    def check() -> bool:
        try:
            r = subprocess.run(
                ['pgrep', '-f', path_substring],
                capture_output=True, timeout=3,
            )
            return r.returncode == 0
        except (subprocess.TimeoutExpired, OSError) as exc:
            log.warning('pgrep(%s) failed: %s', path_substring, exc)
            return True  # conservative: don't restart on check error
    return check


NODES = {
    'mavros': {
        'topic': '/mavros/state',
        'launch': 'mavros.launch.py',
        'device_check': lambda: os.path.exists('/dev/ttyAMA0'),
        'device_label': '/dev/ttyAMA0 (UART)',
        'kill_pattern': 'mavros_node',  # process name to pkill before restart
        'process_check': _is_running(MAVROS_EXECUTABLE_PATH),
    },
    'realsense': {
        'topic': '/camera/color/image_raw',
        'launch': 'realsense.launch.py',
        'device_check': lambda: _usb_device_present('8086:0b3a'),
        'device_label': 'USB 8086:0b3a (RealSense D435i)',
        'kill_pattern': 'realsense2_camera_node',
        'process_check': _is_running(REALSENSE_EXECUTABLE_PATH),
    },
    'arducam': {
        'topic': '/arducam/camera/image_raw',
        'launch': 'arducam.launch.py',
        'device_check': lambda: _usb_device_present('0c45:0578'),
        'device_label': 'USB 0c45:0578 (Arducam B0578)',
        'restart_delay': 5,  # seconds - USB bus contention with RealSense
        'kill_pattern': 'gscam_node',
        'process_check': _is_running(GSCAM_EXECUTABLE_PATH),
    },
    'mux': {
        'topic': '/mavros/setpoint_velocity/cmd_vel',
        # standalone; using teleop.launch.py would re-spawn the whole stack
        'launch': 'mux.launch.py',
        'device_check': lambda: True,  # software node, always "connected"
        'device_label': 'mux_node (software)',
        'kill_pattern': 'mux_node',
        'process_check': _is_running(MUX_EXECUTABLE_PATH),
    },
}

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------

_running = True
_child_procs: dict[str, subprocess.Popen] = {}
_last_restart: dict[str, float] = {}

log = logging.getLogger('watchdog')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_rpi_volt_alarm() -> 'Path | None':
    """Locate the Pi 5 PMIC low-voltage sticky alarm flag.

    hwmon enumeration order is not stable, so resolve by the driver's `name`
    attribute. Reads as 0 normally; flips to 1 after the first under-voltage
    event since boot and stays 1 until reboot.
    """
    for h in Path('/sys/class/hwmon').glob('hwmon*'):
        try:
            if (h / 'name').read_text().strip() == 'rpi_volt':
                alarm = h / 'in0_lcrit_alarm'
                if alarm.exists():
                    return alarm
        except OSError:
            continue
    return None


def _clean_fastrtps_orphans() -> int:
    """Remove 0-byte /dev/shm/fastrtps_port* segments and stranded lock files.

    These appear when a rclpy process is killed mid-initialization. A new
    participant that hashes to the same port spins forever waiting for the
    segment to grow - the fingerprint of the "Jupyter cell 3 hang".
    Returns number of files removed.
    """
    shm = Path('/dev/shm')
    removed = 0
    for port in shm.glob('fastrtps_port*'):
        if port.name.endswith('_el'):
            continue
        try:
            if port.stat().st_size == 0:
                (shm / f'{port.name}_el').unlink(missing_ok=True)
                (shm / f'sem.{port.name}_mutex').unlink(missing_ok=True)
                port.unlink(missing_ok=True)
                removed += 1
        except (OSError, FileNotFoundError):
            pass
    for el in shm.glob('fastrtps_port*_el'):
        data = shm / el.name[:-len('_el')]
        if not data.exists():
            try:
                (shm / f'sem.{data.name}_mutex').unlink(missing_ok=True)
                el.unlink(missing_ok=True)
                removed += 1
            except (OSError, FileNotFoundError):
                pass
    return removed


def _usb_device_present(usb_id: str) -> bool:
    """Check whether a USB vendor:product ID appears in lsusb output."""
    try:
        result = subprocess.run(
            ['lsusb'], capture_output=True, text=True, timeout=5,
        )
        return usb_id.lower() in result.stdout.lower()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _get_active_topics() -> set[str]:
    """Return the set of currently advertised ROS2 topics.

    Note: a topic appears here if any participant advertises OR subscribes
    to it, so MAVROS's subscription keeps /mavros/setpoint_velocity/cmd_vel
    in the list even after mux_node dies. That weakens mux-death detection
    but is strictly safer than a publisher-count check - the rclpy graph
    API has subtle discovery-timing issues across node restarts that can
    produce false negatives and cascade-restart a healthy stack.
    """
    try:
        result = subprocess.run(
            ['ros2', 'topic', 'list'],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return set(result.stdout.strip().splitlines())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        log.warning('Failed to query ros2 topic list')
    return set()


def _log_dir() -> Path:
    """Resolve ~/logs/latest to the real session directory."""
    latest = Path.home() / 'logs' / 'latest'
    if latest.is_symlink() or latest.is_dir():
        return latest.resolve()
    fallback = Path.home() / 'logs'
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _restart_node(name: str, cfg: dict) -> None:
    """Launch an individual node's launch file as a subprocess."""
    now = time.time()
    last = _last_restart.get(name, 0)
    if now - last < RESTART_COOLDOWN:
        remaining = int(RESTART_COOLDOWN - (now - last))
        log.info('%s: cooldown active, retry in %ds', name, remaining)
        return

    # Kill any previous child we started for this node
    old_proc = _child_procs.get(name)
    if old_proc and old_proc.poll() is None:
        log.info('%s: terminating stale child PID %d', name, old_proc.pid)
        old_proc.terminate()
        try:
            old_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            old_proc.kill()

    # Kill any stale system-wide processes (e.g. from teleop.launch) that
    # might still hold the device open, preventing a clean restart.
    # SIGTERM first, then SIGKILL if any survive after 2 seconds.
    kill_pat = cfg.get('kill_pattern')
    if kill_pat:
        try:
            r = subprocess.run(['pkill', '-f', kill_pat], capture_output=True, timeout=5)
            if r.returncode == 0:
                log.info('%s: sent SIGTERM to processes matching "%s"', name, kill_pat)
                time.sleep(2)
                # Force-kill any survivors
                r2 = subprocess.run(['pkill', '-9', '-f', kill_pat],
                                    capture_output=True, timeout=5)
                if r2.returncode == 0:
                    log.info('%s: sent SIGKILL to surviving processes', name)
                time.sleep(1)
        except subprocess.TimeoutExpired:
            pass

    delay = cfg.get('restart_delay', 0)
    if delay > 0:
        log.info('%s: waiting %ds before restart (USB settle)', name, delay)
        for _ in range(delay * 10):
            if not _running:
                return
            time.sleep(0.1)

    ts = datetime.now().strftime('%H%M%S')
    restart_log = _log_dir() / f'restart_{name}_{ts}.log'
    log.info('%s: restarting via %s - log: %s', name, cfg['launch'], restart_log)

    log_fh = open(restart_log, 'w')  # noqa: SIM115
    env = os.environ.copy()
    env['ROS_LOG_DIR'] = str(_log_dir())

    proc = subprocess.Popen(
        ['ros2', 'launch', PACKAGE, cfg['launch']],
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        env=env,
    )
    _child_procs[name] = proc
    _last_restart[name] = now
    log.info('%s: launched PID %d', name, proc.pid)


def _cleanup_children() -> None:
    """Terminate all child processes we spawned."""
    for name, proc in _child_procs.items():
        if proc.poll() is None:
            log.info('Stopping child %s (PID %d)', name, proc.pid)
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def _signal_handler(signum, _frame):
    global _running
    log.info('Received signal %d, shutting down', signum)
    _running = False


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    global _running

    # Set up logging to both file and stderr (journald)
    logdir = _log_dir()
    handlers = [logging.StreamHandler(sys.stderr)]
    try:
        fh = logging.FileHandler(logdir / 'watchdog.log')
        handlers.append(fh)
    except OSError as exc:
        print(f'Warning: cannot open watchdog.log: {exc}', file=sys.stderr)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=handlers,
    )

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    log.info('Watchdog started - monitoring: %s', ', '.join(NODES.keys()))
    log.info('Log directory: %s', logdir)

    volt_alarm_path = _find_rpi_volt_alarm()
    volt_alarm_seen = False
    if volt_alarm_path is None:
        log.info('Pi under-voltage alarm: rpi_volt hwmon not found (skipping check)')
    else:
        try:
            if volt_alarm_path.read_text().strip() == '1':
                log.warning('Pi under-voltage alarm already set at watchdog start '
                            '(under-voltage occurred earlier this boot)')
                volt_alarm_seen = True
            else:
                log.info('Pi under-voltage alarm armed (%s)', volt_alarm_path)
        except OSError:
            pass

    startup_removed = _clean_fastrtps_orphans()
    if startup_removed:
        log.info('Cleaned %d FastRTPS SHM orphan(s) at startup', startup_removed)

    # Deprioritise MAVROS (CPU-bound serial I/O, tolerates nice 5) so the
    # camera pipelines get more scheduling time.  This boosts camera publish
    # rates from ~13-16 Hz to ~25-32 Hz with negligible MAVROS impact.
    try:
        r = subprocess.run(['pgrep', '-f', 'mavros_node'],
                           capture_output=True, text=True, timeout=5)
        for pid in r.stdout.strip().splitlines():
            subprocess.run(['renice', '5', '-p', pid],
                           capture_output=True, timeout=5)
            log.info('Set mavros_node PID %s to nice 5', pid)
    except (subprocess.TimeoutExpired, OSError):
        log.warning('Failed to renice mavros_node')

    last_shm_cleanup = time.monotonic()
    while _running:
        topics = _get_active_topics()

        if time.monotonic() - last_shm_cleanup >= SHM_CLEANUP_INTERVAL:
            last_shm_cleanup = time.monotonic()
            n = _clean_fastrtps_orphans()
            if n:
                log.info('Cleaned %d FastRTPS SHM orphan(s)', n)

        if volt_alarm_path is not None and not volt_alarm_seen:
            try:
                if volt_alarm_path.read_text().strip() == '1':
                    log.warning('Pi under-voltage alarm tripped - 5V rail dipped '
                                'below threshold (USB devices may have reset). '
                                'Likely cause: uBEC margin too low under flight load.')
                    volt_alarm_seen = True
            except OSError:
                pass

        for name, cfg in NODES.items():
            topic = cfg['topic']
            topic_alive = topic in topics
            # `ros2 topic list` includes subscriber-only topics, so the topic
            # check alone gives false positives whenever any other node on the
            # bus subscribes (image_relay holds the camera topics; MAVROS
            # holds /mavros/setpoint_velocity/cmd_vel). process_check pgreps
            # for the actual node binary to close that gap.
            proc_check = cfg.get('process_check')
            if proc_check is not None:
                proc_alive = proc_check()
            else:
                proc_alive = True
            alive = topic_alive and proc_alive
            failure = (
                'topic+process down' if not topic_alive and not proc_alive else
                'topic not advertised' if not topic_alive else
                'process not running' if not proc_alive else
                None
            )

            child = _child_procs.get(name)
            if child and child.poll() is not None:
                log.warning('%s: restarted child PID %d exited with code %s',
                            name, child.pid, child.returncode)
                _child_procs.pop(name, None)

            if alive:
                continue

            device_ok = cfg['device_check']()
            if not device_ok:
                log.warning('%s: %s - device %s NOT connected, skipping restart',
                            name, failure, cfg['device_label'])
                continue

            log.warning('%s: %s - device %s connected, attempting restart',
                        name, failure, cfg['device_label'])
            _restart_node(name, cfg)

        # Sleep in short increments so we can respond to signals promptly
        for _ in range(POLL_INTERVAL * 10):
            if not _running:
                break
            time.sleep(0.1)

    _cleanup_children()
    log.info('Watchdog stopped')


if __name__ == '__main__':
    main()
