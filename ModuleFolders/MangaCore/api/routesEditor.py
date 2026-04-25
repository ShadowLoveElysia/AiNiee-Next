from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ModuleFolders.MangaCore.api.schemas import ApplyOpsRequest
from ModuleFolders.MangaCore.io.persistence import MangaProjectPersistence
from ModuleFolders.MangaCore.ops.apply import apply_operations, redo_operations, undo_operations
from ModuleFolders.MangaCore.ops.operation import Operation
from ModuleFolders.MangaCore.project.session import MangaProjectSession, SessionRegistry

router = APIRouter(prefix="/api/manga", tags=["manga"])


def _get_session_or_404(project_id: str) -> MangaProjectSession:
    session = SessionRegistry.get(project_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Manga project is not open: {project_id}")
    return session


@router.patch("/projects/{project_id}/ops")
def apply_ops(project_id: str, request: ApplyOpsRequest) -> dict[str, object]:
    session = _get_session_or_404(project_id)
    operations = [Operation.from_dict(item) for item in request.ops]
    applied, history_seq = apply_operations(session, operations)
    record = session.history.past[-1]
    MangaProjectPersistence.append_history(session, record.to_log_lines())
    MangaProjectPersistence.save_session(session)
    return {
        "ok": True,
        "applied": applied,
        "history_seq": history_seq,
        "updated_at": session.manifest.updated_at,
    }


@router.post("/projects/{project_id}/undo")
def undo(project_id: str) -> dict[str, object]:
    session = _get_session_or_404(project_id)
    result = undo_operations(session)
    if result is None:
        return {"ok": False, "applied": 0, "message": "Nothing to undo."}
    applied, history_seq = result
    MangaProjectPersistence.save_session(session)
    return {
        "ok": True,
        "applied": applied,
        "history_seq": history_seq,
        "updated_at": session.manifest.updated_at,
    }


@router.post("/projects/{project_id}/redo")
def redo(project_id: str) -> dict[str, object]:
    session = _get_session_or_404(project_id)
    result = redo_operations(session)
    if result is None:
        return {"ok": False, "applied": 0, "message": "Nothing to redo."}
    applied, history_seq = result
    MangaProjectPersistence.save_session(session)
    return {
        "ok": True,
        "applied": applied,
        "history_seq": history_seq,
        "updated_at": session.manifest.updated_at,
    }
