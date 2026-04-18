"""
MCP 运行桥接模块
从 ainiee_cli.py 分离
"""
import os
import socket
import subprocess
import sys
import time
from typing import Any, Dict, Optional

from rich.console import Console
from rich.panel import Panel

from Tools.MCPServer.runtime import format_runtime_status_lines, inspect_mcp_runtime


console = Console()


class MCPRuntimeBridge:
    """MCP server startup and runtime checks."""

    def __init__(self, host):
        self.host = host

    @property
    def i18n(self):
        return getattr(self.host, "i18n", None)

    @property
    def project_root(self):
        return getattr(self.host, "PROJECT_ROOT", os.getcwd())

    def inspect_runtime(self) -> Dict[str, object]:
        return inspect_mcp_runtime(self.project_root)

    def start_mcp_server(self) -> bool:
        """Menu entry: launch MCP as a detached background subprocess and return."""
        status = self.inspect_runtime()
        if not status.get("available"):
            self._show_missing_runtime(status, auto_exit=False)
            time.sleep(3)
            return False

        if self.is_mcp_server_running():
            self._show_status_panel(
                self._t("msg_mcp_server_already_running", "MCP服务已在后台运行。"),
                (
                    f"Transport: streamable-http\n"
                    f"Local: {self.get_mcp_local_endpoint()}\n"
                    f"Network: {self.get_mcp_network_endpoint()}\n\n"
                    f"{self._t('msg_mcp_menu_returning', '3 秒后返回菜单界面...')}"
                ),
                border_style="green",
            )
            time.sleep(3)
            return True

        command = self._build_menu_command()

        try:
            # 菜单模式不能阻塞主线程，所以这里启动独立后台进程并把控制权还给菜单。
            process = subprocess.Popen(
                command,
                cwd=self.project_root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=self._build_subprocess_env(),
            )
        except Exception as exc:
            self._show_runtime_error(
                self._t("msg_mcp_server_start_failed", "MCP服务启动失败。"),
                exc,
                auto_exit=False,
            )
            time.sleep(3)
            return False

        setattr(self.host, "mcp_server_process", process)

        if self._wait_for_port(self._get_probe_host(), self._get_mcp_port(), timeout=3.0):
            self._show_status_panel(
                self._t("msg_mcp_server_started", "MCP服务已启动。"),
                (
                    f"Transport: streamable-http\n"
                    f"Local: {self.get_mcp_local_endpoint()}\n"
                    f"Network: {self.get_mcp_network_endpoint()}\n"
                    f"Backend: http://{self._get_backend_host()}:{self._get_backend_port()}\n\n"
                    f"{self._t('msg_mcp_menu_returning', '3 秒后返回菜单界面...')}"
                ),
                border_style="green",
            )
            time.sleep(3)
            return True

        if process.poll() is not None:
            setattr(self.host, "mcp_server_process", None)
            self._show_status_panel(
                self._t("msg_mcp_server_start_failed", "MCP服务启动失败。"),
                (
                    f"Command: {' '.join(command)}\n"
                    f"{self._t('msg_mcp_check_install', '请检查 MCP 依赖和端口占用。')}\n\n"
                    f"{self._t('msg_mcp_menu_returning', '3 秒后返回菜单界面...')}"
                ),
                border_style="red",
            )
            time.sleep(3)
            return False

        self._show_status_panel(
            self._t("msg_mcp_server_starting_bg", "MCP服务正在后台继续启动。"),
            (
                f"Transport: streamable-http\n"
                f"Expected local: {self.get_mcp_local_endpoint()}\n"
                f"Expected network: {self.get_mcp_network_endpoint()}\n\n"
                f"{self._t('msg_mcp_menu_returning', '3 秒后返回菜单界面...')}"
            ),
            border_style="yellow",
        )
        time.sleep(3)
        return True

    def run_mcp_server_from_command(self, transport: str = "stdio") -> int:
        """
        Command entry: run MCP in-process.

        Missing dependencies are rendered with Rich and delayed for 3 seconds
        before returning a non-zero exit code.
        """
        status = self.inspect_runtime()
        if not status.get("available"):
            self._show_missing_runtime(status, auto_exit=True)
            time.sleep(3)
            return 1

        try:
            from Tools.MCPServer.server import run_mcp_server
        except Exception as exc:
            self._show_runtime_error(
                self._t("msg_mcp_import_failed", "MCP组件导入失败。"),
                exc,
                auto_exit=True,
            )
            time.sleep(3)
            return 1

        try:
            run_mcp_server(
                host_cli=self.host,
                transport=transport,
                host=self._get_mcp_host(),
                port=self._get_mcp_port(),
                path=self._get_mcp_path(),
                backend_host=self._get_backend_host(),
                backend_port=self._get_backend_port(),
            )
        except Exception as exc:
            self._show_runtime_error(
                self._t("msg_mcp_server_start_failed", "MCP服务启动失败。"),
                exc,
                auto_exit=True,
            )
            time.sleep(3)
            return 1

        return 0

    def is_mcp_server_running(self) -> bool:
        process = self._get_mcp_process()
        if process is not None and process.poll() is None:
            return True
        if process is not None and process.poll() is not None:
            setattr(self.host, "mcp_server_process", None)

        return self._is_port_open(self._get_probe_host(), self._get_mcp_port())

    def get_mcp_http_endpoint(self) -> str:
        return self.get_mcp_local_endpoint()

    def get_mcp_local_endpoint(self) -> str:
        return f"http://127.0.0.1:{self._get_mcp_port()}{self._get_mcp_path()}"

    def get_mcp_network_endpoint(self) -> str:
        return f"http://{self._detect_local_ip()}:{self._get_mcp_port()}{self._get_mcp_path()}"

    def _get_mcp_process(self) -> Optional[subprocess.Popen]:
        process = getattr(self.host, "mcp_server_process", None)
        if process is not None and process.poll() is not None:
            setattr(self.host, "mcp_server_process", None)
            return None
        return process

    def _get_config_value(self, key: str, default: Any) -> Any:
        config = getattr(self.host, "config", None)
        if isinstance(config, dict):
            value = config.get(key)
            if value not in (None, ""):
                return value
        return default

    def _get_mcp_host(self) -> str:
        return str(self._get_config_value("mcp_server_host", "0.0.0.0"))

    def _get_mcp_port(self) -> int:
        try:
            return int(self._get_config_value("mcp_server_port", 8765) or 8765)
        except Exception:
            return 8765

    def _get_mcp_path(self) -> str:
        path = str(self._get_config_value("mcp_server_path", "/mcp"))
        return path if path.startswith("/") else f"/{path}"

    def _get_backend_host(self) -> str:
        return str(self._get_config_value("mcp_backend_host", "127.0.0.1"))

    def _get_backend_port(self) -> int:
        try:
            return int(self._get_config_value("mcp_backend_port", 18000) or 18000)
        except Exception:
            return 18000

    def _build_menu_command(self):
        launcher = self._resolve_python_launcher()
        script_path = os.path.join(self.project_root, "Tools", "MCPServer", "server.py")
        return launcher + [
            script_path,
            "--transport",
            "streamable-http",
            "--host",
            self._get_mcp_host(),
            "--port",
            str(self._get_mcp_port()),
            "--path",
            self._get_mcp_path(),
            "--backend-host",
            self._get_backend_host(),
            "--backend-port",
            str(self._get_backend_port()),
        ]

    def _resolve_python_launcher(self):
        executable = sys.executable or ""
        executable_name = os.path.basename(executable).lower()
        if executable and "python" in executable_name:
            return [executable]
        return ["uv", "run", "python"]

    def _build_subprocess_env(self):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env.setdefault("AINIEE_MCP_HOST", self._get_mcp_host())
        env.setdefault("AINIEE_MCP_PORT", str(self._get_mcp_port()))
        env.setdefault("AINIEE_MCP_PATH", self._get_mcp_path())
        env.setdefault("AINIEE_MCP_BACKEND_HOST", self._get_backend_host())
        env.setdefault("AINIEE_MCP_BACKEND_PORT", str(self._get_backend_port()))
        return env

    def _show_missing_runtime(self, status: Dict[str, object], auto_exit: bool):
        lines = format_runtime_status_lines(status)
        footer = self._t(
            "msg_mcp_auto_exit_3s",
            "3 秒后自动退出当前 MCP 启动流程。",
        ) if auto_exit else self._t(
            "msg_mcp_menu_returning",
            "3 秒后返回菜单界面...",
        )

        body = "\n".join(lines + ["", footer])
        self._show_status_panel(
            self._t("msg_mcp_runtime_missing", "MCP组件或依赖缺失。"),
            body,
            border_style="yellow",
        )

    def _show_runtime_error(self, title: str, exc: Exception, auto_exit: bool):
        footer = self._t(
            "msg_mcp_auto_exit_3s",
            "3 秒后自动退出当前 MCP 启动流程。",
        ) if auto_exit else self._t(
            "msg_mcp_menu_returning",
            "3 秒后返回菜单界面...",
        )
        self._show_status_panel(
            title,
            f"{type(exc).__name__}: {exc}\n\n{footer}",
            border_style="red",
        )

    def _show_status_panel(self, title: str, body: str, border_style: str = "cyan"):
        console.print(
            Panel(
                body,
                title=title,
                border_style=border_style,
                expand=False,
            )
        )

    def _wait_for_port(self, host: str, port: int, timeout: float = 3.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._is_port_open(host, port):
                return True
            time.sleep(0.2)
        return False

    def _is_port_open(self, host: str, port: int) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.5)
                return sock.connect_ex((host, port)) == 0
        except Exception:
            return False

    def _get_probe_host(self) -> str:
        host = self._get_mcp_host()
        return "127.0.0.1" if host == "0.0.0.0" else host

    def _detect_local_ip(self) -> str:
        local_ip = "127.0.0.1"
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                local_ip = sock.getsockname()[0]
        except Exception:
            pass
        return local_ip

    def _t(self, key: str, default: str) -> str:
        i18n = self.i18n
        if i18n is None:
            return default

        try:
            value = i18n.get(key)
        except Exception:
            return default

        return default if not value or value == key else value
