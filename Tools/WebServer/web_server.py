"""Compatibility entry point combining the independent API with optional Web assets."""
from Tools.APIServer import application as _api
from Tools.APIServer.server import get_server, stop_server
from Tools.APIServer.server import run_server as _run_api_server

app = _api.app
task_manager = _api.task_manager
profile_handlers = _api.profile_handlers
queue_handlers = _api.queue_handlers


def run_server(host="127.0.0.1", port=8000, monitor_mode=False, log_level="info", allow_remote_access=False):
    return _run_api_server(
        host, port, monitor_mode, log_level, allow_remote_access, serve_web=True,
    )


def __getattr__(name):
    if name == "_current_server":
        return get_server()
    return getattr(_api, name)
