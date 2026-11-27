from typing import Any, Literal
from pydantic import BaseModel, Field


class ControlRequest(BaseModel):
    task_id: str
    action: Literal["pause", "resume", "decrease_threads", "increase_threads", "decrease_batch", "increase_batch", "skip_file", "switch_api"]


class ControlResponse(BaseModel):
    command_id: str
    task_id: str
    context_id: str
    action: str
    status: Literal["queued", "delivered", "processed", "rejected", "expired"]
    state: dict[str, Any] = Field(default_factory=dict)


class WorkerControlRequest(BaseModel):
    task_id: str
    context_id: str
    command_id: str | None = None
    state: dict[str, int | bool] = Field(default_factory=dict)
