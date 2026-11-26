"""Cancel only the process tree owned by a retained worker handle."""
from __future__ import annotations

import os
import secrets
import signal
import subprocess
import time

import psutil

PROCESS_OWNER_ENV = "AINIEE_PROCESS_OWNER_ID"


def mark_worker_environment(env: dict, *, nested: bool = False) -> str:
    marker = secrets.token_hex(32)
    if nested and env.get(PROCESS_OWNER_ENV):
        marker = f"{env[PROCESS_OWNER_ENV]}:{marker}"
    env[PROCESS_OWNER_ENV] = marker
    return marker


def launch_options() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


class OwnedProcessTree:
    def __init__(self, process, *, grouped: bool = True, owner_id: str | None = None, launched_at: float | None = None):
        self.process = process
        self.pid = process.pid
        if not isinstance(self.pid, int) or self.pid <= 0 or self.pid == os.getpid():
            raise ValueError("A distinct worker process is required.")
        self.root = None
        self.created_at = None
        self.group_id = None
        self.owner_id = owner_id
        self.launched_at = launched_at if launched_at is not None else time.time()
        self.owner_user = psutil.Process(os.getpid()).username()
        self._discovery_complete = False
        self._known: dict[int, psutil.Process] = {}
        try:
            root = psutil.Process(self.pid)
            self.created_at = root.create_time()
            self.root = root
            self._known[self.pid] = root
            if grouped and os.name != "nt" and os.getpgid(self.pid) == self.pid:
                self.group_id = self.pid
        except (psutil.NoSuchProcess, ProcessLookupError):
            # A very short-lived worker may exit before identity capture.
            pass

    @staticmethod
    def _alive(process: psutil.Process) -> bool:
        try:
            return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            return False

    def _same_root(self) -> bool:
        if self.root is None:
            return False
        try:
            return self.root.is_running() and psutil.Process(self.pid).create_time() == self.created_at
        except psutil.NoSuchProcess:
            return False

    def _group_members(self) -> list[psutil.Process]:
        if self.group_id is None:
            return []
        members = []
        for process in psutil.process_iter():
            try:
                if os.getpgid(process.pid) == self.group_id and self._alive(process):
                    members.append(process)
            except (ProcessLookupError, psutil.NoSuchProcess):
                continue
        return members

    def _marked_processes(self) -> list[psutil.Process]:
        """An inherited random run marker survives reparenting and new sessions."""
        if not self.owner_id:
            return []
        owned = []
        for process in psutil.process_iter(["create_time", "username"]):
            try:
                if process.pid == os.getpid() or process.info["create_time"] < self.launched_at - 1:
                    continue
                if process.info["username"] != self.owner_user or not self._alive(process):
                    continue
                marker = process.environ().get(PROCESS_OWNER_ENV, "")
                if marker == self.owner_id or marker.startswith(self.owner_id + ":"):
                    owned.append(process)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                if process.pid in self._known and self._alive(self._known[process.pid]):
                    raise
                continue
        return owned

    def terminate(self, timeout: float = 2.0) -> bool:
        """Return true only after owned workers have stopped; retain state on failure."""
        deadline = time.monotonic() + max(0.0, timeout)
        suspended: dict[int, psutil.Process] = {}
        group_stopped = False
        try:
            same_root = self._same_root()
            if not same_root:
                if not getattr(self, "owner_id", None):
                    # A dead parent does not prove that unobserved children exited.
                    return bool(getattr(self, "_discovery_complete", False)) and not any(
                        self._alive(item) for item in self._known.values()
                    ) and not self._group_members()
                for item in self._marked_processes():
                    self._known[item.pid] = item
                    item.suspend()
                    suspended[item.pid] = item
                if not any(self._alive(item) for item in self._known.values()):
                    self.process.poll()
                    return True

            if same_root and self.group_id is not None:
                if os.getpgid(self.pid) != self.group_id or self.group_id == os.getpgrp():
                    return False
                os.killpg(self.group_id, signal.SIGSTOP)
                group_stopped = True
                for item in self._group_members():
                    suspended[item.pid] = item
                    self._known[item.pid] = item
            elif same_root:
                self.root.suspend()
                suspended[self.pid] = self.root

            # Descendants may create their own sessions. Freeze each generation
            # before taking another snapshot so cancellation cannot race a fork.
            while time.monotonic() <= deadline:
                changed = False
                for item in self._marked_processes():
                    if item.pid not in self._known:
                        self._known[item.pid] = item
                        item.suspend()
                        suspended[item.pid] = item
                        changed = True
                for parent in list(self._known.values()):
                    if not self._alive(parent):
                        continue
                    try:
                        children = parent.children(recursive=True)
                    except psutil.NoSuchProcess:
                        continue
                    for child in children:
                        if child.pid in self._known:
                            continue
                        self._known[child.pid] = child
                        changed = True
                        try:
                            child.suspend()
                            suspended[child.pid] = child
                        except psutil.NoSuchProcess:
                            pass
                if not changed:
                    self._discovery_complete = True
                    break
            else:
                return False

            for pid, child in reversed(list(self._known.items())):
                if pid == self.pid:
                    continue
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            if same_root:
                try:
                    self.root.kill()
                except psutil.NoSuchProcess:
                    pass
            try:
                self.process.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                return False
            while time.monotonic() <= deadline:
                if not any(self._alive(item) for item in self._known.values()):
                    return not self._marked_processes() if self.owner_id else not self._group_members()
                time.sleep(min(.02, max(0.0, deadline - time.monotonic())))
            return False
        except (OSError, psutil.Error):
            return False
        finally:
            # If a permission/identity check prevented cancellation, never leave
            # live owned processes frozen merely because the API returned false.
            for item in suspended.values():
                try:
                    if self._alive(item):
                        item.resume()
                except psutil.Error:
                    pass
            if group_stopped:
                try:
                    if self._same_root() and os.getpgid(self.pid) == self.group_id:
                        os.killpg(self.group_id, signal.SIGCONT)
                except (OSError, psutil.Error):
                    pass
