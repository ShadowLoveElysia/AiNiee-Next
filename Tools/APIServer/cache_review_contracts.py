"""Typed requests for project-scoped editor and proofread operations."""
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ReviewProjectRequest(BaseModel):
    project_path: str = Field(min_length=1)
    cache_variant: Literal["main", "proofread"] = "main"
    user_confirmed_external_processing: bool = False


class ReviewProjectWrite(ReviewProjectRequest):
    project_id: str
    expected_revision: str = Field(min_length=1)


class ReviewItemEdit(BaseModel):
    file_path: str
    text_index: int
    field: Literal["source_text", "translated_text", "polished_text"] = "translated_text"
    text: str | None = None
    status: Literal[0, 1, 2, 3, 4, 7] | None = None

    @model_validator(mode="after")
    def require_change(self):
        if self.text is None and self.status is None:
            raise ValueError("Supply text or status")
        if self.field == "source_text" and self.text is not None and not self.text.strip():
            raise ValueError("Source text cannot be empty")
        return self


class ReviewBatchEdit(ReviewProjectWrite):
    edits: list[ReviewItemEdit] = Field(min_length=1, max_length=1000)


class ReviewReplaceRequest(ReviewProjectWrite):
    query: str = Field(min_length=1, max_length=2000)
    replacement: str = Field(max_length=100000)
    field: Literal["source_text", "translated_text", "polished_text"] = "translated_text"
    regex: bool = False
    file_paths: list[str] = Field(default_factory=list, max_length=1000)
    preview: bool = True


class ReviewMutationResponse(BaseModel):
    success: bool = True
    changed: int
    revision: str
    preview: bool = False


class ReviewStatisticsResponse(BaseModel):
    project_id: str
    project_name: str
    revision: str
    total_items: int
    status_counts: dict[str, int]
    hierarchy: dict[str, list[str]]
    cache_variant: Literal["main", "proofread"] = "main"


class ReviewCacheItemResponse(BaseModel):
    project_id: str
    revision: str
    file_path: str
    text_index: int
    source_text: str
    translated_text: str
    polished_text: str
    translation_status: int
    cache_variant: Literal["main", "proofread"] = "main"


class ReviewSearchResponse(BaseModel):
    items: list[ReviewCacheItemResponse]
    total: int
    offset: int
    limit: int


class ReviewVariantInfo(BaseModel):
    variant: Literal["main", "proofread"]
    path: str
    revision: str
    size: int


class ReviewVariantsResponse(BaseModel):
    variants: list[ReviewVariantInfo]


class ReviewDiscoverRequest(BaseModel):
    roots: list[str] = Field(min_length=1, max_length=50)
    user_confirmed_external_processing: bool = False


class ReviewDiscoveredProject(BaseModel):
    project_path: str
    variants: list[ReviewVariantInfo]


class ReviewDiscoveryResponse(BaseModel):
    projects: list[ReviewDiscoveredProject]
    errors: list[dict[str, str]]


class ReviewTermRequest(BaseModel):
    source_text: str = Field(default="", max_length=1000000)
    translation: str = Field(default="", max_length=1000000)
    prefix: str = Field(default="", max_length=2000)
    limit: int = Field(default=10, ge=1, le=100)
    glossary: list[dict[str, Any]] | None = None
    rules_profile: str | None = None
    user_confirmed_external_processing: bool = False


class ReviewTermResponse(BaseModel):
    analysis: dict[str, Any]
    suggestions: list[dict[str, Any]]


class ReviewCheckRequest(ReviewProjectRequest):
    mode: Literal["rules", "rules_and_ai"] = "rules"
    profile: str | None = None
    rules_profile: str | None = None
    confirmed: bool = False
    batch_size: int = Field(default=30, ge=1, le=200)
    context_lines: int = Field(default=3, ge=0, le=100)


class ReviewReportInfo(BaseModel):
    name: str
    size: int


class ReviewReportList(BaseModel):
    reports: list[ReviewReportInfo]


class ReviewLegacyApply(ReviewProjectWrite):
    report_file: str
    severities: list[Literal["high", "medium", "low"]] = Field(default_factory=lambda: ["high"])
    confirmed: bool = False
    overwrite: bool = False


class ReviewLegacyApplyResponse(ReviewMutationResponse):
    output_path: str
    output_variant: Literal["proofread"] = "proofread"
    output_revision: str
    conflicts: list[dict[str, Any]]


class ReviewSuggestionBatch(ReviewProjectWrite):
    cache_variant: Literal["main"] = "main"
    suggestion_ids: list[str] = Field(default_factory=list, max_length=1000)
    severities: list[Literal["high", "medium", "low", "info"]] = Field(default_factory=lambda: ["high"])
    action: Literal["accept", "reject", "ignore", "restore", "delete"] = "accept"
    report_file: str | None = None
    allow_manual_edit_override: bool = False
    confirmed: bool = False


class ReviewSuggestionBatchResponse(BaseModel):
    revision: str
    results: list[dict[str, Any]]
