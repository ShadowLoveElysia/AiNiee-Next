from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ModuleFolders.MangaCore.project.session import MangaProjectSession, SessionRegistry

router = APIRouter(prefix="/api/manga", tags=["manga"])


def _get_session_or_404(project_id: str) -> MangaProjectSession:
    session = SessionRegistry.get(project_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Manga project is not open: {project_id}")
    return session


def _safe_project_asset(session: MangaProjectSession, relative_path: str) -> str:
    target = os.path.realpath(session.project_path / relative_path)
    root = os.path.realpath(session.project_path)
    if not target.startswith(root):
        raise HTTPException(status_code=403, detail="Asset path escapes manga project root.")
    if not os.path.exists(target):
        raise HTTPException(status_code=404, detail=f"Asset not found: {relative_path}")
    return target


def _asset_version(session: MangaProjectSession, relative_path: str) -> int:
    target = session.project_path / relative_path
    if not target.exists():
        return 0
    return int(target.stat().st_mtime_ns)


@router.get("/projects/{project_id}/pages/{page_id}")
def get_page(project_id: str, page_id: str) -> dict[str, object]:
    session = _get_session_or_404(project_id)
    page = session.pages.get(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")

    return {
        "page_id": page.page_id,
        "index": page.index,
        "width": page.width,
        "height": page.height,
        "status": page.status,
        "layers": {
            "source_url": f"/api/manga/projects/{project_id}/assets/{page.layers.source}?v={_asset_version(session, page.layers.source)}",
            "overlay_text_url": f"/api/manga/projects/{project_id}/assets/{page.layers.overlay_text}?v={_asset_version(session, page.layers.overlay_text)}",
            "inpainted_url": f"/api/manga/projects/{project_id}/assets/{page.layers.inpainted}?v={_asset_version(session, page.layers.inpainted)}",
            "rendered_url": f"/api/manga/projects/{project_id}/assets/{page.layers.rendered}?v={_asset_version(session, page.layers.rendered)}",
        },
        "masks": {
            "segment_url": f"/api/manga/projects/{project_id}/assets/{page.masks.segment}?v={_asset_version(session, page.masks.segment)}",
            "bubble_url": f"/api/manga/projects/{project_id}/assets/{page.masks.bubble}?v={_asset_version(session, page.masks.bubble)}",
            "brush_url": f"/api/manga/projects/{project_id}/assets/{page.masks.brush}?v={_asset_version(session, page.masks.brush)}",
        },
        "blocks": [block.to_dict() for block in page.text_blocks],
    }


@router.get("/projects/{project_id}/pages/{page_id}/thumbnail")
def get_page_thumbnail(project_id: str, page_id: str):
    session = _get_session_or_404(project_id)
    page = session.pages.get(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")
    return FileResponse(_safe_project_asset(session, page.thumbnail_path))


@router.get("/projects/{project_id}/assets/{asset_path:path}")
def get_project_asset(project_id: str, asset_path: str):
    session = _get_session_or_404(project_id)
    return FileResponse(_safe_project_asset(session, asset_path))
