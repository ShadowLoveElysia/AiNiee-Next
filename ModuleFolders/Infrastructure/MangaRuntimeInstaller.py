"""Shared Manga runtime backend plans for terminal and API maintenance."""
from __future__ import annotations

import locale
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import time


class MangaRuntimeInstaller:
    PYTHON_TAG = "cp312-cp312"
    TORCH_VERSION = "2.8.0"
    TORCHVISION_VERSION = "0.23.0"
    ONNXRUNTIME_CPU_VERSION = "1.20.1"
    ONNXRUNTIME_GPU_VERSION = "1.20.2"
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
    PYPI_CPU_PACKAGES = PYPI_TORCH_PACKAGES + (f"onnxruntime=={ONNXRUNTIME_CPU_VERSION}",)
    DEVICE_CONFIG_KEYS = (
        "manga_runtime_device",
        "manga_detect_device",
        "manga_ocr_device",
        "manga_inpaint_device",
    )

    def __init__(self, project_root=None, interpreter=None):
        self.project_root = Path(project_root or Path(__file__).resolve().parents[2])
        self.interpreter = interpreter or sys.executable

    def _t(self, key, default):
        return default

    def _project_root(self):
        return self.project_root

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
                        f"onnxruntime-gpu=={self.ONNXRUNTIME_GPU_VERSION}",
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
                        f"onnxruntime=={self.ONNXRUNTIME_CPU_VERSION}",
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
        executable = Path(self.interpreter).absolute()
        if executable.parent.name.lower() in {"scripts", "bin"}:
            return str(executable.parent.parent)
        return ""

    def _default_venv_path(self) -> Path:
        if os.name == "nt":
            return self._project_root() / ".venv-win"
        return self._project_root() / ".venv"

