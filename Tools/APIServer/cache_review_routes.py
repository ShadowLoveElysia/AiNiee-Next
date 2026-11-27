"""Editor and proofread parity routes; authentication remains at the API host."""
from dataclasses import asdict
from typing import Any, Literal
import re
import importlib

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import FileResponse

from ModuleFolders.Infrastructure.ApiSecurity import is_mcp_request
from ModuleFolders.Infrastructure.TaskConfig.ConfigProfileService import (
    load_effective_config, resolve_profile_path, PROFILES_PATH, RULES_PROFILES_PATH,
)
from pathlib import Path
from ModuleFolders.Infrastructure.Cache.CachePersistence import CacheWriteConflict
from ModuleFolders.Service.TaskRuntime.jobs import get_job_manager, JobConflict
from Tools.APIServer.cache_review_contracts import (
    ReviewBatchEdit, ReviewCheckRequest, ReviewLegacyApply, ReviewLegacyApplyResponse,
    ReviewMutationResponse, ReviewReplaceRequest, ReviewReportList, ReviewStatisticsResponse,
    ReviewSuggestionBatch, ReviewSuggestionBatchResponse, ReviewTermRequest, ReviewTermResponse,
    ReviewCacheItemResponse, ReviewSearchResponse, ReviewVariantsResponse,
    ReviewDiscoverRequest, ReviewDiscoveryResponse,
)
from Tools.APIServer.job_contracts import JobResponse
from Tools.APIServer.responses import ERROR_RESPONSES

router = APIRouter(prefix="/api/review", tags=["review"])


class _ReviewService:
    def __getattr__(self, name):
        try:
            service = importlib.import_module("ModuleFolders.Service.TaskRuntime.cache_review")
        except ImportError as exc:
            raise HTTPException(status_code=503, detail="Project review dependencies are not installed") from exc
        return getattr(service, name)


cache_review = _ReviewService()


def cache_revision(output_path, cache_variant="main"):
    return cache_review.cache_revision(output_path, cache_variant)


def _review_config(profile=None, rules_profile=None):
    for directory, name, allow_none in ((PROFILES_PATH, profile, False), (RULES_PROFILES_PATH, rules_profile, True)):
        if name is None:
            continue
        path, normalized = resolve_profile_path(directory, name, allow_none=allow_none)
        if normalized != "None" and not Path(path).is_file():
            raise FileNotFoundError("Selected profile not found")
    return load_effective_config(active_profile_name=profile, active_rules_profile_name=rules_profile, create_missing=False)


def _approved(request: Request, confirmed: bool):
    if is_mcp_request(request) and not confirmed:
        raise HTTPException(status_code=409, detail="Confirm external processing for this project's review operation")


def _host():
    from Tools.APIServer import application
    return application


def _identity(cache, project_id):
    if cache.project.project_id != project_id:
        raise HTTPException(status_code=409, detail="Cache project has changed")


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except (FileNotFoundError, KeyError) as exc:
        raise HTTPException(status_code=404, detail="Requested cache item or report was not found") from exc
    except (FileExistsError, JobConflict, CacheWriteConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, TypeError, re.error) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Project file operation failed") from exc


@router.get("/cache/statistics", response_model=ReviewStatisticsResponse, responses=ERROR_RESPONSES)
def cache_statistics(project_path: str, request: Request, user_confirmed_external_processing: bool = False, cache_variant: Literal["main", "proofread"] = "main"):
    _approved(request, user_confirmed_external_processing)
    output = _host().resolve_cache_output_path(project_path)
    return _call(cache_review.statistics, output, cache_variant)


@router.get("/cache/variants", response_model=ReviewVariantsResponse, responses=ERROR_RESPONSES)
def cache_variants(project_path: str, request: Request, user_confirmed_external_processing: bool = False):
    _approved(request, user_confirmed_external_processing)
    return _call(cache_review.list_variants, _host().resolve_cache_output_path(project_path))


@router.post("/cache/discover", response_model=ReviewDiscoveryResponse, responses=ERROR_RESPONSES)
def discover_cache_projects(payload: ReviewDiscoverRequest, request: Request):
    _approved(request, payload.user_confirmed_external_processing)
    return _call(cache_review.discover_projects, payload.roots)


