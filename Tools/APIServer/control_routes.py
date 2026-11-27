"""Public command submission and private worker delivery share task identity."""
from fastapi import APIRouter, HTTPException
from .control_contracts import ControlRequest, ControlResponse, WorkerControlRequest
from .responses import ERROR_RESPONSES
from ModuleFolders.Service.TaskRuntime.controls import mailbox, ControlConflict
from ModuleFolders.Service.TaskRuntime.manager import TaskManager

router = APIRouter(prefix="/api", tags=["task"])


@router.post("/task/control", response_model=ControlResponse, responses=ERROR_RESPONSES)
def submit_control(request: ControlRequest):
    manager = TaskManager()
    with manager._lock:
        if request.task_id != manager.task_id:
            raise HTTPException(404, "Task not found")
        if manager.process is None or manager.status != "running":
            raise HTTPException(409, "Task cannot accept interactive controls")
        try:
            return mailbox.submit(request.task_id, request.action)
        except ControlConflict as exc:
            raise HTTPException(409, str(exc)) from exc


@router.get("/task/control/{command_id}", response_model=ControlResponse, responses=ERROR_RESPONSES)
def control_status(command_id: str):
    try:
        return mailbox.status(command_id)
    except KeyError as exc:
        raise HTTPException(404, "Control command not found") from exc


@router.post("/internal/task-control/{operation}", response_model=dict, responses=ERROR_RESPONSES)
def worker_control(operation: str, request: WorkerControlRequest):
    manager = TaskManager()
    with manager._lock:
        if request.task_id != manager.task_id or manager.process is None:
            raise HTTPException(409, "Worker no longer owns the task")
        try:
            if operation == "ready":
                mailbox.ready(request.task_id, request.context_id)
            elif operation == "poll":
                return {"command": mailbox.poll(request.task_id, request.context_id)}
            elif operation == "ack":
                receipt = mailbox.acknowledge(request.task_id, request.context_id, request.command_id, request.state)
                manager.push_stats({"control_state": receipt["state"]})
                return receipt
            elif operation == "close":
                mailbox.close(request.task_id, request.context_id)
            else:
                raise HTTPException(404, "Unknown worker control operation")
        except ControlConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"status": "ok"}
