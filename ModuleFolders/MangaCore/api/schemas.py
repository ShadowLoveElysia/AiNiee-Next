from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ProjectOpenRequest(BaseModel):
    project_path: str


class ProjectCreateFromTaskRequest(BaseModel):
    input_path: str
    output_root: str
    source_lang: str = "ja"
    target_lang: str = "zh_cn"
    profile_name: str = "default"
    rules_profile_name: str = "default"
    config_snapshot: dict[str, Any] = Field(default_factory=dict)


class ProjectSaveRequest(BaseModel):
    project_id: str


class PageTranslateRequest(BaseModel):
    save_after_run: bool = True
    refresh_render: bool = True


class BatchTranslateRequest(BaseModel):
    page_ids: list[str]
    generate_text_blocks: bool = True
    auto_inpaint: bool = False
    auto_render: bool = False
    auto_export: bool = False


class ApplyOpsRequest(BaseModel):
    ops: list[dict[str, Any]]


class BrushStrokePoint(BaseModel):
    x: float
    y: float


class BrushMaskStrokeRequest(BaseModel):
    mode: Literal["brush"] = "brush"
    radius: int = Field(default=24, ge=1, le=256)
    points: list[BrushStrokePoint]


class RestoreMaskStrokeRequest(BaseModel):
    mode: Literal["restore"] = "restore"
    radius: int = Field(default=24, ge=1, le=256)
    points: list[BrushStrokePoint]
