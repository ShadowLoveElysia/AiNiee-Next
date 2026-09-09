"""Skills 服务运行桥接。

Skills 是可选的轻量 HTTP 控制面。该桥接只负责生命周期、配置和运行状态，
具体 skill 注册与业务执行仍由 ``Tools.Skills`` 自己处理，避免 TUI、CLI 和
Skills 各自维护一套启动协议。
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import time
from typing import Any, Dict, Optional
from urllib.error import URLError
from urllib.request import urlopen

from rich.console import Console
from rich.panel import Panel

from ModuleFolders.Infrastructure.RemoteAccessPolicy import (
    ensure_bind_allowed,
    remote_access_enabled,
    resolve_bind_host,
)
from Tools.Skills.runtime import format_runtime_status_lines, inspect_skills_runtime


console = Console()


class SkillsRuntimeBridge:
    """TUI/CLI 与 Skills HTTP 服务之间的生命周期桥接。"""

    def __init__(self, host: Any):
        self.host = host
        self._server: Any = None
        self._generated_auth_token = ""

    @property
    def i18n(self):
        return getattr(self.host, "i18n", None)

    @property
    def project_root(self) -> str:
        return getattr(self.host, "PROJECT_ROOT", os.getcwd())

    def inspect_runtime(self) -> Dict[str, Any]:
        """Return file/dependency readiness without importing optional business code."""
        return inspect_skills_runtime(self.project_root)

    def start_skills_server(self) -> bool:
        """Run Skills in the foreground from the TUI service menu."""
        status = self.inspect_runtime()
        if not status.get("business_ready", status.get("available")):
            self._show_missing_runtime(status, auto_exit=False)
            time.sleep(3)
            return False

        if self.is_skills_server_running():
            self._show_status_panel(
                self._t("msg_skills_server_already_running", "Skills 服务已在运行。"),
                self._endpoint_status(),
                border_style="green",
            )
            time.sleep(2)
            return True

        try:
            from Tools.Skills.server import run_server
        except Exception as exc:
            self._show_runtime_error("Skills 组件导入失败。", exc, auto_exit=False)
            time.sleep(3)
            return False

        host = self._get_skills_host()
        port = self._get_skills_port()
        require_auth = self._require_auth()
        auth_token = self._get_auth_token()
        if require_auth and not auth_token:
            # The server also generates a token, but generating here lets the
            # menu display the token when the detached/foreground entry is used.
            auth_token = secrets.token_urlsafe(24)
            self._generated_auth_token = auth_token

        try:
            ensure_bind_allowed(host, self._remote_access_enabled(), "Skills")
        except ValueError as exc:
            self._show_runtime_error("Skills 绑定被拒绝。", exc, auto_exit=False)
            time.sleep(3)
            return False

        self._set_active(True)
        self._show_status_panel(
            self._t("msg_skills_server_started", "Skills 服务已启动。"),
            self._endpoint_status(auth_token=auth_token),
            border_style="green",
        )
        try:
            run_server(
                host=host,
                port=port,
                auth_token=auth_token or None,
                require_auth=require_auth,
                allow_origin=self._get_allow_origin(),
                allow_remote_access=self._remote_access_enabled(),
            )
            return True
        except KeyboardInterrupt:
            console.print(
                f"\n[yellow]{self._t('msg_skills_server_stopping', '正在停止 Skills 服务并返回菜单...')}[/yellow]"
            )
            return True
        except Exception as exc:
            self._show_runtime_error("Skills 服务启动失败。", exc, auto_exit=False)
            time.sleep(3)
            return False
        finally:
            self._set_active(False)
            self._generated_auth_token = ""

    def ensure_skills_server_running(self) -> bool:
        """Start a detached Skills server for Web/automation integrations."""
        status = self.inspect_runtime()
        if not status.get("business_ready", status.get("available")):
            return False

        if self.is_skills_server_running():
            return True

        try:
            from Tools.Skills.server import run_server_detached

            host = self._get_skills_host()
            port = self._get_skills_port()
            require_auth = self._require_auth()
            auth_token = self._get_auth_token()
            if require_auth and not auth_token:
                auth_token = secrets.token_urlsafe(24)
                self._generated_auth_token = auth_token

            ensure_bind_allowed(host, self._remote_access_enabled(), "Skills")
            self._server = run_server_detached(
                host=host,
                port=port,
                auth_token=auth_token or None,
                require_auth=require_auth,
                allow_origin=self._get_allow_origin(),
                allow_remote_access=self._remote_access_enabled(),
            )
            setattr(self.host, "skills_server", self._server)
            self._set_active(True)
            if self._wait_for_health():
                return True
            self.stop_skills_server()
            return False
        except Exception:
            self.stop_skills_server()
            return False

    def stop_skills_server(self) -> None:
        """Stop a detached Skills server owned by this bridge."""
        server = self._server or getattr(self.host, "skills_server", None)
        self._server = None
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass
        if hasattr(self.host, "skills_server"):
            setattr(self.host, "skills_server", None)
        self._set_active(False)
        self._generated_auth_token = ""

    def run_skills_server_from_command(
        self,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
        require_auth: Optional[bool] = None,
        auth_token: Optional[str] = None,
        allow_origin: Optional[str] = None,
        allow_remote_access: Optional[bool] = None,
    ) -> int:
        """Command entry point for a foreground Skills server."""
        status = self.inspect_runtime()
        if not status.get("business_ready", status.get("available")):
            self._show_missing_runtime(status, auto_exit=True)
            return 1

        try:
            from Tools.Skills.server import run_server

            bind_host = host or self._get_skills_host()
            bind_port = self._get_skills_port() if port is None else int(port)
            auth_required = self._require_auth() if require_auth is None else bool(require_auth)
            remote_allowed = (
                self._remote_access_enabled()
                if allow_remote_access is None
                else bool(allow_remote_access)
            )
            # Never allow an explicitly unauthenticated remote listener.
            auth_required = auth_required or remote_allowed
            token = str(auth_token or self._get_auth_token() or "")
            if auth_required and not token:
                token = secrets.token_urlsafe(24)
            ensure_bind_allowed(bind_host, remote_allowed, "Skills")
            self._set_active(True)
            run_server(
                host=bind_host,
                port=bind_port,
                auth_token=token or None,
                require_auth=auth_required,
                allow_origin=self._get_allow_origin() if allow_origin is None else allow_origin,
                allow_remote_access=remote_allowed,
            )
            return 0
        except KeyboardInterrupt:
            return 130
        except Exception as exc:
            self._show_runtime_error("Skills 服务启动失败。", exc, auto_exit=True)
            return 1
        finally:
            self._set_active(False)

    def is_skills_server_running(self) -> bool:
        """Probe the health endpoint so unrelated services on the same port do not match."""
        endpoint = f"http://{self._get_probe_host()}:{self._get_skills_port()}/health"
        try:
            with urlopen(endpoint, timeout=0.6) as response:
                if response.status != 200:
                    return False
                payload = json.loads(response.read().decode("utf-8"))
            return payload.get("service") == "ainiee-skills"
        except (OSError, URLError, ValueError, json.JSONDecodeError):
            return False

    def get_skills_http_endpoint(self) -> str:
        return f"http://127.0.0.1:{self._get_skills_port()}"

    def get_skills_network_endpoint(self) -> str:
        return f"http://{self._detect_local_ip()}:{self._get_skills_port()}"

    def _set_active(self, active: bool) -> None:
        setattr(self.host, "skills_server_active", active)

    def _get_config_value(self, key: str, default: Any) -> Any:
        config = getattr(self.host, "config", None)
        if isinstance(config, dict):
            value = config.get(key)
            if value not in (None, ""):
                return value
        return default

    def _remote_access_enabled(self) -> bool:
        return remote_access_enabled(getattr(self.host, "config", {}))

    def _get_skills_host(self) -> str:
        return resolve_bind_host(getattr(self.host, "config", {}))

    def _get_probe_host(self) -> str:
        host = self._get_skills_host()
        return "127.0.0.1" if host in {"0.0.0.0", "::"} else host

    def _get_skills_port(self) -> int:
        value = self._get_config_value(
            "skills_server_port",
            os.environ.get("AINIEE_SKILLS_PORT", 8766),
        )
        try:
            port = int(value)
        except (TypeError, ValueError):
            return 8766
        return port if 1 <= port <= 65535 else 8766

    def _get_auth_token(self) -> str:
        configured = self._get_config_value("skills_server_auth_token", "")
        return str(configured or os.environ.get("AINIEE_SKILLS_AUTH_TOKEN", "") or "")

    def _require_auth(self) -> bool:
        configured = self._get_config_value("skills_require_auth", True)
        enabled = configured is not False
        # Remote bindings must never disable Skills request authentication.
        return enabled or self._remote_access_enabled()

    def _get_allow_origin(self) -> str:
        return str(self._get_config_value("skills_allow_origin", "") or "")

    def _wait_for_health(self, timeout: float = 3.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.is_skills_server_running():
                return True
            time.sleep(0.1)
        return False

    def _endpoint_status(self, auth_token: str = "") -> str:
        lines = [
            f"Local: {self.get_skills_http_endpoint()}",
            f"Network: {self.get_skills_network_endpoint()}" if self._remote_access_enabled() else "Network: disabled",
            "Authentication: required" if self._require_auth() else "Authentication: disabled (local only)",
        ]
        if auth_token and self._generated_auth_token:
            lines.append(f"Generated token: {auth_token}")
        return "\n".join(lines)

    def _show_missing_runtime(self, status: Dict[str, Any], auto_exit: bool) -> None:
        lines = format_runtime_status_lines(status)
        lines.append(
            "3 秒后退出当前 Skills 启动流程。" if auto_exit else "3 秒后返回菜单界面..."
        )
        self._show_status_panel("Skills 组件或依赖缺失。", "\n".join(lines), "yellow")

    def _show_runtime_error(self, title: str, exc: Exception, auto_exit: bool) -> None:
        footer = "3 秒后退出当前 Skills 启动流程。" if auto_exit else "3 秒后返回菜单界面..."
        self._show_status_panel(title, f"{type(exc).__name__}: {exc}\n\n{footer}", "red")

    def _show_status_panel(self, title: str, body: str, border_style: str = "cyan") -> None:
        console.print(Panel(body, title=title, border_style=border_style, expand=False))

    def _t(self, key: str, default: str) -> str:
        i18n = self.i18n
        if i18n is None:
            return default
        try:
            value = i18n.get(key)
        except Exception:
            return default
        return default if not value or value == key else str(value)

    def _detect_local_ip(self) -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"


__all__ = ["SkillsRuntimeBridge"]
