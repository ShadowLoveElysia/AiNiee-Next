from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ModuleFolders.MangaCore.pipeline.progress import JobRegistry

router = APIRouter(prefix="/api/manga", tags=["manga"])


@router.get("/projects/{project_id}/jobs/{job_id}")
def get_job(project_id: str, job_id: str) -> dict[str, object]:
    job = JobRegistry.get(job_id)
    if job is None or (job.project_id and job.project_id != project_id):
        raise HTTPException(status_code=404, detail=f"Manga job not found: {job_id}")
    return job.to_dict()
