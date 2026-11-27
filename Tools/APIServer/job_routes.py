"""Observe and cancel auxiliary operations through authenticated API routes."""
from fastapi import APIRouter, HTTPException, Request
from ModuleFolders.Infrastructure.ApiSecurity import is_mcp_request
from ModuleFolders.Service.TaskRuntime.jobs import get_job_manager
from .job_contracts import JobResponse
from .responses import ERROR_RESPONSES

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=list[JobResponse], responses=ERROR_RESPONSES)
def list_jobs(request: Request):
    rows = get_job_manager().list()
    if is_mcp_request(request):
        for row in rows:
            if row["metadata"].get("requires_external_confirmation"):
                row["result"] = None
    return rows


@router.get("/{job_id}", response_model=JobResponse, responses=ERROR_RESPONSES)
def job_status(job_id: str, request: Request, user_confirmed_external_processing: bool = False):
    try:
        row = get_job_manager().status(job_id)
        if is_mcp_request(request) and row["metadata"].get("requires_external_confirmation") and not user_confirmed_external_processing:
            raise HTTPException(409, "Confirm external processing before retrieving this job's content")
        return row
    except KeyError as exc:
        raise HTTPException(404, "Job not found") from exc


@router.post("/{job_id}/stop", response_model=JobResponse, responses=ERROR_RESPONSES)
def stop_job(job_id: str, request: Request):
    try:
        row = get_job_manager().cancel(job_id)
        if is_mcp_request(request) and row["metadata"].get("requires_external_confirmation"):
            row["result"] = None
        return row
    except KeyError as exc:
        raise HTTPException(404, "Job not found") from exc
