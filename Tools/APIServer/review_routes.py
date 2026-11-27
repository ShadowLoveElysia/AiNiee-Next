"""Typed, noninteractive entry points for the glossary and rules menus."""
from fastapi import APIRouter, HTTPException, Request

from ModuleFolders.Infrastructure.ApiSecurity import is_mcp_request
from ModuleFolders.Infrastructure.TaskConfig.ConfigProfileService import ConfigConflictError
from ModuleFolders.Service.TaskRuntime import review
from ModuleFolders.Service.TaskRuntime.jobs import JobConflict, get_job_manager
from Tools.APIServer.job_contracts import JobResponse
from Tools.APIServer.responses import ERROR_RESPONSES
from Tools.APIServer.review_contracts import (
    GlossaryAnalyzeRequest, GlossaryFrequencyRequest, GlossaryScanRequest,
    PromptPreviewResponse, PromptTestRequest, ReviewData, ReviewProfile,
    RuleVolumeRequest, RulesCreateRequest, RulesCreateResponse, RulesExportRequest,
    RulesExportResponse, RulesImportRequest, RulesImportResponse, TermTranslateRequest,
    RulesParseRequest,
)

router = APIRouter(prefix="/api/review", tags=["review"])


def _approve_source(payload, request):
    if is_mcp_request(request) and not payload.user_confirmed_external_processing:
        raise HTTPException(status_code=409, detail="Approve external processing of these sources before this operation")


def _invoke(function, *args):
    try:
        return function(*args)
    except (ConfigConflictError, FileExistsError, JobConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Requested resource does not exist") from exc
    except (RuntimeError, ImportError) as exc:
        raise HTTPException(status_code=503, detail="The requested review capability is unavailable") from exc


def _start(kind, payload, request, work):
    _approve_source(payload, request)
    if not payload.confirmed:
        raise HTTPException(status_code=409, detail="Confirm this model request before starting it")
    config = _invoke(review.load_configuration, payload.profile, payload.rules_profile)
    if getattr(payload, "temp_platform_config", None):
        from ModuleFolders.Infrastructure.ApiSecurity import contains_redacted_secret
        if contains_redacted_secret(payload.temp_platform_config):
            raise HTTPException(status_code=422, detail="A redacted placeholder is not a usable provider credential")
    try:
        return get_job_manager().start(kind, lambda cancel: work(payload, config, cancel),
                                       metadata={"requires_external_confirmation": True})
    except JobConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/glossary/scan", response_model=ReviewData, responses=ERROR_RESPONSES)
def scan_glossary(payload: GlossaryScanRequest, request: Request):
    _approve_source(payload, request)
    return {"data": _invoke(review.scan_glossary, payload)}


@router.post("/glossary/frequency", response_model=ReviewData, responses=ERROR_RESPONSES)
def glossary_frequency(payload: GlossaryFrequencyRequest, request: Request):
    _approve_source(payload, request)
    return {"data": _invoke(review.frequency, payload)}


@router.post("/glossary/analyze", response_model=JobResponse, responses=ERROR_RESPONSES)
def analyze_glossary(payload: GlossaryAnalyzeRequest, request: Request):
    return _start("glossary_analysis", payload, request, review.analyze_glossary)


@router.post("/glossary/translate", response_model=JobResponse, responses=ERROR_RESPONSES)
def translate_glossary(payload: TermTranslateRequest, request: Request):
    return _start("glossary_translation", payload, request, review.translate_terms)


@router.post("/rules/preview", response_model=ReviewData, responses=ERROR_RESPONSES)
def preview_rules(payload: ReviewProfile):
    return {"data": _invoke(review.preview_rules, payload.profile, payload.rules_profile)}


@router.post("/rules/volume", response_model=ReviewData, responses=ERROR_RESPONSES)
def rules_for_volume(payload: RuleVolumeRequest):
    return {"data": _invoke(review.volume_rules, payload)}


@router.post("/rules/import", response_model=RulesImportResponse, responses=ERROR_RESPONSES)
def import_rules(payload: RulesImportRequest):
    return _invoke(review.import_rules, payload)


@router.post("/rules/parse", response_model=ReviewData, responses=ERROR_RESPONSES)
def parse_rules(payload: RulesParseRequest):
    return {"data": _invoke(review.parse_rules, payload)}


@router.post("/rules/create", response_model=RulesCreateResponse, responses=ERROR_RESPONSES)
def create_rules_profile(payload: RulesCreateRequest):
    return _invoke(review.create_rules_profile, payload)


@router.post("/rules/export", response_model=RulesExportResponse, responses=ERROR_RESPONSES)
def export_rules(payload: RulesExportRequest):
    return _invoke(review.export_rules, payload)


@router.post("/prompt/preview", response_model=PromptPreviewResponse, responses=ERROR_RESPONSES)
def preview_prompt(payload: PromptTestRequest, request: Request):
    _approve_source(payload, request)
    config = _invoke(review.load_configuration, payload.profile, payload.rules_profile)
    return _invoke(review.build_prompt, payload, config)[0]


@router.post("/prompt/test", response_model=JobResponse, responses=ERROR_RESPONSES)
def test_prompt(payload: PromptTestRequest, request: Request):
    return _start("prompt_test", payload, request, review.test_prompt)
