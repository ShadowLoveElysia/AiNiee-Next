from __future__ import annotations

import inspect
import json
import os
import re
from datetime import datetime
from pathlib import Path

from ModuleFolders.MangaCore.bridge.providerAdapter import (
    download_runtime_assets,
    get_detect_runtime_ids,
    get_inpaint_runtime_id,
    get_ocr_runtime_id,
    get_runtime_asset_status,
    runtime_device_status_from_config,
)
from ModuleFolders.MangaCore.pipeline.modelCatalog import get_model_package, list_model_packages

_DIRECT_REQUIRED_FILES: dict[str, tuple[str, ...]] = {
    "comic-text-detector": (
        "yolo-v5.safetensors",
        "unet.safetensors",
        "dbnet.safetensors",
    ),
}
_DEFAULT_HF_ENDPOINT = "https://hf-mirror.com"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-") or "model"


def _ensure_huggingface_endpoint() -> str:
    endpoint = (os.environ.get("HF_ENDPOINT") or _DEFAULT_HF_ENDPOINT).rstrip("/")
    os.environ["HF_ENDPOINT"] = endpoint
    os.environ.setdefault("HF_HUB_ENDPOINT", endpoint)
    return endpoint


def _snapshot_download(repo_id: str, cache_dir: str) -> str:
    endpoint = _ensure_huggingface_endpoint()
    try:
        from huggingface_hub import snapshot_download
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "huggingface-hub is required only when downloading non-runtime MangaCore "
            "model packages with Hugging Face snapshots. Runtime-backed default models "
            "use the dedicated MangaCore model downloader."
        ) from exc

    kwargs: dict[str, object] = {
        "repo_id": repo_id,
        "cache_dir": cache_dir,
        "local_files_only": False,
    }
    try:
        if "endpoint" in inspect.signature(snapshot_download).parameters:
            kwargs["endpoint"] = endpoint
    except (TypeError, ValueError):
        pass
    return str(snapshot_download(**kwargs))


