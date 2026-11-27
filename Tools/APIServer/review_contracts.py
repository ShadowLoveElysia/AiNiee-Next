"""Contracts for glossary analysis, rule management and prompt experiments."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewProfile(ReviewRequest):
    profile: str | None = None
    rules_profile: str | None = None


class SourceApproval(ReviewProfile):
    user_confirmed_external_processing: bool = False


class GlossaryScanRequest(SourceApproval):
    input_path: str = Field(min_length=1)
    analysis_percent: int = Field(default=100, ge=1, le=100)
    analysis_lines: int | None = Field(default=None, ge=1)


class GlossaryVolume(ReviewRequest):
    input_path: str = Field(min_length=1)
    source_label: str | None = None
    source_volume: int | None = Field(default=None, ge=0)


class GlossaryAnalyzeRequest(SourceApproval):
    inputs: list[GlossaryVolume] = Field(min_length=1, max_length=100)
    analysis_percent: int = Field(default=100, ge=1, le=100)
    analysis_lines: int | None = Field(default=None, ge=1)
    analysis_mode: Literal["full", "split", "incremental_split"] = "full"
    prompt_file: str | None = None
    translate_during_analysis: bool = False
    new: bool = False
    replace: bool = False
    incremental_split_target_tokens: int | None = Field(default=None, ge=1, le=256000)
    legacy_mode: Literal["normal_extract", "legacy_translation_extract", "legacy_mapping_extract"] = "normal_extract"
    min_frequency: int = Field(default=1, ge=1)
    temp_platform_config: dict[str, Any] | None = None
    confirmed: bool = False


class TermRecord(BaseModel):
    model_config = ConfigDict(extra="allow")
    src: str = Field(min_length=1)
    dst: str = ""
    info: str = ""
    type: str = ""


class GlossaryFrequencyRequest(SourceApproval):
    input_path: str = Field(min_length=1)
    terms: list[TermRecord] = Field(min_length=1)
    min_frequency: int = Field(default=1, ge=1)


class TermTranslateRequest(SourceApproval):
    terms: list[TermRecord] = Field(min_length=1, max_length=5000)
    mode: Literal["candidates", "batch"] = "candidates"
    rounds: int = Field(default=3, ge=1, le=10)
    avoid: dict[str, list[str]] = Field(default_factory=dict)
    temp_platform_config: dict[str, Any] | None = None
    confirmed: bool = False


class RuleMergeOptions(ReviewRequest):
    enabled: bool = False
    new: bool = True
    replace: bool = False
    source_label: str | None = None
    source_volume: int | None = Field(default=None, ge=0)


class RulesImportRequest(ReviewProfile):
    rules: dict[str, Any] = Field(default_factory=dict)
    terms: list[TermRecord] | None = None
    expected_revision: str = Field(min_length=1)
    merge: RuleMergeOptions = Field(default_factory=RuleMergeOptions)
    legacy_mapping_confirmed: bool = False
    mode: Literal["merge", "replace"] = "merge"


class RulesParseRequest(ReviewRequest):
    content: str = Field(min_length=1, max_length=20_000_000)
    repair: bool = False


class RulesCreateRequest(ReviewRequest):
    name: str = Field(min_length=1)
    rules: dict[str, Any] = Field(default_factory=dict)
    activate: bool = False
    expected_revision: str | None = None


class RulesExportRequest(ReviewProfile):
    format: Literal["structured", "glossary"] = "structured"
    rules: dict[str, Any] | None = None
    terms: list[TermRecord] | None = None


class RuleVolumeRequest(ReviewProfile):
    volume: int = Field(ge=0)


class PromptTestRequest(SourceApproval):
    text: str = Field(min_length=1, max_length=2_000_000)
    prompt_file: str = Field(min_length=1)
    pure_prompt: bool = True
    temp_platform_config: dict[str, Any] | None = None
    confirmed: bool = False


class ReviewData(BaseModel):
    data: dict[str, Any]


class RulesImportResponse(BaseModel):
    summary: dict[str, int]
    revision: str


class RulesCreateResponse(BaseModel):
    profile: str
    activated: bool
    revision: str | None = None


class RulesExportResponse(BaseModel):
    filename: str
    content: str
    revision: str


class PromptPreviewResponse(BaseModel):
    messages: list[dict[str, Any]]
    system_prompt: str
    source_lines: int
