"""Task-scoped delivery of the same controls consumed by the interactive loop."""
from __future__ import annotations

from collections import OrderedDict
import os
import threading
import time
import uuid

from ModuleFolders.Infrastructure.ApiSecurity import INTERNAL_AUTH_ENV, INTERNAL_AUTH_HEADER

CONTROL_KEYS = {
    "pause": "p", "resume": "r", "decrease_threads": "-", "increase_threads": "+",
    "decrease_batch": "[", "increase_batch": "]", "skip_file": "n", "switch_api": "k",
}


class ControlConflict(ValueError):
    pass


class ControlMailbox:
    def __init__(self):
        self._lock = threading.RLock()
        self._task_id = None
        self._context = None
        self._records = OrderedDict()
        self._closed_contexts = set()

    def ready(self, task_id, context):
        with self._lock:
            if (task_id, context) in self._closed_contexts:
                raise ControlConflict("Worker control context has already ended")
            if (task_id, context) != (self._task_id, self._context):
                if self._context:
                    self._closed_contexts.add((self._task_id, self._context))
                if task_id != self._task_id:
                    self._closed_contexts = {entry for entry in self._closed_contexts if entry[0] == task_id}
                for record in self._records.values():
                    if record["status"] in {"queued", "delivered"}:
                        record["status"] = "expired"
                self._task_id, self._context = task_id, context

    def submit(self, task_id, action):
        with self._lock:
            if task_id != self._task_id or not self._context:
                raise ControlConflict("The worker is not ready for interactive controls")
            if action not in CONTROL_KEYS:
                raise ValueError("Unsupported control action")
            if any(row["status"] in {"queued", "delivered"} for row in self._records.values()):
                raise ControlConflict("Wait for the previous control to be processed")
            record = {"command_id": uuid.uuid4().hex, "task_id": task_id,
                      "context_id": self._context, "action": action, "status": "queued", "state": {}}
            self._records[record["command_id"]] = record
            while len(self._records) > 100:
                self._records.popitem(last=False)
            return dict(record)

    def poll(self, task_id, context):
        with self._lock:
            if (task_id, context) != (self._task_id, self._context):
                raise ControlConflict("The worker context has changed")
            for record in self._records.values():
                if record["status"] in {"queued", "delivered"}:
                    record["status"] = "delivered"
                    return dict(record)
            return None

    def acknowledge(self, task_id, context, command_id, state):
        with self._lock:
            record = self._records.get(command_id)
            if (not record or (task_id, context) != (self._task_id, self._context)
                    or (task_id, context) != (record["task_id"], record["context_id"])
                    or record["status"] not in {"delivered", "processed", "rejected"}):
                raise ControlConflict("Control no longer belongs to this worker")
            if record["status"] == "delivered":
                desired = {"pause": True, "resume": False}.get(record["action"])
                record["status"] = "processed" if desired is None or state.get("paused") == desired else "rejected"
                record["state"] = dict(state)
            return dict(record)

    def status(self, command_id):
        with self._lock:
            if command_id not in self._records:
                raise KeyError(command_id)
            return dict(self._records[command_id])

    def close(self, task_id, context):
        with self._lock:
            if (task_id, context) == (self._task_id, self._context):
                self._closed_contexts.add((task_id, context))
                for row in self._records.values():
                    if row["status"] in {"queued", "delivered"}:
                        row["status"] = "expired"
                self._context = None


mailbox = ControlMailbox()


class WorkerControlClient:
    def __init__(self, endpoint, token, task_id):
        self.endpoint, self.token, self.task_id = endpoint.rstrip("/"), token, task_id
        self.context_id = uuid.uuid4().hex
        self._ready = False
        self._last_poll = 0
        self._command = None
        self._receipt = None
        self._last_notice = 0
        self._processed = set()

    def _transport_failed(self):
        if time.monotonic() - self._last_notice > 30:
            import logging
            logging.getLogger(__name__).warning("Worker control channel unavailable; retrying without replaying delivered controls")
            self._last_notice = time.monotonic()

    @classmethod
    def from_environment(cls):
        task_id = os.environ.get("AINIEE_WEB_TASK_ID")
        endpoint, token = os.environ.get("AINIEE_INTERNAL_API_URL"), os.environ.get(INTERNAL_AUTH_ENV)
        if os.environ.get("AINIEE_BACKEND_WORKER") == "1" and task_id and endpoint and token:
            return cls(endpoint, token, task_id)
        return None

    def _request(self, operation, **payload):
        import requests
        with requests.post(
            f"{self.endpoint}/api/internal/task-control/{operation}",
            headers={INTERNAL_AUTH_HEADER: self.token},
            json={"task_id": self.task_id, "context_id": self.context_id, **payload},
            timeout=0.5, allow_redirects=False,
        ) as response:
            response.raise_for_status()
            return response.json()

    def next_key(self):
        if time.monotonic() - self._last_poll < 0.4:
            return None
        self._last_poll = time.monotonic()
        try:
            if not self._ready:
                self._request("ready")
                self._ready = True
            if self._receipt:
                self._request("ack", **self._receipt)
                self._receipt = None
            self._command = self._request("poll").get("command")
            if self._command and self._command["command_id"] in self._processed:
                self._command = None
                return None
            return CONTROL_KEYS.get(self._command["action"]) if self._command else None
        except (OSError, ValueError):
            self._transport_failed()
            return None

    def acknowledge(self, *, paused, config):
        if self._command:
            self._processed.add(self._command["command_id"])
            if len(self._processed) > 100:
                self._processed = {self._command["command_id"]}
            self._receipt = {"command_id": self._command["command_id"], "state": {
                "paused": paused, "threads": config.actual_thread_counts,
                "lines_limit": config.lines_limit, "tokens_limit": config.tokens_limit,
            }}
            self._command = None

    def close(self):
        try:
            if self._receipt:
                self._request("ack", **self._receipt)
            if self._ready:
                self._request("close")
        except (OSError, ValueError):
            self._transport_failed()
