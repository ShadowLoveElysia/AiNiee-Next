"""HTTP contracts for the existing media runtime, without importing its workers."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool


class MediaInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MediaPreferencesResponse(BaseModel):
    values: dict[str, Any]
    revision: str
    settings_schema: dict[str, Any] = Field(alias="schema")


class MediaPreferencesUpdate(MediaInput):
    changes: dict[str, Any]
    expected_revision: str = Field(min_length=1)


class MediaPreferencesSaved(BaseModel):
    success: bool
    revision: str


class MediaModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    key: str
    name: str
    repo: str
    revision: str
    directory: str
    backend: str
    download_gb: float
    present: bool


class MediaModelsResponse(BaseModel):
    model_root: str
    translation: list[MediaModel]
    recognition: list[MediaModel]


class MediaRuntimeResponse(BaseModel):
    python: str
    managed_python: str
    managed_installed: bool
    ffmpeg: str | None
    ffprobe: str | None
    application_audio_supported: bool
    video_extensions: list[str]
    probe_required: bool


class MediaRuntimeOptions(MediaInput):
    device: str | None = None
    family: str | None = None
    recognizer: str | None = None
    asr_device: str | None = None
    asr_endpoint: str | None = None
    model_root: str | None = None
    download_scope: Literal["all", "asr", "llm"] | None = None
    package_source: Literal["nju", "official"] | None = None


class MediaRuntimeRequest(MediaInput):
    confirmed: StrictBool = False
    options: MediaRuntimeOptions = Field(default_factory=MediaRuntimeOptions)


class MediaJobResponse(BaseModel):
    job_id: str
    kind: str
    status: str
    running: bool
    created_at: str
    finished_at: str | None = None
    result: Any = None
    error: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
    cursor: int = 0
    cursor_reset: bool = False


class MediaSessionOptions(MediaInput):
    model_root: str | None = None
    family: str | None = None
    source_lang: str | None = None
    target_lang: str | None = None
    speaker: str | None = None
    device: str | None = None
    asr_device: str | None = None
    endpoint_silence_ms: int | None = Field(default=None, gt=0)
    target_segment_ms: int | None = Field(default=None, gt=0)
    max_segment_ms: int | None = Field(default=None, gt=0, le=28000)
    context_segments: int | None = Field(default=None, ge=0, le=3)
    cache_ram_mib: int | None = Field(default=None, ge=0)
    recognizer: str | None = None
    asr_endpoint: str | None = None
    application_pid: int | None = Field(default=None, ge=0)
    application_started: str | None = None
    application_name: str | None = None
    glossary: list[dict[str, str]] | None = None
    glossary_profile: str | None = None
    input_path: str | None = None
    output_directory: str | None = None
    subtitle_mode: Literal["soft", "hard"] | None = None
    glossary_mode: Literal["temporary", "manual"] | None = None
    asr_mode: Literal["local", "cloud"] | None = None
    translation_mode: Literal["local", "cloud"] | None = None
    video_encoder: str | None = None
    cloud_asr_endpoint: str | None = None
    cloud_asr_model: str | None = None
    cloud_asr_api_key: str | None = Field(default=None, repr=False)
    recording: StrictBool | None = None
    record_directory: str | None = None


class MediaSessionRequest(MediaInput):
    confirmed: StrictBool = False
    user_confirmed_external_processing: StrictBool = False
    options: MediaSessionOptions = Field(default_factory=MediaSessionOptions)


class MediaSessionResponse(BaseModel):
    session_id: str | None
    mode: str | None
    status: str
    running: bool
    ready: bool
    result: dict[str, Any] | None
    error: dict[str, Any] | None
    events: list[dict[str, Any]]
    cursor: int
    cursor_reset: bool
    recording: bool
    record_path: str | None


class MediaHistoryResponse(BaseModel):
    session_id: str
    generation: int
    total: int
    start: int
    items: list[dict[str, Any]]


class MediaDiagnosticsResponse(BaseModel):
    session_id: str | None
    mode: str | None
    status: str
    running: bool
    ready: bool
    events: list[dict[str, Any]]
    cursor: int
    cursor_reset: bool


class MediaRecordingRequest(MediaInput):
    enabled: StrictBool
    directory: str | None = None
    user_confirmed_external_processing: StrictBool = False


class MediaTextRequest(MediaInput):
    text: str = Field(min_length=1, max_length=2000)
    source_lang: str
    target_lang: str
    max_characters: int = Field(default=0, ge=0, le=1000)
    user_confirmed_external_processing: StrictBool = False


class MediaTextResponse(BaseModel):
    session_id: str
    request_id: str


class MediaSuccess(BaseModel):
    success: bool
    generation: int | None = None
