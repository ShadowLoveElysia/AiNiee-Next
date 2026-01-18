import threading
import time
import os
import rapidjson as json
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

    def to_dict(self):
        d = {k: v for k, v in vars(self).items() if not k.startswith('_')}
        return d

    @classmethod
    def from_dict(cls, data):
        # 兼容旧数据，剔除运行时字段后传入构造函数
        params = data.copy()
        status = params.pop("status", "waiting")
        locked = params.pop("locked", False)  # 移除locked字段，它不属于构造函数参数
        item = cls(**params)
        item.status = status
        item.locked = locked
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
        self.tasks = []
        self.is_running = False
        self.current_task_index = -1
        self.load_tasks()
        self._initialized = True

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
            self.tasks.pop(index)
            self.save_tasks()
            return True
        return False

    def update_task(self, index, task_item):
        if 0 <= index < len(self.tasks):
            self.tasks[index] = task_item
            self.save_tasks()
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

    def move_task_up(self, index):
        """将指定索引的任务向上移动一位"""
        if (1 <= index < len(self.tasks) and
            self.can_modify_task(index) and self.can_modify_task(index - 1)):
            self.tasks[index], self.tasks[index - 1] = self.tasks[index - 1], self.tasks[index]
            self.save_tasks()
            return True
        return False

    def move_task_down(self, index):
        """将指定索引的任务向下移动一位"""
        if (0 <= index < len(self.tasks) - 1 and
            self.can_modify_task(index) and self.can_modify_task(index + 1)):
            self.tasks[index], self.tasks[index + 1] = self.tasks[index + 1], self.tasks[index]
            self.save_tasks()
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
            # 插入到新位置
            self.tasks.insert(to_index, task)
            self.save_tasks()
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

    def hot_reload_queue(self):
        """热重载队列：在不影响锁定任务的情况下重新加载队列"""
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
        """标记任务为执行中并锁定"""
        if 0 <= index < len(self.tasks):
            task = self.tasks[index]
            task.locked = True
            if task.status == "waiting":
                task.status = "translating"
            elif task.status == "translated":
                task.status = "polishing"
            self.save_tasks()
            self.current_task_index = index
            return True
        return False

    def mark_task_completed(self, index, final_status="completed"):
        """标记任务完成并解锁"""
        if 0 <= index < len(self.tasks):
            task = self.tasks[index]
            task.locked = False
            task.status = final_status
            self.save_tasks()
            return True
        return False

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
            self.hot_reload_queue()

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
                
            if task.think_depth is not None: cfg["think_depth"] = task.think_depth
            if task.thinking_budget is not None: cfg["thinking_budget"] = task.thinking_budget

            # 3. Execute
            cli_menu.run_task(step_type, target_path=task.input_path, continue_status=resume, non_interactive=True, from_queue=True)
            
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