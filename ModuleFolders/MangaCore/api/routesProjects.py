from __future__ import annotations

from datetime import datetime
from time import monotonic

from fastapi import APIRouter, HTTPException

from ModuleFolders.MangaCore.api.schemas import (
    ProjectConfigPatchRequest,
    ProjectCreateFromTaskRequest,
    ProjectOpenRequest,
    ProjectSaveRequest,
)
from ModuleFolders.MangaCore.io.persistence import MangaProjectPersistence
from ModuleFolders.MangaCore.pipeline.engines.render import RenderEngine
from ModuleFolders.MangaCore.pipeline.modelCatalog import normalize_model_id
from ModuleFolders.MangaCore.pipeline.modelStore import build_engine_status
from ModuleFolders.MangaCore.pipeline.qualityGate import load_quality_gate, page_blocked_from_final, remove_final_page
from ModuleFolders.MangaCore.pipeline.runtimeReadiness import build_manga_runtime_readiness
from ModuleFolders.MangaCore.project.session import MangaProjectSession, SessionRegistry

router = APIRouter(prefix="/api/manga", tags=["manga"])

PROJECT_CONFIG_SUMMARY_KEYS = (
    "task",
    "input_path",
    "output_path",
    "source_lang",
    "target_lang",
    "profile_name",
    "rules_profile_name",
    "platform",
    "model",
    "api_url",
    "manga_ocr_engine",
    "manga_detect_engine",
    "manga_segment_engine",
    "manga_inpaint_engine",
    "manga_runtime_device",
    "manga_detect_device",
    "manga_ocr_device",
    "manga_inpaint_device",
    "web_mode",
    "manga",
)
PROJECT_CONFIG_PATCH_KEYS = {
    "manga_ocr_engine",
    "manga_detect_engine",
    "manga_segment_engine",
    "manga_inpaint_engine",
    "manga_runtime_device",
    "manga_detect_device",
    "manga_ocr_device",
    "manga_inpaint_device",
}
PROJECT_CONFIG_MODEL_KEYS = {
    "manga_ocr_engine",
    "manga_detect_engine",
    "manga_segment_engine",
    "manga_inpaint_engine",
}

RUNTIME_STATUS_CACHE_TTL_SECONDS = 8.0
_runtime_status_cache: dict[str, tuple[float, dict[str, object]]] = {}


