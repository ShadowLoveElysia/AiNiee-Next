"""API-owned automation triggers using the shared task owner and existing managers."""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import threading
import uuid

from ModuleFolders.Infrastructure.TaskConfig.ConfigProfileService import (
    ConfigConflictError, config_revision, config_transaction, load_effective_config, patch_effective_config,
)
from ModuleFolders.Infrastructure.SensitiveData import contains_sensitive_data, sanitize_sensitive_data
from ModuleFolders.Infrastructure.TaskContract import TaskSpec, select_task_contract_fields


class AutomationConflict(ValueError):
    pass


def _reject_external(value):
    if isinstance(value, dict):
        if str(value.get("execution_mode") or "").strip().lower().replace("-", "_") in {"external_agent", "external", "agent"}:
            raise ValueError("External-Agent tasks require the task-scoped approval endpoint")
        for child in value.values():
            _reject_external(child)
    elif isinstance(value, list):
        for child in value:
            _reject_external(child)


def _workflow(task):
    from ModuleFolders.Infrastructure.Automation.WorkflowRunner import AUTOMATION_TASK_METADATA_FIELDS, normalize_workflow_steps
    from ModuleFolders.Infrastructure.TaskContract import TASK_CONTRACT_INPUT_FIELDS
    _reject_external(task)
    if "workflow_file" in task:
        raise ValueError("Submit structured workflow_steps to the API instead of a workflow file")
    if contains_sensitive_data(task):
        raise ValueError("Use a profile for automation credentials")
    if set(task) - TASK_CONTRACT_INPUT_FIELDS - AUTOMATION_TASK_METADATA_FIELDS:
        raise ValueError("Unknown automation task fields")
    payload = select_task_contract_fields(task)
    steps = task.get("workflow_steps")
    if steps is not None and (not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps)):
        raise ValueError("workflow_steps must contain objects")
    queue_only = task.get("run_queue") or task.get("trigger_type") in {"queue_added", "queue_pending"}
    if queue_only or (steps and all(step.get("type") == "run_queue" for step in steps)):
        payload.update(task_type="queue", input_path="", execution_mode="default_api")
        payload.pop("workflow_steps", None)
        return TaskSpec.from_mapping(payload), [{"type": "run_queue"}]
    payload.setdefault("task_type", "translate")
    payload["execution_mode"] = "default_api"
    normalized = normalize_workflow_steps(steps, payload["task_type"], task.get("auto_start", True))
    payload["workflow_steps"] = normalized
    return TaskSpec.from_mapping(payload), normalized


def preview_workflow(task):
    from ModuleFolders.Infrastructure.Automation.WorkflowRunner import describe_workflow_steps
    spec, steps = _workflow(task)
    return {"task": spec.to_mapping(), "steps": steps, "description": describe_workflow_steps(steps)}


def _validated_section(section, value):
    from ModuleFolders.Infrastructure.Automation.SchedulerManager import ScheduledTask
    from ModuleFolders.Infrastructure.Automation.WatchManager import WatchRule
    from ModuleFolders.Infrastructure.Automation.OutputCollector import normalize_output_collection_config
    _reject_external(value)
    if contains_sensitive_data(value):
        raise ValueError("Automation configuration cannot contain credentials; use profiles")
    if section == "automation_output_collection":
        unknown = set(value) - {"enabled", "output_path", "collision_policy"}
        if unknown or value.get("collision_policy", "rename") not in {"rename", "overwrite"}:
            raise ValueError("Invalid output collection configuration")
        return normalize_output_collection_config(value)
    item_key = "tasks" if section == "scheduler" else "rules"
    allowed = {item_key, "enabled"} | ({"scan_interval", "max_concurrent"} if section == "watch_mode" else set())
    if set(value) - allowed or not isinstance(value.get(item_key, []), list):
        raise ValueError("Invalid automation configuration")
    result = deepcopy(value)
    if "enabled" in result and type(result["enabled"]) is not bool:
        raise ValueError("enabled must be boolean")
    for key in ("scan_interval", "max_concurrent"):
        if key in result and (type(result[key]) is not int or not 1 <= result[key] <= 3600):
            raise ValueError(f"Invalid {key}")
    constructor = ScheduledTask.from_dict if section == "scheduler" else WatchRule.from_dict
    normalized, seen = [], set()
    for item in value.get(item_key, []):
        if not isinstance(item, dict) or not str(item.get("id") or "").strip():
            raise ValueError("Automation entries require a nonempty id")
        if item["id"] in seen:
            raise ValueError("Duplicate automation entry id")
        seen.add(item["id"])
        if section == "scheduler" and item.get("trigger_type", "scheduled") not in {"scheduled", "queue_added", "queue_pending"}:
            raise ValueError("Invalid scheduler trigger")
        if section == "watch_mode":
            if not str(item.get("watch_path") or "").strip():
                raise ValueError("watch_path is required")
            if type(item.get("debounce_seconds", 5)) is not int or item.get("debounce_seconds", 5) < 0:
                raise ValueError("Invalid debounce_seconds")
        if section == "watch_mode" and item.get("trigger_mode", "file") not in {"file", "folder"}:
            raise ValueError("Invalid watch trigger mode")
        if section == "watch_mode" and item.get("watch_target_type", "file") not in {"file", "folder", "both"}:
            raise ValueError("Invalid watch target type")
        for key in ("enabled", "auto_start", "move_to_done", "recursive", "settle_existing", "series_incremental", "run_queue"):
            if key in item and type(item[key]) is not bool:
                raise ValueError(f"{key} must be boolean")
        record = constructor(item)
        _reject_external(record.to_dict())
        normalized.append(record.to_dict())
    result[item_key] = normalized
    return result


