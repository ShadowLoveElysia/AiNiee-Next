from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class MangaFeatureStatus:
    available: bool
    message: str = ""
    message_key: str = ""
    message_args: list[object] = field(default_factory=list)
    details: list[str] = field(default_factory=list)
    missing_model_ids: list[str] = field(default_factory=list)
    issues: list[dict[str, object]] = field(default_factory=list)
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

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "message": self.message,
            "message_key": self.message_key,
            "message_args": list(self.message_args),
            "details": list(self.details),
            "missing_model_ids": list(self.missing_model_ids),
            "issues": list(self.issues),
            "import_error": self.import_error,
        }


def _resolve_required_model_ids(config_snapshot: dict[str, object] | None = None) -> dict[str, str]:
    snapshot = dict(config_snapshot) if isinstance(config_snapshot, dict) else {}
    return {
        "detect": str(snapshot.get("manga_detect_engine") or "comic-text-bubble-detector"),
        "segment": str(snapshot.get("manga_segment_engine") or "comic-text-detector"),
        "ocr": str(snapshot.get("manga_ocr_engine") or "paddleocr-vl-1.5"),
        "inpaint": str(snapshot.get("manga_inpaint_engine") or "aot-inpainting"),
    }


def _runtime_issue(
    *,
    code: str,
    stage: str,
    model_id: str,
    message_key: str,
    message: str,
    message_args: list[object] | None = None,
) -> dict[str, object]:
    return {
        "code": code,
        "stage": stage,
        "model_id": model_id,
        "message_key": message_key,
        "message": message,
        "message_args": list(message_args or []),
    }


def _device_requirement_text(device_status) -> str:
    configured = str(getattr(device_status, "configured", "auto") or "auto")
    if configured.startswith("cuda"):
        missing: list[str] = []
        if not bool(getattr(device_status, "cuda_available", False)):
            missing.append("CUDA-enabled torch")
        if not bool(getattr(device_status, "onnx_cuda_available", False)):
            missing.append("onnxruntime-gpu CUDAExecutionProvider")
        return " / ".join(missing) if missing else "CUDA runtime"
    if configured == "mps":
        return "MPS-enabled torch"
    return configured


