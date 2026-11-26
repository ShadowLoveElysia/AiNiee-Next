"""Transport DTOs; task semantics remain in TaskSpec."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from ModuleFolders.Infrastructure.TaskContract import TaskSpec

# --- Pydantic Models for API Requests ---

class AppConfig(BaseModel):
    # Existing profiles include extension fields; preserve them during migration.
    source_language: Optional[str] = None
    target_language: Optional[str] = None
    actual_thread_counts: Optional[int] = None
    temp_file_limit: Optional[int] = 10
    cache_editor_page_size: Optional[int] = 15
    model_config = ConfigDict(extra="allow", json_schema_extra={"x-contract-scope": "partial"})

class ProfileSwitchRequest(BaseModel):
    profile: str

class RulesProfileSwitchRequest(BaseModel):
    profile: str

class RulesProfileDeleteRequest(BaseModel):
    profile: str

class ProfileCreateRequest(BaseModel):
    name: str
    base: Optional[str] = None

class ProfileRenameRequest(BaseModel):
    old_name: str
    new_name: str

class ProfileDeleteRequest(BaseModel):
    profile: str

class GlossaryItem(BaseModel):
    src: str
    dst: str
    info: Optional[str] = None
    model_config = ConfigDict(extra="allow")

class TermOption(BaseModel):
    dst: str
    info: str

class TermRetryRequest(BaseModel):
    src: str
    type: str
    avoid: List[str]
    analysis_info: Optional[str] = None
    temp_config: Optional[Dict[str, Any]] = None

class ExclusionItem(BaseModel):
    markers: str
    info: Optional[str] = None
    regex: Optional[str] = None
    model_config = ConfigDict(extra="allow")

class ReplacementRuleItem(BaseModel):
    src: Optional[str] = ""
    dst: Optional[str] = ""
    regex: Optional[str] = ""
    info: Optional[str] = None
    model_config = ConfigDict(extra="allow")

class CharacterizationItem(BaseModel):
    original_name: str
    translated_name: str
    aliases: Optional[List[str]] = []
    gender: Optional[str] = ""
    age: Optional[str] = ""
    personality: Optional[str] = ""
    speech_style: Optional[str] = ""
    pronouns: Optional[str] = ""
    speech_quirks: Optional[str] = ""
    additional_info: Optional[str] = ""
    model_config = ConfigDict(extra="allow")

class TranslationExampleItem(BaseModel):
    src: str
    dst: str
    model_config = ConfigDict(extra="allow")

class StringContent(BaseModel):
    content: str

class PluginEnableRequest(BaseModel):
    name: str
    enabled: bool

class DeleteFileRequest(BaseModel):
    files: List[str]

class QueueTaskItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: str | int
    input_path: str
    execution_mode: Optional[str] = "default_api"
    output_path: Optional[str] = None
    profile: Optional[str] = None
    rules_profile: Optional[str] = None
    source_lang: Optional[str] = None
    target_lang: Optional[str] = None
    project_type: Optional[str] = None
    platform: Optional[str] = None
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    threads: Optional[int] = None
    retry: Optional[int] = None
    timeout: Optional[int] = None
    rounds: Optional[int] = None
    pre_lines: Optional[int] = None
    lines_limit: Optional[int] = None
    tokens_limit: Optional[int] = None
    lines: Optional[int] = None
    tokens: Optional[int] = None
    think_depth: Optional[str | int] = None
    thinking_budget: Optional[int] = None
    failover: Optional[bool] = None
    resume: Optional[bool] = False
    polish_mode: Optional[str] = None
    runtime_overrides: Optional[Dict[str, Any]] = None
    step_overrides: Optional[Dict[str, Any]] = None
    status: Optional[str] = "waiting"

    def to_task_spec(self) -> TaskSpec:
        payload = self.model_dump(exclude={"status"}, exclude_none=True)
        return TaskSpec.from_mapping(payload)


class QueueTaskUpdate(BaseModel):
    """队列更新输入；显式 null 用于清空可选覆盖。"""

    model_config = ConfigDict(extra="forbid")

    task_type: Optional[str | int] = None
    input_path: Optional[str] = None
    execution_mode: Optional[str] = None
    output_path: Optional[str] = None
    profile: Optional[str] = None
    rules_profile: Optional[str] = None
    source_lang: Optional[str] = None
    target_lang: Optional[str] = None
    project_type: Optional[str] = None
    platform: Optional[str] = None
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    threads: Optional[int] = None
    retry: Optional[int] = None
    timeout: Optional[int] = None
    rounds: Optional[int] = None
    pre_lines: Optional[int] = None
    lines_limit: Optional[int] = None
    tokens_limit: Optional[int] = None
    lines: Optional[int] = None
    tokens: Optional[int] = None
    think_depth: Optional[str | int] = None
    thinking_budget: Optional[int] = None
    failover: Optional[bool] = None
    resume: Optional[bool] = None
    polish_mode: Optional[str] = None
    runtime_overrides: Optional[Dict[str, Any]] = None
    step_overrides: Optional[Dict[str, Any]] = None

class QueueMoveRequest(BaseModel):
    to_index: int

class QueueReorderRequest(BaseModel):
    new_order: List[int] | List[str]

class QueueRawRequest(BaseModel):
    content: str

class TaskPayload(BaseModel):
    """Web 任务传输模型；执行语义由 TaskSpec 统一归一化。"""

    model_config = ConfigDict(extra="forbid")

    task: Optional[str | int] = None
    task_type: Optional[str | int] = None
    run_all_in_one: Optional[bool] = None
    input_path: Optional[str] = None
    execution_mode: Optional[str] = None
    output_path: Optional[str] = None
    project_type: Optional[str] = None
    resume: Optional[bool] = False
    profile: Optional[str] = None
    rules_profile: Optional[str] = None
    queue_file: Optional[str] = None
    
    # Overrides
    source_lang: Optional[str] = None
    target_lang: Optional[str] = None
    threads: Optional[int] = None
    retry: Optional[int] = None
    timeout: Optional[int] = None
    rounds: Optional[int] = None
    pre_lines: Optional[int] = None
    
    # Platform Overrides
    platform: Optional[str] = None
    model: Optional[str] = None
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    failover: Optional[bool] = None
    think_depth: Optional[str | int] = None
    thinking_budget: Optional[int] = None
    
    # Limits
    lines: Optional[int] = None
    tokens: Optional[int] = None
    lines_limit: Optional[int] = None
    tokens_limit: Optional[int] = None
    polish_mode: Optional[str] = None
    runtime_overrides: Optional[Dict[str, Any]] = None
    step_overrides: Optional[Dict[str, Any]] = None
    manga: Optional[bool] = False

    @model_validator(mode="after")
    def validate_task_contract(self):
        TaskSpec.from_mapping(self.model_dump(exclude_none=True))
        return self

    def to_task_spec(self) -> TaskSpec:
        return TaskSpec.from_mapping(self.model_dump(exclude_none=True))


class ExternalAgentTaskPayload(TaskPayload):
    user_confirmed_external_processing: StrictBool = Field(default=False, exclude=True)


class TaskControlPayload(BaseModel):
    """Optional control body shared by Web status/stop callers."""

    model_config = ConfigDict(extra="forbid")
    task_id: Optional[str] = None


class ExternalAgentStatusPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str = Field(min_length=1)
    status: str
    message: Optional[str] = None


class RuntimeIdentity(BaseModel):
    runtime_id: str
    workspace_id: str
    api_version: str


class TaskLifecycleResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    task_id: Optional[str] = None
    status: str
    running: bool
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    exit_code: Optional[int] = None
    external_agent_cache_path: Optional[str] = None
    external_agent_input_path: Optional[str] = None
    external_agent_output_path: Optional[str] = None


class TaskStartResponse(TaskLifecycleResponse):
    success: bool
    message: str


class TaskCursors(BaseModel):
    logs: int
    chart: int
    comparison: int


class TaskCursorReset(BaseModel):
    logs: bool
    chart: bool
    comparison: bool


class TaskStatsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    rpm: float
    tpm: float
    totalProgress: int
    completedProgress: int
    totalTokens: int
    elapsedTime: int | float
    status: str
    currentFile: str
    successRate: float
    errorRate: float


class TaskLogResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    timestamp: float
    message: str
    type: str
    seq: int


class TaskChartPoint(BaseModel):
    model_config = ConfigDict(extra="allow")
    time: str
    rpm: float
    tpm: float
    seq: int


class TaskComparison(BaseModel):
    source: str
    translation: str


class TaskStatusResponse(TaskLifecycleResponse):
    stats: TaskStatsResponse
    logs: List[TaskLogResponse]
    chart_data: List[TaskChartPoint]
    cursors: TaskCursors
    cursors_reset: TaskCursorReset
    comparison: Optional[TaskComparison] = None
    comparison_updated_at: float


class TaskPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    valid: bool
    missing_prompts: List[str]
    task_type: str
    argv: List[str]
    steps: Dict[str, Any]



class GlossaryAnalysisRequest(BaseModel):
    input_path: str
    analysis_percent: int = 100
    analysis_lines: Optional[int] = None
    analysis_mode: str = "full"
    incremental_split_target_tokens: Optional[int] = None
    prompt_file: Optional[str] = None
    translate_during_analysis: bool = False
    use_temp_config: bool = False
    temp_platform: Optional[str] = None
    temp_api_key: Optional[str] = None
    temp_api_url: Optional[str] = None
    temp_model: Optional[str] = None
    temp_threads: Optional[int] = None

class GlossaryAnalysisPreflightRequest(BaseModel):
    input_path: str
    analysis_percent: int = 100
    analysis_lines: Optional[int] = None

class GlossaryAnalysisStatus(BaseModel):
    status: str  # 'idle', 'running', 'completed', 'error'
    progress: int = 0
    total: int = 0
    message: str = ""
    results: List[dict] = []

class SaveAnalysisRequest(BaseModel):
    min_frequency: int = 1
    filename: str = "auto_glossary"

class PlatformCreateRequest(BaseModel):
    name: str
    base_config: Optional[Dict[str, Any]] = None

class InternalComparisonPayload(BaseModel):
    source: str
    translation: str
    task_id: Optional[str] = None

class CacheItem(BaseModel):
    id: int
    file_path: str
    text_index: int
    source: str
    translation: str
    original_translation: str
    translation_status: int
    modified: bool = False
    project_path: Optional[str] = None
    project_id: Optional[str] = None
    revision: Optional[str] = None

class CacheUpdateRequest(BaseModel):
    item_id: int
    translation: str

class CacheLoadRequest(BaseModel):
    project_path: str

class CacheRestoreRequest(BaseModel):
    project_path: str
    backup_file: str

class ProofreadStartRequest(BaseModel):
    project_path: str
    report_mode: Optional[str] = None
    suggestion_mode: Optional[str] = None
    overwrite_confirmed: bool = False

class ProofreadSuggestionActionRequest(BaseModel):
    project_path: str
    report_file: Optional[str] = None
    allow_manual_edit_override: bool = False

class ProofreadReviewStateRequest(BaseModel):
    project_path: str
    report_file: Optional[str] = None
    current_suggestion_id: Optional[str] = None
    active_filter: Optional[str] = None

class CacheUpdateRequestWithPath(BaseModel):
    item_id: int
    translation: str
    project_path: str
    report_file: Optional[str] = None
    project_id: Optional[str] = None
    file_path: Optional[str] = None
    text_index: Optional[int] = None
    expected_revision: Optional[str] = None

class ProofreadSingleRequest(BaseModel):
    project_path: str
    file_path: str
    text_index: int
    translation: Optional[str] = None


class InternalLogPayload(BaseModel):
    message: str
    type: str = "info"
    task_id: Optional[str] = None
