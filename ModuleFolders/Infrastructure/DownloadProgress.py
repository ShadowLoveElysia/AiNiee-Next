"""Thread-safe transfer accounting and terminal/JSON progress without URLs."""

import json
import os
import re
import sys
import threading
import time

_OUTPUT_LOCK = threading.Lock()


def safe_installer_line(line):
    line = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', line).strip()
    line = re.sub(r'https?://\S+', '[download host]', line)
    line = re.sub(r'(?i)(authorization|api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*\S+', r'\1=[redacted]', line)
    return line[:500]


def stream_response(response, destination, name, *, quiet=False):
    try:
        total = int(response.headers.get('content-length', 0)) or None
    except (TypeError, ValueError):
        total = None
    if response.headers.get('content-encoding', 'identity').lower() != 'identity':
        total = None
    with DownloadProgress(name, total, emit=(lambda _: None) if quiet else None) as progress:
        with open(destination, 'wb') as output:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if chunk:
                    output.write(chunk)
                    progress.advance(len(chunk))
        if total is not None and sum(progress.positions.values()) != total:
            raise RuntimeError('Downloaded size does not match Content-Length')


def format_bytes(value):
    value = max(0, value)
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if value < 1024 or unit == 'TiB':
            return f'{value:.1f} {unit}'
        value /= 1024


def format_progress(event):
    completed = event.get('downloaded_bytes', 0)
    total = event.get('total_bytes')
    size = format_bytes(completed) + (' / ' + format_bytes(total) if total is not None else ' / ?')
    percent = f" {event['percent']:.1f}%" if event.get('percent') is not None else ''
    eta = f" ETA {event['eta_seconds']:.0f}s" if event.get('eta_seconds') is not None else ''
    speed = event.get('speed_bps') or 0
    return f"{event.get('model', 'Download')} · {event.get('stage', 'download')} · {size}{percent} · {format_bytes(speed)}/s{eta}"


def emit_progress(event):
    with _OUTPUT_LOCK:
        if sys.stdout.isatty() and os.environ.get('AINIEE_DOWNLOAD_JSON') != '1':
            # Multiple parallel assets use separate lines to avoid overwriting each other.
            print(format_progress(event), flush=True)
        else:
            print(json.dumps(event, ensure_ascii=False), flush=True)


class DownloadProgress:
    def __init__(self, name, total=None, *, emit=None, interval=.5, now=time.monotonic, heartbeat=True):
        self.name = name
        self.total = total if total is not None and total >= 0 else None
        self.emit = emit or emit_progress
        self.interval = interval
        self.now = now
        self.lock = threading.Lock()
        self.positions = {}
        self.network_bytes = 0
        self.last_network = 0
        self.last_time = now()
        self.stage = 'download'
        self.stopped = threading.Event()
        self.thread = None
        if heartbeat:
            self.thread = threading.Thread(target=self._heartbeat, name='download-progress', daemon=True)

    def __enter__(self):
        self.publish(force=True)
        if self.thread:
            self.thread.start()
        return self

    def set_position(self, part, value, *, transferred=0):
        with self.lock:
            self.positions[part] = max(0, value)
            self.network_bytes += max(0, transferred)
        self.publish()

    def advance(self, increment):
        with self.lock:
            self.positions['stream'] = self.positions.get('stream', 0) + increment
            self.network_bytes += increment
        self.publish()

    def publish(self, *, force=False, stage=None):
        with self.lock:
            instant = self.now()
            elapsed = instant - self.last_time
            if not force and elapsed < self.interval:
                return
            if stage:
                self.stage = stage
            speed = (self.network_bytes - self.last_network) / elapsed if elapsed > 0 else 0
            downloaded = sum(self.positions.values())
            percent = min(100, downloaded / self.total * 100) if self.total else (100 if self.total == 0 else None)
            remaining = max(0, self.total - downloaded) if self.total is not None else None
            event = {'type': 'download', 'model': self.name, 'stage': self.stage,
                     'downloaded_bytes': downloaded, 'total_bytes': self.total,
                     'percent': percent, 'speed_bps': round(speed, 2),
                     'eta_seconds': round(remaining / speed, 1) if remaining is not None and speed > 0 else None}
            self.last_time = instant
            self.last_network = self.network_bytes
            self.emit(event)

    def _heartbeat(self):
        while not self.stopped.wait(self.interval):
            self.publish()

    def __exit__(self, error_type, error, traceback):
        self.stopped.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1)
        self.publish(force=True, stage='failed' if error_type else 'complete')