class MangaModelStore:
    def __init__(self, root_dir: str | Path | None = None) -> None:
        if root_dir is None:
            root_dir = Path(__file__).resolve().parents[3] / "Resource" / "Models" / "MangaCore"
        self.root_dir = Path(root_dir)

    def huggingface_cache_dir(self) -> Path:
        return self.root_dir / "huggingface"

    def registry_dir(self) -> Path:
        return self.root_dir / "registry"

    def registry_path(self, model_id: str) -> Path:
        return self.registry_dir() / f"{_safe_name(model_id)}.json"

    def local_direct_snapshot_path(self, model_id: str) -> Path | None:
        package = get_model_package(model_id)
        candidate = self.huggingface_cache_dir() / package.repo_id
        required_files = _DIRECT_REQUIRED_FILES.get(package.model_id)
        if required_files:
            if all((candidate / filename).is_file() for filename in required_files):
                return candidate
            return None
        if candidate.exists():
            return candidate
        return None

    def get_status(self, model_id: str) -> dict[str, object]:
        package = get_model_package(model_id)
        record = self._read_record(model_id)
        snapshot_path = Path(record.get("snapshot_path", "")) if record.get("snapshot_path") else None
        runtime_status = get_runtime_asset_status(model_id, self.root_dir)
        if not snapshot_path and runtime_status.available and runtime_status.storage_path:
            snapshot_path = Path(runtime_status.storage_path)
        if runtime_status.supported:
            available = runtime_status.available
        else:
            if not snapshot_path or not snapshot_path.exists():
                snapshot_path = self.local_direct_snapshot_path(model_id)
            available = bool(snapshot_path and snapshot_path.exists())
        payload = package.to_dict()
        payload.update(
            {
                "available": available,
                "storage_root": str(self.root_dir),
                "cache_dir": str(self.huggingface_cache_dir()),
                "snapshot_path": str(snapshot_path) if snapshot_path else "",
                "downloaded_at": str(record.get("downloaded_at", "")),
                "revision": str(record.get("revision", "")),
                "runtime_supported": runtime_status.supported,
                "runtime_assets_path": runtime_status.storage_path,
                "runtime_engine_id": runtime_status.runtime_engine_id,
            }
        )
        return payload

    def list_statuses(self) -> list[dict[str, object]]:
        return [self.get_status(package.model_id) for package in list_model_packages()]

    def register_downloaded_snapshot(
        self,
        model_id: str,
        snapshot_path: str | Path,
        *,
        revision: str = "",
    ) -> dict[str, object]:
        package = get_model_package(model_id)
        snapshot = Path(snapshot_path).resolve()
        self._write_record(
            model_id,
            {
                "model_id": package.model_id,
                "repo_id": package.repo_id,
                "repo_url": package.repo_url,
                "snapshot_path": str(snapshot),
                "downloaded_at": _now_iso(),
                "revision": revision,
            },
        )
        return self.get_status(model_id)

    def download(self, model_id: str) -> dict[str, object]:
        package = get_model_package(model_id)
        runtime_status = get_runtime_asset_status(model_id, self.root_dir)
        if runtime_status.supported:
            downloaded_runtime_status = download_runtime_assets(model_id, self.root_dir)
            if downloaded_runtime_status is None or not downloaded_runtime_status.available:
                raise RuntimeError(f"Failed to prepare runtime assets for manga model: {model_id}")
            return self.register_downloaded_snapshot(
                model_id,
                downloaded_runtime_status.storage_path,
                revision=f"runtime:{downloaded_runtime_status.runtime_engine_id}",
            )

        self.huggingface_cache_dir().mkdir(parents=True, exist_ok=True)
        snapshot_path = _snapshot_download(package.repo_id, str(self.huggingface_cache_dir()))
        return self.register_downloaded_snapshot(
            model_id,
            snapshot_path,
            revision="downloaded",
        )

    def _read_record(self, model_id: str) -> dict[str, object]:
        path = self.registry_path(model_id)
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}

    def _write_record(self, model_id: str, payload: dict[str, object]) -> None:
        path = self.registry_path(model_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")


def build_engine_status(config_snapshot: dict[str, object] | None = None) -> dict[str, object]:
    snapshot = dict(config_snapshot) if isinstance(config_snapshot, dict) else {}
    store = MangaModelStore()

    ocr_id = str(snapshot.get("manga_ocr_engine") or "paddleocr-vl-1.5")
    detect_id = str(snapshot.get("manga_detect_engine") or "comic-text-bubble-detector")
    segment_id = str(snapshot.get("manga_segment_engine") or "comic-text-detector")
    inpaint_id = str(snapshot.get("manga_inpaint_engine") or "aot-inpainting")
    detector_runtime_id, segmenter_runtime_id = get_detect_runtime_ids(detect_id, segment_id, store.root_dir)
    ocr_device = runtime_device_status_from_config(snapshot, "ocr")
    detect_device = runtime_device_status_from_config(snapshot, "detect")
    inpaint_device = runtime_device_status_from_config(snapshot, "inpaint")

    return {
        "ocr": {
            "configured_engine_id": ocr_id,
            "configured_device": ocr_device.configured,
            "resolved_device": ocr_device.resolved,
            "device": ocr_device.to_dict(),
            "runtime_engine_id": get_ocr_runtime_id(ocr_id, store.root_dir),
            "package": store.get_status(ocr_id),
        },
        "detect": {
            "configured_detector_id": detect_id,
            "configured_segmenter_id": segment_id,
            "configured_device": detect_device.configured,
            "resolved_device": detect_device.resolved,
            "device": detect_device.to_dict(),
            "runtime_detector_id": detector_runtime_id,
            "runtime_segmenter_id": segmenter_runtime_id,
            "detector_package": store.get_status(detect_id),
            "segmenter_package": store.get_status(segment_id),
        },
        "inpaint": {
            "configured_engine_id": inpaint_id,
            "configured_device": inpaint_device.configured,
            "resolved_device": inpaint_device.resolved,
            "device": inpaint_device.to_dict(),
            "runtime_engine_id": get_inpaint_runtime_id(inpaint_id, store.root_dir),
            "package": store.get_status(inpaint_id),
        },
    }
