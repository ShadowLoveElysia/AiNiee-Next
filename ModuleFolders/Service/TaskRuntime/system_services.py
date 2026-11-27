"""Own optional MCP and Skills processes started through the API."""
from __future__ import annotations

import os
import socket
import subprocess
import threading
import time
import uuid
import psutil

from ModuleFolders.Infrastructure.RemoteAccessPolicy import ensure_bind_allowed
from ModuleFolders.Service.TaskRuntime.manager import resolve_task_worker_python
from ModuleFolders.Service.TaskRuntime.processes import OwnedProcessTree, launch_options, mark_worker_environment

_lock = threading.RLock()
_services: dict[str, dict] = {}


def _snapshot(record):
    return {key: value for key, value in record.items() if key not in {"process", "tree"}}


def _port_open(host, port):
    host = "127.0.0.1" if host == "0.0.0.0" else "::1" if host == "::" else host
    try:
        with socket.create_connection((host, port), timeout=.2):
            return True
    except OSError:
        return False


def _owned_port_ready(process, port):
    try:
        return any(connection.status == psutil.CONN_LISTEN and connection.laddr.port == port
                   for connection in psutil.Process(process.pid).net_connections(kind="inet"))
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def list_services():
    with _lock:
        for record in _services.values():
            if record["process"].poll() is not None:
                record["status"] = "exited"
        return [_snapshot(record) for record in _services.values()]


def start_service(service, *, host, port, transport, path, auth_token, backend, config, project_root, cancel=None):
    if service not in {"mcp", "skills"}:
        raise ValueError("Unsupported service")
    ensure_bind_allowed(host, config.get("enable_remote_access") is True, service)
    if not auth_token:
        raise ValueError("Supply an authentication token or configure the service token environment variable")
    with _lock:
        previous = _services.get(service)
        if previous is not None and (previous["process"].poll() is None or not previous["tree"].terminate(timeout=.2)):
            raise RuntimeError("This service is already owned; stop it before changing its settings")
        if _port_open(host, port):
            raise RuntimeError("Address is already in use; existing listeners are not taken over")
        command = [resolve_task_worker_python(project_root), "-m"]
        env = os.environ.copy()
        marker = mark_worker_environment(env)
        if service == "mcp":
            backend_host = "127.0.0.1" if backend["host"] == "0.0.0.0" else "::1" if backend["host"] == "::" else backend["host"]
            command += ["Tools.MCPServer.server", "--transport", transport, "--host", host,
                        "--port", str(port), "--path", path, "--backend-host", backend_host,
                        "--backend-port", str(backend["port"])]
            env["AINIEE_MCP_AUTH_TOKEN"] = auth_token
        else:
            command += ["Tools.Skills.server", "--host", host, "--port", str(port)]
            if config.get("enable_remote_access") is True:
                command.append("--allow-remote-access")
            env["AINIEE_SKILLS_AUTH_TOKEN"] = auth_token
        launched_at = time.time()
        process = subprocess.Popen(command, cwd=project_root, env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **launch_options())
        record = {"service": service, "service_id": uuid.uuid4().hex, "status": "starting",
                  "host": host, "port": port, "transport": transport if service == "mcp" else "http",
                  "auth_configured": True, "owned": True, "process": process,
                  "tree": OwnedProcessTree(process, owner_id=marker, launched_at=launched_at)}
        _services[service] = record
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if cancel is not None and cancel.is_set():
            stopped = stop_service(service, record["service_id"])
            if stopped["status"] == "stopped":
                from ModuleFolders.Service.TaskRuntime.jobs import CancelledJob
                raise CancelledJob()
            raise RuntimeError("Service cleanup is pending")
        if process.poll() is not None:
            stop_service(service, record["service_id"])
            raise RuntimeError("Service process exited before it became ready")
        if _owned_port_ready(process, port):
            with _lock:
                if record["status"] == "starting":
                    record["status"] = "running"
                return _snapshot(record)
        time.sleep(.05)
    stop_service(service, record["service_id"])
    raise RuntimeError("Service did not become ready before the startup timeout")


def stop_service(service, service_id):
    with _lock:
        record = _services.get(service)
        if record is None or record["service_id"] != service_id:
            raise KeyError("Service ownership has changed")
        record["status"] = "stopping"
        if record["tree"].terminate(timeout=3):
            record["status"] = "stopped"
        return _snapshot(record)


def shutdown_services():
    with _lock:
        stopped = True
        for name, record in list(_services.items()):
            stopped = (stop_service(name, record["service_id"])["status"] == "stopped") and stopped
        return stopped
