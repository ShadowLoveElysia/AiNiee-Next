"""Compute selection keeps GGUF acceleration separate from ASR Torch devices."""

import json
import subprocess
import sys


def detect_adapters() -> list[dict]:
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


def select_compute(requested: str, *, gguf: bool, cuda_available: bool, adapters: list[dict]) -> dict:
    if requested not in {"auto", "cuda:0", "vulkan", "cpu"}:
        raise ValueError("Unsupported compute device")
    vendors = {item["vendor"] for item in adapters}
    chosen = requested
    if requested == "auto":
        chosen = "cuda:0" if cuda_available else (
            "vulkan" if gguf and vendors & {"amd", "intel", "nvidia"} else "cpu")
    if chosen == "cuda:0" and not cuda_available:
        raise RuntimeError("CUDA is not available; select Vulkan for GGUF or CPU")
    if chosen == "vulkan" and not gguf:
        raise RuntimeError("Vulkan requires a GGUF translation model")
    return {"translation_device": chosen, "asr_device": "cuda:0" if chosen == "cuda:0" else "cpu",
            "llama_backend": {"cuda:0": "cuda", "vulkan": "vulkan", "cpu": "cpu"}[chosen]}
