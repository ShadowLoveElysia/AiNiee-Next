import threading
import time
import os
import rapidjson as json
from datetime import datetime, timedelta
from ModuleFolders.Base.Base import Base
from ModuleFolders.Infrastructure.TaskConfig.TaskType import TaskType

class QueueTaskItem:
    def __init__(self, task_type, input_path, output_path=None, profile=None, rules_profile=None, 
                 source_lang=None, target_lang=None, project_type=None,
                 platform=None, api_url=None, api_key=None, model=None, 
                 threads=None, retry=None, timeout=None, rounds=None, 
                 pre_lines=None, lines_limit=None, tokens_limit=None, 
                 think_depth=None, thinking_budget=None):
        self.task_type = task_type
        self.input_path = input_path
        self.output_path = output_path
        self.profile = profile
        self.rules_profile = rules_profile
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.project_type = project_type
        
        # 精细化 API 覆盖参数
        self.platform = platform
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        
        # 性能覆盖参数
        self.threads = threads
        self.retry = retry
        self.timeout = timeout
        self.rounds = rounds
        self.pre_lines = pre_lines
        self.lines_limit = lines_limit
        self.tokens_limit = tokens_limit
        self.think_depth = think_depth
        self.thinking_budget = thinking_budget
        
        self.status = "waiting" # waiting, translating, translated, polishing, completed, error, stopped
        self.locked = False  # 是否被锁定（正在执行中不可修改）

        # 新增：准确的处理状态跟踪
        self.is_processing = False  # 是否真正在处理中
        self.last_activity_time = None  # 最后活动时间（ISO格式字符串）
        self.process_start_time = None  # 处理开始时间

    def to_dict(self):
        d = {k: v for k, v in vars(self).items() if not k.startswith('_')}
        return d

    @classmethod
    def from_dict(cls, data):
        # 兼容旧数据，剔除运行时字段后传入构造函数
        params = data.copy()
        status = params.pop("status", "waiting")
        locked = params.pop("locked", False)  # 移除locked字段，它不属于构造函数参数

        # 新增字段的处理（兼容旧数据）
        is_processing = params.pop("is_processing", False)
        last_activity_time = params.pop("last_activity_time", None)
        process_start_time = params.pop("process_start_time", None)

        item = cls(**params)
        item.status = status
        item.locked = locked
        item.is_processing = is_processing
        item.last_activity_time = last_activity_time
        item.process_start_time = process_start_time
        return item

