#!/usr/bin/env python3
"""UAV Neo node watchdog — monitors ROS2 nodes and restarts on failure.

Watches for the MAVROS, RealSense, and Arducam nodes.  When a node
disappears, checks whether the underlying hardware is still connected
and, if so, relaunches the individual launch file.  All events are
logged to ~/logs/latest/watchdog.log.

Designed to run as a systemd service (uav-watchdog.service).
"""

import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

POLL_INTERVAL = 5        # seconds between health checks
RESTART_COOLDOWN = 30    # minimum seconds between restarts of the same node
STARTUP_GRACE = 15       # seconds to wait before first check (set in systemd too)

# Each monitored node group: a friendly name, a topic that proves it is alive,
# the device-check callable, and the launch file to restart it.
PACKAGE = 'uav_neo_ros2_driver'

NODES = {
    'mavros': {
        'topic': '/mavros/state',
        'launch': 'mavros.launch.py',
        'device_check': lambda: os.path.exists('/dev/ttyAMA0'),
        'device_label': '/dev/ttyAMA0 (UART)',
    },
    'realsense': {
        'topic': '/camera/color/image_raw',
        'launch': 'realsense.launch.py',
        'device_check': lambda: _usb_device_present('8086:0b3a'),
        'device_label': 'USB 8086:0b3a (RealSense D435i)',
    },
    'arducam': {
        'topic': '/arducam/camera/image_raw',
        'launch': 'arducam.launch.py',
        'device_check': lambda: _usb_device_present('0c45:0578'),
        'device_label': 'USB 0c45:0578 (Arducam B0578)',
        'restart_delay': 5,  # seconds — USB bus contention with RealSense
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
    """Return the set of currently advertised ROS2 topics."""
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

    delay = cfg.get('restart_delay', 0)
    if delay > 0:
        log.info('%s: waiting %ds before restart (USB settle)', name, delay)
        for _ in range(delay * 10):
            if not _running:
                return
            time.sleep(0.1)

    ts = datetime.now().strftime('%H%M%S')
    restart_log = _log_dir() / f'restart_{name}_{ts}.log'
    log.info('%s: restarting via %s — log: %s', name, cfg['launch'], restart_log)

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

    log.info('Watchdog started — monitoring: %s', ', '.join(NODES.keys()))
    log.info('Log directory: %s', logdir)

    while _running:
        topics = _get_active_topics()

        for name, cfg in NODES.items():
            topic = cfg['topic']
            alive = topic in topics

            # Also check if a child we restarted has exited unexpectedly
            child = _child_procs.get(name)
            if child and child.poll() is not None:
                log.warning('%s: restarted child PID %d exited with code %s',
                            name, child.pid, child.returncode)
                _child_procs.pop(name, None)

            if alive:
                continue

            # Node is missing — check hardware
            device_ok = cfg['device_check']()
            if not device_ok:
                log.warning('%s: topic %s missing — device %s NOT connected, '
                            'skipping restart', name, topic, cfg['device_label'])
                continue

            log.warning('%s: topic %s missing — device %s connected, '
                        'attempting restart', name, topic, cfg['device_label'])
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
