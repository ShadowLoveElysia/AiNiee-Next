from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class MangaFeatureStatus:
    available: bool
    message: str = ""
    details: list[str] = field(default_factory=list)
    missing_model_ids: list[str] = field(default_factory=list)
    import_error: str = ""

    def user_message(self) -> str:
        segments: list[str] = []
        if self.message.strip():
            segments.append(self.message.strip())
        for detail in self.details:
            normalized = detail.strip()
            if normalized and normalized not in segments:
                segments.append(normalized)
        return " ".join(segments).strip()


def _resolve_required_model_ids(config_snapshot: dict[str, object] | None = None) -> dict[str, str]:
    snapshot = dict(config_snapshot) if isinstance(config_snapshot, dict) else {}
    return {
        "detect": str(snapshot.get("manga_detect_engine") or "comic-text-bubble-detector"),
        "segment": str(snapshot.get("manga_segment_engine") or "comic-text-detector"),
        "ocr": str(snapshot.get("manga_ocr_engine") or "paddleocr-vl-1.5"),
        "inpaint": str(snapshot.get("manga_inpaint_engine") or "aot-inpainting"),
    }


def get_manga_feature_status(
    *,
    config_snapshot: dict[str, object] | None = None,
    require_models: bool = False,
    model_root_dir: str | Path | None = None,
) -> MangaFeatureStatus:
    try:
        importlib.import_module("ModuleFolders.MangaCore")
    except Exception as exc:
        return MangaFeatureStatus(
            available=False,
            message="漫画模块当前不可用。MangaCore 组件未安装或导入失败。",
            details=["当前不会影响主程序其它功能。需要使用漫画翻译时，再补齐漫画模块。"],
            import_error=str(exc),
        )

    if not require_models:
        return MangaFeatureStatus(available=True)

    try:
        model_store_module = importlib.import_module("ModuleFolders.MangaCore.pipeline.modelStore")
        MangaModelStore = getattr(model_store_module, "MangaModelStore")
    except Exception as exc:
        return MangaFeatureStatus(
            available=False,
            message="漫画模块已加载，但漫画模型检查器不可用。",
            details=["当前不会影响普通文本翻译。只有在使用漫画翻译时才需要补齐漫画模型配置。"],
            import_error=str(exc),
        )

    store = MangaModelStore(root_dir=model_root_dir) if model_root_dir is not None else MangaModelStore()
    required_model_ids = _resolve_required_model_ids(config_snapshot)
    details: list[str] = []
    missing_model_ids: list[str] = []

    for stage, model_id in required_model_ids.items():
        try:
            status = store.get_status(model_id)
        except Exception as exc:
            missing_model_ids.append(model_id)
            details.append(f"{stage}: 未知漫画引擎 `{model_id}` ({exc})")
            continue

        if not bool(status.get("available")):
            missing_model_ids.append(model_id)
            runtime_assets_path = str(status.get("runtime_assets_path", "") or "")
            hint_path = runtime_assets_path or str(status.get("cache_dir", "") or "")
            details.append(
                f"{stage}: 缺少模型包 `{model_id}`，请先下载到 `{hint_path}`。"
            )

    if missing_model_ids:
        return MangaFeatureStatus(
            available=False,
            message=(
                "未配置漫画相关内容：缺少漫画翻译所需模型包。"
                f" 当前缺少: {', '.join(missing_model_ids)}"
            ),
            details=details + ["主程序其它功能不受影响；仅在使用漫画翻译时需要补齐这些内容。"],
            missing_model_ids=missing_model_ids,
        )

    return MangaFeatureStatus(
        available=True,
        message="漫画模块及默认模型包已就绪。",
    )