class QueueManager(Base):
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(QueueManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
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
        self.is_running = False
        self.current_task_index = -1
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

    def load_tasks(self, custom_path=None):
        if custom_path:
            self.queue_file = custom_path
        if os.path.exists(self.queue_file):
            try:
                with open(self.queue_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.tasks = [QueueTaskItem.from_dict(d) for d in data]
            except Exception as e:
                self.error(f"Failed to load queue tasks: {e}")
                self.tasks = []
        else:
            self.tasks = []

    def save_tasks(self):
        try:
            os.makedirs(os.path.dirname(self.queue_file), exist_ok=True)
            with open(self.queue_file, 'w', encoding='utf-8') as f:
                json.dump([t.to_dict() for t in self.tasks], f, indent=4, ensure_ascii=False)
        except Exception as e:
            self.error(f"Failed to save queue tasks: {e}")

    def add_task(self, task_item):
        self.tasks.append(task_item)
        self.save_tasks()

    def remove_task(self, index):
        if 0 <= index < len(self.tasks):
            task_name = os.path.basename(self.tasks[index].input_path)
            self.tasks.pop(index)
            self.save_tasks()
            self.hot_reload_queue(quiet=True)  # 静默热刷新队列
            self._log_queue_operation(Base.i18n.get('msg_task_removed').format(task_name))
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
                        changes.append(Base.i18n.get('param_added').format(Base.i18n.get(i18n_key), new_display))
                    elif old_value is not None and new_value is None:
                        changes.append(Base.i18n.get('param_removed').format(Base.i18n.get(i18n_key)))
                    elif old_value != new_value:
                        changes.append(Base.i18n.get('param_changed').format(Base.i18n.get(i18n_key), old_display, new_display))
            else:
                # 普通参数的处理
                if old_value != new_value:
                    if old_value is None and new_value is not None:
                        changes.append(Base.i18n.get('param_added').format(Base.i18n.get(i18n_key), new_value))
                    elif old_value is not None and new_value is None:
                        changes.append(Base.i18n.get('param_removed').format(Base.i18n.get(i18n_key)))
                    elif old_value != new_value:
                        changes.append(Base.i18n.get('param_changed').format(Base.i18n.get(i18n_key), old_value, new_value))

        return changes

    def _mask_sensitive_value(self, value):
        """遮掩敏感信息"""
        if value is None:
            return None
        if len(str(value)) <= 8:
            return "****"
        else:
            return str(value)[:4] + "****" + str(value)[-4:]

    def update_task(self, index, task_item):
        if 0 <= index < len(self.tasks):
            try:
                old_task = self.tasks[index]
                task_name = os.path.basename(old_task.input_path)

                # 检测参数变更
                changes = self.detect_parameter_changes(old_task, task_item)

                # 更新任务
                self.tasks[index] = task_item
                self.save_tasks()
                self.hot_reload_queue(quiet=True)

                # 打印详细的变更日志
                if changes:
                    self._log_queue_operation(Base.i18n.get('msg_task_updated').format(task_name))
                    for change in changes:
                        self._log_queue_operation(change)
                else:
                    # 如果没有参数变更，只是简单的更新
                    self._log_queue_operation(f"[INFO] {Base.i18n.get('msg_task_updated').format(task_name)} {Base.i18n.get('msg_no_config_changes')}")

            except Exception as e:
                self._log_queue_operation(f"[ERROR] Failed to update task: {e}")
                return False

            return True
        return False

    def clear_tasks(self):
        self.tasks = []
        self.save_tasks()
        return True

    def lock_task(self, index):
        """锁定任务（正在执行中）"""
        if 0 <= index < len(self.tasks):
            self.tasks[index].locked = True
            self.save_tasks()
            return True
        return False

    def unlock_task(self, index):
        """解锁任务"""
        if 0 <= index < len(self.tasks):
            self.tasks[index].locked = False
            self.save_tasks()
            return True
        return False

    def can_modify_task(self, index):
        """检查任务是否可以被修改（未锁定）"""
        if 0 <= index < len(self.tasks):
            return not self.tasks[index].locked
        return False

    # ================ 智能处理状态管理 ================

    def update_task_activity(self, index):
        """更新任务活动时间（心跳机制）"""
        if 0 <= index < len(self.tasks):
            self.tasks[index].last_activity_time = datetime.now().isoformat()
            self.save_tasks()
            return True
        return False

    def start_task_processing(self, index):
        """开始处理任务 - 设置处理状态和时间戳"""
        if 0 <= index < len(self.tasks):
            task = self.tasks[index]
            now = datetime.now().isoformat()
            task.is_processing = True
            task.process_start_time = now
            task.last_activity_time = now
            task.locked = True
            self.save_tasks()
            return True
        return False

    def stop_task_processing(self, index):
        """停止处理任务 - 清除处理状态"""
        if 0 <= index < len(self.tasks):
            task = self.tasks[index]
            task.is_processing = False
            task.process_start_time = None
            task.last_activity_time = None
            task.locked = False
            self.save_tasks()
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

    def cleanup_stale_locks(self, timeout_minutes=5):
        """
        清理过期的锁定状态

        Args:
            timeout_minutes: 超时时间（分钟）

        Returns:
            int: 清理的任务数量
        """
        cleaned_count = 0

        for i, task in enumerate(self.tasks):
            if task.locked and not self.is_task_actually_processing(i, timeout_minutes):
                self.info(f"Cleaning stale lock for task {i+1}: {task.input_path}")
                task.locked = False
                task.is_processing = False
                task.process_start_time = None
                task.last_activity_time = None

                # 重置状态到合适的值
                if task.status in ["translating", "polishing"]:
                    task.status = "waiting"

                cleaned_count += 1

        if cleaned_count > 0:
            self.save_tasks()
            self.info(f"Cleaned {cleaned_count} stale task locks")

        return cleaned_count

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
        """将指定索引的任务向上移动一位"""
        if (1 <= index < len(self.tasks) and
            self.can_modify_task(index) and self.can_modify_task(index - 1)):
            task_name = os.path.basename(self.tasks[index].input_path)
            self.tasks[index], self.tasks[index - 1] = self.tasks[index - 1], self.tasks[index]
            self.save_tasks()
            self.hot_reload_queue(quiet=True)  # 静默热刷新队列
            self._log_queue_operation(Base.i18n.get('msg_task_moved_up').format(task_name, index+1, index))
            return True
        return False

    def move_task_down(self, index):
        """将指定索引的任务向下移动一位"""
        if (0 <= index < len(self.tasks) - 1 and
            self.can_modify_task(index) and self.can_modify_task(index + 1)):
            task_name = os.path.basename(self.tasks[index].input_path)
            self.tasks[index], self.tasks[index + 1] = self.tasks[index + 1], self.tasks[index]
            self.save_tasks()
            self.hot_reload_queue(quiet=True)  # 静默热刷新队列
            self._log_queue_operation(Base.i18n.get('msg_task_moved_down').format(task_name, index+1, index+2))
            return True
        return False

    def move_task(self, from_index, to_index):
        """将任务从from_index移动到to_index位置"""
        if (0 <= from_index < len(self.tasks) and
            0 <= to_index < len(self.tasks) and
            from_index != to_index and
            self.can_modify_task(from_index)):

            # 检查移动路径上是否有锁定的任务
            start, end = min(from_index, to_index), max(from_index, to_index)
            for i in range(start, end + 1):
                if i != from_index and not self.can_modify_task(i):
                    return False

            # 移除任务
            task = self.tasks.pop(from_index)
            task_name = os.path.basename(task.input_path)
            # 插入到新位置
            self.tasks.insert(to_index, task)
            self.save_tasks()
            self.hot_reload_queue(quiet=True)  # 静默热刷新队列
            self._log_queue_operation(Base.i18n.get('msg_task_moved').format(task_name, from_index+1, to_index+1))
            return True
        return False

    def reorder_tasks(self, new_order):
        """根据新的索引顺序重新排列任务

        Args:
            new_order: 新的索引顺序列表，如 [2, 0, 1] 表示原来的第2个任务移到第0位
        """
        if (len(new_order) == len(self.tasks) and
            set(new_order) == set(range(len(self.tasks)))):

            # 重新排序任务
            self.tasks = [self.tasks[i] for i in new_order]
            self.save_tasks()
            return True
        return False

    def hot_reload_queue(self, quiet=False):
        """热重载队列：在不影响锁定任务的情况下重新加载队列

        Args:
            quiet (bool): 如果为True，不打印成功日志。用于操作后的静默刷新。
        """
        if not os.path.exists(self.queue_file):
            return False

        try:
            # 保存当前锁定状态
            locked_states = {}
            for i, task in enumerate(self.tasks):
                if task.locked:
                    locked_states[i] = {
                        'task_id': f"{task.task_type}_{task.input_path}",
                        'status': task.status
                    }

            # 重新加载任务
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                new_tasks = [QueueTaskItem.from_dict(d) for d in data]

            # 恢复锁定状态（通过任务特征匹配）
            for i, new_task in enumerate(new_tasks):
                task_id = f"{new_task.task_type}_{new_task.input_path}"
                for old_index, locked_info in locked_states.items():
                    if locked_info['task_id'] == task_id:
                        new_task.locked = True
                        new_task.status = locked_info['status']
                        break

            self.tasks = new_tasks

            # 只有在非静默模式下才打印成功日志
            if not quiet:
                self.info("Queue hot reloaded successfully.")
            return True

        except Exception as e:
            self.error(f"Failed to hot reload queue: {e}")
            return False

    def get_next_unlocked_task(self, start_index=0):
        """获取下一个未锁定的待执行任务"""
        for i in range(start_index, len(self.tasks)):
            task = self.tasks[i]
            if not task.locked and task.status in ["waiting", "translated"]:
                return i, task
        return None, None

    def mark_task_executing(self, index):
        """标记任务为执行中并锁定 - 使用智能处理状态管理"""
        if 0 <= index < len(self.tasks):
            task = self.tasks[index]

            # 使用新的智能处理状态管理
            self.start_task_processing(index)

            # 设置合适的状态
            if task.status == "waiting":
                task.status = "translating"
            elif task.status == "translated":
                task.status = "polishing"

            self.current_task_index = index
            self.save_tasks()
            return True
        return False

    def mark_task_completed(self, index, final_status="completed"):
        """标记任务完成并解锁 - 使用智能处理状态管理"""
        if 0 <= index < len(self.tasks):
            task = self.tasks[index]

            # 使用新的智能处理状态管理
            self.stop_task_processing(index)

            task.status = final_status
            self.save_tasks()
            return True
        return False

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

    def skip_task_to_end(self, file_path):
        """跳过任务并移动到队列末尾"""
        try:
            task_index, task = self.find_task_by_file_path(file_path)
            if task_index is None:
                return False, "Task not found in queue"

            if not task.locked:
                return False, "Task is not currently locked"

            # 解锁任务并重置状态
            task.locked = False
            task.status = "waiting"

            # 移动到队列末尾
            moved_task = self.tasks.pop(task_index)
            self.tasks.append(moved_task)

            # 保存队列
            self.save_tasks()

            file_name = os.path.basename(file_path)
            self.info(f"Task [{file_name}] skipped and moved to end of queue")
            return True, f"Task moved to position {len(self.tasks)}"

        except Exception as e:
            self.error(f"Failed to skip task: {e}")
            return False, str(e)

    def start_queue(self, cli_menu):
        if self.is_running: return
        self.is_running = True
        threading.Thread(target=self._process_queue, args=(cli_menu,), daemon=True).start()

    def _process_queue(self, cli_menu):
        self.info("Starting task queue processing with full API overrides...")

        # Phase 1: Translation
        while True:
            if Base.work_status == Base.STATUS.STOPING: break

            # 热重载队列
            self.hot_reload_queue(quiet=True)

            # 清理过期的锁定状态
            self.cleanup_stale_locks()

            # 查找下一个需要翻译的任务
            index, task = self.get_next_unlocked_task()
            if index is None:
                break  # 没有更多翻译任务

            if task.task_type not in [TaskType.TRANSLATION, TaskType.TRANSLATE_AND_POLISH]:
                # 标记为完成并继续
                self.mark_task_completed(index, "completed")
                continue

            # 标记任务为执行中
            self.mark_task_executing(index)

            try:
                self._run_single_step(cli_menu, task, TaskType.TRANSLATION)

                # 完成后标记状态
                if task.task_type == TaskType.TRANSLATE_AND_POLISH:
                    self.mark_task_completed(index, "translated")
                else:
                    self.mark_task_completed(index, "completed")
            except Exception as e:
                self.error(f"Task {index+1} failed: {e}")
                self.mark_task_completed(index, "error")

        # Phase 2: Polishing
        if Base.work_status != Base.STATUS.STOPING:
            while True:
                if Base.work_status == Base.STATUS.STOPING: break

                # 热重载队列
                self.hot_reload_queue()

                # 清理过期的锁定状态
                self.cleanup_stale_locks()

                # 查找下一个需要润色的任务
                found_task = False
                for i, task in enumerate(self.tasks):
                    if (not task.locked and
                        task.status == "translated" and
                        task.task_type in [TaskType.POLISH, TaskType.TRANSLATE_AND_POLISH]):

                        found_task = True
                        self.mark_task_executing(i)

                        try:
                            self._run_single_step(cli_menu, task, TaskType.POLISH, resume=True)
                            self.mark_task_completed(i, "completed")
                        except Exception as e:
                            self.error(f"Polish task {i+1} failed: {e}")
                            self.mark_task_completed(i, "error")
                        break

                if not found_task:
                    break  # 没有更多润色任务

        self.is_running = False
        self.info("Task queue processing finished.")

    def _run_single_step(self, cli_menu, task, step_type, resume=False):
        original_active_profile = cli_menu.active_profile_name
        original_rules_profile = cli_menu.active_rules_profile_name
        
        try:
            # 1. Apply Profile Base
            if task.profile: cli_menu.active_profile_name = task.profile
            if task.rules_profile: cli_menu.active_rules_profile_name = task.rules_profile
            cli_menu.load_config()

            # 2. Apply Fine-grained Overrides
            cfg = cli_menu.config
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
                cfg["tokens_limit"] = task.tokens_limit
                
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

            # 3. Execute
            # 更新活动时间（心跳）
            if self.current_task_index >= 0:
                self.update_task_activity(self.current_task_index)

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
                from_queue=True,
                skip_prompt_validation=skip_prompt_validation,
            )
            if not task_ok:
                raise RuntimeError("Task blocked before start.")
            
            if Base.work_status != Base.STATUS.STOPING:
                if step_type == TaskType.TRANSLATION and task.task_type == TaskType.TRANSLATE_AND_POLISH:
                    task.status = "translated"
                else:
                    task.status = "completed"
        except Exception as e:
            self.error(f"Task Error: {e}")
            task.status = "error"
        finally:
            self.save_tasks()
            cli_menu.active_profile_name = original_active_profile
            cli_menu.active_rules_profile_name = original_rules_profile
            cli_menu.load_config()
