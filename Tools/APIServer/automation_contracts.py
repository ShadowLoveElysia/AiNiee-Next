"""Automation transport models; schedule and workflow semantics stay in services."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AutomationRecord(BaseModel):
    model_config = ConfigDict(extra="allow", json_schema_extra={"x-contract-scope": "partial"})


class AutomationConfigurationResponse(BaseModel):
    revision: str
    scheduler: dict[str, Any]
    watch_mode: dict[str, Any]
    output_collection: dict[str, Any]


class AutomationMutation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: str = Field(min_length=1)
    data: dict[str, Any]


class AutomationDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: str = Field(min_length=1)


class AutomationControl(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: bool = False
    event_triggers: bool = True
    stop_tasks: bool = True


class AutomationWorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task: dict[str, Any]


class AutomationSchedulePreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expression: str
    trigger_type: Literal["scheduled", "queue_added", "queue_pending"] = "scheduled"


class AutomationRequeueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_id: str = Field(min_length=1)
    file_path: str = Field(min_length=1)
    workflow_steps: list[dict[str, Any]] | None = None
    auto_start: bool = False


class AutomationResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str = Field(min_length=1)
    expected_revision: str = Field(min_length=1)
    mode: Literal["partial", "stopped"]
    auto_start: bool = False


class AutomationRunResponse(AutomationRecord):
    task_id: str
    status: str
    running: bool


class AutomationStatusResponse(BaseModel):
    scheduler: dict[str, Any]
    watch: dict[str, Any]
    owned_task_ids: list[str]


class AutomationWorkflowPreviewResponse(BaseModel):
    task: dict[str, Any]
    steps: list[dict[str, Any]]
    description: str


class AutomationLogsResponse(BaseModel):
    scheduler: list[dict[str, Any]]
    watch: list[dict[str, Any]]


class AutomationRunsResponse(BaseModel):
    runs: list[dict[str, Any]]


class AutomationScanResponse(BaseModel):
    snapshots: list[dict[str, Any]]


class AutomationResultResponse(AutomationRecord):
    success: bool
