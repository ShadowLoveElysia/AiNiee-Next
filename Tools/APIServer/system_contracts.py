"""System management requests and responses independent of running services."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool


class SystemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SettingDescription(BaseModel):
    key: str
    default: Any
    level: str
    type: str
    category: str
    label_key: str
    description_key: str
    choices: list[Any]
    minimum: float | None
    maximum: float | None
    depends_on: str | None
    submenu: str
    online_only: bool


class SettingsValidationRequest(SystemRequest):
    values: dict[str, Any]


class SettingsValidationResponse(BaseModel):
    valid: bool
    errors: dict[str, str]


class EbookPreviewRequest(SystemRequest):
    template: str = Field(default="X 第N卷", min_length=1, max_length=1000)
    series: str = Field(min_length=1, max_length=1000)


class EbookPreviewResponse(BaseModel):
    single: str
    merged: str


class RevisionResponse(BaseModel):
    revision: str
    success: bool = True


class PlatformRequest(SystemRequest):
    platform: str = Field(min_length=1)
    expected_revision: str | None = None


class PlatformSelectRequest(PlatformRequest):
    task: Literal["translate", "polish", "both"] = "both"
    model: str | None = None


class PlatformKeysRequest(PlatformRequest):
    keys_text: SecretStr


class PlatformCallRequest(SystemRequest):
    platform: str | None = None
    confirmed: StrictBool = False


class PlatformSummary(BaseModel):
    name: str
    local: bool
    group: str
    api_format: str
    model: str
    selected_for: list[str]


class DiagnosticRequest(SystemRequest):
    error_text: str = Field(min_length=1, max_length=100_000)
    language: str = "zh_CN"
    allow_llm: bool = False
    confirmed: StrictBool = False


class KnowledgeEntry(BaseModel):
    id: str
    question: str
    keywords: list[str]
    answer: str
    category: str
    score: float | None = None


class DiagnosticResponse(BaseModel):
    is_matched: bool
    is_code_bug: bool
    error_type: str
    root_cause: str
    solution: str
    self_check: list[str] | None
    confidence: float
    matched_rule: str
    token_cost: int


class RecentProject(BaseModel):
    path: str
    profile: str = "default"
    rules_profile: str = "default"
    pinned: bool = False


class RecentProjectsResponse(BaseModel):
    projects: list[RecentProject]
    revision: str


class RecentProjectsRequest(SystemRequest):
    projects: list[RecentProject] = Field(max_length=1000)
    expected_revision: str


class RecentCleanRequest(SystemRequest):
    expected_revision: str


class RecentActivateRequest(SystemRequest):
    path: str
    expected_revision: str


class ProfileDocumentResponse(BaseModel):
    kind: Literal["settings", "rules"]
    name: str
    content: dict[str, Any]
    revision: str


class ProfileDocumentRequest(SystemRequest):
    content: dict[str, Any]
    expected_revision: str = "missing"


class ServiceStartRequest(SystemRequest):
    confirmed: StrictBool = False
    host: str = "127.0.0.1"
    port: int = Field(ge=1, le=65535)
    transport: Literal["streamable-http", "sse"] = "streamable-http"
    path: str = Field(default="/mcp", pattern=r"^/[A-Za-z0-9/_-]*$")
    auth_token: SecretStr | None = None


class ServiceStopRequest(SystemRequest):
    service_id: str
    confirmed: StrictBool = False


class ServiceStatus(BaseModel):
    service: Literal["mcp", "skills"]
    service_id: str
    status: str
    host: str
    port: int
    transport: str
    auth_configured: bool
    owned: bool = True


class ServiceListResponse(BaseModel):
    services: list[ServiceStatus]


class ServiceReadinessResponse(BaseModel):
    mcp: dict[str, Any]
    skills: dict[str, Any]


class AcknowledgementsResponse(BaseModel):
    title: str
    introduction: str
    sponsors: list[str]