@router.get("/cache/item", response_model=ReviewCacheItemResponse, responses=ERROR_RESPONSES)
def get_editor_item(project_path: str, file_path: str, text_index: int, request: Request, user_confirmed_external_processing: bool = False, cache_variant: Literal["main", "proofread"] = "main"):
    _approved(request, user_confirmed_external_processing)
    return _call(cache_review.read_item, _host().resolve_cache_output_path(project_path), file_path, text_index, cache_variant)


@router.get("/cache/search", response_model=ReviewSearchResponse, responses=ERROR_RESPONSES)
def search_editor_items(
    project_path: str, request: Request, query: str = "",
    scope: Literal["all", "source_text", "translated_text", "polished_text"] = "all",
    regex: bool = False, flagged: bool = False, offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000), user_confirmed_external_processing: bool = False,
    cache_variant: Literal["main", "proofread"] = "main",
):
    _approved(request, user_confirmed_external_processing)
    return _call(cache_review.search, _host().resolve_cache_output_path(project_path), query, scope, regex, flagged, offset, limit, cache_variant)


@router.put("/cache/items", response_model=ReviewMutationResponse, responses=ERROR_RESPONSES)
def edit_cache_items(payload: ReviewBatchEdit, request: Request):
    _approved(request, payload.user_confirmed_external_processing)
    host = _host()
    output = host.resolve_cache_output_path(payload.project_path)
    with host._edit_cache_project(output, expected_revision=payload.expected_revision, cache_variant=payload.cache_variant) as (cache, _):
        _identity(cache, payload.project_id)
        changed = _call(cache_review.apply_edits, cache, payload.edits)
        _call(cache.save_to_file)
        if payload.cache_variant == "main":
            _, store = host._load_proofread_store(output)
            _call(store.complete_manually_edited_lines, cache.project, client="web")
        return {"changed": changed, "revision": cache_revision(output, payload.cache_variant)}


@router.get("/cache/items", response_model=ReviewSearchResponse, responses=ERROR_RESPONSES)
def list_editor_items(
    project_path: str, request: Request, file_path: str | None = None,
    offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
    cache_variant: Literal["main", "proofread"] = "main", user_confirmed_external_processing: bool = False,
):
    _approved(request, user_confirmed_external_processing)
    return _call(cache_review.list_items, _host().resolve_cache_output_path(project_path), file_path, offset, limit, cache_variant)


@router.post("/cache/replace", response_model=ReviewMutationResponse, responses=ERROR_RESPONSES)
def replace_cache_items(payload: ReviewReplaceRequest, request: Request):
    _approved(request, payload.user_confirmed_external_processing)
    host = _host()
    output = host.resolve_cache_output_path(payload.project_path)
    with host._edit_cache_project(output, expected_revision=payload.expected_revision, cache_variant=payload.cache_variant) as (cache, revision):
        _identity(cache, payload.project_id)
        changed = _call(cache_review.replace_items, cache, payload)
        if not payload.preview and changed:
            _call(cache.save_to_file)
            if payload.cache_variant == "main":
                _, store = host._load_proofread_store(output)
                _call(store.complete_manually_edited_lines, cache.project, client="web")
            revision = cache_revision(output, payload.cache_variant)
        return {"changed": changed, "revision": revision, "preview": payload.preview}


@router.post("/cache/terms", response_model=ReviewTermResponse, responses=ERROR_RESPONSES)
def analyze_cache_terms(payload: ReviewTermRequest, request: Request):
    _approved(request, payload.user_confirmed_external_processing)
    config = {} if payload.glossary is not None else _call(_review_config, rules_profile=payload.rules_profile)
    return _call(cache_review.analyze_terms, payload, config)


