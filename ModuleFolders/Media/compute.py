"""Compute selection keeps GGUF acceleration separate from ASR Torch devices."""

import json
import platform
import subprocess
import sys


def detect_adapters() -> list[dict]:
    if sys.platform == "darwin":
        if platform.machine().lower() in {"arm64", "aarch64"}:
            return [{"name": "Apple Silicon", "vendor": "apple"}]
        return []
    if sys.platform != "win32":
        return []
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
             "Get-CimInstance Win32_VideoController | Select-Object Name,PNPDeviceID | ConvertTo-Json -Compress"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode:
            return []
        rows = json.loads(result.stdout)
        if isinstance(rows, dict):
            rows = [rows]
        adapters = []
        for row in rows or []:
            name = row.get("Name", "")
            identity = row.get("PNPDeviceID", "").upper()
            upper = name.upper()
            vendor = "nvidia" if "VEN_10DE" in identity or "NVIDIA" in upper else (
                "amd" if "VEN_1002" in identity or "AMD" in upper or "RADEON" in upper else (
                    "intel" if "VEN_8086" in identity or "INTEL" in upper else "unknown"))
            adapters.append({"name": name, "vendor": vendor})
        return adapters
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []


def select_compute(requested: str, *, gguf: bool, cuda_available: bool, adapters: list[dict],
                   mlx_compatible: bool = True, mps_available: bool | None = None) -> dict:
    if requested not in {"auto", "cuda:0", "vulkan", "cpu", "mlx", "metal", "mps"}:
        raise ValueError("Unsupported compute device")
    vendors = {item["vendor"] for item in adapters}
    chosen = requested
    if requested == "auto":
        if "apple" in vendors:
            chosen = "metal" if gguf else "mlx" if mlx_compatible else "mps"
        elif cuda_available:
            chosen = "cuda:0"
        else:
            chosen = "vulkan" if gguf and vendors & {"amd", "intel", "nvidia"} else "cpu"
    if chosen in {"mlx", "metal", "mps"} and sys.platform != "darwin":
        raise RuntimeError("Apple acceleration requires macOS")
    if chosen == "mlx" and ("apple" not in vendors or gguf or not mlx_compatible):
        raise RuntimeError("MLX requires native Apple Silicon and an Index Transformers checkpoint; use Metal GGUF or MPS")
    if chosen == "metal" and not gguf:
        raise RuntimeError("Metal requires a GGUF translation model")
    if chosen == "mps" and (gguf or mps_available is False):
        raise RuntimeError("MPS requires a supported PyTorch macOS device and a Transformers checkpoint")
    if chosen == "cuda:0" and not cuda_available:
        raise RuntimeError("CUDA is not available; select Vulkan for GGUF or CPU")
    if chosen == "vulkan" and not gguf:
        raise RuntimeError("Vulkan requires a GGUF translation model")
    return {"translation_device": chosen, "asr_device": "cuda:0" if chosen == "cuda:0" else "cpu",
            "llama_backend": {"cuda:0": "cuda", "vulkan": "vulkan", "cpu": "cpu",
                              "metal": "metal", "mlx": "", "mps": ""}[chosen]}


def device_choices() -> tuple[str, ...]:
    return ("auto", "mlx", "metal", "mps", "cpu") if sys.platform == "darwin" else ("auto", "cuda:0", "vulkan", "cpu")


def model_device_choices(family: str) -> tuple[str, ...]:
    from ModuleFolders.Media.model_catalog import get_model
    model = get_model(family)
    excluded = {"mlx", "mps"} if model.backend == "gguf" else {"metal", "vulkan"}
    if model.family != "index":
        excluded.add("mlx")
    return tuple(choice for choice in device_choices() if choice not in excluded)
