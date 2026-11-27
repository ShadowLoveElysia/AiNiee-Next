"""Authenticated automation adapters; execution remains in the shared task runtime."""
from contextlib import contextmanager
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request

from Tools.APIServer.automation_contracts import (
    AutomationConfigurationResponse, AutomationControl, AutomationDelete, AutomationLogsResponse,
    AutomationMutation, AutomationRecord, AutomationRequeueRequest, AutomationResultResponse,
    AutomationResumeRequest, AutomationRunResponse, AutomationRunsResponse, AutomationScanResponse,
    AutomationSchedulePreview, AutomationStatusResponse, AutomationWorkflowPreviewResponse,
    AutomationWorkflowRequest,
)
from Tools.APIServer.responses import ERROR_RESPONSES

router = APIRouter(prefix="/api/automation", tags=["automation"])


def controller():
    from ModuleFolders.Service.TaskRuntime.automation import get_automation_controller
    return get_automation_controller()


def _read_result(request, confirmed, result):
    from ModuleFolders.Infrastructure.ApiSecurity import is_mcp_request, sanitize_data_for_mcp
    if is_mcp_request(request):
        if not confirmed:
            raise HTTPException(409, "Approve external processing before reading automation logs or task content")
        return sanitize_data_for_mcp(result, path="/api/automation")
    return result


