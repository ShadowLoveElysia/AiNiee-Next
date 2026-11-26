import logging
import os
import subprocess
import sys
import threading
import time
from typing import Dict

import rapidjson as json

from ModuleFolders.Infrastructure.Automation.AutomationProgress import (
    PROGRESS_FILE_ENV,
    RUN_ID_ENV,
    TASK_SECRETS_ENV,
    TERMINAL_STATUSES,
    AutomationProgressReporter,
    get_progress_dir,
    new_run_id,
    progress_file_for_run,
    read_progress_file,
    scrub_legacy_task_credentials,
    task_config_file_for_run,
)
from ModuleFolders.Infrastructure.SensitiveData import split_sensitive_data
from ModuleFolders.Service.TaskRuntime.processes import OwnedProcessTree, launch_options, mark_worker_environment
from ModuleFolders.Infrastructure.Automation.WorkflowRunner import describe_workflow_steps, WorkflowRunner


class AutomationProcessRunner:
    _lock = threading.RLock()
    _processes: Dict[str, subprocess.Popen] = {}
    _progress_files: Dict[str, str] = {}
    _task_config_files: Dict[str, str] = {}
    _process_trees: Dict[str, OwnedProcessTree] = {}

    @classmethod
    def start(cls, task_config: dict, project_root: str = None) -> dict:
        project_root = project_root or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        scrub_legacy_task_credentials(get_progress_dir(project_root))
        run_id = new_run_id(task_config.get("rule_id", ""), task_config.get("input_path", ""))
        progress_file = progress_file_for_run(run_id, project_root)
        task_config_path = task_config_file_for_run(run_id, project_root)

        runtime_config = dict(task_config)
        runtime_config["automation_run_id"] = run_id
        runtime_config["automation_progress_file"] = progress_file
        runtime_config["workflow_description"] = describe_workflow_steps(runtime_config.get("workflow_steps") or [])
        if not runtime_config.get("runtime_snapshot") and (runtime_config.get("runtime_overrides") or runtime_config.get("step_overrides") or any(s.get("runtime_overrides") for s in runtime_config.get("workflow_steps", []))):
            from ModuleFolders.Infrastructure.TaskConfig.RuntimeSnapshot import snapshot_for_task
            runtime_config["runtime_snapshot"] = snapshot_for_task(runtime_config)
        prepared_config, secret_overlay = split_sensitive_data(runtime_config)

        with open(task_config_path, "w", encoding="utf-8") as file:
            json.dump(prepared_config, file, ensure_ascii=False, indent=2)

        reporter = AutomationProgressReporter(
            progress_file,
            run_id,
            initial={
                "status": "queued",
                "phase": "queued",
                "message": "Automation task queued",
                "input_path": prepared_config.get("input_path", ""),
                "file_name": (
                    prepared_config.get("trigger_file_name")
                    or os.path.basename(os.path.normpath(prepared_config.get("trigger_file_path") or ""))
                    or os.path.basename(os.path.normpath(prepared_config.get("input_path", "")))
                ),
                "rule_id": prepared_config.get("rule_id", ""),
                "workflow": prepared_config.get("workflow_description", ""),
            },
        )

        env = os.environ.copy()
        env.pop(TASK_SECRETS_ENV, None)
        env[PROGRESS_FILE_ENV] = progress_file
        env[RUN_ID_ENV] = run_id
        if secret_overlay:
            # Each Popen receives its own environment copy, so concurrent workflow
            # credentials cannot overwrite one another or reach the task file.
            env[TASK_SECRETS_ENV] = json.dumps(secret_overlay, ensure_ascii=False)

        log_path = os.path.join(os.path.dirname(progress_file), f"{run_id}.worker.log")
        cmd = [
            sys.executable,
            "-m",
            "ModuleFolders.Infrastructure.Automation.AutomationWorker",
            "--task-config",
            task_config_path,
        ]
        marker = mark_worker_environment(env, nested=True)
        launched_at = time.time()
        with open(log_path, "a", encoding="utf-8") as log_file:
            process = subprocess.Popen(
                cmd, cwd=project_root, env=env, stdout=log_file,
                stderr=subprocess.STDOUT, text=True, **launch_options(),
            )

        with cls._lock:
            cls._processes[run_id] = process
            cls._process_trees[run_id] = OwnedProcessTree(process, owner_id=marker, launched_at=launched_at)
            cls._progress_files[run_id] = progress_file
            cls._task_config_files[run_id] = task_config_path

        try:
            reporter.update(status="running", phase="worker", pid=process.pid, message="Automation worker started")
        finally:
            threading.Thread(target=cls._watch_process, args=(run_id, process), daemon=True).start()

        return {
            "run_id": run_id,
            "progress_file": progress_file,
            "task_config_file": task_config_path,
            "pid": process.pid,
        }

    @classmethod
    def _watch_process(cls, run_id: str, process: subprocess.Popen):
        process.wait()
        with cls._lock:
            if cls._processes.get(run_id) is process and not cls._finish_run_locked(run_id):
                logging.getLogger(__name__).warning("Automation cleanup is pending for %s; ownership retained.", run_id)

    @classmethod
    def _finish_run_locked(cls, run_id: str, message: str | None = None) -> bool:
        process = cls._processes.get(run_id)
        if process is None or not cls._process_trees[run_id].terminate(timeout=2):
            return False

        progress_file = cls._progress_files[run_id]
        state = read_progress_file(progress_file)
        if message is not None or state.get("status") not in TERMINAL_STATUSES:
            reporter = AutomationProgressReporter(
                progress_file,
                run_id,
                initial=cls._state_for_resume(state),
                emit_initial=False,
            )
            if message is not None:
                reporter.finish("interrupted", message)
            elif process.returncode == 0:
                task_config = cls._read_task_config_for_run(run_id, progress_file)
                if WorkflowRunner.is_enqueue_only(task_config):
                    reporter.finish("enqueued", "Queued for task processing")
                else:
                    reporter.finish("completed", "Automation worker completed")
            else:
                reporter.finish("interrupted", f"Automation worker exited with code {process.returncode}")

        cls._processes.pop(run_id)
        cls._progress_files.pop(run_id)
        cls._task_config_files.pop(run_id)
        cls._process_trees.pop(run_id)
        return True

    @classmethod
    def _read_task_config_for_run(cls, run_id: str, progress_file: str) -> dict:
        with cls._lock:
            task_config_path = cls._task_config_files.get(run_id)
        if not task_config_path:
            task_config_path = os.path.splitext(progress_file)[0] + ".task.json"
        try:
            with open(task_config_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _state_for_resume(state: dict) -> dict:
        return {
            key: value
            for key, value in (state or {}).items()
            if not str(key).startswith("_") and key != "logs"
        }

    @classmethod
    def get_process(cls, run_id: str):
        with cls._lock:
            return cls._processes.get(run_id)

    @classmethod
    def snapshot_processes(cls) -> dict:
        with cls._lock:
            return dict(cls._processes)

    @classmethod
    def terminate(cls, run_id: str, message: str = "Automation task interrupted") -> bool:
        with cls._lock:
            return cls._finish_run_locked(run_id, message)

    @classmethod
    def terminate_all(cls, message: str = "Automation status view exited; background tasks interrupted") -> int:
        with cls._lock:
            run_ids = list(cls._processes.keys())
        count = 0
        for run_id in run_ids:
            if cls.terminate(run_id, message):
                count += 1
        return count