def _get_session_or_404(project_id: str) -> MangaProjectSession:
    session = SessionRegistry.get(project_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Manga project is not open: {project_id}")
    return session


@router.get("/projects")
def list_open_projects() -> list[dict[str, object]]:
    return [
        {
            "project_id": session.manifest.project_id,
            "name": session.manifest.name,
            "page_count": session.manifest.page_count,
            "project_path": str(session.project_path),
        }
        for session in SessionRegistry.list_open_projects()
    ]


def _project_config_summary(session: MangaProjectSession) -> dict[str, object]:
    snapshot = session.config_snapshot if isinstance(session.config_snapshot, dict) else {}
    return {key: snapshot[key] for key in PROJECT_CONFIG_SUMMARY_KEYS if key in snapshot}


def _scene_page_summary(project_id: str, page_ref, quality_gate: dict[str, object] | None = None) -> dict[str, object]:
    payload = {
        "page_id": page_ref.page_id,
        "index": page_ref.index,
        "status": page_ref.status,
        "thumbnail_url": f"/api/manga/projects/{project_id}/pages/{page_ref.page_id}/thumbnail",
    }
    if quality_gate is not None:
        payload["quality_gate"] = quality_gate
    return payload


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _project_main_payload(session: MangaProjectSession, *, include_runtime: bool = False, include_quality: bool = False) -> dict[str, object]:
    payload: dict[str, object] = {
        "project_id": session.manifest.project_id,
        "name": session.manifest.name,
        "page_count": session.manifest.page_count,
        "project_path": str(session.project_path),
        "current_page_id": session.scene.current_page_id,
        "manifest": session.manifest.to_dict(),
        "task_config": _project_config_summary(session),
        "scene": {
            "project_id": session.scene.project_id,
            "current_page_id": session.scene.current_page_id,
            "render_preset": session.scene.render_preset,
            "export_preset": session.scene.export_preset,
            "pages": [
                _scene_page_summary(
                    session.manifest.project_id,
                    page_ref,
                    _scene_page_quality_payload(session, session.get_page(page_ref.page_id)) if include_quality else None,
                )
                for page_ref in session.scene.pages
            ],
        },
    }
    if include_runtime:
        scene_payload = payload["scene"]
        if isinstance(scene_payload, dict):
            scene_payload.update(_runtime_status_payload(session))
    return payload


def _runtime_status_payload(session: MangaProjectSession) -> dict[str, object]:
    cache_key = session.manifest.project_id
    now = monotonic()
    cached = _runtime_status_cache.get(cache_key)
    if cached is not None:
        cached_at, payload = cached
        if now - cached_at < RUNTIME_STATUS_CACHE_TTL_SECONDS:
            return {
                "engines": payload.get("engines", {}),
                "runtime_readiness": payload.get("runtime_readiness", {}),
                "checked_at": payload.get("checked_at", ""),
                "cache_ttl_ms": int(RUNTIME_STATUS_CACHE_TTL_SECONDS * 1000),
                "cache_hit": True,
                "stale": False,
                "refreshing": False,
            }

    payload = {
        "engines": build_engine_status(session.config_snapshot),
        "runtime_readiness": build_manga_runtime_readiness(config_snapshot=session.config_snapshot).to_dict(),
        "checked_at": _now_iso(),
    }
    _runtime_status_cache[cache_key] = (now, payload)
    return {
        "engines": payload["engines"],
        "runtime_readiness": payload["runtime_readiness"],
        "checked_at": payload["checked_at"],
        "cache_ttl_ms": int(RUNTIME_STATUS_CACHE_TTL_SECONDS * 1000),
        "cache_hit": False,
        "stale": False,
        "refreshing": False,
    }


@router.post("/projects/open")
def open_project(request: ProjectOpenRequest) -> dict[str, object]:
    session = SessionRegistry.register(MangaProjectPersistence.load_project(request.project_path))
    return _project_main_payload(session, include_runtime=False, include_quality=False)


@router.post("/projects/create-from-task")
def create_project_from_task(request: ProjectCreateFromTaskRequest) -> dict[str, object]:
    session = SessionRegistry.register(
        MangaProjectPersistence.create_project_from_input(
            input_path=request.input_path,
            output_root=request.output_root,
            config_snapshot=request.config_snapshot,
            profile_name=request.profile_name,
            rules_profile_name=request.rules_profile_name,
            source_lang=request.source_lang,
            target_lang=request.target_lang,
        )
    )
    return {
        "project_id": session.manifest.project_id,
        "project_path": str(session.project_path),
        "page_count": session.manifest.page_count,
    }


@router.post("/projects/save")
def save_project(request: ProjectSaveRequest) -> dict[str, object]:
    session = _get_session_or_404(request.project_id)
    session.load_all_pages()
    render_engine = RenderEngine()
    for page_ref in session.scene.pages:
        page = session.get_page(page_ref.page_id)
        blocked, _reasons = page_blocked_from_final(session, page)
        if blocked:
            remove_final_page(session, page)
        render_engine.run_page(session, page, write_final=not blocked)
    MangaProjectPersistence.save_session(session)
    return {
        "ok": True,
        "project_id": session.manifest.project_id,
        "updated_at": session.manifest.updated_at,
    }


def _scene_page_quality_payload(session: MangaProjectSession, page) -> dict[str, object]:
    blocked, _reasons = page_blocked_from_final(session, page)
    gate = load_quality_gate(session, page)
    blocking_issue_count = (
        len([issue for issue in gate.issues if issue.blocks_final])
        if gate is not None
        else 0
    )
    return {
        "exists": gate is not None,
        "blocked_from_final": blocked,
        "issue_count": blocking_issue_count,
        "final_allowed": gate.final_allowed if gate else True,
    }


@router.get("/projects/{project_id}/scene")
def get_scene(project_id: str, quality: bool = True, runtime: bool = True) -> dict[str, object]:
    session = _get_session_or_404(project_id)
    payload: dict[str, object] = {
        "project_id": session.scene.project_id,
        "current_page_id": session.scene.current_page_id,
        "render_preset": session.scene.render_preset,
        "export_preset": session.scene.export_preset,
        "pages": [
            _scene_page_summary(
                project_id,
                page_ref,
                _scene_page_quality_payload(session, session.get_page(page_ref.page_id)) if quality else None,
            )
            for page_ref in session.scene.pages
        ],
    }
    if runtime:
        payload.update(_runtime_status_payload(session))
    return payload


@router.get("/projects/{project_id}/runtime-status")
def get_runtime_status(project_id: str, refresh: bool = False) -> dict[str, object]:
    session = _get_session_or_404(project_id)
    if refresh:
        _runtime_status_cache.pop(project_id, None)
    return _runtime_status_payload(session)


@router.patch("/projects/{project_id}/config")
def update_project_config(project_id: str, request: ProjectConfigPatchRequest) -> dict[str, object]:
    session = _get_session_or_404(project_id)
    updates = request.updates if isinstance(request.updates, dict) else {}
    unknown_keys = sorted(str(key) for key in updates if str(key) not in PROJECT_CONFIG_PATCH_KEYS)
    if unknown_keys:
        raise HTTPException(status_code=400, detail=f"Unsupported Manga project config key(s): {', '.join(unknown_keys)}")

    snapshot = dict(session.config_snapshot) if isinstance(session.config_snapshot, dict) else {}
    applied: dict[str, object] = {}
    for key, value in updates.items():
        normalized_key = str(key)
        if normalized_key in PROJECT_CONFIG_MODEL_KEYS:
            normalized_value = normalize_model_id(str(value or "").strip())
        else:
            normalized_value = str(value or "").strip() or "auto"
        if not normalized_value:
            continue
        snapshot[normalized_key] = normalized_value
        applied[normalized_key] = normalized_value

    session.config_snapshot = snapshot
    _runtime_status_cache.pop(project_id, None)
    MangaProjectPersistence.save_session(session)
    return {
        "ok": True,
        "project_id": project_id,
        "updates": applied,
        "task_config": _project_config_summary(session),
        **_runtime_status_payload(session),
    }
