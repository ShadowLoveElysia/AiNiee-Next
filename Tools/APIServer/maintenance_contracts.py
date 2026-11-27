"""Explicit maintenance requests; no arbitrary command or download URL input."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class MaintenanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: StrictBool = False


class UpdateRequest(MaintenanceRequest):
    target: Literal["application", "web"] = "application"
    channel: Literal["stable", "preview", "main", "local", "build"] = "stable"
    archive_name: str | None = None


class MangaInstallRequest(MaintenanceRequest):
    backend: Literal["cpu", "cuda", "mps"]


class MangaDefaultsRequest(MaintenanceRequest):
    device: Literal["auto", "cpu", "cuda", "mps"] | None = None
    engines: dict[str, str] = Field(default_factory=dict)
    preset_id: str | None = None
    expected_revision: str | None = None


class UpdateInfoResponse(BaseModel):
    local_version: str
    commit: dict[str, Any] | None = None
    stable: dict[str, Any] | None = None
    preview: dict[str, Any] | None = None


class MangaRuntimeResponse(BaseModel):
    interpreter: str
    platform: str
    backends: list[dict[str, Any]]
    devices: list[str]
    packages: dict[str, str]
    configured: dict[str, Any]
    recommended_backend: str
    probe_performed: bool = False
    cuda_available: bool | None = None
    onnxruntime_providers: list[str] = Field(default_factory=list)
    probe_errors: dict[str, str] = Field(default_factory=dict)


class MaintenanceResult(BaseModel):
    success: bool
    revision: str | None = None
    restart_required: bool = False
