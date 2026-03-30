#!/usr/bin/env python3
"""UAV Neo web dashboard — real-time ROS2 node and topic monitor.

Serves a single-page dashboard on port 8080 that displays node health,
topic publish rates, and watchdog restart events.  Uses only Python
stdlib (http.server, json, subprocess) — no external dependencies.

Designed to run as a systemd service (uav-dashboard.service).
"""

import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PORT = 8080
CACHE_TTL = 2.0  # seconds to cache status between requests

# Topics that indicate each node group is alive
MONITORED = {
    'mavros': {
        'topic': '/mavros/state',
        'label': 'MAVROS (Pixhawk)',
    },
    'realsense': {
        'topic': '/camera/color/image_raw',
        'label': 'RealSense D435i',
    },
    'arducam': {
        'topic': '/arducam/camera/image_raw',
        'label': 'Arducam B0578',
    },
}

# Key topics to measure publish rate
RATE_TOPICS = [
    '/mavros/state',
    '/mavros/imu/data',
    '/camera/depth/image_rect_raw',
    '/camera/color/image_raw',
    '/camera/imu',
    '/arducam/camera/image_raw',
]

log = logging.getLogger('dashboard')

# ---------------------------------------------------------------------------
# Status collection (cached)
# ---------------------------------------------------------------------------

_status_lock = threading.Lock()
_latest_status: dict = {
    'timestamp': '',
    'nodes': {},
    'node_list': [],
    'topic_list': [],
    'rates': {},
    'watchdog_log': [],
    'log_dir': str(Path.home() / 'logs' / 'latest'),
}
_monitor_running = True