@contextmanager
def operation():
    from ModuleFolders.Infrastructure.TaskConfig.ConfigProfileService import ConfigConflictError
    from ModuleFolders.Service.TaskRuntime.automation import AutomationConflict
    from ModuleFolders.Service.TaskRuntime.operations import TaskOperationError
    try:
        yield
    except KeyError as exc:
        raise HTTPException(404, "Automation entry or owned run not found") from exc
    except (AutomationConflict, ConfigConflictError) as exc:
        raise HTTPException(409, str(exc)) from exc
    except TaskOperationError as exc:
        status = {"TASK_NOT_FOUND": 404, "INVALID_TASK": 422, "FEATURE_UNAVAILABLE": 503,
                  "TASK_START_FAILED": 500, "EXTERNAL_CHANNEL_REQUIRED": 403}.get(exc.code, 409)
        raise HTTPException(status, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ImportError as exc:
        raise HTTPException(503, "Automation runtime dependency is unavailable") from exc
    except OSError as exc:
        raise HTTPException(500, "Automation file operation failed") from exc


@router.get("/configuration", response_model=AutomationConfigurationResponse, responses=ERROR_RESPONSES)
def configuration():
    from ModuleFolders.Service.TaskRuntime.automation import read_automation_config
    with operation():
        return read_automation_config()


@router.put("/configuration/{section}", response_model=AutomationConfigurationResponse, responses=ERROR_RESPONSES)
def replace_configuration(section: str, request: AutomationMutation):
    with operation():
        return controller().configuration_change(section, request.expected_revision, lambda _current: request.data)


@router.get("/status", response_model=AutomationStatusResponse, responses=ERROR_RESPONSES)
def status():
    with operation():
        return controller().status()


@router.post("/stop", response_model=AutomationStatusResponse, responses=ERROR_RESPONSES)
def stop_automation():
    with operation():
        owned = controller()
        if not owned.shutdown():
            raise HTTPException(409, "Automation shutdown is still pending")
        return owned.status()


@router.get("/logs", response_model=AutomationLogsResponse, responses=ERROR_RESPONSES)
def logs(request: Request, limit: int = Query(50, ge=1, le=100), user_confirmed_external_processing: bool = False):
    with operation():
        _read_result(request, user_confirmed_external_processing, {})
        return _read_result(request, user_confirmed_external_processing, controller().logs(limit))


@router.post("/scheduler/preview", response_model=AutomationRecord, responses=ERROR_RESPONSES)
def schedule_preview(request: AutomationSchedulePreview):
    with operation():
        from ModuleFolders.Infrastructure.Automation.SchedulerManager import ScheduleParser
        rule = ScheduleParser.parse(request.expression, allow_empty=request.trigger_type != "scheduled")
        next_run = ScheduleParser.next_run(rule, datetime.now())
        return {"type": rule["type"], "next_run": next_run.isoformat() if next_run else None,
                "trigger_type": request.trigger_type}


@router.post("/scheduler/tasks", response_model=AutomationConfigurationResponse, responses=ERROR_RESPONSES)
def create_schedule(request: AutomationMutation):
    with operation():
        return controller().mutate_entry("scheduler", request.data.get("id"), request.data, request.expected_revision, create=True)


@router.get("/scheduler/tasks", response_model=list[AutomationRecord], responses=ERROR_RESPONSES)
def list_schedules():
    with operation():
        return controller().entries("scheduler")


@router.put("/scheduler/tasks/{task_id}", response_model=AutomationConfigurationResponse, responses=ERROR_RESPONSES)
def update_schedule(task_id: str, request: AutomationMutation):
    with operation():
        return controller().mutate_entry("scheduler", task_id, request.data, request.expected_revision)


@router.delete("/scheduler/tasks/{task_id}", response_model=AutomationConfigurationResponse, responses=ERROR_RESPONSES)
def delete_schedule(task_id: str, request: AutomationDelete):
    with operation():
        return controller().mutate_entry("scheduler", task_id, {}, request.expected_revision, delete=True)


@router.post("/scheduler/tasks/{task_id}/trigger", response_model=AutomationRunResponse, responses=ERROR_RESPONSES)
def trigger_schedule(task_id: str):
    with operation():
        return controller().trigger(task_id)


@router.post("/scheduler/start", response_model=AutomationStatusResponse, responses=ERROR_RESPONSES)
def start_scheduler(request: AutomationControl):
    with operation():
        return controller().control("scheduler", True, confirmed=request.confirmed, event_triggers=request.event_triggers)


@router.post("/scheduler/stop", response_model=AutomationStatusResponse, responses=ERROR_RESPONSES)
def stop_scheduler(request: AutomationControl):
    with operation():
        return controller().control("scheduler", False, stop_tasks=request.stop_tasks)


@router.post("/watch/rules", response_model=AutomationConfigurationResponse, responses=ERROR_RESPONSES)
def create_watch_rule(request: AutomationMutation):
    with operation():
        return controller().mutate_entry("watch_mode", request.data.get("id"), request.data, request.expected_revision, create=True)


@router.get("/watch/rules", response_model=list[AutomationRecord], responses=ERROR_RESPONSES)
def list_watch_rules():
    with operation():
        return controller().entries("watch")


@router.put("/watch/rules/{rule_id}", response_model=AutomationConfigurationResponse, responses=ERROR_RESPONSES)
def update_watch_rule(rule_id: str, request: AutomationMutation):
    with operation():
        return controller().mutate_entry("watch_mode", rule_id, request.data, request.expected_revision)


@router.delete("/watch/rules/{rule_id}", response_model=AutomationConfigurationResponse, responses=ERROR_RESPONSES)
def delete_watch_rule(rule_id: str, request: AutomationDelete):
    with operation():
        return controller().mutate_entry("watch_mode", rule_id, {}, request.expected_revision, delete=True)


@router.get("/watch/files", response_model=AutomationScanResponse, responses=ERROR_RESPONSES)
def watch_files(limit_per_rule: int = Query(30, ge=1, le=1000), include_unmatched: bool = True):
    with operation():
        return {"snapshots": controller().scan(limit_per_rule, include_unmatched)}


@router.post("/watch/start", response_model=AutomationStatusResponse, responses=ERROR_RESPONSES)
def start_watch(request: AutomationControl):
    with operation():
        return controller().control("watch", True, confirmed=request.confirmed)


@router.post("/watch/stop", response_model=AutomationStatusResponse, responses=ERROR_RESPONSES)
def stop_watch(request: AutomationControl):
    with operation():
        return controller().control("watch", False, stop_tasks=request.stop_tasks)


@router.delete("/watch/history", response_model=AutomationResultResponse, responses=ERROR_RESPONSES)
def clear_watch_history():
    with operation():
        return controller().clear_history()


@router.post("/watch/requeue", response_model=AutomationResultResponse, responses=ERROR_RESPONSES)
def requeue_watch_file(request: AutomationRequeueRequest):
    with operation():
        return controller().requeue(request.rule_id, request.file_path, request.workflow_steps, request.auto_start)


@router.post("/workflows/preview", response_model=AutomationWorkflowPreviewResponse, responses=ERROR_RESPONSES)
def workflow_preview(request: AutomationWorkflowRequest):
    from ModuleFolders.Service.TaskRuntime.automation import preview_workflow
    with operation():
        return preview_workflow(request.task)


@router.post("/workflows/start", response_model=AutomationRunResponse, responses=ERROR_RESPONSES)
def workflow_start(request: AutomationWorkflowRequest):
    with operation():
        return controller().start_workflow(request.task)


@router.get("/runs", response_model=AutomationRunsResponse, responses=ERROR_RESPONSES)
def runs(request: Request, limit: int = Query(50, ge=1, le=100), user_confirmed_external_processing: bool = False):
    with operation():
        _read_result(request, user_confirmed_external_processing, {})
        return _read_result(request, user_confirmed_external_processing, {"runs": controller().runs(limit)})


@router.get("/runs/{task_id}", response_model=AutomationRunResponse, responses=ERROR_RESPONSES)
def run_status(task_id: str, request: Request, user_confirmed_external_processing: bool = False):
    with operation():
        _read_result(request, user_confirmed_external_processing, {})
        return _read_result(request, user_confirmed_external_processing, controller().run_status(task_id))


@router.post("/runs/{task_id}/stop", response_model=AutomationRunResponse, responses=ERROR_RESPONSES)
def run_stop(task_id: str):
    with operation():
        return controller().stop_run(task_id)


@router.post("/queue/resume", response_model=AutomationResultResponse, responses=ERROR_RESPONSES)
def resume_queue_task(request: AutomationResumeRequest):
    with operation():
        return controller().resume_queue_task(request.task_id, request.expected_revision, request.mode, request.auto_start)
