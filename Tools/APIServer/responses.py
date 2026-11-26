"""Response projections preserving extension fields used by existing clients."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from Tools.APIServer.contracts import CacheItem, TaskLifecycleResponse


class ResponseRecord(BaseModel):
    model_config = ConfigDict(extra="allow")


class MessageResponse(ResponseRecord):
    message: str


class ConfigSaveResponse(MessageResponse):
    revision: str


class SuccessResponse(ResponseRecord):
    success: bool


class StatusResponse(ResponseRecord):
    status: str


class ModeResponse(ResponseRecord):
    mode: Literal["full", "monitor"]


class VersionResponse(ResponseRecord):
    version: str


class ConfigResponse(ResponseRecord):
    model_config = ConfigDict(extra="allow", json_schema_extra={"x-contract-scope": "partial"})
    active_profile: str | None = None
    active_rules_profile: str | None = None
    source_language: str | None = None
    target_language: str | None = None
    platforms: dict[str, dict[str, Any]] | None = None


class RuleRecord(ResponseRecord):
    model_config = ConfigDict(extra="allow", json_schema_extra={"x-contract-scope": "partial"})
    # Bulk rule and draft endpoints accept extension records without normalizing their values.
    id: Any = None
    src: Any = None
    dst: Any = None
    info: Any = None


class RuleMutationResponse(MessageResponse):
    items: list[RuleRecord]


class TermTranslationResponse(ResponseRecord):
    dst: str
    info: str


class ParameterDefinition(ResponseRecord):
    key: str
    group: str
    type: str
    default: Any
    minimum: int | float | None
    maximum: int | float | None
    choices: list[Any]
    label: str
    description: str
    depends_on: str | None
    steps: list[str]


class RuntimeParametersResponse(ResponseRecord):
    parameters: list[ParameterDefinition]


class AnalysisStateResponse(StatusResponse):
    progress: int | float
    total: int
    message: str
    results: list[dict[str, Any]]
    logs: list[str]
    estimated_tokens: int
    analysis_mode: str
    structured_analysis: dict[str, Any]


class AnalysisPreflightResponse(ResponseRecord):
    total_lines: int
    lines_to_analyze: int
    estimated_tokens: int
    warning_threshold: int
    recommended_split_target_tokens: int
    max_split_target_tokens: int
    exceeds_warning: bool


class AnalysisSaveResponse(MessageResponse):
    file: str
    profile: str
    count: int
    rules: dict[str, Any]


class PluginResponse(ResponseRecord):
    name: str
    description: str
    enabled: bool
    default_enable: bool


class PlatformCreateResponse(MessageResponse):
    config: dict[str, Any]


class ExternalTaskStatusResponse(TaskLifecycleResponse):
    applied: bool


class QueueRunResponse(TaskLifecycleResponse):
    success: bool


class UploadedFileResponse(ResponseRecord):
    info: str
    path: str
    deleted: str | None = None


class UploadLimitResponse(ResponseRecord):
    status: Literal["limit_reached"]
    limit: int
    oldest: str
    buffer_available: bool


class TemporaryFileResponse(ResponseRecord):
    name: str
    path: str
    size: int


class FileDeleteFailure(ResponseRecord):
    file: str
    error: str


class FileDeleteResponse(ResponseRecord):
    deleted: list[str]
    failed: list[FileDeleteFailure]


class CacheStatusResponse(ResponseRecord):
    loaded: bool
    file_count: int
    total_items: int
    project_name: str | None
    project_path: str | None = None
    project_id: str | None = None
    revision: str | None = None


class CacheLoadResponse(SuccessResponse):
    message: str
    file_count: int
    total_items: int


class CacheRestoreResponse(CacheLoadResponse):
    file: str


class CacheBackup(ResponseRecord):
    file: str
    modified_time: str
    size: int
    size_label: str
    project_name: str
    item_count: int
    translated_count: int
    polished_count: int | None = None
    total_count: int
    completion_rate: float
    completion_label: str


class CacheBackupsResponse(ResponseRecord):
    backups: list[CacheBackup]


class PaginationResponse(ResponseRecord):
    current_page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_prev: bool


class CacheItemsResponse(ResponseRecord):
    items: list[CacheItem]
    pagination: PaginationResponse


class CacheSearchItem(ResponseRecord):
    file_path: str
    line_number: int
    source: str
    translation: str
    text_index: int
    translation_status: int


class CacheSearchResponse(ResponseRecord):
    results: list[CacheSearchItem]
    total_found: int
    query: str
    scope: str


class ProofreadReportResponse(ResponseRecord):
    report_file: str
    is_archive: bool
    run: dict[str, Any]
    review_state: dict[str, Any]
    summary: dict[str, Any]
    suggestions: list[dict[str, Any]]


class ProofreadReportsResponse(ResponseRecord):
    project_path: str
    current: dict[str, Any] | None
    archives: list[dict[str, Any]]


class ProofreadLocateResponse(ResponseRecord):
    global_index: int
    page: int
    row_index: int
    file_path: str
    text_index: int


class ProofreadReviewResponse(SuccessResponse):
    suggestion_id: str | None
    status: str | None
    message: str
    report: ProofreadReportResponse


class CacheUpdateResponse(SuccessResponse):
    message: str
    report: ProofreadReportResponse | None
    revision: str | None = None


class ProofreadReviewStateResponse(SuccessResponse):
    review_state: dict[str, Any]


class ProofreadStateResponse(ResponseRecord):
    running: bool
    progress: int | float
    total: int
    issues: list[dict[str, Any]]
    tokens_used: int
    error: str | None
    completed: bool
    output_path: str | None


class ProofreadAcceptResponse(StatusResponse):
    suggestion_id: str
    report: ProofreadReportResponse


class ProofreadSingleResponse(ResponseRecord):
    has_issues: bool
    message: str | None = None
    issues: list[dict[str, Any]] | None = None
    corrected_translation: str | None = None


class QueueRawResponse(ResponseRecord):
    content: str
    revision: str


class QueueItemResponse(ResponseRecord):
    task_id: str
    revision: str
    protected: bool
    task_type: str
    execution_mode: str
    input_path: str
    output_path: str | None
    profile: str | None
    rules_profile: str | None
    source_lang: str | None
    target_lang: str | None
    project_type: str | None
    platform: str | None
    api_url: str | None
    model: str | None
    status: str
    runtime_overrides: dict[str, Any]
    step_overrides: dict[str, Any]
    api_key: str
    api_key_configured: bool
    threads: int | None
    retry: int | None
    timeout: int | None
    rounds: int | None
    pre_lines: int | None
    lines_limit: int | None
    tokens_limit: int | None
    think_depth: str | int | None
    thinking_budget: int | None
    failover: bool | None
    resume: bool | None
    polish_mode: str | None
    locked: bool
    is_actually_processing: bool
    is_processing: bool
    process_start_time: str | None
    last_activity_time: str | None


class ValidationIssue(ResponseRecord):
    loc: list[str | int]
    msg: str
    type: str


class ErrorResponse(ResponseRecord):
    detail: str | list[ValidationIssue] | dict[str, Any]


ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Invalid request or unsupported operation"},
    403: {"model": ErrorResponse, "description": "Channel authentication or operation authorization required"},
    404: {"model": ErrorResponse, "description": "Requested task or resource does not exist"},
    409: {"model": ErrorResponse, "description": "State, revision or task ownership conflict"},
    410: {"model": ErrorResponse, "description": "Legacy operation retired; use the documented replacement"},
    413: {"model": ErrorResponse, "description": "Request content exceeds the accepted size"},
    422: {"model": ErrorResponse, "description": "Request validation failed"},
    428: {"model": ErrorResponse, "description": "A resource revision is required before modifying it"},
    500: {"model": ErrorResponse, "description": "Operation failed"},
    503: {"model": ErrorResponse, "description": "Required runtime capability is unavailable"},
}

PROOFREAD_REVIEW_RESPONSES = {
    **ERROR_RESPONSES,
    409: {
        "model": ErrorResponse | ProofreadReviewResponse,
        "description": "Review conflict with current report, or an operation error",
    },
}