def _run(cmd: list[str], timeout: int = 5) -> str:
    """Run a command and return stdout, or empty string on failure."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ''
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ''


def _get_topic_list() -> list[str]:
    out = _run(['ros2', 'topic', 'list'], timeout=10)
    return out.splitlines() if out else []


def _get_node_list() -> list[str]:
    out = _run(['ros2', 'node', 'list'], timeout=10)
    return out.splitlines() if out else []


def _measure_hz(topic: str) -> float | None:
    """Measure topic rate over a short window. Returns Hz or None."""
    try:
        r = subprocess.run(
            ['ros2', 'topic', 'hz', topic, '--window', '3'],
            capture_output=True, text=True, timeout=15,
        )
        # ros2 topic hz may print to stdout or stderr depending on version
        output = r.stdout + '\n' + r.stderr
        for line in output.splitlines():
            if 'average rate' in line:
                return float(line.split(':')[1].strip())
    except subprocess.TimeoutExpired as e:
        # On timeout, partial output may still contain a rate measurement
        raw = e.stdout or b''
        if isinstance(raw, bytes):
            raw = raw.decode(errors='replace')
        for line in raw.splitlines():
            if 'average rate' in line:
                try:
                    return float(line.split(':')[1].strip())
                except (ValueError, IndexError):
                    pass
    except (ValueError, IndexError, OSError):
        pass
    return None


def _read_watchdog_tail(n: int = 10) -> list[str]:
    """Return the last n lines of the watchdog log."""
    logfile = Path.home() / 'logs' / 'latest' / 'watchdog.log'
    if not logfile.exists():
        return []
    try:
        lines = logfile.read_text().strip().splitlines()
        return lines[-n:]
    except OSError:
        return []


def _monitor_loop() -> None:
    """Background thread that continuously collects status."""
    global _monitor_running
    while _monitor_running:
        try:
            # Phase 1: quick check (topic list + node list)
            topics = _get_topic_list()
            nodes = _get_node_list()

            node_status = {}
            for name, cfg in MONITORED.items():
                present = cfg['topic'] in topics
                node_status[name] = {
                    'label': cfg['label'],
                    'topic': cfg['topic'],
                    'alive': present,
                    'status': 'healthy' if present else 'dead',
                }

            # Phase 2: measure rates in parallel threads
            rate_results: dict[str, float | None] = {}
            alive_topics = [t for t in RATE_TOPICS if t in topics]

            def measure(topic):
                rate_results[topic] = _measure_hz(topic)

            threads = []
            for topic in alive_topics:
                t = threading.Thread(target=measure, args=(topic,), daemon=True)
                t.start()
                threads.append(t)
            for t in threads:
                t.join(timeout=10)

            rates = {}
            for topic in RATE_TOPICS:
                if topic in rate_results:
                    hz = rate_results[topic]
                    rates[topic] = {'hz': hz, 'stale': hz is None or hz < 0.5}
                else:
                    rates[topic] = {'hz': None, 'stale': True}

            status = {
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'nodes': node_status,
                'node_list': nodes,
                'topic_list': topics,
                'rates': rates,
                'watchdog_log': _read_watchdog_tail(),
                'log_dir': str(Path.home() / 'logs' / 'latest'),
            }

            with _status_lock:
                _latest_status.update(status)

        except Exception:
            log.exception('Error in monitor loop')

        # Sleep between updates (short increments for clean shutdown)
        for _ in range(30):
            if not _monitor_running:
                break
            time.sleep(0.1)


def get_status() -> dict:
    """Return the most recent status snapshot (non-blocking)."""
    with _status_lock:
        return dict(_latest_status)


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UAV Neo Dashboard</title>
<style>
  :root { --bg: #1a1a2e; --card: #16213e; --green: #0f0; --yellow: #ff0; --red: #f44; --text: #e0e0e0; --muted: #888; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Courier New', monospace; background: var(--bg); color: var(--text); padding: 1rem; }
  h1 { color: #7ec8e3; margin-bottom: 0.5rem; font-size: 1.4rem; }
  .meta { color: var(--muted); font-size: 0.85rem; margin-bottom: 1rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }
  .card { background: var(--card); border-radius: 8px; padding: 1rem; border-left: 4px solid var(--muted); }
  .card.healthy { border-left-color: var(--green); }
  .card.stale   { border-left-color: var(--yellow); }
  .card.dead    { border-left-color: var(--red); }
  .card h2 { font-size: 1rem; margin-bottom: 0.5rem; }
  .indicator { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }
  .indicator.healthy { background: var(--green); box-shadow: 0 0 6px var(--green); }
  .indicator.stale   { background: var(--yellow); box-shadow: 0 0 6px var(--yellow); }
  .indicator.dead    { background: var(--red); box-shadow: 0 0 6px var(--red); }
  table { width: 100%; border-collapse: collapse; margin-bottom: 1.5rem; }
  th, td { text-align: left; padding: 0.4rem 0.8rem; border-bottom: 1px solid #2a2a4a; font-size: 0.85rem; }
  th { color: #7ec8e3; }
  .hz { font-weight: bold; }
  .hz.ok   { color: var(--green); }
  .hz.stale { color: var(--yellow); }
  .hz.dead  { color: var(--red); }
  .log-box { background: #0d1117; border-radius: 6px; padding: 0.8rem; font-size: 0.78rem; max-height: 200px; overflow-y: auto; white-space: pre-wrap; color: var(--muted); }
  .section-title { color: #7ec8e3; font-size: 1rem; margin-bottom: 0.5rem; }
  #error-banner { display: none; background: #4a1010; color: var(--red); padding: 0.5rem 1rem; border-radius: 6px; margin-bottom: 1rem; }
</style>
</head>
<body>

<h1>UAV Neo &mdash; System Dashboard</h1>
<div class="meta">
  <span id="timestamp">Loading...</span> &bull;
  <span id="log-dir"></span>
</div>
<div id="error-banner"></div>

<div class="section-title">Nodes</div>
<div class="grid" id="nodes"></div>

<div class="section-title">Topic Rates</div>
<table>
  <thead><tr><th>Topic</th><th>Rate</th><th>Status</th></tr></thead>
  <tbody id="rates"></tbody>
</table>

<div class="section-title">Watchdog Log</div>
<div class="log-box" id="watchdog-log">No watchdog events yet.</div>

<script>
function update() {
  fetch('/api/status')
    .then(r => r.json())
    .then(data => {
      document.getElementById('error-banner').style.display = 'none';
      document.getElementById('timestamp').textContent = data.timestamp;
      document.getElementById('log-dir').textContent = data.log_dir;

      // Nodes
      let nh = '';
      for (const [key, n] of Object.entries(data.nodes)) {
        nh += `<div class="card ${n.status}">
          <h2><span class="indicator ${n.status}"></span>${n.label}</h2>
          <div style="color:var(--muted);font-size:0.8rem">${n.topic}</div>
          <div style="margin-top:0.3rem">${n.alive ? 'Publishing' : 'NOT DETECTED'}</div>
        </div>`;
      }
      document.getElementById('nodes').innerHTML = nh;

      // Rates
      let rh = '';
      for (const [topic, info] of Object.entries(data.rates)) {
        const hz = info.hz !== null ? info.hz.toFixed(1) + ' Hz' : '—';
        const cls = info.hz === null ? 'dead' : (info.stale ? 'stale' : 'ok');
        const label = info.hz === null ? 'NO DATA' : (info.stale ? 'STALE' : 'OK');
        rh += `<tr><td>${topic}</td><td class="hz ${cls}">${hz}</td><td class="hz ${cls}">${label}</td></tr>`;
      }
      document.getElementById('rates').innerHTML = rh;

      // Watchdog log
      const wl = data.watchdog_log;
      document.getElementById('watchdog-log').textContent = wl.length ? wl.join('\n') : 'No watchdog events yet.';
    })
    .catch(err => {
      const banner = document.getElementById('error-banner');
      banner.textContent = 'Failed to fetch status: ' + err;
      banner.style.display = 'block';
    });
}

update();
setInterval(update, 3000);
</script>
</body>
</html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    """Handle GET / and GET /api/status."""

    def do_GET(self):
        if self.path == '/':
            self._serve_html()
        elif self.path == '/api/status':
            self._serve_status()
        else:
            self.send_error(404)

    def _serve_html(self):
        content = DASHBOARD_HTML.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _serve_status(self):
        data = get_status()
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        """Suppress default per-request logging."""
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    global _monitor_running

    # Set up logging
    logdir = Path.home() / 'logs' / 'latest'
    handlers = [logging.StreamHandler(sys.stderr)]
    try:
        if logdir.exists():
            fh = logging.FileHandler(logdir / 'dashboard.log')
            handlers.append(fh)
    except OSError:
        pass

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=handlers,
    )

    # Start background monitor thread
    monitor = threading.Thread(target=_monitor_loop, daemon=True)
    monitor.start()
    log.info('Background monitor started')

    server = HTTPServer(('0.0.0.0', PORT), DashboardHandler)
    log.info('Dashboard listening on http://0.0.0.0:%d', PORT)

    def _shutdown(signum, _frame):
        log.info('Received signal %d, shutting down', signum)
        _monitor_running = False
        threading.Thread(target=server.shutdown).start()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        server.serve_forever()
    finally:
        _monitor_running = False
        server.server_close()
        monitor.join(timeout=5)
        log.info('Dashboard stopped')


if __name__ == '__main__':
    main()
