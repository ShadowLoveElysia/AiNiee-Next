"""Transport records for auxiliary operations."""
from typing import Any, Literal
from pydantic import BaseModel, Field


class JobResponse(BaseModel):
    job_id: str
    kind: str
    status: Literal["running", "stopping", "completed", "failed", "stopped"]
    running: bool
    cancel_requested: bool = False
    created_at: str
    finished_at: str | None = None
    result: Any = None
    error: dict[str, str] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
