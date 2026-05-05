from __future__ import annotations

import importlib.metadata as metadata
import locale
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

    PYTHON_TAG = "cp312-cp312"
    TORCH_VERSION = "2.8.0"
    TORCHVISION_VERSION = "0.23.0"
    ONNXRUNTIME_VERSION = "1.20.1"
    PYTORCH_WHEEL_MIRROR = "https://mirrors.aliyun.com/pytorch-wheels"
    PYTORCH_WHEEL_OFFICIAL = "https://download.pytorch.org/whl"
    PYPI_INDEX_URL = "https://pypi.org/simple"
    PYTORCH_SOURCE_ENV_KEYS = ("AINIEE_MANGA_PYTORCH_SOURCE", "AINIEE_PYTORCH_SOURCE")
    PYTORCH_MIRROR_ENV_KEY = "AINIEE_MANGA_PYTORCH_MIRROR"
    PYTORCH_OFFICIAL_ENV_KEY = "AINIEE_MANGA_PYTORCH_OFFICIAL"
    INSTALL_PACKAGE_NAMES = (
        "torch",
        "torchvision",
        "onnxruntime",
        "onnxruntime-gpu",
    )
    CONFLICT_PACKAGE_NAMES = INSTALL_PACKAGE_NAMES + ("torchaudio",)
    PYPI_TORCH_PACKAGES = (
        "torch>=2.0.0",
        "torchvision>=0.15.0",
    )
    PYPI_CPU_PACKAGES = PYPI_TORCH_PACKAGES + (f"onnxruntime=={ONNXRUNTIME_VERSION}",)
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
        self.console.print(
            f"[yellow]{self._t('manga_runtime_collecting_system_info', 'Collecting system information, please wait....')}[/yellow]"
        )
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
        for package_name in self.CONFLICT_PACKAGE_NAMES:
            table.add_row(package_name, self._package_version(package_name))
        table.add_row("torch.cuda.is_available()", self._torch_cuda_status())
        table.add_row("onnxruntime providers", self._onnxruntime_providers())
        table.add_row("Manga device config", self._device_config_summary())
        self.console.print(table)

        self.console.print(
            f"[dim]{self._t('manga_runtime_menu_scope_hint', 'This menu only switches Manga visual runtime packages. It cleans torchaudio if present, but does not install it; tokenizers, transformers, and tiktoken are not touched.')}[/dim]"
        )

    def _package_version(self, package_name: str) -> str:
        try:
            return metadata.version(package_name)
        except metadata.PackageNotFoundError:
            return self._t("label_not_set", "Not Set")

    def _torch_cuda_status(self) -> str:
        return self._run_python_probe(
            "import torch\n"
            "available=bool(torch.cuda.is_available())\n"
            "count=int(torch.cuda.device_count()) if available else 0\n"
            "name=torch.cuda.get_device_name(0) if available and count > 0 else 'none'\n"
            "cuda=getattr(torch.version, 'cuda', None) or 'none'\n"
            "print(f'{available} | torch={torch.__version__} | cuda={cuda} | devices={count} | device={name} | file={torch.__file__}')\n"
        )

    def _onnxruntime_providers(self) -> str:
        return self._run_python_probe(
            "import onnxruntime as ort\n"
            "providers=', '.join(ort.get_available_providers())\n"
            "print(f'{providers} | version={ort.__version__} | file={ort.__file__}')\n"
        )

    def _run_python_probe(self, code: str) -> str:
        try:
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=str(self._project_root()),
                env=self._uv_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
            )
        except Exception as exc:
            return f"{self._t('manga_runtime_status_unavailable', 'Unavailable')}: {exc}"

        output = (result.stdout or "").strip()
        if result.returncode == 0 and output:
            return output.splitlines()[-1]
        return f"{self._t('manga_runtime_status_unavailable', 'Unavailable')}: {output or result.returncode}"

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
        if not self._repair_runtime_metadata():
            self._wait()
            return
        if not self._run_uv_pip(["uninstall", "--python", sys.executable, *self.CONFLICT_PACKAGE_NAMES]):
            self._wait()
            return

        self.console.print(Panel(self._t("manga_runtime_installing", "Installing selected runtime packages...").format(label)))
        ok = self._install_backend(backend)

        if ok:
            self._apply_device_config(str(backend["device"]))
            self.console.print(f"[bold green]{self._t('manga_runtime_switch_done', 'Manga runtime switch completed.')}[/bold green]")
            self._restart_after_install()
        else:
            self.console.print(f"[bold red]{self._t('manga_runtime_switch_failed', 'Manga runtime switch failed.')}[/bold red]")
            self._wait()

    def _install_backend(self, backend: dict[str, object]) -> bool:
        if not self._repair_runtime_metadata():
            return False
        plans = self._backend_install_plans(str(backend["key"]))
        for index, plan in enumerate(plans):
            source_label = str(plan["label"])
            if len(plans) > 1:
                message_key = "manga_runtime_source_selected" if index == 0 else "manga_runtime_source_retry"
                default = "Runtime dependency source: {}" if index == 0 else "Current source failed. Retrying with {}..."
                self.console.print(f"[yellow]{self._t(message_key, default).format(source_label)}[/yellow]")

            if self._run_uv_pip(["install", "--python", sys.executable, *plan["install_args"]]):
                return True
        return False

    def _repair_runtime_metadata(self) -> bool:
        repair_script = self._project_root() / "ModuleFolders" / "MangaCore" / "runtime" / "repair_runtime_metadata.py"
        if not repair_script.exists():
            return True

        cmd = [sys.executable, str(repair_script)]
        self.console.print(f"[dim]{self._format_command(cmd)}[/dim]")
        try:
            process = subprocess.run(
                cmd,
                cwd=str(self._project_root()),
                env=self._uv_env(),
                check=False,
            )
        except Exception as exc:
            self.console.print(f"[red]{self._t('manga_runtime_command_start_failed', 'Failed to start command')}: {exc}[/red]")
            return False
        return process.returncode == 0

    def _run_uv_pip(self, pip_args: list[str]) -> bool:
        uv_executable = self._uv_executable()
        if not uv_executable:
            self.console.print(
                f"[red]{self._t('manga_runtime_uv_missing', 'uv was not found. Please run the project prepare script first.')}[/red]"
            )
            return False

        env = self._uv_pip_env(pip_args)
        use_terminal_output = self.console.is_terminal
        cmd = [uv_executable]
        if use_terminal_output:
            cmd.extend(("--color", "always"))
        cmd.extend(("pip", *pip_args))
        self.console.print(f"[dim]{self._format_command(cmd)}[/dim]")
        if use_terminal_output:
            try:
                return (
                    subprocess.run(
                        cmd,
                        cwd=str(self._project_root()),
                        env=env,
                        check=False,
                    ).returncode
                    == 0
                )
            except Exception as exc:
                self.console.print(f"[red]{self._t('manga_runtime_command_start_failed', 'Failed to start command')}: {exc}[/red]")
                return False

        try:
            process = subprocess.Popen(
                cmd,
                cwd=str(self._project_root()),
                env=env,
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

    def _uv_pip_env(self, pip_args: list[str]) -> dict[str, str]:
        env = self._uv_env()
        env["UV_LINK_MODE"] = "copy"
        env.pop("UV_NO_PROGRESS", None)

        torch_backend = self._torch_backend_from_args(pip_args)
        if torch_backend:
            env["UV_TORCH_BACKEND"] = torch_backend
        return env

    def _torch_backend_from_args(self, pip_args: list[str]) -> str:
        try:
            index = pip_args.index("--torch-backend")
        except ValueError:
            return ""

        if index + 1 >= len(pip_args):
            return ""
        return pip_args[index + 1]

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
        return {
            "key": "cpu",
            "label": "CPU",
            "device": "cpu",
        }

    def _cuda_backend(self) -> dict[str, object]:
        return {
            "key": "cuda",
            "label": "CUDA",
            "device": "cuda",
        }

    def _mps_backend(self) -> dict[str, object]:
        return {
            "key": "mps",
            "label": "Metal/MPS",
            "device": "mps",
        }

    def _backend_install_plans(self, key: str) -> tuple[dict[str, object], ...]:
        if key == "cuda":
            return tuple(
                {
                    "label": source["label"],
                    "install_args": self._torch_runtime_install_args(
                        "cu128",
                        source,
                        f"onnxruntime-gpu=={self.ONNXRUNTIME_VERSION}",
                    ),
                }
                for source in self._pytorch_source_order()
            )

        if key == "cpu" and self._uses_pytorch_cpu_index():
            return tuple(
                {
                    "label": source["label"],
                    "install_args": self._torch_runtime_install_args(
                        "cpu",
                        source,
                        f"onnxruntime=={self.ONNXRUNTIME_VERSION}",
                    ),
                }
                for source in self._pytorch_source_order()
            )

        return (
            {
                "label": self._t("manga_runtime_source_pypi", "PyPI"),
                "install_args": (*self._default_index_args(), *self._refresh_runtime_package_args(), "--reinstall", *self.PYPI_CPU_PACKAGES),
            },
        )

    def _torch_runtime_install_args(self, backend: str, source: dict[str, str], onnxruntime_requirement: str) -> tuple[str, ...]:
        return (
            *self._default_index_args(),
            *self._refresh_runtime_package_args(),
            "--reinstall",
            *self._pytorch_wheel_urls(backend, source),
            onnxruntime_requirement,
        )

    def _default_index_args(self) -> tuple[str, ...]:
        if os.environ.get("UV_DEFAULT_INDEX") or os.environ.get("UV_INDEX_URL"):
            return ()
        return ("--default-index", self.PYPI_INDEX_URL)

    def _refresh_runtime_package_args(self) -> tuple[str, ...]:
        args: list[str] = []
        for package_name in self.INSTALL_PACKAGE_NAMES:
            args.extend(("--refresh-package", package_name))
        return tuple(args)

    def _pytorch_source_order(self) -> tuple[dict[str, str], dict[str, str]]:
        sources = self._pytorch_sources()
        preferred = self._pytorch_source_override()
        if not preferred:
            preferred = "mirror" if self._prefer_china_mirror() else "official"

        secondary = "official" if preferred == "mirror" else "mirror"
        return sources[preferred], sources[secondary]

    def _pytorch_sources(self) -> dict[str, dict[str, str]]:
        mirror_base_url = os.environ.get(self.PYTORCH_MIRROR_ENV_KEY, self.PYTORCH_WHEEL_MIRROR).strip()
        official_base_url = os.environ.get(self.PYTORCH_OFFICIAL_ENV_KEY, self.PYTORCH_WHEEL_OFFICIAL).strip()
        return {
            "mirror": {
                "key": "mirror",
                "label": self._t("manga_runtime_source_aliyun", "Aliyun PyTorch mirror"),
                "base_url": mirror_base_url or self.PYTORCH_WHEEL_MIRROR,
                "layout": "flat",
            },
            "official": {
                "key": "official",
                "label": self._t("manga_runtime_source_official", "official PyTorch source"),
                "base_url": official_base_url or self.PYTORCH_WHEEL_OFFICIAL,
                "layout": "package",
            },
        }

    def _pytorch_source_override(self) -> str:
        for env_key in self.PYTORCH_SOURCE_ENV_KEYS:
            raw_value = os.environ.get(env_key, "").strip().lower()
            if raw_value in {"mirror", "aliyun", "china", "cn", "国内"}:
                return "mirror"
            if raw_value in {"official", "global", "foreign", "abroad", "pytorch", "国外"}:
                return "official"
        return ""

    def _prefer_china_mirror(self) -> bool:
        signals = [
            os.environ.get("LANG", ""),
            os.environ.get("LC_ALL", ""),
            os.environ.get("LC_MESSAGES", ""),
            os.environ.get("LANGUAGE", ""),
            os.environ.get("TZ", ""),
            " ".join(time.tzname),
            time.strftime("%Z"),
        ]
        try:
            signals.extend(value or "" for value in locale.getlocale())
        except Exception:
            pass

        normalized = " ".join(signals).lower().replace("-", "_")
        return any(
            token in normalized
            for token in (
                "zh_cn",
                "zh_hans",
                "china",
                "asia/shanghai",
                "asia/chongqing",
                "asia/urumqi",
                "中国",
                "中文",
            )
        )

    def _pytorch_wheel_urls(self, backend: str, source: dict[str, str]) -> tuple[str, str]:
        platform_tag = self._pytorch_platform_tag()
        suffix = backend if backend == "cpu" else "cu128"
        return (
            self._pytorch_wheel_url(source, backend, "torch", self.TORCH_VERSION, suffix, platform_tag),
            self._pytorch_wheel_url(source, backend, "torchvision", self.TORCHVISION_VERSION, suffix, platform_tag),
        )

    def _pytorch_wheel_url(
        self,
        source: dict[str, str],
        backend: str,
        package_name: str,
        version: str,
        suffix: str,
        platform_tag: str,
    ) -> str:
        filename = f"{package_name}-{version}+{suffix}-{self.PYTHON_TAG}-{platform_tag}.whl"
        filename = filename.replace("+", "%2B")
        base_url = source["base_url"].rstrip("/")
        if source.get("layout") == "flat":
            return f"{base_url}/{backend}/{filename}"
        return f"{base_url}/{backend}/{package_name}/{filename}"

    def _pytorch_platform_tag(self) -> str:
        if self._platform_system() == "windows":
            return "win_amd64"
        return "manylinux_2_28_x86_64"

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

        project_root = self._project_root()
        script_path = project_root / "ainiee_cli.py"
        cmd = [sys.executable, str(script_path), *sys.argv[1:]]
        env = self._uv_env()
        self.console.print(f"[dim]{self._format_command(cmd)}[/dim]")
        try:
            os.chdir(project_root)
            os.execve(sys.executable, cmd, env)
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
