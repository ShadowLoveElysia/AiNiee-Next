"""Compute selection keeps GGUF acceleration separate from ASR Torch devices."""

import json
import os
import platform
import re
import shutil
import subprocess
import sys


def detect_nvidia_devices() -> list[dict]:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return []
    try:
        result = subprocess.run([executable, "--query-gpu=name,compute_cap", "--format=csv,noheader,nounits"],
                                capture_output=True, text=True, encoding="utf-8", errors="replace",
                                timeout=15, stdin=subprocess.DEVNULL)
        if result.returncode:
            return []
        devices = []
        for line in result.stdout.splitlines():
            name, capability = line.rsplit(',', 1)
            parts = tuple(int(part) for part in capability.strip().split('.'))
            if len(parts) != 2:
                return []
            devices.append({"name": name.strip(), "vendor": "nvidia", "compute_capability": list(parts)})
        visible = os.environ.get("CUDA_VISIBLE_DEVICES")
        if visible is not None:
            indices = [int(value) for value in visible.split(',') if value.strip().isdigit()]
            if indices and all(index < len(devices) for index in indices):
                devices = [devices[index] for index in indices]
        return devices
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []


def detect_adapters() -> list[dict]:
    if sys.platform == "darwin":
        if platform.machine().lower() in {"arm64", "aarch64"}:
            return [{"name": "Apple Silicon", "vendor": "apple"}]
        return []
    if sys.platform != "win32":
        return detect_nvidia_devices()
    nvidia = detect_nvidia_devices()
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
             "Get-CimInstance Win32_VideoController | Select-Object Name,PNPDeviceID | ConvertTo-Json -Compress"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode:
            return nvidia
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
        return nvidia + [item for item in adapters if not nvidia or item["vendor"] != "nvidia"]
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return nvidia


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
            "llama_backend": {"cuda:0": cuda_runtime_backend(adapters), "vulkan": "vulkan", "cpu": "cpu",
                              "metal": "metal", "mlx": "", "mps": ""}[chosen]}


def cuda_runtime_backend(adapters: list[dict]) -> str:
    return "cuda-blackwell" if any(nvidia_architecture(item) == "blackwell" for item in adapters
                                    if item.get("vendor") == "nvidia") else "cuda"


def selected_cuda_adapters(torch, adapters: list[dict]) -> list[dict]:
    if torch.cuda.is_available():
        return [{"vendor": "nvidia", "name": torch.cuda.get_device_name(0),
                 "compute_capability": list(torch.cuda.get_device_capability(0))}]
    return adapters


def nvidia_architecture(adapter: dict) -> str:
    capability = adapter.get("compute_capability")
    if isinstance(capability, (list, tuple)) and len(capability) == 2:
        major = capability[0]
        if major < 5:
            return "unsupported"
        if major < 7:
            return "legacy"
        if major < 10:
            return "modern"
        if major in {10, 12}:
            return "blackwell"
        return "unknown"
    name = adapter.get("name", "").upper()
    if re.search(r"\bBLACKWELL\b|\bRTX\s*50[5-9]0\b|\bRTX\s+PRO\s+\d+\b|\b[BG]B(?:100|200|300)\b|\bB(?:100|200|300)\b", name):
        return "blackwell"
    if re.search(r"\b(?:GTX|GEFORCE)\s*(?:750|9\d{2}|10\d{2})(?:M)?\b|\b(?:QUADRO\s+)?[MP]\d{3,4}(?:M)?\b|\bTESLA\s+(?:M[46]0|P(?:4|6|40|100))\b|\bTITAN\s+(?:X|XP)\b|\b(?:MX(?:110|130|150|230|250|330|350|450|550|570)|GT\s+1030)\b", name):
        return "legacy"
    if re.search(r"\bRTX\s*(?:[234]\d{3}|A\d{3,4})\b|\bQUADRO\s+RTX\s+(?:5000|6000|8000)\b|\bGTX\s*16\d{2}\b|\bADA\b|\b(?:A100|A30|A40|A10G?|A16|A2|A800|H100|H200|H20|H800|V100|T4|L4|L40S?)\b|\b(?:QUADRO\s+)?T(?:400|500|550|600|1000|1200|2000)\b|\bTITAN\s+(?:V|RTX)\b", name):
        return "modern"
    return "unknown"


def select_cuda_build(adapters: list[dict], *, installed_build="", selected_adapter=None) -> str:
    devices = [selected_adapter] if selected_adapter else [item for item in adapters if item.get("vendor") == "nvidia"]
    categories = {nvidia_architecture(item) for item in devices}
    if "unsupported" in categories:
        raise RuntimeError("This GPU architecture is unsupported by Torch 2.9.1; select CPU explicitly")
    if not categories or "unknown" in categories:
        raise RuntimeError("Cannot identify NVIDIA architecture; use prepare_media.bat cuda:0 MODEL cu126 or cu128 explicitly")
    if "legacy" in categories and "blackwell" in categories:
        raise RuntimeError("Mixed legacy and Blackwell GPUs require a selected CUDA device; set CUDA_VISIBLE_DEVICES then retry")
    allowed = {"cu126"} if "legacy" in categories else {"cu128"} if "blackwell" in categories else {"cu126", "cu128"}
    return installed_build if installed_build in allowed else "cu126" if "legacy" in categories else "cu128"


def device_choices() -> tuple[str, ...]:
    return ("auto", "mlx", "metal", "mps", "cpu") if sys.platform == "darwin" else ("auto", "cuda:0", "vulkan", "cpu")


def model_device_choices(family: str) -> tuple[str, ...]:
    from ModuleFolders.Media.model_catalog import get_model
    model = get_model(family)
    excluded = {"mlx", "mps"} if model.backend == "gguf" else {"metal", "vulkan"}
    if model.family != "index":
        excluded.add("mlx")
    return tuple(choice for choice in device_choices() if choice not in excluded)
