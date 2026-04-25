from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ModuleFolders.MangaCore.api.schemas import (
    ProjectCreateFromTaskRequest,
    ProjectOpenRequest,
    ProjectSaveRequest,
)
from ModuleFolders.MangaCore.io.persistence import MangaProjectPersistence
from ModuleFolders.MangaCore.pipeline.modelStore import build_engine_status
from ModuleFolders.MangaCore.project.session import MangaProjectSession, SessionRegistry
from ModuleFolders.MangaCore.render.painter import MangaRenderer

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
    MangaRenderer().render_session(session)
    MangaProjectPersistence.save_session(session)
    return {
        "ok": True,
        "project_id": session.manifest.project_id,
        "updated_at": session.manifest.updated_at,
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
            }
            for page in session.scene.pages
        ],
    }