@router.post("/proofread/check", response_model=JobResponse, responses=ERROR_RESPONSES)
def run_project_checks(payload: ReviewCheckRequest, request: Request):
    _approved(request, payload.user_confirmed_external_processing)
    if payload.mode == "rules_and_ai" and not payload.confirmed:
        raise HTTPException(status_code=409, detail="Confirm the AI proofread request")
    output = _host().resolve_cache_output_path(payload.project_path)
    config = _call(_review_config, payload.profile, payload.rules_profile) if payload.mode == "rules_and_ai" else {}
    return _call(get_job_manager().start, "proofread-check", lambda cancel: cache_review.check_project(output, payload, config, cancel),
                 metadata={"project_path": output, "cache_variant": payload.cache_variant, "mode": payload.mode, "requires_external_confirmation": True})


@router.get("/proofread/reports", response_model=ReviewReportList, responses=ERROR_RESPONSES)
def legacy_reports(project_path: str, request: Request, user_confirmed_external_processing: bool = False):
    _approved(request, user_confirmed_external_processing)
    return _call(cache_review.list_reports, _host().resolve_cache_output_path(project_path))


@router.get("/proofread/report", response_model=dict[str, Any], responses=ERROR_RESPONSES)
def legacy_report(project_path: str, report_file: str, request: Request, user_confirmed_external_processing: bool = False):
    _approved(request, user_confirmed_external_processing)
    output = _host().resolve_cache_output_path(project_path)
    path = _call(cache_review.report_path, output, report_file)
    return _call(cache_review.ProofreadReport.load, path).to_dict()


@router.get("/proofread/report/download", response_class=FileResponse, responses=ERROR_RESPONSES)
def download_legacy_report(project_path: str, report_file: str, request: Request, user_confirmed_external_processing: bool = False):
    _approved(request, user_confirmed_external_processing)
    output = _host().resolve_cache_output_path(project_path)
    path = _call(cache_review.report_path, output, report_file)
    return FileResponse(path, media_type="application/json", filename=path.name)


@router.post("/proofread/report/apply", response_model=ReviewLegacyApplyResponse, responses=ERROR_RESPONSES)
def apply_legacy_corrections(payload: ReviewLegacyApply, request: Request):
    _approved(request, payload.user_confirmed_external_processing)
    if not payload.confirmed:
        raise HTTPException(status_code=409, detail="Confirm applying the selected corrections")
    host = _host()
    output = host.resolve_cache_output_path(payload.project_path)
    with host._edit_cache_project(output, expected_revision=payload.expected_revision, cache_variant=payload.cache_variant) as (cache, revision):
        _identity(cache, payload.project_id)
        result = _call(cache_review.apply_legacy_report, cache, output, payload)
        return {**result, "revision": revision, "output_revision": cache_revision(output, "proofread")}


@router.post("/proofread/suggestions/batch", response_model=ReviewSuggestionBatchResponse, responses=ERROR_RESPONSES)
def batch_review_suggestions(payload: ReviewSuggestionBatch, request: Request):
    from ModuleFolders.Service.Proofreader import ProofreadReviewService

    _approved(request, payload.user_confirmed_external_processing)
    if not payload.confirmed:
        raise HTTPException(status_code=409, detail="Confirm the batch review action")
    host = _host()
    output = host.resolve_cache_output_path(payload.project_path)
    with host._edit_cache_project(output, expected_revision=payload.expected_revision, cache_variant=payload.cache_variant) as (cache, _):
        _identity(cache, payload.project_id)
        _, store = host._load_proofread_store(output, payload.report_file)
        by_id = {item.suggestion_id: item for item in store.suggestions}
        if any(item not in by_id for item in payload.suggestion_ids):
            raise HTTPException(status_code=404, detail="Unknown proofread suggestion")
        ids = payload.suggestion_ids or [item.suggestion_id for item in store.pending() if item.severity in payload.severities]
        service = ProofreadReviewService(store, cache.project, save_project=cache.save_to_file)
        results = []
        for suggestion_id in ids:
            kwargs = {"client": "web"}
            if payload.action == "accept":
                kwargs["allow_manual_edit_override"] = payload.allow_manual_edit_override
            result = _call(getattr(service, payload.action), suggestion_id, **kwargs)
            results.append(asdict(result))
        return {"results": results, "revision": cache_revision(output, payload.cache_variant)}
