from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ModuleFolders.MangaCore.pipeline.modelStore import MangaModelStore

router = APIRouter(prefix="/api/manga", tags=["manga"])


@router.get("/models")
def list_models() -> list[dict[str, object]]:
    return MangaModelStore().list_statuses()


@router.get("/models/{model_id}")
def get_model(model_id: str) -> dict[str, object]:
    try:
        return MangaModelStore().get_status(model_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/models/{model_id}/download")
def download_model(model_id: str) -> dict[str, object]:
    try:
        return MangaModelStore().download(model_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to download manga model package: {exc}") from exc
