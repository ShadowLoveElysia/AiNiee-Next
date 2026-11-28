"""Own the local task worker and its lifecycle independently of UI transports."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from ModuleFolders.Infrastructure.ApiSecurity import INTERNAL_AUTH_ENV
from ModuleFolders.Infrastructure.TaskContract import (
    TASK_API_KEY_ENV, TaskContractError, TaskSpec, build_cli_args,
)
from .events import SequencedBuffer
from .processes import OwnedProcessTree, launch_options, mark_worker_environment
from ModuleFolders.Service.TaskQueue.QueueOutcome import QUEUE_RESULT_PREFIX, validate_queue_result

WEB_TASK_API_KEY_ENV = TASK_API_KEY_ENV
WEB_TASK_ID_ENV = "AINIEE_WEB_TASK_ID"

# External-Agent tasks deliberately do not own a child process.  Keep their
# lifecycle in the same task contract so Web callers can wait, resume and stop
# them without accidentally falling back to the default API worker.
TASK_ACTIVE_STATUSES = frozenset({"starting", "running", "stopping", "waiting_for_agent", "agent_disconnected", "committed"})
TASK_EXTERNAL_STATUSES = frozenset({"waiting_for_agent", "running", "agent_disconnected", "committed", "completed", "failed", "stopped"})

# External-Agent updates come from a separate connection and can arrive late.
# Keep terminal tasks immutable and reject stale updates instead of allowing a
# disconnected or old Agent to resurrect a finished Web task.
EXTERNAL_AGENT_STATUS_TRANSITIONS = {
    "waiting_for_agent": frozenset({"running", "agent_disconnected", "stopped", "failed"}),
    "running": frozenset({"waiting_for_agent", "agent_disconnected", "committed", "completed", "failed", "stopped"}),
    "agent_disconnected": frozenset({"waiting_for_agent", "running", "committed", "stopped", "failed"}),
    "committed": frozenset({"completed", "failed", "stopped"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "stopped": frozenset(),
}


def resolve_task_worker_python(project_root: str, platform_name: str | None = None) -> str:
    """Use the launcher's project environment, never the adapter's ambient Python."""
    current_platform = str(platform_name or sys.platform).lower()
    windows = current_platform == "win32"
    root = Path(project_root).absolute()
    environment = os.environ.get("UV_PROJECT_ENVIRONMENT")
    if environment:
        environments = [root / environment]
    elif current_platform in {"linux", "darwin"}:
        environments = [root / "tmp" / "environments" / f"{current_platform}-{platform.machine()}", root / ".venv"]
    else:
        environments = [root / (".venv-win" if windows else ".venv")]
    relative_python = Path("Scripts/python.exe" if windows else "bin/python")
    for candidate in environments:
        executable = candidate / relative_python
        if executable.is_file() and os.access(executable, os.X_OK):
            return str(executable)
    raise FileNotFoundError("Task worker Python environment not found: " + ", ".join(str(item / relative_python) for item in environments))


class TaskManager:
    """A singleton class to manage the CLI task execution state."""
    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        with self._lock:
            if not hasattr(self, 'initialized'):  # Prevent re-initialization
                self.process: Optional[subprocess.Popen] = None
                self.process_tree: OwnedProcessTree | None = None
                self._accepting_tasks = True
                self._output_drained = threading.Condition(self._lock)
                self._output_pending = False
                self._stop_waiting = False
                self.status: str = "idle"  # idle, running, stopping, waiting_for_agent, agent_disconnected, completed, error
                # ``status`` is retained for the existing Web UI.  The lifecycle
                # fields below are the stable cross-entry task contract consumed
                # by Web, CLI, and Skills callers.
                self.lifecycle_status: str = "idle"
                self.task_id: Optional[str] = None
                self.created_at: Optional[str] = None
                self.started_at: Optional[str] = None
                self.finished_at: Optional[str] = None
                self.exit_code: Optional[int] = None
                self.task_type: str | None = None
                self.logs = SequencedBuffer(500, lock=self._lock)
                self.chart_data = SequencedBuffer(60, lock=self._lock)
                self.stats: Dict[str, Any] = self._get_initial_stats()
                self.project_root = str(Path(__file__).resolve().parents[3])
                self._load_config: Callable[[], dict] | None = None
                self.internal_auth_token = ""
                self.initialized = True
                self.current_source = ""      # 当前批次原文
                self.current_translation = "" # 当前批次译文
                self.api_url = "http://127.0.0.1" # 默认地址（启动后会带端口）

                self.internal_api_url = "http://127.0.0.1" # Worker callback URL（启动后会带端口）
                self.comparison_seq = 0
                self._comparison_cleared_at: int | None = None
                self.comparison_updated_at = 0.0
                self.external_agent_cache_path: Optional[str] = None
                self.external_agent_input_path: Optional[str] = None
                self.external_agent_output_path: Optional[str] = None

                # Use a separate thread to monitor the process output
                self.monitor_thread: Optional[threading.Thread] = None

    def configure(
        self,
        *,
        project_root: str | None = None,
        load_config: Callable[[], dict] | None = None,
        internal_auth_token: str | None = None,
        internal_api_url: str | None = None,
    ) -> None:
        """Bind host dependencies without importing a transport or starting it."""
        with self._lock:
            root = os.path.abspath(project_root) if project_root is not None else self.project_root
            if self._is_task_active_locked() and root != self.project_root:
                raise RuntimeError("Cannot replace the task workspace while a task is active.")
            self.project_root = root
            if load_config is not None:
                self._load_config = load_config
            if internal_auth_token is not None:
                self.internal_auth_token = internal_auth_token
            if internal_api_url is not None:
                self.internal_api_url = internal_api_url

    def _load_task_config(self, spec: TaskSpec) -> dict:
        if self._load_config is not None and not (spec.profile or spec.rules_profile):
            return self._load_config()
        from ModuleFolders.Infrastructure.TaskConfig.ConfigProfileService import load_effective_config

        return load_effective_config(
            active_profile_name=spec.profile,
            active_rules_profile_name=spec.rules_profile,
            create_missing=False,
        )

    @staticmethod
    def _timestamp() -> str:
        return datetime.now().astimezone().isoformat(timespec="milliseconds")

    def _canonical_status(self) -> str:
        """Return the stable lifecycle status without breaking legacy stats."""
        return self.lifecycle_status

    def _is_task_active_locked(self) -> bool:
        # The child process is the source of truth for occupancy.  Lifecycle
        # fields describe the last known state and may outlive a cleaned-up
        # process (for example after a failed monitor thread or host restart).
        # Treating a stale ``lifecycle_status=running`` as active would block
        # every later task even though no worker is owned by this manager.
        if self.process is None:
            # Waiting external-Agent tasks intentionally have no child
            # process, but still reserve the single Web task slot.
            return (
                self.stats.get("execution_mode") == "external_agent"
                and self.lifecycle_status in {"running", "waiting_for_agent", "agent_disconnected", "committed"}
            )
        # Keep the slot reserved until the monitor finalizes a process that
        # has already exited.  Otherwise a fast worker can be replaced by a
        # new task while its monitor thread is still writing the terminal
        # status, and that thread will then lose ownership of its record.
        if self.status in {"running", "stopping", "waiting_for_agent", "agent_disconnected", "committed"}:
            return True
        try:
            return self.process.poll() is None
        except (AttributeError, OSError):
            # A minimal/fake process may not expose ``poll``.  In that case
            # regard an owned process as active unless it has already reached
            # a terminal legacy status.
            return self.status in {"starting", "running", "stopping", "waiting_for_agent", "agent_disconnected", "committed"}

    def task_conflict_detail(self) -> str | None:
        """Return the protocol error for a concurrent start, if one exists."""
        with self._lock:
            if not self._accepting_tasks:
                return "The API owner is shutting down."
            from .activities import auxiliary_active
            if auxiliary_active():
                return "Another application operation is active."
            if not self._is_task_active_locked():
                return None
            if self.status == "stopping" or self.lifecycle_status == "stopping":
                return "Task process is still stopping; retry after it exits."
            return "A task is already running."

    def set_task_admission(self, enabled: bool) -> bool:
        """Gate starts under the same lock as worker creation; return whether the slot is idle."""
        with self._lock:
            self._accepting_tasks = enabled
            return not self._is_task_active_locked()

    def _task_contract(self) -> Dict[str, Any]:
        running = self.lifecycle_status in TASK_ACTIVE_STATUSES
        return {
            "task_id": self.task_id,
            "status": self._canonical_status(),
            "running": running,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exit_code": self.exit_code,
            "external_agent_cache_path": self.external_agent_cache_path,
            "external_agent_input_path": self.external_agent_input_path,
            "external_agent_output_path": self.external_agent_output_path,
        }

    def _get_initial_stats(self) -> Dict[str, Any]:
        return {
            "rpm": 0, "tpm": 0, "totalProgress": 0, "completedProgress": 0,
            "totalTokens": 0, "elapsedTime": 0, "status": "idle",
            "currentFile": "N/A", "successRate": 0, "errorRate": 0
        }

    def push_log(self, message: str, type: str = "info"):
        """Directly push a log message from the host process."""
        self.logs.append({"timestamp": time.time(), "message": message, "type": type})

    def push_comparison(self, source: str, translation: str):
        """Update the side-by-side comparison data from the host process."""
        with self._lock:
            self.current_source = source
            self.current_translation = translation
            self.comparison_seq += 1
            self.comparison_updated_at = time.time()

    def reset_comparison(self):
        """Clear comparison state for a brand-new task run."""
        with self._lock:
            self.current_source = ""
            self.current_translation = ""
            self._comparison_cleared_at = self.comparison_seq
            self.comparison_seq += 1
            self.comparison_updated_at = 0.0

    def push_stats(self, stats: Dict[str, Any]):
        """Directly push stats from the host process."""
        with self._lock:
            self.stats.update(stats)
            self.chart_data.append({
                "time": time.strftime('%H:%M:%S'),
                "rpm": self.stats.get("rpm", 0),
                "tpm": self.stats.get("tpm", 0)
            })

    def snapshot_status(self, log_cursor: int = 0, chart_cursor: int = 0, comparison_cursor: int = 0) -> Dict[str, Any]:
        """Return an atomic snapshot; reset flags replace expired client history."""
        with self._lock:
            logs, log_seq, logs_reset = self.logs.snapshot(log_cursor)
            chart, chart_seq, chart_reset = self.chart_data.snapshot(chart_cursor)
            comparison_reset = (
                comparison_cursor < 0
                or comparison_cursor > self.comparison_seq
                or (self._comparison_cleared_at is not None and comparison_cursor <= self._comparison_cleared_at)
            )
            comparison_changed = comparison_reset or self.comparison_seq > comparison_cursor
            return {
                "task_type": self.task_type,
                "stats": copy.deepcopy(self.stats),
                "logs": logs,
                "chart_data": chart,
                "comparison": {
                    "source": self.current_source,
                    "translation": self.current_translation
                } if comparison_changed else None,
                "cursors": {
                    "logs": log_seq,
                    "chart": chart_seq,
                    "comparison": self.comparison_seq,
                },
                "cursors_reset": {
                    "logs": logs_reset,
                    "chart": chart_reset,
                    "comparison": comparison_reset,
                },
                "comparison_updated_at": self.comparison_updated_at,
                **self._task_contract(),
            }

    def _log_and_parse(self, stream):
        """Read from a stream, log the output, and parse for stats."""
        # The stream provides correctly decoded strings because of the `encoding` setting in Popen
        for line in iter(stream.readline, ''):
            line = line.strip()
            if not line:
                continue

            # Check for our special stats line
            if line.startswith("[STATS]"):
                try:
                    # Example: [STATS] RPM: 0.00 | TPM: 0.00k | Progress: 0/1435 | Tokens: 0
                    parts = line.split('|')
                    rpm_part = parts[0].split(':')[1].strip()
                    tpm_part = parts[1].split(':')[1].strip().replace('k', '')
                    progress_part = parts[2].split(':')[1].strip()
                    tokens_part = parts[3].split(':')[1].strip()

                    completed, total = map(int, progress_part.split('/'))

                    with self._lock:
                        self.stats["rpm"] = float(rpm_part)
                        self.stats["tpm"] = float(tpm_part) # This is already in k
                        self.stats["completedProgress"] = completed
                        self.stats["totalProgress"] = total
                        self.stats["totalTokens"] = int(tokens_part)
                except (IndexError, ValueError) as e:
                    # Log parsing error if the format is unexpected, but don't crash
                    self.push_log(f"[PARSER_ERROR] Could not parse stats line: {line}. Error: {e}", "warning")
            else:
                # It's a regular log line
                self.push_log(line)


    def start_task(self, payload: TaskSpec | Dict[str, Any]) -> str | None:
        """Start a worker and return the stable task ID, or ``None`` on failure."""
        with self._lock:
            if self.task_conflict_detail() is not None:
                return None

            self.task_id = str(uuid.uuid4())
            self.created_at = self._timestamp()
            self.started_at = None
            self.finished_at = None
            self.exit_code = None
            self.process_tree = None
            self.task_type = None
            self.lifecycle_status = "starting"

            self.status = "running"
            self.logs.clear()
            self.chart_data.clear()
            self.reset_comparison()
            self.stats = self._get_initial_stats()
            self.stats["status"] = "running"
            self.stats["task_id"] = self.task_id
            self.external_agent_cache_path = None
            self.external_agent_input_path = None
            self.external_agent_output_path = None
            self.push_log("Task starting with resolved execution parameters...")

            try:
                spec = payload if isinstance(payload, TaskSpec) else TaskSpec.from_mapping(payload)
            except TaskContractError as exc:
                self.status = "error"
                self.lifecycle_status = "failed"
                self.stats["status"] = "error"
                self.push_log(f"Invalid task payload: {exc}", "error")
                self.finished_at = self._timestamp()
                return None

            self.task_type = spec.task_type

            if spec.execution_mode == "external_agent":
                self.external_agent_input_path = spec.input_path
                self.external_agent_cache_path = None
                try:
                    self.external_agent_output_path = self._external_agent_output_path(spec)
                    if spec.input_path and os.path.isfile(spec.input_path):
                        self._prepare_external_agent_cache(spec)
                    else:
                        self.stats["external_agent_bootstrap_status"] = "source_not_found"
                        self.push_log(
                            "External-Agent cache preparation was skipped because the source path is not a local file.",
                            "warning",
                        )
                except Exception as exc:
                    self.status = "error"
                    self.lifecycle_status = "failed"
                    self.stats["status"] = "error"
                    self.stats["execution_mode"] = "external_agent"
                    self.stats["external_agent_bootstrap_status"] = "failed"
                    self.push_log(f"External-Agent cache preparation failed: {exc}", "error")
                    self.finished_at = self._timestamp()
                    return self.task_id
                self.status = "waiting_for_agent"
                self.lifecycle_status = "waiting_for_agent"
                self.stats["status"] = "waiting_for_agent"
                self.stats["execution_mode"] = "external_agent"
                self.stats["external_agent_cache_path"] = self.external_agent_cache_path
                self.stats["external_agent_output_path"] = self.external_agent_output_path
                self.push_log("Task is waiting for an external Agent.", "system")
                return self.task_id

            try:
                worker_python = resolve_task_worker_python(self.project_root)
            except FileNotFoundError as exc:
                self.status = "error"
                self.lifecycle_status = "failed"
                self.stats["status"] = "error"
                self.push_log(str(exc), "error")
                self.finished_at = self._timestamp()
                return None

            cli_args = [
                worker_python,
                os.path.join(self.project_root, "ainiee_cli.py"),
                *build_cli_args(spec, non_interactive=True, web_mode=True),
            ]

            try:
                # 注入环境变量以便子进程知道 WebServer 的内部接口位置
                env = os.environ.copy()
                # Keep credentials out of argv, which is commonly visible in process listings.
                env.pop(WEB_TASK_API_KEY_ENV, None)
                if spec.api_key:
                    env[WEB_TASK_API_KEY_ENV] = spec.api_key
                if spec.runtime_overrides or spec.step_overrides or spec.workflow_steps:
                    from ModuleFolders.Infrastructure.TaskConfig.RuntimeSnapshot import RUNTIME_SNAPSHOT_ENV, write_worker_snapshot
                    env[RUNTIME_SNAPSHOT_ENV] = write_worker_snapshot(spec.to_mapping())
                if self.task_id:
                    env[WEB_TASK_ID_ENV] = self.task_id
                # 获取当前 WebServer 的运行地址
                env["AINIEE_INTERNAL_API_URL"] = self.internal_api_url
                env[INTERNAL_AUTH_ENV] = self.internal_auth_token
                # 强制子进程使用 UTF-8 编码输出，防止在 Windows 下产生编码冲突
                env["PYTHONIOENCODING"] = "utf-8"
                # 标记该进程为后端 Worker，与核心主进程（WebServer）区分
                env["AINIEE_BACKEND_WORKER"] = "1"
                owner_id = mark_worker_environment(env)
                launched_at = time.time()

                self.process = subprocess.Popen(
                    cli_args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    errors='replace', # 增加解码容错，防止非法字符导致线程崩溃
                    bufsize=1,
                    cwd=self.project_root,
                    env=env,
                    **launch_options(),
                )
                if isinstance(getattr(self.process, "pid", None), int):
                    self.process_tree = OwnedProcessTree(self.process, owner_id=owner_id, launched_at=launched_at)

                self.monitor_thread = threading.Thread(
                    target=self._process_monitor,
                    args=(self.process,),
                )

                self.started_at = self._timestamp()
                self.lifecycle_status = "running"
                self.monitor_thread.daemon = True
                self._output_pending = True
                self.monitor_thread.start()

                return self.task_id

            except Exception as e:
                self._output_pending = False
                failed_process = self.process
                if failed_process is not None:
                    try:
                        if self.process_tree is not None:
                            if not self.process_tree.terminate(timeout=2):
                                self.status = self.lifecycle_status = "stopping"
                                self.stats["status"] = "stopping"
                                self.push_log("Worker launch failed; owned processes are still being stopped.", "error")
                                return None
                        elif failed_process.poll() is None:
                            failed_process.kill()
                        failed_process.wait(timeout=2)
                    except (OSError, subprocess.TimeoutExpired, AttributeError):
                        self.status = self.lifecycle_status = self.stats["status"] = "stopping"
                        self.push_log("Worker launch failed; cleanup has not been confirmed.", "error")
                        return None
                    self.process = None
                    self.process_tree = None
                self.status = "error"
                self.lifecycle_status = "failed"
                self.stats["status"] = "error"
                self.push_log(f"Failed to start process: {e}", "error")
                self.finished_at = self._timestamp()
                return None

    def _external_agent_output_path(self, spec: TaskSpec) -> str:
        config = self._load_task_config(spec)
        configured = spec.output_path or config.get("label_output_path")
        if configured:
            return os.path.abspath(str(configured))
        source = os.path.abspath(str(spec.input_path or ""))
        parent = os.path.dirname(source)
        stem = os.path.splitext(os.path.basename(source))[0] or "AiNiee_Task"
        return os.path.join(parent, f"{stem}_AiNiee_Output")

    def _prepare_external_agent_cache(self, spec: TaskSpec) -> None:
        """Parse a new external-Agent input without making any API request."""
        from ModuleFolders.Domain.FileReader.FileReader import FileReader

        # Use a task-local manager so prewarming cannot replace a cache that
        # the Web UI has loaded for another operation.
        from ModuleFolders.Infrastructure.Cache.CacheManager import CacheManager
        cache_manager = CacheManager()
        config = self._load_task_config(spec)
        project_type = spec.project_type or config.get("translation_project", "AutoType")
        exclude_rules = config.get("label_input_exclude_rule", config.get("exclude_rule_str", "")) or ""
        # MCP/stdio callers must stay protocol-clean on Windows consoles whose
        # legacy code page cannot encode Rich progress glyphs.
        from ModuleFolders.Domain.FileReader import ReaderUtil
        previous_suppression = getattr(ReaderUtil, "_SUPPRESS_OUTPUT", False)
        ReaderUtil._SUPPRESS_OUTPUT = True
        try:
            project = FileReader().read_files(project_type, spec.input_path, exclude_rules)
        finally:
            ReaderUtil._SUPPRESS_OUTPUT = previous_suppression
        if not project or not getattr(project, "files", None):
            raise RuntimeError("no readable source items were found")
        output_path = self.external_agent_output_path or self._external_agent_output_path(spec)
        # Keep the mutable cache inside AiNiee's controlled project root even
        # when the requested final output directory is an external user path.
        # The final exporter may still write to ``output_path`` after commit.
        cache_output_path = os.path.join(
            self.project_root,
            "Resource",
            "automation_progress",
            "external_agent_tasks",
            str(self.task_id),
        )
        os.makedirs(cache_output_path, exist_ok=True)
        cache_manager.load_from_project(project)
        cache_manager.save_to_file_require_path = cache_output_path
        cache_manager.save_to_file()
        self.external_agent_output_path = output_path
        self.external_agent_cache_path = os.path.join(cache_output_path, "cache", "AinieeCacheData.json")
        self.stats["external_agent_bootstrap_status"] = "ready"
        self.stats["external_agent_total_items"] = cache_manager.get_item_count()
        self.push_log(
            f"External-Agent source parsed; cache ready with {cache_manager.get_item_count()} items.",
            "system",
        )

    def _read_process_output(self, process):
        if process and process.stdout:
            # Popen now handles the decoding, so we can iterate over strings directly.
            for line in iter(process.stdout.readline, ''):
                line = line.strip()
                if line:
                    with self._lock:
                        if self.process is not process:
                            break
                        self.push_log(line)

                        if self.task_type == "queue" and line.startswith(QUEUE_RESULT_PREFIX):
                            try:
                                result = validate_queue_result(json.loads(line[len(QUEUE_RESULT_PREFIX):]))
                            except (TypeError, ValueError):
                                result = None
                            if result is not None:
                                self.stats["queue_summary"] = result
                            else:
                                self.push_log("Queue worker emitted an invalid completion summary.", "warning")
                            continue

                        # 1. Parsing current file
                        if "File:" in line:
                            try: self.stats["currentFile"] = line.split("File:")[1].strip().split("|")[0].strip()
                            except: pass

                        # 2. Parsing [STATS] line (Robust Regex)
                        if "[STATS]" in line:
                            try:
                                # RPM
                                rpm_match = re.search(r"RPM:\s*([\d\.]+)", line)
                                if rpm_match: self.stats["rpm"] = float(rpm_match.group(1))

                                # TPM
                                tpm_match = re.search(r"TPM:\s*([\d\.]+k?)", line)
                                if tpm_match:
                                    tpm_val = tpm_match.group(1).replace('k', '')
                                    self.stats["tpm"] = float(tpm_val)

                                # Progress (Completed/Total)
                                prog_match = re.search(r"Progress:\s*(\d+)/(\d+)", line)
                                if prog_match:
                                    self.stats["completedProgress"] = int(prog_match.group(1))
                                    self.stats["totalProgress"] = int(prog_match.group(2))

                                # Tokens
                                tokens_match = re.search(r"Tokens:\s*(\d+)", line)
                                if tokens_match: self.stats["totalTokens"] = int(tokens_match.group(1))

                                # Success/Error Rate
                                s_rate_match = re.search(r"S-Rate:\s*([\d\.]+)%", line)
                                if s_rate_match: self.stats["successRate"] = float(s_rate_match.group(1))

                                e_rate_match = re.search(r"E-Rate:\s*([\d\.]+)%", line)
                                if e_rate_match: self.stats["errorRate"] = float(e_rate_match.group(1))

                                # Append to Chart Data
                                self.chart_data.append({
                                    "time": time.strftime('%H:%M:%S'),
                                    "rpm": self.stats["rpm"],
                                    "tpm": self.stats["tpm"]
                                })

                            except Exception as e:
                                # Non-fatal parsing error
                                pass


    def _process_monitor(self, process=None):
        """Track the owned process, even when a descendant keeps its stdout open."""
        process = process or self.process
        with self._lock:
            if self.process is not process:
                return
            self._output_pending = True
        output_failed = False

        def drain():
            nonlocal output_failed
            try:
                with process.stdout:
                    self._read_process_output(process)
            except Exception:
                output_failed = True

        reader = None
        if process and process.stdout:
            reader = threading.Thread(target=drain, daemon=True)
            reader.start()
        if process:
            process.wait()
        with self._lock:
            if self.process is not process:
                return
            cleaned = self.process_tree is None or self.process_tree.terminate(timeout=2)
            if not cleaned:
                self.status = self.lifecycle_status = "stopping"
                self.stats["status"] = "stopping"
                self.push_log("Worker exited but owned descendants are not confirmed stopped.", "error")
        if reader is not None:
            reader.join()

        with self._lock:
            if self.process is not process:
                return
            self._output_pending = False
            self._output_drained.notify_all()
            if output_failed:
                self.push_log("Worker output could not be fully read; its result is unconfirmed.", "error")
            if not cleaned or self._stop_waiting:
                return
            if self.status == "running":
                summary = self.stats.get("queue_summary") if self.task_type == "queue" else None
                if not output_failed and summary and summary["outcome"] == "stopped":
                    self.status = "idle"
                    self.lifecycle_status = "stopped"
                    self.stats["status"] = "idle"
                elif not output_failed and process and process.returncode == 0 and (self.task_type != "queue" or summary and summary["outcome"] == "completed"):
                    self.status = "completed"
                    self.lifecycle_status = "completed"
                    self.stats["status"] = "completed"
                else:
                    self.status = "error"
                    self.lifecycle_status = "failed"
                    self.stats["status"] = "error"
            elif self.status == "stopping":
                self.status = "idle"
                self.lifecycle_status = "stopped"
                self.stats["status"] = "idle"
                self.push_log("Task stopped.")
            self.exit_code = process.returncode if process else None
            self.finished_at = self._timestamp()
            self.process = None
            self.process_tree = None

    def stop_task(self, task_id: str | None = None):
        """Return False for a stale task ID, incomplete cleanup or pending output."""
        with self._lock:
            if task_id and task_id != self.task_id:
                return False
            if (
                self.stats.get("execution_mode") == "external_agent"
                and self.status in {"running", "waiting_for_agent", "agent_disconnected", "committed"}
                and not self.process
            ):
                self.status = "idle"
                self.lifecycle_status = "stopped"
                self.stats["status"] = "idle"
                self.exit_code = None
                self.finished_at = self._timestamp()
                self.push_log("Task stopped before an external Agent resumed it.", "warning")
                return True
            if self.status not in {"running", "stopping"} or not self.process:
                return True
            if self._stop_waiting:
                return False

            self.status = "stopping"
            self.lifecycle_status = "stopping"
            self.stats["status"] = "stopping"
            self.push_log("Sending force stop signal...", "warning")

            process = self.process
            try:
                if self.process_tree is not None:
                    if not self.process_tree.terminate(timeout=2):
                        self.push_log("Owned worker processes have not all exited; task remains stopping.", "error")
                        return False
                else:
                    process.kill()
                    process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.push_log(
                    "Task process did not exit after the stop signal; new tasks remain blocked.",
                    "error",
                )
                return False
            except Exception as e:
                self.push_log(f"Force stop error: {e}", "error")
                return False

            self._stop_waiting = True
            try:
                if not self._output_drained.wait_for(lambda: not self._output_pending, timeout=2):
                    self.push_log("Worker output is still draining; task remains stopping.", "warning")
                    return False
            finally:
                self._stop_waiting = False

            self.process = None
            self.process_tree = None
            self.status = "idle"
            self.lifecycle_status = "stopped"
            self.stats["status"] = "idle"
            self.exit_code = process.returncode
            self.finished_at = self._timestamp()
            self.push_log("Task stopped.")
            return True

    def update_external_agent_status(
        self,
        status: str,
        task_id: str | None = None,
        message: str | None = None,
    ) -> bool:
        """Apply a guarded lifecycle transition for an external-Agent task.

        The method is intentionally small and process-local.  MCP/Skills
        integrations can call it when they share the Web process; a caller
        must provide the stable task ID so an old task cannot update a newer
        one.
        """
        normalized = str(status or "").strip().lower()
        if normalized not in TASK_EXTERNAL_STATUSES:
            return False
        with self._lock:
            if task_id and task_id != self.task_id:
                return False
            if self.stats.get("execution_mode") != "external_agent":
                return False
            current = self.lifecycle_status
            if current == normalized:
                return True
            if normalized not in EXTERNAL_AGENT_STATUS_TRANSITIONS.get(current, frozenset()):
                return False
            if normalized == "completed":
                self.status = "completed"
                self.lifecycle_status = "completed"
                self.stats["status"] = "completed"
            elif normalized == "failed":
                self.status = "error"
                self.lifecycle_status = "failed"
                self.stats["status"] = "error"
            elif normalized == "stopped":
                self.status = "idle"
                self.lifecycle_status = "stopped"
                self.stats["status"] = "idle"
            else:
                self.status = normalized
                self.lifecycle_status = normalized
                self.stats["status"] = normalized
                if normalized == "running" and self.started_at is None:
                    self.started_at = self._timestamp()
            self.finished_at = self._timestamp() if normalized in {"completed", "failed", "stopped"} else None
            self.push_log(message or f"External Agent task status: {normalized}.", "warning" if normalized == "agent_disconnected" else "system")
            return True
