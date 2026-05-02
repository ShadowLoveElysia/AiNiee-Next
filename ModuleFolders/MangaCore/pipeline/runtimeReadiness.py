from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from ModuleFolders.MangaCore.bridge.providerAdapter import (
    get_runtime_dependency_status,
    get_runtime_requirement_status,
)
from ModuleFolders.MangaCore.pipeline.modelStore import MangaModelStore


@dataclass(slots=True)
class RuntimeReadinessItem:
    stage: str
    model_id: str
    display_name: str = ""
    status: str = "ready"
    blocking: bool = False
    message: str = ""
    message_key: str = ""
    message_args: list[object] = field(default_factory=list)
    action_hint_key: str = ""
    action_hint_args: list[object] = field(default_factory=list)
    available: bool = False
    runtime_supported: bool = False
    runtime_engine_id: str = ""
    storage_path: str = ""
    snapshot_path: str = ""
    required_modules: list[str] = field(default_factory=list)
    missing_modules: list[str] = field(default_factory=list)
    required_assets: list[str] = field(default_factory=list)
    required_asset_paths: list[str] = field(default_factory=list)
    missing_asset_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class RuntimeReadinessReport:
    ok: bool
    checked_at: str
    model_root: str
    items: list[RuntimeReadinessItem] = field(default_factory=list)
    issue_count: int = 0
    summary: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["items"] = [item.to_dict() for item in self.items]
        return payload


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _resolve_required_model_ids(config_snapshot: dict[str, object] | None = None) -> dict[str, str]:
    snapshot = dict(config_snapshot) if isinstance(config_snapshot, dict) else {}
    return {
        "detect": str(snapshot.get("manga_detect_engine") or "comic-text-bubble-detector"),
        "segment": str(snapshot.get("manga_segment_engine") or "comic-text-detector"),
        "ocr": str(snapshot.get("manga_ocr_engine") or "paddleocr-vl-1.5"),
        "inpaint": str(snapshot.get("manga_inpaint_engine") or "aot-inpainting"),
    }


def _format_missing_modules(missing_modules: list[str]) -> str:
    return ", ".join(missing_modules) if missing_modules else ""


def _build_unknown_item(stage: str, model_id: str, exc: Exception) -> RuntimeReadinessItem:
    message = f"{stage}: unknown manga model `{model_id}` ({exc})"
    return RuntimeReadinessItem(
        stage=stage,
        model_id=model_id,
        status="unknown_model",
        blocking=True,
        message=message,
        message_key="manga_runtime_readiness_unknown_model",
        message_args=[stage, model_id, str(exc)],
    )


def _build_item(
    *,
    stage: str,
    model_id: str,
    status: dict[str, object],
    dependency_status,
    requirement_status,
) -> RuntimeReadinessItem:
    available = bool(status.get("available"))
    runtime_supported = bool(status.get("runtime_supported"))
    missing_modules = list(getattr(dependency_status, "missing_modules", ()) or [])
    required_modules = list(getattr(dependency_status, "required_modules", ()) or [])
    required_assets = list(getattr(requirement_status, "required_assets", ()) or [])
    required_asset_paths = list(getattr(requirement_status, "required_asset_paths", ()) or [])
    missing_asset_paths = list(getattr(requirement_status, "missing_asset_paths", ()) or [])
    display_name = str(status.get("display_name") or model_id)
    runtime_engine_id = str(status.get("runtime_engine_id") or "")
    storage_path = str(
        status.get("runtime_assets_path")
        or getattr(requirement_status, "storage_path", "")
        or status.get("snapshot_path")
        or ""
    )
    item = RuntimeReadinessItem(
        stage=stage,
        model_id=model_id,
        display_name=display_name,
        available=available,
        runtime_supported=runtime_supported,
        runtime_engine_id=runtime_engine_id,
        storage_path=storage_path,
        snapshot_path=str(status.get("snapshot_path") or ""),
        required_modules=required_modules,
        missing_modules=missing_modules,
        required_assets=required_assets,
        required_asset_paths=required_asset_paths,
        missing_asset_paths=missing_asset_paths,
    )

    if not available:
        item.status = "missing_model"
        item.blocking = True
        item.message = f"{stage}: missing manga model package `{model_id}`."
        item.message_key = "manga_runtime_readiness_missing_model"
        item.message_args = [stage, model_id]
        item.action_hint_key = "manga_runtime_readiness_action_prepare_model"
        item.action_hint_args = [model_id]
        return item

    if stage != "segment" and not runtime_supported:
        item.status = "unsupported_runtime_model"
        item.blocking = True
        item.message = f"{stage}: model `{model_id}` has no available runtime bridge."
        item.message_key = "manga_runtime_readiness_unsupported_runtime_model"
        item.message_args = [stage, model_id]
        return item

    if stage != "segment" and bool(getattr(dependency_status, "supported", False)) and missing_modules:
        item.status = "missing_dependency"
        item.blocking = True
        item.message = f"{stage}: model `{model_id}` is present, but runtime dependencies are missing: {_format_missing_modules(missing_modules)}."
        item.message_key = "manga_runtime_readiness_missing_dependency"
        item.message_args = [stage, model_id, _format_missing_modules(missing_modules)]
        item.action_hint_key = "manga_runtime_readiness_action_install_runtime_requirements"
        item.action_hint_args = ["ModuleFolders/MangaCore/runtime/requirements_cpu.txt"]
        return item

    item.status = "ready"
    item.blocking = False
    item.message = f"{stage}: runtime ready for `{model_id}`."
    item.message_key = "manga_runtime_readiness_ready"
    item.message_args = [stage, model_id]
    return item


def build_manga_runtime_readiness(
    *,
    config_snapshot: dict[str, object] | None = None,
    model_root_dir: str | Path | None = None,
) -> RuntimeReadinessReport:
    store = MangaModelStore(root_dir=model_root_dir) if model_root_dir is not None else MangaModelStore()
    required_model_ids = _resolve_required_model_ids(config_snapshot)
    items: list[RuntimeReadinessItem] = []

    for stage, model_id in required_model_ids.items():
        try:
            status = store.get_status(model_id)
        except Exception as exc:
            items.append(_build_unknown_item(stage, model_id, exc))
            continue

        dependency_status = get_runtime_dependency_status(model_id)
        requirement_status = get_runtime_requirement_status(model_id, store.root_dir)
        items.append(
            _build_item(
                stage=stage,
                model_id=model_id,
                status=status,
                dependency_status=dependency_status,
                requirement_status=requirement_status,
            )
        )

    status_counts: dict[str, int] = {}
    for item in items:
        status_counts[item.status] = status_counts.get(item.status, 0) + 1
    blocking_items = [item for item in items if item.blocking]
    ready_items = [item for item in items if not item.blocking]
    return RuntimeReadinessReport(
        ok=not blocking_items,
        checked_at=_now_iso(),
        model_root=str(store.root_dir),
        items=items,
        issue_count=len(blocking_items),
        summary={
            "stage_count": len(items),
            "ready_stage_count": len(ready_items),
            "blocking_stage_count": len(blocking_items),
            "status_counts": status_counts,
        },
    )