def _device_diagnostic_line(stage: str, model_id: str, device_status) -> str:
    providers = ", ".join(getattr(device_status, "onnx_providers", ()) or ()) or "none"
    torch_cuda_version = str(getattr(device_status, "torch_cuda_version", "") or "none")
    torch_file = str(getattr(device_status, "torch_file", "") or "unknown")
    onnx_file = str(getattr(device_status, "onnx_file", "") or "unknown")
    torch_error = str(getattr(device_status, "torch_error", "") or "")
    onnx_error = str(getattr(device_status, "onnx_error", "") or "")
    error_parts = []
    if torch_error:
        error_parts.append(f"torch_error={torch_error}")
    if onnx_error:
        error_parts.append(f"onnxruntime_error={onnx_error}")
    error_suffix = f" | {' | '.join(error_parts)}" if error_parts else ""
    return (
        f"{stage}/{model_id} runtime diagnostics: python={sys.executable} | "
        f"torch={getattr(device_status, 'torch_version', '') or 'missing'} "
        f"(cuda_build={torch_cuda_version}, cuda_available={bool(getattr(device_status, 'cuda_available', False))}, "
        f"devices={int(getattr(device_status, 'cuda_device_count', 0) or 0)}, "
        f"device_name={getattr(device_status, 'cuda_device_name', '') or 'none'}, file={torch_file}) | "
        f"onnxruntime={getattr(device_status, 'onnx_version', '') or 'missing'} "
        f"(cuda_provider={bool(getattr(device_status, 'onnx_cuda_available', False))}, "
        f"providers={providers}, file={onnx_file})"
        f"{error_suffix}"
    )


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
            message_key="manga_runtime_preflight_module_unavailable",
            message_args=[str(exc)],
            details=["当前不会影响主程序其它功能。需要使用漫画翻译时，再补齐漫画模块。"],
            import_error=str(exc),
        )

    if not require_models:
        return MangaFeatureStatus(available=True)

    try:
        model_store_module = importlib.import_module("ModuleFolders.MangaCore.pipeline.modelStore")
        provider_adapter_module = importlib.import_module("ModuleFolders.MangaCore.bridge.providerAdapter")
        MangaModelStore = getattr(model_store_module, "MangaModelStore")
        get_runtime_dependency_status = getattr(provider_adapter_module, "get_runtime_dependency_status")
        runtime_device_status_from_config = getattr(provider_adapter_module, "runtime_device_status_from_config")
    except Exception as exc:
        return MangaFeatureStatus(
            available=False,
            message="漫画模块已加载，但漫画模型检查器不可用。",
            message_key="manga_runtime_preflight_checker_unavailable",
            message_args=[str(exc)],
            details=["当前不会影响普通文本翻译。只有在使用漫画翻译时才需要补齐漫画模型配置。"],
            import_error=str(exc),
        )

    store = MangaModelStore(root_dir=model_root_dir) if model_root_dir is not None else MangaModelStore()
    required_model_ids = _resolve_required_model_ids(config_snapshot)
    details: list[str] = []
    missing_model_ids: list[str] = []
    runtime_problem_ids: list[str] = []
    issues: list[dict[str, object]] = []

    for stage, model_id in required_model_ids.items():
        try:
            status = store.get_status(model_id)
        except Exception as exc:
            missing_model_ids.append(model_id)
            message = f"{stage}: 未知漫画引擎 `{model_id}` ({exc})"
            details.append(message)
            issues.append(
                _runtime_issue(
                    code="unknown_model",
                    stage=stage,
                    model_id=model_id,
                    message_key="manga_runtime_preflight_unknown_model",
                    message=message,
                    message_args=[stage, model_id, str(exc)],
                )
            )
            continue

        if not bool(status.get("available")):
            missing_model_ids.append(model_id)
            runtime_assets_path = str(status.get("runtime_assets_path", "") or "")
            hint_path = runtime_assets_path or str(status.get("cache_dir", "") or "")
            message = f"{stage}: 缺少模型包 `{model_id}`，请先下载到 `{hint_path}`。"
            details.append(message)
            issues.append(
                _runtime_issue(
                    code="missing_model",
                    stage=stage,
                    model_id=model_id,
                    message_key="manga_runtime_preflight_missing_model",
                    message=message,
                    message_args=[stage, model_id, hint_path],
                )
            )
            continue

        if stage in {"detect", "ocr", "inpaint"} and not bool(status.get("runtime_supported")):
            runtime_problem_ids.append(model_id)
            message = f"{stage}: 模型包 `{model_id}` 当前没有可用 Runtime 桥接，自动流水线会退回 fallback。"
            details.append(message)
            issues.append(
                _runtime_issue(
                    code="unsupported_runtime_model",
                    stage=stage,
                    model_id=model_id,
                    message_key="manga_runtime_preflight_unsupported_runtime_model",
                    message=message,
                    message_args=[stage, model_id],
                )
            )
            continue

        if bool(status.get("runtime_supported")):
            dependency_status = get_runtime_dependency_status(model_id)
            if getattr(dependency_status, "supported", False) and not getattr(dependency_status, "ok", False):
                runtime_problem_ids.append(model_id)
                missing_modules = ", ".join(getattr(dependency_status, "missing_modules", ()))
                message = f"{stage}: 模型包 `{model_id}` 已存在，但视觉 runtime 依赖不可用，缺少 Python 模块: {missing_modules}。"
                details.append(message)
                issues.append(
                    _runtime_issue(
                        code="missing_dependency",
                        stage=stage,
                        model_id=model_id,
                        message_key="manga_runtime_preflight_missing_dependency",
                        message=message,
                        message_args=[stage, model_id, missing_modules],
                    )
                )
                continue

        if stage in {"detect", "ocr", "inpaint"}:
            device_status = runtime_device_status_from_config(config_snapshot, stage)
            configured_device = str(getattr(device_status, "configured", "auto") or "auto")
            resolved_device = str(getattr(device_status, "resolved", "cpu") or "cpu")
            device_missing = (
                configured_device.startswith("cuda") and not bool(getattr(device_status, "cuda_available", False))
            ) or (
                configured_device == "mps" and not bool(getattr(device_status, "mps_available", False))
            )
            if device_missing:
                runtime_problem_ids.append(model_id)
                requirement = _device_requirement_text(device_status)
                message = (
                    f"{stage}: 已强制使用 `{configured_device}`，但当前运行时解析为 `{resolved_device}`，"
                    f"缺少 {requirement}。"
                )
                details.append(message)
                details.append(_device_diagnostic_line(stage, model_id, device_status))
                issues.append(
                    _runtime_issue(
                        code="missing_device",
                        stage=stage,
                        model_id=model_id,
                        message_key="manga_runtime_preflight_missing_device",
                        message=message,
                        message_args=[stage, model_id, configured_device, resolved_device, requirement],
                    )
                )

    if missing_model_ids:
        return MangaFeatureStatus(
            available=False,
            message=(
                "未配置漫画相关内容：缺少漫画翻译所需模型包。"
                f" 当前缺少: {', '.join(missing_model_ids)}"
            ),
            message_key="manga_runtime_preflight_failed",
            message_args=[len(issues)],
            details=details + ["主程序其它功能不受影响；仅在使用漫画翻译时需要补齐这些内容。"],
            missing_model_ids=missing_model_ids,
            issues=issues,
        )

    if runtime_problem_ids:
        return MangaFeatureStatus(
            available=False,
            message=(
                "漫画模型文件已存在，但视觉 runtime 依赖不可用。"
                f" 当前不可运行: {', '.join(runtime_problem_ids)}"
            ),
            message_key="manga_runtime_preflight_failed",
            message_args=[len(issues)],
            details=details + ["已阻止 fallback 自动流水线；请先补齐依赖后再做自动成稿验收。"],
            missing_model_ids=runtime_problem_ids,
            issues=issues,
        )

    return MangaFeatureStatus(
        available=True,
        message="漫画模块及默认模型包已就绪。",
    )
