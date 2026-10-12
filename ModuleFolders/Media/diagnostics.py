"""Content-free diagnostic events for the locked core TUI."""

from collections import deque
from datetime import datetime
import json
import math
import sys
import time

PREFIX = "AINIEE_MEDIA_DIAGNOSTIC "
METRICS = ("audio_duration_ms", "asr_ms", "translation_ms", "inference_ms", "queue_wait_ms",
           "translation_first_text_ms", "latency_from_segment_end_ms", "endpoint_wait_ms",
           "queue_depth", "dropped_segments", "audio_position_ms", "capture_ms", "vad_ms")
STAGES = {"worker_started", "importing_runtime", "translation_loaded", "loading_translation",
          "loading_asr", "warming_up", "opening_audio", "recognizing", "translating", "checking_environment", "preparing_runtime"}


def diagnostic_event(event: dict) -> dict | None:
    kind = event.get("type")
    if kind == 'download':
        return {key: event.get(key) for key in ('type', 'model', 'stage', 'downloaded_bytes', 'total_bytes', 'percent', 'speed_bps', 'eta_seconds')}
    if kind not in {"status", "ready", "error", "stopped", "caption", "segment", "capture", "backlog"}:
        return None
    result = {"type": kind, "time": datetime.now().astimezone().isoformat(timespec="milliseconds")}
    if kind == "status":
        if event.get("message") not in STAGES:
            return None
        result["stage"] = event["message"]
    if kind == "error":
        result["error_type"] = str(event.get("message", "RuntimeError")).split(":", 1)[0][:80]
    for key in ("pid", "sequence", "start_ms", "end_ms", "exit_code"):
        if isinstance(event.get(key), int):
            result[key] = event[key]
    metrics = event.get("metadata", {}) if kind == "caption" else event
    for key in METRICS:
        value = metrics.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            result[key] = value
    return result


def emit_diagnostic(event: dict) -> None:
    payload = diagnostic_event(event)
    if payload is not None:
        print(PREFIX + json.dumps(payload, ensure_ascii=False), flush=True)


def emit_setup_line(message):
    from ModuleFolders.Infrastructure.DownloadProgress import safe_installer_line
    print(PREFIX + json.dumps({'type': 'setup_output', 'message': safe_installer_line(message)}, ensure_ascii=False), flush=True)


class DiagnosticState:
    def __init__(self, limit=8):
        self.started = time.monotonic()
        self.last_update = None
        self.status = "waiting"
        self.metrics = {}
        self.recent = deque(maxlen=limit)
        self.captions = 0
        self.last_stage_started = self.started
        self.last_stage_duration = None
        self.download = None
        self.setup_output = ''

    def accept(self, event):
        if not isinstance(event, dict) or event.get("type") not in {
            "status", "ready", "error", "stopped", "caption", "segment", "capture", "backlog", 'download', 'setup_output'
        }:
            return
        self.last_update = time.monotonic()
        self.metrics.update({key: event[key] for key in METRICS if key in event})
        kind = event["type"]
        if kind == 'download':
            self.download = event
            return
        if kind == 'setup_output':
            self.setup_output = event.get('message', '')
            return
        if kind == "status":
            self.last_stage_duration = round((time.monotonic() - self.last_stage_started) * 1000)
            self.last_stage_started = time.monotonic()
            self.status = event.get("stage", "waiting")
        elif kind in {"ready", "error", "stopped"}:
            self.last_stage_duration = round((time.monotonic() - self.last_stage_started) * 1000)
            self.last_stage_started = time.monotonic()
            self.status = kind
        elif kind == "caption":
            self.captions += 1
            self.status = "ready"
        if kind != "capture":
            self.recent.append(event)

    def render(self, translate, *, width=120):
        from rich.panel import Panel
        from rich.table import Table
        from rich.console import Group
        from rich.text import Text

        tr = lambda key: translate("media_diag_" + key)
        summary = Table.grid(padding=(0, 2))
        elapsed = round(time.monotonic() - self.started, 1)
        age = round(time.monotonic() - self.last_update, 1) if self.last_update is not None else "—"
        stage_key = "media_" + self.status
        labels = {"ready": "listening", "waiting": "waiting", "stopped": "stopped"}
        stage_key = "media_" + labels.get(self.status, self.status)
        label = translate(stage_key)
        if label == stage_key:
            label = self.status
        summary.add_row(tr("time"), datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z"), tr("elapsed"), f"{elapsed} s")
        summary.add_row(tr("state"), str(label), tr("last_update"), f"{age} s")
        summary.add_row(tr("completed"), str(self.captions), tr("queue"), str(self.metrics.get("queue_depth", "—")))
        summary.add_row(tr("audio"), self._duration("audio_duration_ms"), tr("dropped"), str(self.metrics.get("dropped_segments", 0)))
        summary.add_row(tr("stage_elapsed"), f"{time.monotonic() - self.last_stage_started:.1f} s",
                        tr("previous_stage"), self._format(self.last_stage_duration))
        summary.add_row(tr("asr"), self._format(self.metrics.get("asr_ms")),
                        tr("translation"), self._format(self.metrics.get("translation_ms")))
        summary.add_row(tr("first_text"), self._format(self.metrics.get("translation_first_text_ms")),
                        tr("queue_wait"), self._format(self.metrics.get("queue_wait_ms")))
        summary.add_row(tr("endpoint"), self._format(self.metrics.get("endpoint_wait_ms")),
                        tr("total"), self._format(self.metrics.get("latency_from_segment_end_ms")))
        summary.add_row(tr("compute"), self._format(self.metrics.get("inference_ms")), "", "")
        table = Table(expand=True)
        compact = width < 120
        columns = ("time", "stage") if compact else (
            "time", "stage", "audio", "asr", "translation", "first_text", "queue_wait", "endpoint", "total")
        for key in columns:
            table.add_column(tr(key), no_wrap=key != "stage")
        for event in self.recent:
            stage = event.get("stage", event["type"])
            translated = translate("media_" + labels.get(stage, stage))
            if translated == "media_" + labels.get(stage, stage):
                translated = stage
            if event["type"] == "error":
                translated = event.get("error_type", "error")
            if stage == "caption":
                translated = translate("media_subtitles")
            elif stage == "segment":
                translated = tr("audio")
            elif stage == "backlog":
                translated = tr("queue")
            if compact:
                table.add_row(Text(str(event.get("time", ""))[11:23]), Text(str(translated)))
                continue
            table.add_row(Text(str(event.get("time", ""))[11:23]), Text(str(translated)),
                          self._format(event.get("audio_duration_ms"), seconds=True),
                          *[self._format(event.get(key)) for key in
                            ("asr_ms", "translation_ms", "translation_first_text_ms", "queue_wait_ms",
                             "endpoint_wait_ms", "latency_from_segment_end_ms")])
        capture = Text(tr("capture_info").format(
            position=self._format(self.metrics.get("audio_position_ms"), seconds=True),
            capture=self._format(self.metrics.get("capture_ms")), vad=self._format(self.metrics.get("vad_ms"))))
        from ModuleFolders.Infrastructure.DownloadProgress import format_progress
        transfer = Text(format_progress(self.download) if self.download else self.setup_output)
        return Panel(Group(summary, transfer, capture, table, Text(tr("scope"))), title=tr("title"), border_style="cyan")

    @staticmethod
    def _format(value, seconds=False):
        if value is None:
            return "—"
        return f"{value / 1000:.2f} s" if seconds else (f"{value:.2f} ms" if 0 < value < 1 else f"{value:.0f} ms")

    def _duration(self, key):
        return self._format(self.metrics.get(key), seconds=True)
