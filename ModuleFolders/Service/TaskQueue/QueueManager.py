import threading
import time
import os
import copy
import contextlib
import hashlib
import shutil
import tempfile
import uuid
from collections import Counter
from functools import wraps
import rapidjson as json
from datetime import datetime, timedelta
from ModuleFolders.Base.Base import Base
from ModuleFolders.Service.TaskQueue.QueueOutcome import summarize_queue
from ModuleFolders.Infrastructure.SensitiveData import (
    contains_sensitive_data,
    sanitize_sensitive_data,
)
from ModuleFolders.Infrastructure.TaskConfig.TaskType import TaskType
from ModuleFolders.Infrastructure.TaskContract import (
    TaskContractError,
    TaskSpec,
    select_task_contract_fields,
)

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows has no fcntl
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX has no msvcrt
    msvcrt = None


_QUEUE_THREAD_LOCKS = {}
_QUEUE_THREAD_LOCKS_GUARD = threading.Lock()
_HELD_QUEUE_FILES = threading.local()


def _serialized(method):
    @wraps(method)
    def locked(self, *args, **kwargs):
        with self.state_lock:
            return method(self, *args, **kwargs)
    return locked


def _worker_update(method):
    @wraps(method)
    def update(self, task_id, *args, **kwargs):
        with self.state_lock, _queue_file_lock(self.queue_file):
            if not isinstance(task_id, str):
                return False
            if self._queue_revision != _queue_file_revision(self.queue_file):
                if not self.hot_reload_queue(quiet=True, preserve_local_locks=False):
                    return False
            index = self.resolve_index(task_id)
            if index < 0:
                return False
            task = self.tasks[index]
            claim = getattr(self, "_worker_claim", None)
            if claim != (task.task_id, task.process_start_time) or not task.is_processing or not task.locked:
                return False
            self.current_task_index = index
            return method(self, index, *args, **kwargs)
    return update


def _queue_thread_lock(queue_path):
    key = os.path.normcase(os.path.abspath(queue_path))
    with _QUEUE_THREAD_LOCKS_GUARD:
        lock = _QUEUE_THREAD_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _QUEUE_THREAD_LOCKS[key] = lock
        return lock


@contextlib.contextmanager
def _queue_file_lock(queue_path):
    """Serialize queue file transactions across threads/processes."""
    normalized_path = os.path.abspath(queue_path)
    held = getattr(_HELD_QUEUE_FILES, "paths", ())
    if normalized_path in held:
        yield
        return
    lock_key = hashlib.sha256(
        os.path.normcase(normalized_path).encode("utf-8")
    ).hexdigest()
    try:
        lock_root = os.path.join(tempfile.gettempdir(), "ainiee-queue-locks")
        os.makedirs(lock_root, exist_ok=True)
        lock_path = os.path.join(lock_root, f"{lock_key}.lock")
    except (OSError, RuntimeError):
        # Some packaged or sandboxed environments do not expose a usable
        # system temporary directory. Keep lock artifacts in the ignored
        # project runtime area rather than next to a user queue file.
        project_root = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )
        lock_root = os.path.join(project_root, "Resource", "automation_progress", "queue_locks")
        os.makedirs(lock_root, exist_ok=True)
        lock_path = os.path.join(
            lock_root,
            f"{lock_key}.lock",
        )

    with _queue_thread_lock(normalized_path):
        with open(lock_path, "a+b") as handle:
            locked = False
            try:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                    locked = True
                elif msvcrt is not None:
                    handle.seek(0, os.SEEK_END)
                    if handle.tell() == 0:
                        handle.write(b"0")
                        handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                    locked = True
                _HELD_QUEUE_FILES.paths = (*held, normalized_path)
                yield
            finally:
                _HELD_QUEUE_FILES.paths = held
                if locked:
                    try:
                        if fcntl is not None:
                            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                        elif msvcrt is not None:
                            handle.seek(0)
                            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass


def _queue_file_revision(queue_path):
    """Return a content revision; ``None`` means that the queue did not exist."""
    try:
        with open(queue_path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except FileNotFoundError:
        return None


def _queue_backup_path(queue_path):
    """Return a persistent backup path outside the source checkout's tracked files."""
    project_root = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )
    backup_root = os.path.join(
        project_root, "Resource", "automation_progress", "queue_backups"
    )
    key = hashlib.sha256(
        os.path.normcase(os.path.abspath(queue_path)).encode("utf-8")
    ).hexdigest()
    return os.path.join(backup_root, f"{key}.json.bak")

class QueueTaskItem:
    def __init__(self, task_type, input_path, output_path=None, profile=None, rules_profile=None, 
                 source_lang=None, target_lang=None, project_type=None,
                 execution_mode="default_api",
                 platform=None, api_url=None, api_key=None, model=None, 
                 threads=None, retry=None, timeout=None, rounds=None, 
                 pre_lines=None, lines_limit=None, tokens_limit=None, 
                 think_depth=None, thinking_budget=None, failover=None,
                 polish_mode=None, resume=False, resume_explicit=None, manga=False, workflow_steps=None,
                 source=None, rule_id=None, automation_run_id=None,
                 automation_progress_file=None, automation_worker_pid=None,
                 trigger_file_path=None, trigger_file_name=None, trigger_detected_at=None,
                 series_incremental=False, series_key=None, series_volume=None, extra=None,
                 task_id=None, runtime_overrides=None, step_overrides=None):
        spec = TaskSpec.from_mapping(
            {
                "task_type": task_type,
                "input_path": input_path,
                "output_path": output_path,
                "profile": profile,
                "rules_profile": rules_profile,
                "source_lang": source_lang,
                "target_lang": target_lang,
                "project_type": project_type,
                "execution_mode": execution_mode,
                "platform": platform,
                "api_url": api_url,
                "api_key": api_key,
                "model": model,
                "threads": threads,
                "retry": retry,
                "timeout": timeout,
                "rounds": rounds,
                "pre_lines": pre_lines,
                "lines_limit": lines_limit,
                "tokens_limit": tokens_limit,
                "think_depth": think_depth,
                "thinking_budget": thinking_budget,
                "failover": failover,
                "polish_mode": polish_mode,
                "resume": resume,
                "manga": manga,
                "runtime_overrides": runtime_overrides,
                "step_overrides": step_overrides,
            }
        )
        queue_fields = spec.to_queue_fields()
        self.task_id = self.normalize_task_id(task_id)
        for field_name, value in queue_fields.items():
            setattr(self, field_name, value)
        self.resume_explicit = bool(resume_explicit) if resume_explicit is not None else None
        self.workflow_steps = workflow_steps or []
        if not self.workflow_steps and (spec.runtime_overrides or spec.step_overrides):
            kinds = ["translate", "polish"] if spec.task_type == "all_in_one" else [spec.task_type]
            self.workflow_steps = [{"id": kind, "type": kind} for kind in kinds]
        self.source = source
        self.rule_id = rule_id
        self.automation_run_id = automation_run_id
        self.automation_progress_file = automation_progress_file
        self.automation_worker_pid = automation_worker_pid
        self.trigger_file_path = trigger_file_path
        self.trigger_file_name = trigger_file_name
        self.trigger_detected_at = trigger_detected_at
        self.series_incremental = bool(series_incremental)
        self.series_key = series_key
        self.series_volume = series_volume
        self.extra = copy.deepcopy(extra) if isinstance(extra, dict) else {}
        if (self.runtime_overrides or self.step_overrides or any(step.get("runtime_overrides") for step in self.workflow_steps)) and "runtime_snapshot" not in self.extra:
            from ModuleFolders.Infrastructure.TaskConfig.RuntimeSnapshot import snapshot_for_task
            self.extra["runtime_snapshot"] = snapshot_for_task({**spec.to_mapping(), "workflow_steps": self.workflow_steps})
        
        self.status = "waiting" # waiting, workflow, translating, translated, polishing, completed, partial, error, stopped
        self.locked = False  # 是否被锁定（正在执行中不可修改）

        # 新增：准确的处理状态跟踪
        self.is_processing = False  # 是否真正在处理中
        self.last_activity_time = None  # 最后活动时间（ISO格式字符串）
        self.process_start_time = None  # 处理开始时间

    @staticmethod
    def normalize_task_id(task_id):
        """Return a canonical UUID, generating one for legacy or invalid values."""
        try:
            return str(uuid.UUID(str(task_id)))
        except (AttributeError, TypeError, ValueError):
            return str(uuid.uuid4())

    def to_runtime_dict(self):
        """Return the full in-memory task, including temporary credential overrides."""
        data = copy.deepcopy({k: v for k, v in vars(self).items() if not k.startswith('_')})
        if self.resume_explicit is False or (
            self.resume_explicit is None and self.workflow_steps
        ):
            data.pop("resume", None)
        if self.extra.get("runtime_snapshot"):
            data["runtime_snapshot"] = copy.deepcopy(self.extra["runtime_snapshot"])
        return data

    def to_persistent_dict(self):
        """Return a task representation that is safe to write or expose."""
        return sanitize_sensitive_data(self.to_runtime_dict())

    def to_dict(self):
        """Keep the generic serializer safe by default."""
        return self.to_persistent_dict()

    def to_task_spec(self):
        """把旧队列字段转换为共享任务协议，运行元数据仍留在队列对象。"""
        contract_error = (getattr(self, "extra", {}) or {}).get("task_contract_error")
        if contract_error:
            raise TaskContractError(str(contract_error))
        payload = select_task_contract_fields(self.to_runtime_dict())
        payload["task_type"] = self.task_type
        return TaskSpec.from_mapping(payload)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise TaskContractError("Queue task item must be an object")
        # 兼容旧数据，剔除运行时字段后传入构造函数
        params = data.copy()
        params.pop("runtime_snapshot", None)
        if "resume_explicit" not in params:
            params["resume_explicit"] = params.get("resume") is not None
        status = params.pop("status", "waiting")
        locked = params.pop("locked", False)  # 移除locked字段，它不属于构造函数参数

        # 新增字段的处理（兼容旧数据）
        is_processing = params.pop("is_processing", False)
        last_activity_time = params.pop("last_activity_time", None)
        process_start_time = params.pop("process_start_time", None)

        try:
            item = cls(**params)
        except Exception as exc:
            # 单条旧任务损坏不应导致整个队列无法加载。
            task_id = params.get("task_id")
            input_path = params.get("input_path")
            if not isinstance(input_path, str) or not input_path.strip():
                input_path = f"<invalid-queue-item:{task_id or 'unknown'}>"
            item = cls(
                task_type=TaskType.TRANSLATION,
                input_path=input_path,
                extra=params.get("extra") if isinstance(params.get("extra"), dict) else None,
                task_id=task_id,
            )
            status = "error"
            item.extra["task_contract_error"] = str(exc)
        item.status = status
        item.locked = locked
        item.is_processing = is_processing
        item.last_activity_time = last_activity_time
        item.process_start_time = process_start_time
        return item

