from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from huggingface_hub import snapshot_download

from ModuleFolders.MangaCore.pipeline.modelCatalog import MangaModelPackage, get_model_package, list_model_packages


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-") or "model"


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

    def get_status(self, model_id: str) -> dict[str, object]:
        package = get_model_package(model_id)
        record = self._read_record(model_id)
        snapshot_path = Path(record.get("snapshot_path", "")) if record.get("snapshot_path") else None
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
        self.huggingface_cache_dir().mkdir(parents=True, exist_ok=True)
        snapshot_path = snapshot_download(
            repo_id=package.repo_id,
            cache_dir=str(self.huggingface_cache_dir()),
            local_files_only=False,
        )
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

    return {
        "ocr": {
            "configured_engine_id": ocr_id,
            "runtime_engine_id": "rapidocr-onnxruntime",
            "package": store.get_status(ocr_id),
        },
        "detect": {
            "configured_detector_id": detect_id,
            "configured_segmenter_id": segment_id,
            "runtime_detector_id": "heuristic-grouping",
            "runtime_segmenter_id": "pil-mask-rasterizer",
            "detector_package": store.get_status(detect_id),
            "segmenter_package": store.get_status(segment_id),
        },
        "inpaint": {
            "configured_engine_id": inpaint_id,
            "runtime_engine_id": "opencv-telea/pil-fallback",
            "package": store.get_status(inpaint_id),
        },
    }