def read_automation_config():
    with config_transaction():
        config = load_effective_config(create_missing=False)
        return {
            "revision": config_revision(config),
            "scheduler": sanitize_sensitive_data(config.get("scheduler", {})),
            "watch_mode": sanitize_sensitive_data(config.get("watch_mode", {})),
            "output_collection": sanitize_sensitive_data(config.get("automation_output_collection", {})),
        }


class AutomationController:
    def __init__(self, operations_factory=None, project_root=None):
        self._lock = threading.RLock()
        self._control_lock = threading.RLock()
        self._scheduler = None
        self._watch = None
        self._revision = None
        self._stop = threading.Event()
        self._owned = OrderedDict()
        self._runs_lock = threading.RLock()
        self._operations_factory = operations_factory
        self.project_root = Path(project_root or Path(__file__).resolve().parents[3])

    def operations(self):
        if self._operations_factory:
            return self._operations_factory()
        from ModuleFolders.Service.TaskQueue.QueueManager import QueueManager
        from .manager import TaskManager
        from .operations import TaskOperations
        return TaskOperations(TaskManager(), queue_is_running=lambda: QueueManager(read_only=True).is_running)

    def _load_managers(self):
        from ModuleFolders.Infrastructure.Automation.SchedulerManager import SchedulerManager, ScheduledTask
        from ModuleFolders.Infrastructure.Automation.WatchManager import WatchManager, WatchRule
        with config_transaction():
            config = load_effective_config(create_missing=False)
            revision = config_revision(config)
        if self._scheduler is not None and self._revision == revision:
            return
        if self._scheduler is not None and (self._scheduler.running or self._watch.running):
            return
        scheduler_config = _validated_section("scheduler", config.get("scheduler", {}))
        watch_config = _validated_section("watch_mode", config.get("watch_mode", {}))
        scheduler = SchedulerManager(execute_callback=self._scheduled_callback)
        watch = WatchManager(queue_callback=lambda task: self._enqueue(task, triggered=True), queue_start_callback=self._start_queue_if_idle)
        # Hydration is read-only: WatchManager.add_rule creates directories.
        for item in scheduler_config.get("tasks", []):
            record = ScheduledTask.from_dict(item)
            scheduler.tasks[record.id] = record
        for item in watch_config.get("rules", []):
            record = WatchRule.from_dict(item)
            watch.rules[record.id] = record
        watch.scan_interval = watch_config.get("scan_interval", 1)
        watch.max_concurrent = watch_config.get("max_concurrent", 2)
        watch.processed_file_path = str(self.project_root / "Resource/automation_progress/api_watch_processed.json")
        self._scheduler, self._watch, self._revision = scheduler, watch, revision

    def configuration_change(self, section, revision, change):
        if section not in {"scheduler", "watch_mode", "automation_output_collection"}:
            raise ValueError("Unknown automation configuration section")
        with self._control_lock, self._lock:
            if any(manager is not None and manager.running for manager in (self._scheduler, self._watch)):
                raise AutomationConflict("Stop API-owned automation triggers before editing their configuration")
            with config_transaction():
                current = load_effective_config(create_missing=False)
                if revision != config_revision(current):
                    raise ConfigConflictError()
                value = change(deepcopy(current.get(section, {})))
                patch_effective_config({section: _validated_section(section, value)}, expected_revision=revision)
            self._revision = None
            return read_automation_config()

    def mutate_entry(self, section, identifier, data, revision, *, delete=False, create=False):
        key = "tasks" if section == "scheduler" else "rules"
        identifier = identifier or uuid.uuid4().hex
        def change(current):
            entries = list(current.get(key, []))
            found = next((i for i, item in enumerate(entries) if item.get("id") == identifier), None)
            if create and found is not None:
                raise AutomationConflict("Automation entry already exists")
            if not create and found is None:
                raise KeyError(identifier)
            if delete:
                entries.pop(found)
            else:
                payload = {**(entries[found] if found is not None else {}), **data, "id": identifier}
                if found is None:
                    entries.append(payload)
                else:
                    entries[found] = payload
            return {**current, key: entries}
        return self.configuration_change(section, revision, change)

    def status(self):
        with self._lock:
            self._load_managers()
            scheduler, watch = self._scheduler, self._watch
        with self._runs_lock:
            ids = list(self._owned)
        return {"scheduler": scheduler.get_status(), "watch": watch.get_status(), "owned_task_ids": ids}

    def control(self, kind, start, *, confirmed=False, event_triggers=True, stop_tasks=True):
        with self._control_lock:
            return self._control(kind, start, confirmed=confirmed, event_triggers=event_triggers, stop_tasks=stop_tasks)

    def _control(self, kind, start, *, confirmed=False, event_triggers=True, stop_tasks=True):
        if start and not confirmed:
            raise AutomationConflict("Confirm starting automatic task triggers")
        with self._lock:
            self._load_managers()
            manager = self._scheduler if kind == "scheduler" else self._watch
            if start:
                config = read_automation_config()
                if config["revision"] != self._revision and not manager.running:
                    raise AutomationConflict("Stop automatic triggers before loading the changed configuration")
                _validated_section("scheduler" if kind == "scheduler" else "watch_mode", config["scheduler" if kind == "scheduler" else "watch_mode"])
                if kind == "watch":
                    for rule in manager.rules.values():
                        if not Path(rule.watch_path).is_dir():
                            raise ValueError("Watch directories must exist before starting")
                    Path(manager.processed_file_path).parent.mkdir(parents=True, exist_ok=True)
                self._stop.clear()
                if kind == "scheduler":
                    manager.set_event_triggers_active(event_triggers)
        if start:
            owner = self.operations().manager
            with owner._lock:
                if getattr(owner, "_accepting_tasks", True) is False:
                    raise AutomationConflict("The API owner is shutting down")
                manager.start()
        if not start:
            manager.stop()
            if manager._thread and manager._thread.is_alive():
                raise AutomationConflict("Automation trigger is still stopping")
            if stop_tasks:
                self.stop_owned_tasks()
        return self.status()

    def start_workflow(self, task, *, trigger=None):
        from .configuration import CallerContext
        spec, _ = _workflow(task)
        operations = self.operations()
        with operations.manager._lock:
            if trigger is not None and (self._stop.is_set() or not trigger.running):
                raise AutomationConflict("Automation trigger has stopped")
            result = operations.start(spec, caller=CallerContext("web"))
            with self._runs_lock:
                self._owned[result["task_id"]] = deepcopy(result)
                while len(self._owned) > 256:
                    self._owned.popitem(last=False)
            observer = threading.Thread(target=self._remember_terminal, args=(result["task_id"],), daemon=True)
            observer.start()
        return result

    def _remember_terminal(self, task_id):
        import time
        from .operations import TaskOperationError
        while True:
            try:
                state = self.run_status(task_id)
            except (KeyError, TaskOperationError):
                return
            if not state.get("running"):
                return
            time.sleep(.2)

    def _scheduled_callback(self, task):
        if self._stop.is_set():
            raise AutomationConflict("Automation owner is stopping")
        result = self.start_workflow(task, trigger=self._scheduler)
        task_id = result["task_id"]
        while True:
            state = self.run_status(task_id)
            if not state["running"]:
                if state["status"] not in {"completed", "enqueued"}:
                    raise AutomationConflict("Scheduled workflow did not complete")
                return True
            if self._stop.wait(.2):
                self.stop_run(task_id)
                raise AutomationConflict("Scheduled workflow stopped")

    def trigger(self, identifier):
        with self._lock:
            self._load_managers()
            task = self._scheduler.get_task(identifier)
            if task is None:
                raise KeyError(identifier)
            payload = select_task_contract_fields(task.to_dict())
            payload.update(workflow_steps=deepcopy(task.workflow_steps), run_queue=task.run_queue, trigger_type=task.trigger_type)
        return self.start_workflow(payload)

    def run_status(self, task_id):
        with self._runs_lock:
            if task_id not in self._owned:
                raise KeyError(task_id)
        operations = self.operations()
        with operations.manager._lock:
            if task_id == operations.manager.task_id:
                result = operations.status(task_id)
                with self._runs_lock:
                    self._owned[task_id] = deepcopy(result)
                return sanitize_sensitive_data(result)
        with self._runs_lock:
            result = deepcopy(self._owned[task_id])
        if result.get("running"):
            result.update(status="unknown", running=False, message="The task owner now tracks a different task")
        return sanitize_sensitive_data(result)

    def stop_run(self, task_id):
        with self._runs_lock:
            if task_id not in self._owned:
                raise KeyError(task_id)
        operations = self.operations()
        if operations.manager.task_id != task_id:
            raise AutomationConflict("This run is no longer owned by the active task manager")
        return operations.stop(task_id)

    def stop_owned_tasks(self):
        operations = self.operations()
        with operations.manager._lock:
            task_id = operations.manager.task_id
            with self._runs_lock:
                owned = task_id in self._owned
            if owned:
                operations.stop(task_id)

    def shutdown(self, *, stop_tasks=True):
        with self._control_lock:
            self._stop.set()
            with self._lock:
                managers = (self._scheduler, self._watch)
            for manager in managers:
                if manager is not None:
                    manager.stop()
                    if manager._thread and manager._thread.is_alive():
                        return False
            if stop_tasks:
                self.stop_owned_tasks()
            return True

    def _enqueue(self, task, *, triggered=False):
        from ModuleFolders.Service.TaskQueue.QueueManager import QueueManager, QueueTaskItem
        _reject_external(task)
        if triggered and self._stop.is_set():
            raise AutomationConflict("Automation owner is stopping")
        if contains_sensitive_data(task):
            raise ValueError("Use profiles for automation credentials")
        payload = select_task_contract_fields(task)
        fields = TaskSpec.from_mapping(payload).to_queue_fields()
        fields.pop("workflow_steps", None)
        item = QueueTaskItem(**fields, workflow_steps=task.get("workflow_steps") or [],
            source="watch", rule_id=task.get("rule_id"), trigger_file_path=task.get("trigger_file_path"),
            trigger_file_name=task.get("trigger_file_name"), trigger_detected_at=task.get("trigger_detected_at"),
            series_incremental=task.get("series_incremental", False), series_key=task.get("series_key"),
            series_volume=task.get("series_volume"), extra={key: task[key] for key in (
                "folder_batch_id", "folder_batch_index", "folder_batch_total", "series_initial_volume",
                "series_batch_volumes", "series_container_path", "series_missing_volumes", "defer_auto_start",
            ) if key in task})
        queue = QueueManager(read_only=True)
        with queue.state_lock:
            if not queue.is_running and Path(queue.queue_file).is_file():
                if not queue.hot_reload_queue(quiet=True, preserve_local_locks=False):
                    raise AutomationConflict("Queue could not be refreshed")
            if not queue.add_task(item):
                raise AutomationConflict("Could not enqueue the detected file")
        if task.get("auto_start", True) and not task.get("defer_auto_start"):
            self._start_queue_if_idle(triggered=triggered)
        return item.task_id

    def _start_queue_if_idle(self, *, triggered=True):
        from .operations import TaskOperationError
        if triggered and self._stop.is_set():
            return
        try:
            self.start_workflow({"task_type": "queue", "run_queue": True})
        except TaskOperationError as exc:
            if exc.code not in {"TASK_CONFLICT", "QUEUE_CONFLICT"}:
                raise

    def scan(self, limit=30, include_unmatched=True):
        from ModuleFolders.Service.TaskQueue.QueueManager import QueueManager
        with self._lock:
            self._load_managers()
            watch = self._watch
        QueueManager(read_only=True)
        return watch.get_file_status_snapshot(limit_per_rule=limit, include_unmatched=include_unmatched)

    def logs(self, limit=50):
        with self._lock:
            self._load_managers()
            return sanitize_sensitive_data({"scheduler": self._scheduler.get_logs(limit), "watch": self._watch.get_logs(limit)})

    def entries(self, kind):
        with self._lock:
            self._load_managers()
            manager = self._scheduler if kind == "scheduler" else self._watch
        with manager._lock:
            records = manager.get_all_tasks() if kind == "scheduler" else manager.get_all_rules()
            result = []
            for item in records:
                record = item.to_dict()
                fields = ("last_run", "next_run", "run_count", "last_status", "pending_event", "pending_event_count") if kind == "scheduler" else ("files_processed", "last_activity")
                for field in fields:
                    value = getattr(item, field)
                    record[field] = value.isoformat() if isinstance(value, datetime) else value
                result.append(record)
            return result

    def clear_history(self):
        with self._lock:
            self._load_managers()
            if self._watch.running:
                raise AutomationConflict("Stop the watch manager before clearing history")
            Path(self._watch.processed_file_path).parent.mkdir(parents=True, exist_ok=True)
            self._watch.clear_processed_history()
            self._watch._save_processed_files()
        return {"success": True}

    def requeue(self, rule_id, file_path, steps=None, auto_start=False):
        with self._lock:
            self._load_managers()
            rule = self._watch.get_rule(rule_id)
            if rule is None:
                raise KeyError(rule_id)
            path = Path(file_path).resolve()
            root = Path(rule.watch_path).resolve()
            if not path.is_relative_to(root) or not path.is_file() or not rule.matches_pattern(path.name):
                raise ValueError("File must be a matching file inside the watch rule directory")
            task = {**select_task_contract_fields(rule.extra), "task_type": rule.task_type,
                    "input_path": str(path), "output_path": rule.output_path or self._watch._generate_output_path(str(path)),
                    "profile": rule.profile, "rules_profile": rule.rules_profile or None,
                    "workflow_steps": steps if steps is not None else rule.workflow_steps,
                    "auto_start": auto_start, "rule_id": rule.id, "trigger_file_path": str(path),
                    "trigger_file_name": path.name, "trigger_detected_at": datetime.now().isoformat()}
        task_id = self._enqueue(task)
        from ModuleFolders.Infrastructure.Automation.WorkflowRunner import describe_workflow_steps
        self._watch.requeue_file(str(path), rule_id, describe_workflow_steps(task["workflow_steps"]))
        return {"success": True, "task_id": task_id}

    def resume_queue_task(self, task_id, revision, mode, auto_start=False):
        from ModuleFolders.Service.TaskQueue.QueueManager import QueueManager
        queue = QueueManager(read_only=True)
        with queue.state_lock:
            if not queue.is_running and Path(queue.queue_file).is_file():
                if not queue.hot_reload_queue(quiet=True, preserve_local_locks=False):
                    raise AutomationConflict("Queue could not be refreshed")
            if queue.revision != revision:
                raise AutomationConflict("Queue changed; reload before resuming")
            index = queue.resolve_index(task_id)
            if index < 0:
                raise KeyError(task_id)
            task = queue.tasks[index]
            method = queue.continue_partial_task if mode == "partial" else queue.resume_stopped_task
            if not method(task_id=task.task_id):
                raise AutomationConflict("The queue task cannot be resumed in this state")
        if auto_start:
            self._start_queue_if_idle(triggered=False)
        return {"success": True, "task_id": task_id}

    def runs(self, limit=50):
        from ModuleFolders.Infrastructure.Automation.AutomationProgress import read_progress_file
        with self._runs_lock:
            ids = list(self._owned)[-limit:]
        records = [self.run_status(task_id) for task_id in reversed(ids)]
        directory = self.project_root / "Resource/automation_progress"
        if directory.is_dir():
            paths = sorted(directory.glob("*.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)
            for path in paths[:limit]:
                if path.is_symlink():
                    continue
                record = sanitize_sensitive_data(read_progress_file(str(path)))
                record.pop("_path", None)
                record["owned"] = False
                records.append(record)
        return records[:limit]


_controller = None
_controller_lock = threading.Lock()


def get_automation_controller():
    global _controller
    with _controller_lock:
        if _controller is None:
            _controller = AutomationController()
            from .activities import register_activity
            register_activity("automation-triggers", lambda: False, shutdown_automation)
        return _controller


def shutdown_automation(*, stop_tasks=True):
    return True if _controller is None else _controller.shutdown(stop_tasks=stop_tasks)