class QueueManager(Base):
    _instance = None
    _lock = threading.Lock()
    state_lock = threading.RLock()

    @property
    def revision(self):
        return self._queue_revision or "missing"

    def resolve_index(self, target):
        if isinstance(target, int):
            return target if 0 <= target < len(self.tasks) else -1
        return next((index for index, task in enumerate(self.tasks) if task.task_id == str(target)), -1)

    def __new__(cls, *, read_only=False):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(QueueManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    @_serialized
    def __init__(self, *, read_only=False):
        if self._initialized: return
        super().__init__()
        # 使用绝对路径确保跨目录一致性
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.join(script_dir, "..", "..", "..")
        project_root = os.path.normpath(project_root)
        self.default_queue_file = os.path.join(project_root, "Resource", "queue_tasks.json")
        self.queue_file = self.default_queue_file

        # 添加队列操作日志文件
        self.queue_log_file = os.path.join(project_root, "Resource", "queue_operations.log")

        self.tasks = []
        self.last_save_error = None
        self.is_running = False
        self.run_result = None
        self.last_run_error = None
        self._run_done = threading.Event()
        self._run_done.set()
        self._automation_stop_requested = False
        self.current_task_index = -1
        self._queue_revision = None
        self._queue_revision_path = self.queue_file
        if read_only:
            if os.path.exists(self.queue_file):
                self.hot_reload_queue(quiet=True, preserve_local_locks=False)
        else:
            self.load_tasks()
        self._initialized = True

    def _log_queue_operation(self, message):
        """记录队列操作日志到文件，用于跨进程通信"""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            log_entry = f"[{timestamp}] {message}\n"

            # 确保日志目录存在
            os.makedirs(os.path.dirname(self.queue_log_file), exist_ok=True)

            # 追加写入日志文件
            with open(self.queue_log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)

            # 同时输出到控制台（保留原有行为）
            print(message)

        except Exception as e:
            # 如果日志文件写入失败，至少保证控制台输出
            print(message)
            print(f"[WARNING] Failed to write queue log: {e}")

    def get_queue_log_path(self):
        """获取队列日志文件路径"""
        return self.queue_log_file

    def get_recent_queue_logs(self, lines=10):
        """获取最近的队列操作日志"""
        try:
            if not os.path.exists(self.queue_log_file):
                return []

            with open(self.queue_log_file, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()

            # 返回最后几行，去掉换行符
            recent_lines = all_lines[-lines:] if len(all_lines) >= lines else all_lines
            return [line.strip() for line in recent_lines if line.strip()]

        except Exception as e:
            self.warning(f"Failed to read queue log: {e}")
            return []

    def clear_queue_logs(self):
        """清空队列操作日志"""
        try:
            if os.path.exists(self.queue_log_file):
                with open(self.queue_log_file, 'w', encoding='utf-8') as f:
                    f.write('')  # 清空文件内容
                return True
        except Exception as e:
            self.warning(f"Failed to clear queue log: {e}")
        return False

    @_serialized
    def load_tasks(self, custom_path=None):
        if custom_path:
            self.queue_file = custom_path
        queue_path = os.path.abspath(self.queue_file)
        try:
            with _queue_file_lock(queue_path):
                if os.path.exists(queue_path):
                    with open(queue_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    task_ids_changed = self._replace_tasks_from_data(data)
                    self._queue_revision = _queue_file_revision(queue_path)
                    self._queue_revision_path = queue_path
                    # Legacy queue files may contain plaintext credentials. Keep them
                    # only in this process, then scrub under the same file lock.
                    if contains_sensitive_data(data) or task_ids_changed:
                        self._save_tasks_locked(queue_path)
                else:
                    self.tasks = []
                    self._queue_revision = None
                    self._queue_revision_path = queue_path
        except Exception as e:
            self.last_run_error = "QUEUE_LOAD_FAILED"
            self.error(f"Failed to load queue tasks: {e}")
            self.tasks = []
            self._queue_revision = None
            self._queue_revision_path = queue_path

    @_serialized
    def save_tasks(self):
        """Atomically persist the queue without exposing a partial JSON file."""
        queue_path = os.path.abspath(self.queue_file)
        try:
            with _queue_file_lock(queue_path):
                revision_path = getattr(self, "_queue_revision_path", queue_path)
                expected_revision = getattr(
                    self,
                    "_queue_revision",
                    _queue_file_revision(queue_path),
                )
                if os.path.abspath(revision_path) != queue_path:
                    expected_revision = _queue_file_revision(queue_path)
                current_revision = _queue_file_revision(queue_path)
                if current_revision != expected_revision:
                    self.last_save_error = "conflict"
                    if self.is_running:
                        self.last_run_error = "QUEUE_SAVE_FAILED"
                    self.error(
                        "Queue changed since it was loaded; refusing to overwrite "
                        f"{queue_path}"
                    )
                    return False
                return self._save_tasks_locked(queue_path)
        except Exception as e:
            self.last_save_error = str(e)
            if self.is_running:
                self.last_run_error = "QUEUE_SAVE_FAILED"
            self.error(f"Failed to save queue tasks: {e}")
            return False

    def _save_tasks_locked(self, queue_path):
        """Write queue data; caller must hold ``_queue_file_lock``."""
        temporary_path = None
        try:
            self.last_save_error = None
            queue_directory = os.path.dirname(queue_path)
            os.makedirs(queue_directory, exist_ok=True)
            temporary_path = (
                f"{queue_path}.{os.getpid()}.{threading.get_ident()}.tmp"
            )
            with open(temporary_path, 'w', encoding='utf-8') as f:
                json.dump(
                    [t.to_persistent_dict() for t in self.tasks],
                    f,
                    indent=4,
                    ensure_ascii=False,
                )
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary_path, queue_path)
            # Keep a sanitized, atomically replaceable recovery copy. The
            # backup is updated only after the primary replacement succeeds,
            # so a failed write leaves the last known-good backup intact.
            try:
                backup_path = _queue_backup_path(queue_path)
                os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                backup_temporary_path = f"{backup_path}.{os.getpid()}.{threading.get_ident()}.tmp"
                try:
                    shutil.copyfile(queue_path, backup_temporary_path)
                    with open(backup_temporary_path, "rb") as backup_file:
                        os.fsync(backup_file.fileno())
                    os.replace(backup_temporary_path, backup_path)
                finally:
                    try:
                        if os.path.exists(backup_temporary_path):
                            os.remove(backup_temporary_path)
                    except OSError:
                        pass
            except OSError as backup_error:
                logger = getattr(self, "warning", None)
                if callable(logger):
                    logger(f"Failed to update queue backup: {backup_error}")
            self._queue_revision = _queue_file_revision(queue_path)
            self._queue_revision_path = queue_path
            return True
        except Exception as e:
            self.last_save_error = str(e)
            if self.is_running:
                self.last_run_error = "QUEUE_SAVE_FAILED"
            self.error(f"Failed to save queue tasks: {e}")
            if temporary_path:
                try:
                    os.remove(temporary_path)
                except OSError:
                    pass
            return False

    @staticmethod
    def _credential_context(task):
        return tuple(
            getattr(task, field, None)
            for field in ("platform", "api_url", "profile")
        )

    @staticmethod
    def _runtime_credentials_by_task_id(tasks):
        task_id_counts = Counter(getattr(task, "task_id", None) for task in tasks)
        return {
            task.task_id: (
                QueueManager._credential_context(task),
                getattr(task, "api_key", None),
            )
            for task in tasks
            if task_id_counts.get(getattr(task, "task_id", None)) == 1
        }

    @staticmethod
    def _restore_runtime_api_keys(old_tasks, new_tasks):
        runtime_credentials = QueueManager._runtime_credentials_by_task_id(old_tasks)
        for task in new_tasks:
            credential_context, api_key = runtime_credentials.get(
                task.task_id,
                (None, None),
            )
            if (
                task.api_key is None
                and credential_context == QueueManager._credential_context(task)
            ):
                task.api_key = api_key

    def _replace_tasks_from_data(self, data, *, recover_runtime_state=True):
        if not isinstance(data, list):
            raise ValueError("Queue data must be an array")
        old_tasks = self.tasks
        new_tasks = []
        runtime_state_changed = False
        for index, item in enumerate(data):
            if isinstance(item, dict):
                task = QueueTaskItem.from_dict(item)
                # A process can crash after an external-Agent row was marked
                # active.  It has no local worker to own that lock, so recover
                # it to a durable waiting state instead of blocking the queue
                # until the generic five-minute stale-lock timeout.
                if (
                    recover_runtime_state
                    and str(getattr(task, "execution_mode", "default_api") or "default_api").strip().lower()
                    == "external_agent"
                    and (
                        getattr(task, "status", "")
                        in {
                            "waiting",
                            "translated",
                            "translating",
                            "polishing",
                            "workflow",
                            "waiting_for_agent",
                        }
                        or bool(getattr(task, "workflow_steps", None))
                    )
                ):
                    if (
                        task.status != "waiting_for_agent"
                        or task.locked
                        or task.is_processing
                        or task.process_start_time is not None
                        or task.last_activity_time is not None
                        or bool(getattr(task, "workflow_steps", None))
                    ):
                        runtime_state_changed = True
                    task.status = "waiting_for_agent"
                    task.workflow_steps = []
                    task.locked = False
                    task.is_processing = False
                    task.process_start_time = None
                    task.last_activity_time = None
                new_tasks.append(task)
                continue
            fallback = QueueTaskItem(
                TaskType.TRANSLATION,
                f"<invalid-queue-item:{index}>",
            )
            fallback.status = "error"
            fallback.extra["task_contract_error"] = "Queue task item must be an object"
            new_tasks.append(fallback)
        id_counts = Counter(task.task_id for task in new_tasks)
        used = set(id_counts)
        identified = []
        for index, (item, task) in enumerate(zip(data, new_tasks)):
            try:
                original = str(uuid.UUID(str(item.get("task_id"))))
            except (ValueError, AttributeError):
                original = None
            if original == task.task_id and id_counts[original] == 1:
                identified.append(task)
                continue
            source = os.path.abspath(getattr(self, "queue_file", ""))
            seed = f"{source}:{index}:{json.dumps(sanitize_sensitive_data(item), sort_keys=True)}"
            candidate = str(uuid.uuid5(uuid.NAMESPACE_URL, seed))
            while candidate in used:
                candidate = str(uuid.uuid5(uuid.NAMESPACE_URL, candidate))
            task.task_id = candidate
            used.add(candidate)
        self._restore_runtime_api_keys(old_tasks, identified)
        task_ids_changed = any(
            not isinstance(item, dict) or item.get("task_id") != task.task_id
            for item, task in zip(data, new_tasks)
        )
        self.tasks = new_tasks
        return task_ids_changed or runtime_state_changed

    @_serialized
    def add_task(self, task_item):
        if self.resolve_index(task_item.task_id) >= 0:
            self.last_save_error = "conflict"
            return False
        self.tasks.append(task_item)
        if not self.save_tasks():
            self.tasks.pop()
            return False
        return True

    @_serialized
    def remove_task(self, index):
        index = self.resolve_index(index)
        if 0 <= index < len(self.tasks):
            if any(not self.can_modify_task(pos) for pos in range(index, len(self.tasks))):
                self.last_save_error = "locked"
                return False
            task_name = os.path.basename(self.tasks[index].input_path)
            removed_task = self.tasks.pop(index)
            if not self.save_tasks():
                self.tasks.insert(index, removed_task)
                return False
            self._log_queue_operation(self.tra('msg_task_removed').format(task_name))
            return True
        return False

    def detect_parameter_changes(self, old_task, new_task):
        """检测任务参数变更并返回变更详情"""
        changes = []

        # 定义需要监控的参数及其对应的I18N键
        params_to_monitor = {
            'platform': 'param_platform',
            'api_url': 'param_api_url',
            'api_key': 'param_api_key',
            'model': 'param_model',
            'threads': 'param_threads',
            'source_lang': 'param_source_lang',
            'target_lang': 'param_target_lang',
            'retry': 'param_retry',
            'timeout': 'param_timeout',
            'rounds': 'param_rounds',
            'pre_lines': 'param_pre_lines',
            'lines_limit': 'param_lines_limit',
            'tokens_limit': 'param_tokens_limit',
            'think_depth': 'param_think_depth',
            'thinking_budget': 'param_thinking_budget',
            'task_type': 'param_task_type',
            'profile': 'param_profile',
            'rules_profile': 'param_rules_profile',
            'project_type': 'param_project_type'
        }

        for param, i18n_key in params_to_monitor.items():
            old_value = getattr(old_task, param, None)
            new_value = getattr(new_task, param, None)

            # 对于API密钥等敏感信息，只显示部分内容
            if param == 'api_key':
                if old_value != new_value:
                    old_display = self._mask_sensitive_value(old_value)
                    new_display = self._mask_sensitive_value(new_value)
                    if old_value is None and new_value is not None:
                        changes.append(self.tra('param_added').format(self.tra(i18n_key), new_display))
                    elif old_value is not None and new_value is None:
                        changes.append(self.tra('param_removed').format(self.tra(i18n_key)))
                    elif old_value != new_value:
                        changes.append(self.tra('param_changed').format(self.tra(i18n_key), old_display, new_display))
            else:
                # 普通参数的处理
                if old_value != new_value:
                    if old_value is None and new_value is not None:
                        changes.append(self.tra('param_added').format(self.tra(i18n_key), new_value))
                    elif old_value is not None and new_value is None:
                        changes.append(self.tra('param_removed').format(self.tra(i18n_key)))
                    elif old_value != new_value:
                        changes.append(self.tra('param_changed').format(self.tra(i18n_key), old_value, new_value))

        return changes

    def _mask_sensitive_value(self, value):
        """遮掩敏感信息"""
        if value is None:
            return None
        if len(str(value)) <= 8:
            return "****"
        else:
            return str(value)[:4] + "****" + str(value)[-4:]

    @_serialized
    def update_task(self, index, task_item, *, expected_revision=None):
        index = self.resolve_index(index)
        if 0 <= index < len(self.tasks):
            if task_item.task_id != self.tasks[index].task_id or (expected_revision is not None and expected_revision != self.revision):
                self.last_save_error = "conflict"
                return False
            if not self.can_modify_task(index):
                self.last_save_error = "locked"
                return False
            try:
                if task_item.runtime_overrides or task_item.step_overrides:
                    if not task_item.workflow_steps:
                        kind = task_item.to_task_spec().task_type
                        kinds = ["translate", "polish"] if kind == "all_in_one" else [kind]
                        task_item.workflow_steps = [{"id": name, "type": name} for name in kinds]
                    if "runtime_snapshot" not in task_item.extra:
                        from ModuleFolders.Infrastructure.TaskConfig.RuntimeSnapshot import snapshot_for_task
                        task_item.extra["runtime_snapshot"] = snapshot_for_task(task_item.to_task_spec().to_mapping())
                old_task = self.tasks[index]
                task_name = os.path.basename(old_task.input_path)

                # 检测参数变更
                changes = self.detect_parameter_changes(old_task, task_item)

                # 更新任务
                self.tasks[index] = task_item
                if not self.save_tasks():
                    self.tasks[index] = old_task
                    return False

                # 打印详细的变更日志
                if changes:
                    self._log_queue_operation(self.tra('msg_task_updated').format(task_name))
                    for change in changes:
                        self._log_queue_operation(change)
                else:
                    # 如果没有参数变更，只是简单的更新
                    self._log_queue_operation(f"[INFO] {self.tra('msg_task_updated').format(task_name)} {self.tra('msg_no_config_changes')}")

            except Exception as e:
                self._log_queue_operation(f"[ERROR] Failed to update task: {e}")
                return False

            return True
        return False

    @_serialized
    def clear_tasks(self):
        if any(not self.can_modify_task(index) for index in range(len(self.tasks))):
            self.last_save_error = "locked"
            return False
        previous_tasks = self.tasks
        self.tasks = []
        if not self.save_tasks():
            self.tasks = previous_tasks
            return False
        return True

    @_serialized
    def lock_task(self, index):
        """锁定任务（正在执行中）"""
        if 0 <= index < len(self.tasks):
            previous = self.tasks[index].locked
            self.tasks[index].locked = True
            if not self.save_tasks():
                self.tasks[index].locked = previous
                return False
            return True
        return False

    @_serialized
    def unlock_task(self, index):
        """解锁任务"""
        if 0 <= index < len(self.tasks):
            previous = self.tasks[index].locked
            self.tasks[index].locked = False
            if not self.save_tasks():
                self.tasks[index].locked = previous
                return False
            return True
        return False

    def can_modify_task(self, index):
        """检查任务是否可以被修改（未锁定）"""
        if 0 <= index < len(self.tasks):
            task = self.tasks[index]
            return not (task.locked or task.is_processing or task.status in (
                "starting", "running", "stopping", "translating", "polishing", "workflow", "staging", "committed",
            ))
        return False

    # ================ 智能处理状态管理 ================

    @_worker_update
    def update_task_activity(self, index):
        """更新任务活动时间（心跳机制）"""
        if 0 <= index < len(self.tasks):
            task = self.tasks[index]
            previous = task.last_activity_time
            task.last_activity_time = datetime.now().isoformat()
            if not self.save_tasks():
                task.last_activity_time = previous
                return False
            return True
        return False

    @_serialized
    def start_task_processing(self, index):
        """开始处理任务 - 设置处理状态和时间戳"""
        if 0 <= index < len(self.tasks):
            task = self.tasks[index]
            previous = (
                task.is_processing,
                task.process_start_time,
                task.last_activity_time,
                task.locked,
            )
            now = datetime.now().isoformat()
            task.is_processing = True
            task.process_start_time = now
            task.last_activity_time = now
            task.locked = True
            if not self.save_tasks():
                (
                    task.is_processing,
                    task.process_start_time,
                    task.last_activity_time,
                    task.locked,
                ) = previous
                return False
            return True
        return False

    @_serialized
    def stop_task_processing(self, index):
        """停止处理任务 - 清除处理状态"""
        if 0 <= index < len(self.tasks):
            task = self.tasks[index]
            previous = (
                task.is_processing,
                task.process_start_time,
                task.last_activity_time,
                task.locked,
            )
            task.is_processing = False
            task.process_start_time = None
            task.last_activity_time = None
            task.locked = False
            if not self.save_tasks():
                (
                    task.is_processing,
                    task.process_start_time,
                    task.last_activity_time,
                    task.locked,
                ) = previous
                return False
            return True
        return False

    def is_task_actually_processing(self, index, timeout_minutes=5):
        """
        检查任务是否真正在处理中

        Args:
            index: 任务索引
            timeout_minutes: 超时时间（分钟），超过此时间没有活动则认为不在处理中

        Returns:
            bool: 是否真正在处理中
        """
        if not (0 <= index < len(self.tasks)):
            return False

        task = self.tasks[index]

        # 如果明确标记为未处理，直接返回False
        if not task.is_processing:
            return False

        # 检查最后活动时间
        if not task.last_activity_time:
            return False

        try:
            last_activity = datetime.fromisoformat(task.last_activity_time)
            now = datetime.now()
            inactive_time = now - last_activity

            # 如果超过超时时间没有活动，认为不在处理中
            if inactive_time > timedelta(minutes=timeout_minutes):
                self.warning(f"Task {index+1} has been inactive for {inactive_time.total_seconds():.1f} seconds, marking as not processing")
                return False

            return True

        except (ValueError, TypeError) as e:
            self.warning(f"Invalid activity time format for task {index+1}: {e}")
            return False

    @_serialized
    def cleanup_stale_locks(self, timeout_minutes=5):
        """
        清理过期的锁定状态

        Args:
            timeout_minutes: 超时时间（分钟）

        Returns:
            int: 清理的任务数量
        """
        cleaned_count = 0
        previous_tasks = copy.deepcopy(self.tasks)

        for i, task in enumerate(self.tasks):
            if task.locked and not self.is_task_actually_processing(i, timeout_minutes):
                self.info(f"Cleaning stale lock for task {i+1}: {task.input_path}")
                task.locked = False
                task.is_processing = False
                task.process_start_time = None
                task.last_activity_time = None

                # 重置状态到合适的值
                if task.status in ["translating", "polishing", "workflow"]:
                    task.status = "waiting"

                cleaned_count += 1

        if cleaned_count > 0:
            if self.save_tasks() is False:
                self.tasks = previous_tasks
                self.last_save_error = getattr(self, "last_save_error", None) or "save_failed"
                return 0
            self.info(f"Cleaned {cleaned_count} stale task locks")

        return cleaned_count

    def _cleanup_stale_locks_or_fail(self, timeout_minutes=5):
        """Run stale-lock cleanup and distinguish a failed save from no work."""
        self.last_save_error = None
        # Keep the default call compatible with integrations that replace the
        # no-argument cleanup hook while still allowing explicit timeouts.
        if timeout_minutes == 5:
            self.cleanup_stale_locks()
        else:
            self.cleanup_stale_locks(timeout_minutes)
        return not bool(getattr(self, "last_save_error", None))

    def get_task_processing_status(self, index):
        """
        获取任务的详细处理状态

        Returns:
            dict: 包含处理状态信息的字典
        """
        if not (0 <= index < len(self.tasks)):
            return None

        task = self.tasks[index]
        is_actually_processing = self.is_task_actually_processing(index)

        status_info = {
            "locked": task.locked,
            "is_processing": task.is_processing,
            "is_actually_processing": is_actually_processing,
            "process_start_time": task.process_start_time,
            "last_activity_time": task.last_activity_time,
            "status": task.status
        }

        return status_info

    def move_task_up(self, index):
        return self.move_task(index, index - 1)

    def move_task_down(self, index):
        return self.move_task(index, index + 1)

    @_serialized
    def move_task(self, from_index, to_index):
        """将任务从from_index移动到to_index位置"""
        if (0 <= from_index < len(self.tasks) and
            0 <= to_index < len(self.tasks) and
            from_index != to_index):

            # 检查移动路径上是否有锁定的任务
            start, end = min(from_index, to_index), max(from_index, to_index)
            for i in range(start, end + 1):
                if not self.can_modify_task(i):
                    self.last_save_error = "locked"
                    return False

            # 移除任务
            previous_tasks = list(self.tasks)
            task = self.tasks.pop(from_index)
            task_name = os.path.basename(task.input_path)
            # 插入到新位置
            self.tasks.insert(to_index, task)
            if not self.save_tasks():
                self.tasks = previous_tasks
                return False
            self._log_queue_operation(self.tra('msg_task_moved').format(task_name, from_index+1, to_index+1))
            return True
        return False

    @_serialized
    def reorder_tasks(self, new_order):
        """根据新的索引顺序重新排列任务

        Args:
            new_order: 新的索引顺序列表，如 [2, 0, 1] 表示原来的第2个任务移到第0位
        """
        if (len(new_order) == len(self.tasks) and
            set(new_order) == set(range(len(self.tasks)))):
            segment = 0
            segments = []
            for index in range(len(self.tasks)):
                if not self.can_modify_task(index):
                    if new_order[index] != index:
                        self.last_save_error = "locked"
                        return False
                    segment += 1
                segments.append(segment)
            if any(segments[index] != segments[previous] for index, previous in enumerate(new_order)):
                self.last_save_error = "locked"
                return False
            previous_tasks = list(self.tasks)
            self.tasks = [self.tasks[i] for i in new_order]
            if not self.save_tasks():
                self.tasks = previous_tasks
                return False
            return True
        return False

    @_serialized
    def hot_reload_queue(self, quiet=False, *, preserve_local_locks=True):
        """热重载队列：在不影响锁定任务的情况下重新加载队列

        Args:
            quiet (bool): 如果为True，不打印成功日志。用于操作后的静默刷新。
            preserve_local_locks (bool): False observes the file without recovery or writeback.
        """
        queue_path = os.path.abspath(self.queue_file)
        if not os.path.exists(queue_path):
            return False

        previous_tasks = copy.deepcopy(self.tasks)
        previous_revision = getattr(self, "_queue_revision", None)
        previous_revision_path = getattr(self, "_queue_revision_path", None)
        try:
            with _queue_file_lock(queue_path):
                # 保存当前锁定状态
                locked_states = {}
                for task in self.tasks:
                    if preserve_local_locks and task.locked and not self._is_external_agent_task(task):
                        locked_states[task.task_id] = task.status

                # 重新加载任务
                with open(queue_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                task_ids_changed = self._replace_tasks_from_data(
                    data, recover_runtime_state=preserve_local_locks
                )

                # 恢复锁定状态（通过持久化任务 ID 匹配）
                for new_task in self.tasks:
                    if new_task.task_id in locked_states:
                        new_task.locked = True
                        new_task.status = locked_states[new_task.task_id]

                self._queue_revision = _queue_file_revision(queue_path)
                self._queue_revision_path = queue_path
                if preserve_local_locks and (contains_sensitive_data(data) or task_ids_changed):
                    if not self._save_tasks_locked(queue_path):
                        self.tasks = previous_tasks
                        self._queue_revision = previous_revision
                        self._queue_revision_path = previous_revision_path
                        return False

            # 只有在非静默模式下才打印成功日志
            if not quiet:
                self.info("Queue hot reloaded successfully.")
            return True

        except Exception as e:
            if self.is_running:
                self.last_run_error = "QUEUE_LOAD_FAILED"
            self.tasks = previous_tasks
            self._queue_revision = previous_revision
            self._queue_revision_path = previous_revision_path
            self.error(f"Failed to hot reload queue: {e}")
            return False

    def get_queue_json(self):
        """Return the editable queue document without credential material."""
        return json.dumps(
            [task.to_persistent_dict() for task in self.tasks],
            indent=4,
            ensure_ascii=False,
        )

    @_serialized
    def load_from_json(self, content, *, expected_revision=None):
        """Load a raw queue document while ensuring its persisted form is sanitized."""
        data = json.loads(content, allow_nan=False)
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise ValueError("Queue JSON must be an array of task objects")
        supplied_ids = [str(uuid.UUID(str(row["task_id"]))) for row in data if "task_id" in row]
        if len(supplied_ids) != len(set(supplied_ids)):
            raise ValueError("Duplicate queue task ID")

        queue_path = os.path.abspath(self.queue_file)
        with _queue_file_lock(queue_path):
            if (expected_revision is not None and expected_revision != self.revision) or _queue_file_revision(queue_path) != self._queue_revision:
                self.last_save_error = "conflict"
                return False
            if any(not self.can_modify_task(index) for index in range(len(self.tasks))):
                self.last_save_error = "locked"
                return False
            previous_tasks = self.tasks
            self._replace_tasks_from_data(data, recover_runtime_state=False)
            if any(task.extra.get("task_contract_error") or not isinstance(task.status, str)
                   or type(task.locked) is not bool or type(task.is_processing) is not bool
                   for task in self.tasks):
                self.tasks = previous_tasks
                raise ValueError("Queue contains an invalid task")
            if any(not self.can_modify_task(index) for index in range(len(self.tasks))):
                self.tasks = previous_tasks
                raise ValueError("Raw editing cannot claim a running task")
            if not self._save_tasks_locked(queue_path):
                self.tasks = previous_tasks
                return False
            return True

    @staticmethod
    def _is_external_agent_task(task):
        return str(getattr(task, "execution_mode", "default_api") or "default_api").strip().lower() == "external_agent"

    @_serialized
    def _set_external_agent_status(self, index, status):
        """Persist a queue-side external-Agent lifecycle transition.

        External-Agent work is completed by the MCP/Skills batch protocol, so
        the queue worker must never claim it as an API task.  Keeping the
        transition here also makes a mixed queue durable across hot reloads.
        """
        if not (0 <= index < len(self.tasks)):
            return False
        task = self.tasks[index]
        if not self._is_external_agent_task(task):
            return False
        previous = (
            task.status,
            task.locked,
            task.is_processing,
            task.process_start_time,
            task.last_activity_time,
        )
        task.status = str(status)
        if status in {
            "waiting_for_agent",
            "agent_disconnected",
            "staging",
            "committed",
            "completed",
            "stopped",
            "error",
        }:
            task.locked = False
            task.is_processing = False
            task.process_start_time = None
            task.last_activity_time = None
        if self.save_tasks() is False:
            (
                task.status,
                task.locked,
                task.is_processing,
                task.process_start_time,
                task.last_activity_time,
            ) = previous
            return False
        return True

    @_serialized
    def mark_external_agent_disconnected(self, task_id: str = "", input_path: str = ""):
        """Mark an external-Agent queue item as disconnected and unlock it."""
        target_input = os.path.abspath(input_path) if input_path else ""
        for index, task in enumerate(self.tasks):
            matches_id = bool(task_id) and str(getattr(task, "task_id", "")) == str(task_id)
            matches_path = target_input and os.path.abspath(getattr(task, "input_path", "") or "") == target_input
            if (matches_id or matches_path) and self._is_external_agent_task(task):
                return self._set_external_agent_status(index, "agent_disconnected")
        return False

    @_serialized
    def sync_external_agent_status(self, task_id: str, status: str) -> bool:
        """Apply a batch-protocol status to the matching queue item.

        This is intentionally an explicit bridge: external-Agent services may
        run without a QueueManager, while a queue-backed task can opt into
        durable status updates after claim, disconnect, staging or commit.
        """
        allowed = {
            "waiting_for_agent",
            "agent_disconnected",
            "staging",
            "committed",
            "completed",
            "stopped",
            "error",
        }
        if status not in allowed:
            raise ValueError(f"Unsupported external-Agent queue status: {status!r}")
        for index, task in enumerate(self.tasks):
            if str(getattr(task, "task_id", "")) == str(task_id) and self._is_external_agent_task(task):
                return self._set_external_agent_status(index, status)
        return False

    @_serialized
    def resume_external_agent_task(self, task_id: str = "", input_path: str = ""):
        """Return a disconnected external-Agent item to the waiting state."""
        target_input = os.path.abspath(input_path) if input_path else ""
        resumable = {"agent_disconnected", "stopped", "error", "waiting_for_agent"}
        for index, task in enumerate(self.tasks):
            matches_id = bool(task_id) and str(getattr(task, "task_id", "")) == str(task_id)
            matches_path = target_input and os.path.abspath(getattr(task, "input_path", "") or "") == target_input
            if (
                (matches_id or matches_path)
                and self._is_external_agent_task(task)
                and getattr(task, "status", "") in resumable
            ):
                return self._set_external_agent_status(index, "waiting_for_agent")
        return False

    @_serialized
    def get_next_unlocked_task(self, start_index=0, statuses=None):
        """获取下一个未锁定的待执行任务"""
        allowed_statuses = set(statuses or {"waiting", "translated"})
        for i in range(start_index, len(self.tasks)):
            task = self.tasks[i]
            if self._is_external_agent_task(task):
                if not task.locked and task.status in allowed_statuses:
                    # Persist this once so a following hot reload does not
                    # turn the item back into an API-eligible ``waiting`` row.
                    self._set_external_agent_status(i, "waiting_for_agent")
                continue
            if self._task_has_workflow(task):
                continue
            if self.can_modify_task(i) and task.status in allowed_statuses:
                return i, task
        return None, None

    @_serialized
    def mark_task_executing(self, task):
        """标记任务为执行中并锁定 - 使用智能处理状态管理"""
        if getattr(self, "_worker_claim", None) is not None:
            return False
        index = self.resolve_index(task.task_id)
        if self.can_modify_task(index) and self.tasks[index] is task:

            if self._is_external_agent_task(task):
                self._set_external_agent_status(index, "waiting_for_agent")
                return False

            previous = (
                task.status,
                task.locked,
                task.is_processing,
                task.process_start_time,
                task.last_activity_time,
            )
            if self._task_has_workflow(task):
                task.status = "workflow"
            elif task.status == "waiting":
                task.status = "translating"
            elif task.status == "translated":
                task.status = "polishing"
            now = datetime.now().isoformat()
            task.is_processing = True
            task.process_start_time = now
            task.last_activity_time = now
            task.locked = True

            # Marking and persisting the processing state must be one transaction;
            # otherwise a concurrent writer can observe a locked task with the
            # old status between the two saves.
            if self.save_tasks() is False:
                (
                    task.status,
                    task.locked,
                    task.is_processing,
                    task.process_start_time,
                    task.last_activity_time,
                ) = previous
                return False
            self.current_task_index = index
            self._worker_claim = (task.task_id, now)
            return True
        return False

    @_worker_update
    def mark_task_completed(self, index, final_status="completed", final_state: dict = None):
        """标记任务完成并解锁 - 使用智能处理状态管理"""
        if 0 <= index < len(self.tasks):
            task = self.tasks[index]

            previous = (
                task.status,
                task.locked,
                task.is_processing,
                task.process_start_time,
                task.last_activity_time,
                copy.deepcopy(getattr(task, "extra", {}) or {}),
            )

            task.is_processing = False
            task.process_start_time = None
            task.last_activity_time = None
            task.locked = False
            task.status = final_status
            skip = (getattr(self, "_deferred_skip", None) == self._worker_claim
                    and final_status not in {"stopped", "error"}
                    and all(self.can_modify_task(pos) for pos in range(index + 1, len(self.tasks))))
            if skip:
                self.tasks.append(self.tasks.pop(index))
                task.status = "waiting"
            if task.status == "partial" and isinstance(final_state, dict):
                task.extra = getattr(task, "extra", {}) or {}
                task.extra["partial_step_type"] = final_state.get("step_type") or ""
                task.extra["partial_step_id"] = final_state.get("step_id") or ""
                task.extra["partial_step_index"] = final_state.get("step_index") or 0
                task.extra["partial_message"] = final_state.get("message") or ""
            if self.save_tasks() is not False:
                self._worker_claim = None
                self._deferred_skip = None
                self.current_task_index = -1
                if task.status == "completed":
                    self._collect_completed_automation_outputs(task)
                return True

            if skip:
                self.tasks.insert(index, self.tasks.pop())
            (
                task.status,
                task.locked,
                task.is_processing,
                task.process_start_time,
                task.last_activity_time,
                task.extra,
            ) = previous
            return False
        return False

    def _collect_completed_automation_outputs(self, task):
        try:
            from ModuleFolders.Infrastructure.Automation.OutputCollector import (
                AUTOMATION_OUTPUT_COLLECTION_CONFIG_KEY,
                collect_automation_outputs,
                normalize_output_collection_config,
                should_collect_automation_outputs,
            )

            if not should_collect_automation_outputs(task):
                return

            config = self.load_config()
            collection_config = normalize_output_collection_config(
                config.get(AUTOMATION_OUTPUT_COLLECTION_CONFIG_KEY, {})
            )
            if not collection_config["enabled"] or not collection_config["output_path"]:
                return

            copied = collect_automation_outputs(task, collection_config)
            file_name = os.path.basename(getattr(task, "input_path", "") or "-")
            if copied:
                self._log_queue_operation(
                    f"Automation output collection copied {len(copied)} file(s) for {file_name} -> {collection_config['output_path']}"
                )
            else:
                self._log_queue_operation(
                    f"Automation output collection found no product files for {file_name}"
                )
        except Exception as e:
            self._log_queue_operation(f"Automation output collection failed: {e}")

    @_serialized
    def mark_automation_interrupted(self, run_id: str, final_status: str = "stopped") -> bool:
        if not run_id:
            return False
        updated = False
        previous_tasks = copy.deepcopy(self.tasks)
        for task in self.tasks:
            if getattr(task, "automation_run_id", None) == run_id:
                task.status = final_status
                task.locked = False
                task.is_processing = False
                task.process_start_time = None
                task.last_activity_time = None
                updated = True
        if updated:
            if not self.save_tasks():
                self.tasks = previous_tasks
                return False
        return updated

    @_serialized
    def continue_partial_task(self, run_id: str = "", input_path: str = "") -> bool:
        target_input = os.path.abspath(input_path) if input_path else ""
        for task in self.tasks:
            matches_run = run_id and getattr(task, "automation_run_id", None) == run_id
            matches_path = target_input and os.path.abspath(getattr(task, "input_path", "") or "") == target_input
            if not (matches_run or matches_path):
                continue
            if getattr(task, "status", "") != "partial":
                continue
            previous_tasks = copy.deepcopy(self.tasks)
            task.status = "waiting"
            task.locked = False
            task.is_processing = False
            task.process_start_time = None
            task.last_activity_time = None
            task.workflow_steps = self._workflow_steps_for_partial_resume(task)
            remaining_ids = {step.get("id") for step in task.workflow_steps}
            task.step_overrides = {key: value for key, value in task.step_overrides.items() if key in remaining_ids}
            task.automation_run_id = None
            task.automation_progress_file = None
            task.automation_worker_pid = None
            task.extra = getattr(task, "extra", {}) or {}
            task.extra.pop("partial_step_id", None)
            task.extra.pop("partial_step_type", None)
            task.extra.pop("partial_step_index", None)
            task.extra.pop("partial_message", None)
            if not self.save_tasks():
                self.tasks = previous_tasks
                return False
            return True
        return False

    @_serialized
    def resume_stopped_task(self, run_id: str = "", input_path: str = "") -> bool:
        target_input = os.path.abspath(input_path) if input_path else ""
        for task in self.tasks:
            matches_run = run_id and getattr(task, "automation_run_id", None) == run_id
            matches_path = target_input and os.path.abspath(getattr(task, "input_path", "") or "") == target_input
            if not (matches_run or matches_path):
                continue
            if getattr(task, "status", "") not in {"stopped", "interrupted"}:
                continue
            previous_tasks = copy.deepcopy(self.tasks)
            task.status = "waiting"
            task.locked = False
            task.is_processing = False
            task.process_start_time = None
            task.last_activity_time = None
            task.automation_run_id = None
            task.automation_progress_file = None
            task.automation_worker_pid = None
            task.extra = getattr(task, "extra", {}) or {}
            task.extra.pop("partial_step_id", None)
            task.extra.pop("partial_step_type", None)
            task.extra.pop("partial_step_index", None)
            task.extra.pop("partial_message", None)
            if not self.save_tasks():
                self.tasks = previous_tasks
                return False
            return True
        return False

    def _workflow_steps_for_partial_resume(self, task):
        steps = [
            dict(step)
            for step in (getattr(task, "workflow_steps", None) or [])
            if isinstance(step, dict)
        ]
        step_types = [str(step.get("type") or "").strip().lower() for step in steps]
        try:
            partial_step = str((getattr(task, "extra", {}) or {}).get("partial_step_type") or "").strip().lower()
        except Exception:
            partial_step = ""
        partial_id = (getattr(task, "extra", {}) or {}).get("partial_step_id")
        exact_index = next((index for index, step in enumerate(steps) if step.get("id") == partial_id), None) if partial_id else None
        if exact_index is not None:
            resume_steps = steps[exact_index:]
        elif partial_step in step_types:
            index = step_types.index(partial_step)
            resume_steps = steps[index:]
        elif "translate" in step_types:
            index = step_types.index("translate")
            resume_steps = steps[index:]
        elif "all_in_one" in step_types:
            resume_steps = [
                {
                    **steps[step_types.index("all_in_one")],
                    "type": "all_in_one",
                }
            ]
        elif "polish" in step_types:
            index = step_types.index("polish")
            resume_steps = steps[index:]
        else:
            resume_steps = self._workflow_steps_for_background_task(task)

        for step in resume_steps:
            step.pop("series_incremental", None)
            step.pop("source_volume", None)
            step.pop("source_label", None)
            if step.get("type") in {"translate", "polish", "all_in_one"}:
                step["resume"] = True
        return resume_steps

    def find_task_by_file_path(self, file_path):
        """根据文件路径查找任务"""
        if not file_path:
            return None

        file_path = os.path.normpath(file_path)
        for i, task in enumerate(self.tasks):
            task_input_path = os.path.normpath(task.input_path)
            if task_input_path == file_path:
                return i, task
        return None, None

    @_serialized
    def skip_task_to_end(self, file_path):
        """Keep the claim until its worker exits; only then may the row move."""
        claim = getattr(self, "_worker_claim", None)
        index = self.resolve_index(claim[0]) if claim else -1
        if index < 0 or not file_path:
            return False, "No owned task to skip"
        task = self.tasks[index]
        if os.path.normpath(task.input_path) != os.path.normpath(file_path) or not task.locked:
            return False, "Task is not the current worker's claim"
        if any(not self.can_modify_task(pos) for pos in range(index + 1, len(self.tasks))):
            return False, "Cannot move another protected task"
        self._deferred_skip = claim
        return True, f"Task will move to position {len(self.tasks)}"

    @_serialized
    def start_queue(self, cli_menu, automation_background=False):
        if self.is_running:
            return
        self.is_running = True
        self.run_result = None
        self.last_run_error = None
        self._worker_claim = None
        self._run_done.clear()
        self._automation_stop_requested = False
        threading.Thread(target=self._process_queue, args=(cli_menu, automation_background), daemon=True).start()

    def wait_for_completion(self, timeout=None):
        return self._run_done.wait(timeout)

    def _process_queue(self, cli_menu, automation_background=False):
        try:
            completed = self._process_queue_steps(cli_menu, automation_background)
            if completed is not True and not self._automation_stop_requested and Base.work_status != Base.STATUS.STOPING:
                self.last_run_error = self.last_run_error or "QUEUE_EXECUTION_FAILED"
        except Exception as exc:
            self.last_run_error = "QUEUE_EXECUTION_FAILED"
            self.error(f"Queue execution failed: {type(exc).__name__}")
        finally:
            with self.state_lock:
                self.run_result = summarize_queue(
                    self.tasks,
                    stopped=self._automation_stop_requested or Base.work_status == Base.STATUS.STOPING,
                    error=self.last_run_error,
                )
                self._worker_claim = None
                self.is_running = False
                self._run_done.set()

    def request_automation_stop(self):
        self._automation_stop_requested = True

    def _process_queue_steps(self, cli_menu, automation_background=False):
        self.info("Starting task queue processing with full API overrides...")

        if automation_background:
            return self._process_background_queue(cli_menu)

        # Phase 0: Custom automation workflows
        if self._process_workflow_tasks(cli_menu) is False:
            return

        # Phase 1: Translation
        while True:
            if Base.work_status == Base.STATUS.STOPING: break

            # 热重载队列
            if not self.hot_reload_queue(quiet=True):
                self.error("Failed to reload queue state; stopping queue processing.")
                return

            # 清理过期的锁定状态
            if not self._cleanup_stale_locks_or_fail():
                self.error("Failed to persist stale queue-lock cleanup; stopping queue processing.")
                return

            # 优先处理运行期间新加入的自动化工作流任务
            if self._process_workflow_tasks(cli_menu) is False:
                self.error("Workflow queue state could not be persisted; stopping queue processing.")
                return

            # 查找下一个需要翻译的任务
            index, task = self.get_next_unlocked_task(statuses={"waiting"})
            if index is None:
                break  # 没有更多翻译任务

            if self.mark_task_executing(task) is False:
                self.error("Failed to persist queue task execution state.")
                return

            if task.task_type == TaskType.POLISH:
                if self.mark_task_completed(task.task_id, "translated") is False:
                    self.error("Failed to persist polish-only queue task state.")
                    return
                continue

            if task.task_type not in [TaskType.TRANSLATION, TaskType.TRANSLATE_AND_POLISH]:
                if self.mark_task_completed(task.task_id, "error") is False:
                    self.error("Failed to persist invalid queue task state.")
                    return
                continue

            if self._run_single_step(
                cli_menu,
                task,
                TaskType.TRANSLATION,
                resume=bool(getattr(task, "resume", False)),
            ):
                if Base.work_status == Base.STATUS.STOPING:
                    if self.mark_task_completed(task.task_id, "stopped") is False:
                        self.error("Failed to persist stopped queue task state.")
                        return
                    break
                # 完成后标记状态
                if task.task_type == TaskType.TRANSLATE_AND_POLISH:
                    if self.mark_task_completed(task.task_id, "translated") is False:
                        self.error("Failed to persist translated queue task state.")
                        return
                else:
                    if self.mark_task_completed(task.task_id, "completed") is False:
                        self.error("Failed to persist completed queue task state.")
                        return
            else:
                if self._is_external_agent_task(task):
                    # ``False`` means the external hand-off is waiting, not
                    # that an API translation failed.  Leave the durable
                    # waiting state for the Agent batch protocol to advance.
                    continue
                if self.mark_task_completed(
                    task.task_id,
                    "stopped" if Base.work_status == Base.STATUS.STOPING else "error",
                ) is False:
                    self.error("Failed to persist failed queue task state.")
                    return

        if Base.work_status == Base.STATUS.STOPING:
            self.info("Task queue processing stopped.")
            return

        # Phase 2: Polishing
        if Base.work_status != Base.STATUS.STOPING:
            while True:
                if Base.work_status == Base.STATUS.STOPING: break

                # 热重载队列
                if not self.hot_reload_queue():
                    self.error("Failed to reload queue state; stopping queue processing.")
                    return

                # 清理过期的锁定状态
                if not self._cleanup_stale_locks_or_fail():
                    self.error("Failed to persist stale queue-lock cleanup; stopping queue processing.")
                    return

                # 优先处理运行期间新加入的自动化工作流任务
                if self._process_workflow_tasks(cli_menu) is False:
                    self.error("Workflow queue state could not be persisted; stopping queue processing.")
                    return

                # 查找下一个需要润色的任务
                found_task = False
                for i, task in enumerate(self.tasks):
                    if self._task_has_workflow(task):
                        continue
                    if (not task.locked and
                        not self._is_external_agent_task(task) and
                        task.status == "translated" and
                        task.task_type in [TaskType.POLISH, TaskType.TRANSLATE_AND_POLISH]):

                        found_task = True
                        if self.mark_task_executing(task) is False:
                            self.error("Failed to persist polishing queue task state.")
                            return

                        if self._run_single_step(cli_menu, task, TaskType.POLISH, resume=True):
                            if Base.work_status == Base.STATUS.STOPING:
                                if self.mark_task_completed(task.task_id, "stopped") is False:
                                    self.error("Failed to persist stopped polishing task state.")
                                    return
                                break
                            if self.mark_task_completed(task.task_id, "completed") is False:
                                self.error("Failed to persist completed polishing task state.")
                                return
                        else:
                            if self.mark_task_completed(
                                task.task_id,
                                "stopped" if Base.work_status == Base.STATUS.STOPING else "error",
                            ) is False:
                                self.error("Failed to persist failed polishing task state.")
                                return
                        break

                if not found_task:
                    break  # 没有更多润色任务

        self.info("Task queue processing finished.")
        return True

    def _process_background_queue(self, cli_menu):
        try:
            idle_rounds = 0
            while True:
                if self._automation_stop_requested or Base.work_status == Base.STATUS.STOPING:
                    break

                if not self.hot_reload_queue(quiet=True):
                    self.last_run_error = self.last_run_error or "QUEUE_EXECUTION_FAILED"
                    self.error("Failed to reload background queue state; stopping queue processing.")
                    break
                if not self._cleanup_stale_locks_or_fail():
                    self.last_run_error = self.last_run_error or "QUEUE_EXECUTION_FAILED"
                    self.error("Failed to persist stale queue-lock cleanup; stopping background queue processing.")
                    break
                if self._ensure_background_workflow_tasks() is False:
                    self.last_run_error = self.last_run_error or "QUEUE_EXECUTION_FAILED"
                    break
                if self._process_workflow_tasks(cli_menu) is False:
                    self.last_run_error = self.last_run_error or "QUEUE_EXECUTION_FAILED"
                    break

                if not self.hot_reload_queue(quiet=True):
                    self.last_run_error = self.last_run_error or "QUEUE_EXECUTION_FAILED"
                    self.error("Failed to reload background queue state; stopping queue processing.")
                    break
                if self._has_background_pending_tasks():
                    idle_rounds = 0
                    continue

                idle_rounds += 1
                if idle_rounds >= 2:
                    break
                time.sleep(0.5)
        finally:
            self.info("Background task queue processing finished.")

        return self.last_run_error is None

    @_serialized
    def _ensure_background_workflow_tasks(self):
        previous_tasks = copy.deepcopy(self.tasks)
        changed = False
        for task in self.tasks:
            if self._is_external_agent_task(task):
                # Background automation is an API worker path.  Never attach
                # workflow steps to an external-Agent item, otherwise the
                # queue can accidentally claim it as a local subprocess task.
                continue
            if task.locked or self._task_has_workflow(task):
                continue
            if task.status not in {"waiting", "translated"}:
                continue

            steps = self._workflow_steps_for_background_task(task)
            if not steps:
                continue
            task.workflow_steps = steps
            changed = True

        if changed:
            if self.save_tasks() is False:
                self.tasks = previous_tasks
                return False
        return True

    def _workflow_steps_for_background_task(self, task):
        if task.status == "translated":
            return [{"type": "polish", "resume": True}]

        if task.task_type == TaskType.TRANSLATE_AND_POLISH:
            return [{"type": "all_in_one"}]
        if task.task_type == TaskType.POLISH:
            return [{"type": "polish", "resume": True}]
        return [{"type": "translate"}]

    def _has_background_pending_tasks(self):
        for task in self.tasks:
            if task.locked:
                continue
            if self._is_external_agent_task(task):
                continue
            if task.status in {"waiting", "translated"}:
                return True
        return False

    def _task_has_workflow(self, task):
        return bool(getattr(task, "workflow_steps", None))

    def _get_next_workflow_task(self):
        for i, task in enumerate(self.tasks):
            if (
                not task.locked
                and not self._is_external_agent_task(task)
                and task.status in {"waiting", "translated"}
                and self._task_has_workflow(task)
            ):
                return i, task
        return None, None

    def _process_workflow_tasks(self, cli_menu):
        while True:
            if self._automation_stop_requested or Base.work_status == Base.STATUS.STOPING:
                break

            if not self.hot_reload_queue(quiet=True):
                return False
            if not self._cleanup_stale_locks_or_fail():
                return False

            index, task = self._get_next_workflow_task()
            if index is None:
                break

            if self.mark_task_executing(task) is False:
                return False

            workflow_status = self._run_workflow_task(cli_menu, task)
            if workflow_status in {"completed", "partial", "enqueued"}:
                completed = self.mark_task_completed(
                    task.task_id,
                    workflow_status,
                    getattr(task, "_automation_final_state", None),
                )
            else:
                completed = self.mark_task_completed(
                    task.task_id,
                    "stopped" if workflow_status == "interrupted" else "error",
                )
            if completed is False:
                return False
        return True

    @_worker_update
    def _record_workflow_run(self, index, run_info):
        task = self.tasks[index]
        previous = task.automation_run_id, task.automation_progress_file, task.automation_worker_pid
        task.automation_run_id, task.automation_progress_file, task.automation_worker_pid = (
            run_info.get("run_id"), run_info.get("progress_file"), run_info.get("pid"))
        if self.save_tasks():
            return True
        task.automation_run_id, task.automation_progress_file, task.automation_worker_pid = previous
        return False

    def _run_workflow_task(self, cli_menu, task):
        try:
            from ModuleFolders.Infrastructure.Automation.AutomationProcessRunner import AutomationProcessRunner

            task_config = task.to_runtime_dict()
            if os.environ.get("AINIEE_BACKEND_WORKER") == "1":
                task_config["web_mode"] = True
            run_info = AutomationProcessRunner.start(
                task_config,
                project_root=getattr(cli_menu, "PROJECT_ROOT", None),
            )
            run_id = run_info.get("run_id")
            if not self._record_workflow_run(task.task_id, run_info):
                try:
                    from ModuleFolders.Infrastructure.Automation.AutomationProcessRunner import (
                        AutomationProcessRunner,
                    )
                    AutomationProcessRunner.terminate(
                        run_id,
                        "Automation workflow state could not be persisted",
                    )
                except Exception as terminate_error:
                    self.warning(
                        f"Failed to terminate unpersisted workflow task: {terminate_error}"
                    )
                return "error"

            process = AutomationProcessRunner.get_process(run_id)
            while process and process.poll() is None:
                if self._automation_stop_requested or Base.work_status == Base.STATUS.STOPING:
                    if AutomationProcessRunner.terminate(run_id, "Automation workflow interrupted by user"):
                        return "interrupted"
                    self.warning("Automation worker cancellation is still pending.")
                if not self.update_task_activity(task.task_id):
                    if AutomationProcessRunner.terminate(run_id, "Queue claim lost"):
                        return "error"
                    self.warning("Automation worker cancellation is still pending.")
                time.sleep(0.5)
            from ModuleFolders.Infrastructure.Automation.AutomationProgress import read_progress_file

            state = read_progress_file(run_info["progress_file"])
            task._automation_final_state = state
            status = state.get("status")
            if status in {"completed", "partial", "interrupted", "enqueued"}:
                return status
            state_status = self._workflow_status_from_progress_state(state)
            if state_status:
                return state_status
            return "completed" if process and process.returncode == 0 else "error"
        except Exception as e:
            self.error(f"Workflow Task Error: {e}")
            return "error"

    @staticmethod
    def _workflow_status_from_progress_state(state: dict):
        if not isinstance(state, dict):
            return None
        try:
            current = int(state.get("line") or state.get("completed") or 0)
            total = int(state.get("total_line") or state.get("total") or 0)
        except (TypeError, ValueError):
            return None
        if total <= 0:
            return None
        if current >= total:
            return "completed"
        if current > 0:
            return "partial"
        return None

    def _run_single_step(self, cli_menu, task, step_type, resume=False):
        if self._is_external_agent_task(task):
            # The deterministic API runner is intentionally unavailable for
            # external-Agent tasks.  Their status is advanced by the batch
            # protocol after an Agent session claims/submits/commits work.
            task.status = "waiting_for_agent"
            return False

        if self._task_has_workflow(task):
            return True

        original_active_profile = cli_menu.active_profile_name
        original_rules_profile = cli_menu.active_rules_profile_name
        original_root_config = copy.deepcopy(getattr(cli_menu, "root_config", {}))
        original_config = copy.deepcopy(getattr(cli_menu, "config", {}))
        original_runtime_overrides = copy.deepcopy(
            getattr(cli_menu, "runtime_config_overrides", {})
        )
        
        try:
            # 1. Apply Profile Base
            target_profile = task.profile or original_active_profile
            target_rules_profile = task.rules_profile or original_rules_profile
            cli_menu.load_config(
                active_profile_name=target_profile,
                active_rules_profile_name=target_rules_profile,
            )

            if task.extra.get("runtime_snapshot"):
                from ModuleFolders.Infrastructure.TaskConfig.RuntimeSnapshot import restore_runtime_snapshot
                cli_menu.config = restore_runtime_snapshot(cli_menu.config, task.extra["runtime_snapshot"])

            # 2. Apply Fine-grained Overrides
            cfg = cli_menu.config
            if task.runtime_overrides:
                cfg["_task_runtime_overrides"] = copy.deepcopy(task.runtime_overrides)
            if task.source_lang: cfg["source_language"] = task.source_lang
            if task.target_lang: cfg["target_language"] = task.target_lang
            if task.project_type: cfg["translation_project"] = task.project_type
            if task.output_path: cfg["label_output_path"] = task.output_path
            
            # --- API Overrides ---
            if task.platform: cfg["target_platform"] = task.platform
            if task.api_url: cfg["base_url"] = task.api_url
            if task.api_key: 
                cfg["api_key"] = task.api_key
                # 同步到具体平台字典中
                tp = cfg.get("target_platform")
                if tp and tp in cfg.get("platforms", {}):
                    cfg["platforms"][tp]["api_key"] = task.api_key
                    
            if task.model: cfg["model"] = task.model
            
            # --- Performance Overrides ---
            if task.threads is not None: cfg["user_thread_counts"] = task.threads
            if task.retry is not None: cfg["retry_count"] = task.retry
            if task.timeout is not None: cfg["request_timeout"] = task.timeout
            if task.rounds is not None: cfg["round_limit"] = task.rounds
            if task.pre_lines is not None: cfg["pre_line_counts"] = task.pre_lines
            
            if task.lines_limit is not None:
                cfg["tokens_limit_switch"] = False
                cfg["lines_limit"] = task.lines_limit
            if task.tokens_limit is not None:
                cfg["tokens_limit_switch"] = True
                cfg["tokens_limit"] = max(400, int(task.tokens_limit))
                
            if task.think_depth is not None:
                cfg["think_depth"] = task.think_depth
                tp = cfg.get("target_platform")
                if tp and tp in cfg.get("platforms", {}):
                    cfg["platforms"][tp]["think_depth"] = task.think_depth
            if task.thinking_budget is not None:
                cfg["thinking_budget"] = task.thinking_budget
                tp = cfg.get("target_platform")
                if tp and tp in cfg.get("platforms", {}):
                    cfg["platforms"][tp]["thinking_budget"] = task.thinking_budget
            if task.failover is not None:
                cfg["enable_api_failover"] = bool(task.failover)
            if task.polish_mode:
                runtime_overrides = getattr(cli_menu, "runtime_config_overrides", {})
                if not isinstance(runtime_overrides, dict):
                    runtime_overrides = {}
                runtime_overrides["polishing_mode_selection"] = task.polish_mode
                cli_menu.runtime_config_overrides = runtime_overrides

            # 3. Execute
            # 更新活动时间（心跳）
            if self.current_task_index >= 0 and not self.update_task_activity(task.task_id):
                return False

            skip_prompt_validation = False
            if step_type == TaskType.TRANSLATION and task.task_type == TaskType.TRANSLATE_AND_POLISH:
                if not cli_menu.prompt_selection_guard.ensure_prompts_selected(
                    TaskType.TRANSLATE_AND_POLISH,
                    interactive=False,
                ):
                    raise RuntimeError("Required prompt selection is missing for all-in-one task.")
                skip_prompt_validation = True
            elif step_type == TaskType.POLISH and task.task_type == TaskType.TRANSLATE_AND_POLISH:
                skip_prompt_validation = True

            task_ok = cli_menu.run_task(
                step_type,
                target_path=task.input_path,
                continue_status=resume,
                non_interactive=True,
                web_mode=os.environ.get("AINIEE_BACKEND_WORKER") == "1",
                from_queue=True,
                skip_prompt_validation=skip_prompt_validation,
                save_runtime_config=False,
                execution_mode=getattr(task, "execution_mode", "default_api"),
            )
            if not task_ok:
                if getattr(task, "execution_mode", "default_api") == "external_agent":
                    task.status = "waiting_for_agent"
                    return False
                raise RuntimeError("Task blocked before start.")
            
            return Base.work_status != Base.STATUS.STOPING
        except Exception as e:
            self.error(f"Task Error: {e}")
            return False
        finally:
            cli_menu.active_profile_name = original_active_profile
            cli_menu.active_rules_profile_name = original_rules_profile
            cli_menu.root_config = original_root_config
            cli_menu.config = original_config
            cli_menu.runtime_config_overrides = original_runtime_overrides
