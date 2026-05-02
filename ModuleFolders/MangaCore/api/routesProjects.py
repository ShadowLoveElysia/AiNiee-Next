from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ModuleFolders.MangaCore.api.schemas import (
    ProjectCreateFromTaskRequest,
    ProjectOpenRequest,
    ProjectSaveRequest,
)
from ModuleFolders.MangaCore.io.persistence import MangaProjectPersistence
from ModuleFolders.MangaCore.pipeline.engines.render import RenderEngine
from ModuleFolders.MangaCore.pipeline.modelStore import build_engine_status
from ModuleFolders.MangaCore.pipeline.qualityGate import load_quality_gate, page_blocked_from_final, remove_final_page
from ModuleFolders.MangaCore.project.session import MangaProjectSession, SessionRegistry

router = APIRouter(prefix="/api/manga", tags=["manga"])


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


@router.post("/projects/open")
def open_project(request: ProjectOpenRequest) -> dict[str, object]:
    session = SessionRegistry.register(MangaProjectPersistence.load_project(request.project_path))
    return {
        "project_id": session.manifest.project_id,
        "name": session.manifest.name,
        "page_count": session.manifest.page_count,
        "current_page_id": session.scene.current_page_id,
    }


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
    render_engine = RenderEngine()
    for page_ref in session.scene.pages:
        page = session.pages[page_ref.page_id]
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
def get_scene(project_id: str) -> dict[str, object]:
    session = _get_session_or_404(project_id)
    return {
        "project_id": session.scene.project_id,
        "current_page_id": session.scene.current_page_id,
        "render_preset": session.scene.render_preset,
        "export_preset": session.scene.export_preset,
        "engines": build_engine_status(session.config_snapshot),
        "pages": [
            {
                "page_id": page.page_id,
                "index": page.index,
                "status": page.status,
                "thumbnail_url": f"/api/manga/projects/{project_id}/pages/{page.page_id}/thumbnail",
                "quality_gate": _scene_page_quality_payload(session, page),
            }
            for page in session.scene.pages
        ],
    }
