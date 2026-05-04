from __future__ import annotations

import importlib.metadata as metadata
import os
import platform
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt
from rich.table import Table


class MangaRuntimeMenu:
    """MangaCore visual runtime dependency switcher."""

    RUNTIME_PACKAGE_NAMES = (
        "torch",
        "torchvision",
        "torchaudio",
        "onnxruntime",
        "onnxruntime-gpu",
    )
    TORCH_PACKAGES = (
        "torch==2.8.0",
        "torchvision==0.23.0",
        "torchaudio==2.8.0",
    )
    PYPI_TORCH_PACKAGES = (
        "torch>=2.0.0",
        "torchvision>=0.15.0",
        "torchaudio>=2.0.0",
    )
    CPU_PACKAGES = TORCH_PACKAGES + ("onnxruntime==1.20.1",)
    CUDA_PACKAGES = TORCH_PACKAGES + ("onnxruntime-gpu==1.20.1",)
    PYPI_CPU_PACKAGES = PYPI_TORCH_PACKAGES + ("onnxruntime==1.20.1",)
    DEVICE_CONFIG_KEYS = (
        "manga_runtime_device",
        "manga_detect_device",
        "manga_ocr_device",
        "manga_inpaint_device",
    )

    def __init__(self, host):
        self.host = host
        self.console = Console()

    @property
    def i18n(self):
        return self.host.i18n

    def _t(self, key: str, default: str) -> str:
        value = self.i18n.get(key)
        return default if value == key else value

    def show(self) -> None:
        while True:
            self.host.display_banner()
            self.console.print(Panel(f"[bold]{self._t('menu_manga_runtime_manager', 'Manga Runtime Manager')}[/bold]"))
            self._print_status()

            action_map = {}
            option_id = 1
            table = Table(show_header=False, box=None)

            table.add_row(f"[cyan]{option_id}.[/]", self._t("manga_runtime_menu_check", "Check current runtime"))
            action_map[option_id] = self._wait
            option_id += 1

            recommended = self._recommended_backend()
            table.add_row(
                f"[cyan]{option_id}.[/]",
                self._t("manga_runtime_menu_install_recommended", "Install recommended runtime ({})").format(
                    recommended["label"]
                ),
            )
            action_map[option_id] = lambda target=recommended["key"]: self._switch_runtime(target)
            option_id += 1

            for backend in self._installable_backends():
                table.add_row(
                    f"[cyan]{option_id}.[/]",
                    self._install_menu_label(str(backend["key"])).format(backend["label"]),
                )
                action_map[option_id] = lambda target=backend["key"]: self._switch_runtime(str(target))
                option_id += 1

            for device in self._config_devices():
                table.add_row(f"[cyan]{option_id}.[/]", self._config_menu_label(device))
                action_map[option_id] = lambda value=device: self._apply_device_config_and_wait(value)
                option_id += 1

            table.add_row("[red]0.[/]", self.i18n.get("menu_exit"))
            self.console.print(table)

            choice = IntPrompt.ask(
                f"\n{self.i18n.get('prompt_select')}",
                choices=[str(i) for i in range(option_id)],
                show_choices=False,
            )
            if choice == 0:
                return
            action = action_map.get(choice)
            if action:
                action()

    def _print_status(self) -> None:
        table = Table(show_header=True, expand=False)
        table.add_column(self._t("manga_runtime_status_item", "Item"), style="cyan")
        table.add_column(self._t("manga_runtime_status_value", "Value"), style="white")
        table.add_row("Python", sys.executable)
        table.add_row(self._t("manga_runtime_status_venv", "Venv"), str(self._current_venv_path()))
        table.add_row(self._t("manga_runtime_status_platform", "Platform"), self._platform_summary())
        table.add_row(
            self._t("manga_runtime_status_recommended", "Recommended runtime"),
            str(self._recommended_backend()["label"]),
        )
        for package_name in self.RUNTIME_PACKAGE_NAMES:
            table.add_row(package_name, self._package_version(package_name))
        table.add_row("torch.cuda.is_available()", self._torch_cuda_status())
        table.add_row("onnxruntime providers", self._onnxruntime_providers())
        table.add_row("Manga device config", self._device_config_summary())
        self.console.print(table)

        self.console.print(
            f"[dim]{self._t('manga_runtime_menu_scope_hint', 'This menu only switches visual backend packages. It does not reinstall tokenizers, transformers, or tiktoken.')}[/dim]"
        )

    def _package_version(self, package_name: str) -> str:
        try:
            return metadata.version(package_name)
        except metadata.PackageNotFoundError:
            return self._t("label_not_set", "Not Set")

    def _torch_cuda_status(self) -> str:
        try:
            import torch

            available = bool(torch.cuda.is_available())
            cuda_version = getattr(torch.version, "cuda", None) or "none"
            device_count = torch.cuda.device_count() if available else 0
            return f"{available} | cuda={cuda_version} | devices={device_count}"
        except Exception as exc:
            return f"{self._t('manga_runtime_status_unavailable', 'Unavailable')}: {exc}"

    def _onnxruntime_providers(self) -> str:
        try:
            import onnxruntime

            return ", ".join(onnxruntime.get_available_providers())
        except Exception as exc:
            return f"{self._t('manga_runtime_status_unavailable', 'Unavailable')}: {exc}"

    def _device_config_summary(self) -> str:
        return ", ".join(f"{key}={self.host.config.get(key, 'auto')}" for key in self.DEVICE_CONFIG_KEYS)

    def _switch_runtime(self, target: str) -> None:
        backend = self._backend_by_key(target)
        if backend is None:
            self.console.print(
                f"[red]{self._t('manga_runtime_backend_unavailable', 'This runtime backend is not available on the current system.')}[/red]"
            )
            self._wait()
            return

        label = str(backend["label"])
        if not Confirm.ask(
            self._t(
                "manga_runtime_confirm_switch",
                "This will uninstall conflicting Manga visual runtime packages and install the selected backend. Continue?",
            ).format(label),
            default=False,
        ):
            return

        self.console.print(Panel(self._t("manga_runtime_uninstalling", "Removing conflicting runtime packages...")))
        if not self._run_uv_pip(["uninstall", "--python", sys.executable, *self.RUNTIME_PACKAGE_NAMES]):
            self._wait()
            return

        self.console.print(Panel(self._t("manga_runtime_installing", "Installing selected runtime packages...").format(label)))
        ok = self._run_uv_pip(["install", "--python", sys.executable, *backend["install_args"]])

        if ok:
            self._apply_device_config(str(backend["device"]))
            self.console.print(f"[bold green]{self._t('manga_runtime_switch_done', 'Manga runtime switch completed.')}[/bold green]")
            self._restart_after_install()
        else:
            self.console.print(f"[bold red]{self._t('manga_runtime_switch_failed', 'Manga runtime switch failed.')}[/bold red]")
            self._wait()

    def _run_uv_pip(self, pip_args: list[str]) -> bool:
        uv_executable = self._uv_executable()
        if not uv_executable:
            self.console.print(
                f"[red]{self._t('manga_runtime_uv_missing', 'uv was not found. Please run the project prepare script first.')}[/red]"
            )
            return False

        cmd = [uv_executable, "pip", *pip_args]
        self.console.print(f"[dim]{self._format_command(cmd)}[/dim]")
        try:
            process = subprocess.Popen(
                cmd,
                cwd=str(self._project_root()),
                env=self._uv_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as exc:
            self.console.print(f"[red]{self._t('manga_runtime_command_start_failed', 'Failed to start command')}: {exc}[/red]")
            return False

        assert process.stdout is not None
        for line in process.stdout:
            self.console.print(line.rstrip())
        return process.wait() == 0

    def _apply_device_config(self, device: str) -> None:
        normalized = device if device in {"auto", "cpu", "cuda", "mps"} else "auto"
        for key in self.DEVICE_CONFIG_KEYS:
            self.host.config[key] = normalized
        self.host.save_config()
        self.console.print(
            f"[green]{self._t('manga_runtime_config_saved', 'Manga device config saved')}: {self._device_config_summary()}[/green]"
        )

    def _apply_device_config_and_wait(self, device: str) -> None:
        self._apply_device_config(device)
        self._wait()

    def _install_menu_label(self, key: str) -> str:
        if key == "cuda":
            return self._t("manga_runtime_menu_switch_cuda", "Switch/install {} runtime")
        if key == "mps":
            return self._t("manga_runtime_menu_switch_metal", "Switch/install {} runtime")
        return self._t("manga_runtime_menu_switch_cpu", "Switch/install {} runtime")

    def _config_menu_label(self, device: str) -> str:
        if device == "auto":
            return self._t("manga_runtime_menu_config_auto", "Only set Manga device config to auto")
        if device == "cuda":
            return self._t("manga_runtime_menu_config_cuda", "Only set Manga device config to CUDA")
        if device == "mps":
            return self._t("manga_runtime_menu_config_mps", "Only set Manga device config to Metal/MPS")
        return self._t("manga_runtime_menu_config_cpu", "Only set Manga device config to CPU")

    def _installable_backends(self) -> list[dict[str, object]]:
        backends = [self._cpu_backend()]
        if self._supports_cuda_install():
            backends.append(self._cuda_backend())
        if self._is_macos():
            backends.append(self._mps_backend())
        return backends

    def _backend_by_key(self, key: str) -> dict[str, object] | None:
        for backend in self._installable_backends():
            if backend["key"] == key:
                return backend
        return None

    def _recommended_backend(self) -> dict[str, object]:
        if self._is_macos():
            return self._mps_backend()
        if self._supports_cuda_install() and self._detect_nvidia_gpu():
            return self._cuda_backend()
        return self._cpu_backend()

    def _config_devices(self) -> list[str]:
        devices = ["auto", "cpu"]
        if self._supports_cuda_install():
            devices.append("cuda")
        if self._is_macos():
            devices.append("mps")
        return devices

    def _cpu_backend(self) -> dict[str, object]:
        install_args: list[str] = []
        if self._uses_pytorch_cpu_index():
            install_args.extend(
                [
                    "--index-url",
                    "https://download.pytorch.org/whl/cpu",
                    "--extra-index-url",
                    "https://pypi.org/simple",
                    *self.CPU_PACKAGES,
                ]
            )
        else:
            install_args.extend(self.PYPI_CPU_PACKAGES)
        return {
            "key": "cpu",
            "label": "CPU",
            "device": "cpu",
            "install_args": tuple(install_args),
        }

    def _cuda_backend(self) -> dict[str, object]:
        return {
            "key": "cuda",
            "label": "CUDA",
            "device": "cuda",
            "install_args": (
                "--index-url",
                "https://download.pytorch.org/whl/cu128",
                "--extra-index-url",
                "https://pypi.org/simple",
                *self.CUDA_PACKAGES,
            ),
        }

    def _mps_backend(self) -> dict[str, object]:
        return {
            "key": "mps",
            "label": "Metal/MPS",
            "device": "mps",
            "install_args": self.PYPI_CPU_PACKAGES,
        }

    def _uses_pytorch_cpu_index(self) -> bool:
        return self._platform_system() in {"windows", "linux"} and self._is_x64()

    def _supports_cuda_install(self) -> bool:
        return self._platform_system() in {"windows", "linux"} and self._is_x64()

    def _is_macos(self) -> bool:
        return self._platform_system() == "darwin"

    def _is_x64(self) -> bool:
        machine = platform.machine().lower()
        return machine in {"amd64", "x86_64", "x64"}

    def _platform_system(self) -> str:
        return platform.system().lower()

    def _platform_summary(self) -> str:
        return f"{platform.system() or 'Unknown'} / {platform.machine() or 'Unknown'}"

    def _detect_nvidia_gpu(self) -> bool:
        try:
            import torch

            if bool(torch.cuda.is_available()):
                return True
        except Exception:
            pass

        nvidia_smi = shutil.which("nvidia-smi")
        if not nvidia_smi:
            return False
        try:
            result = subprocess.run(
                [nvidia_smi, "-L"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _uv_executable(self) -> str:
        uv_path = shutil.which("uv")
        if uv_path:
            return uv_path

        candidate = Path.home() / ".cargo" / "bin" / ("uv.exe" if os.name == "nt" else "uv")
        if candidate.exists():
            return str(candidate)
        return ""

    def _uv_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["UV_PROJECT_ENVIRONMENT"] = str(self._current_venv_path())
        return env

    def _current_venv_path(self) -> Path:
        for raw_path in (
            os.environ.get("UV_PROJECT_ENVIRONMENT"),
            os.environ.get("VIRTUAL_ENV"),
            self._venv_from_executable(),
        ):
            if not raw_path:
                continue
            candidate = Path(raw_path)
            if (candidate / "pyvenv.cfg").exists():
                return candidate
        return self._default_venv_path()

    def _venv_from_executable(self) -> str:
        executable = Path(sys.executable).resolve()
        if executable.parent.name.lower() in {"scripts", "bin"}:
            return str(executable.parent.parent)
        return ""

    def _default_venv_path(self) -> Path:
        if os.name == "nt":
            return self._project_root() / ".venv-win"
        return self._project_root() / ".venv"

    def _restart_after_install(self) -> None:
        self.console.print(f"[bold yellow]{self._t('manga_runtime_restart_notice', 'Project will restart in 3 seconds...')}[/bold yellow]")
        time.sleep(3)

        uv_executable = self._uv_executable()
        if not uv_executable:
            self.console.print(
                f"[red]{self._t('manga_runtime_uv_missing', 'uv was not found. Please run the project prepare script first.')}[/red]"
            )
            self._wait()
            return

        project_root = self._project_root()
        script_path = project_root / "ainiee_cli.py"
        cmd = [uv_executable, "run", "--directory", str(project_root), "--no-sync", "python", str(script_path), *sys.argv[1:]]
        env = self._uv_env()
        self.console.print(f"[dim]{self._format_command(cmd)}[/dim]")
        try:
            os.execvpe(uv_executable, cmd, env)
        except Exception as exc:
            self.console.print(f"[red]{self._t('manga_runtime_command_start_failed', 'Failed to start command')}: {exc}[/red]")
            self._wait()

    def _format_command(self, cmd: list[str]) -> str:
        if os.name == "nt":
            return subprocess.list2cmdline(cmd)
        return shlex.join(cmd)

    def _project_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def _wait(self) -> None:
        self.console.print()
        self.console.input(self.i18n.get("msg_press_enter_to_continue"))
