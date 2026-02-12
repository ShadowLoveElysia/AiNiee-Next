"""
文件夹监控管理器
监控指定目录，检测新文件并自动加入翻译队列
"""
import os
import shutil
import threading
import time
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any, Set
from ModuleFolders.Base.Base import Base


class WatchRule:
    """监控规则"""

    def __init__(self, rule_id: str, watch_path: str, output_path: str = "",
                 done_path: str = "", file_patterns: List[str] = None,
                 profile: str = "default", task_type: str = "translation",
                 auto_start: bool = True, debounce_seconds: int = 5,
                 recursive: bool = False, enabled: bool = True,
                 move_to_done: bool = True, **kwargs):
        self.id = rule_id
        self.watch_path = os.path.abspath(watch_path)
        self.output_path = output_path
        self.done_path = done_path
        self.file_patterns = file_patterns or ["*.txt", "*.epub", "*.srt"]
        self.profile = profile
        self.task_type = task_type
        self.auto_start = auto_start
        self.debounce_seconds = debounce_seconds
        self.recursive = recursive
        self.enabled = enabled
        self.move_to_done = move_to_done
        self.extra = kwargs

        # 运行状态
        self.files_processed = 0
        self.last_activity: Optional[datetime] = None

    def matches_pattern(self, filename: str) -> bool:
        """检查文件是否匹配模式"""
        from fnmatch import fnmatch
        return any(fnmatch(filename.lower(), pattern.lower())
                   for pattern in self.file_patterns)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "watch_path": self.watch_path,
            "output_path": self.output_path,
            "done_path": self.done_path,
            "file_patterns": self.file_patterns,
            "profile": self.profile,
            "task_type": self.task_type,
            "auto_start": self.auto_start,
            "debounce_seconds": self.debounce_seconds,
            "recursive": self.recursive,
            "enabled": self.enabled,
            "move_to_done": self.move_to_done,
            **self.extra
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WatchRule":
        """从字典创建"""
        return cls(
            rule_id=data.get("id", ""),
            watch_path=data.get("watch_path", ""),
            output_path=data.get("output_path", ""),
            done_path=data.get("done_path", ""),
            file_patterns=data.get("file_patterns", ["*.txt", "*.epub", "*.srt"]),
            profile=data.get("profile", "default"),
            task_type=data.get("task_type", "translation"),
            auto_start=data.get("auto_start", True),
            debounce_seconds=data.get("debounce_seconds", 5),
            recursive=data.get("recursive", False),
            enabled=data.get("enabled", True),
            move_to_done=data.get("move_to_done", True)
        )


class FileState:
    """文件状态追踪"""

    def __init__(self, path: str):
        self.path = path
        self.size = 0
        self.mtime = 0
        self.hash = ""
        self.first_seen = datetime.now()
        self.stable_since: Optional[datetime] = None
        self.status = "pending"  # pending, stable, processing, done, error

    def update(self) -> bool:
        """更新文件状态，返回是否有变化"""
        try:
            stat = os.stat(self.path)
            new_size = stat.st_size
            new_mtime = stat.st_mtime

            if new_size != self.size or new_mtime != self.mtime:
                self.size = new_size
                self.mtime = new_mtime
                self.stable_since = None
                return True
            else:
                if self.stable_since is None:
                    self.stable_since = datetime.now()
                return False
        except OSError:
            return False

    def is_stable(self, debounce_seconds: int) -> bool:
        """检查文件是否稳定（不再被写入）"""
        if self.stable_since is None:
            return False
        elapsed = (datetime.now() - self.stable_since).total_seconds()
        return elapsed >= debounce_seconds


class WatchManager(Base):
    """文件夹监控管理器"""

    def __init__(self, task_callback: Callable[[dict], Any] = None,
                 queue_callback: Callable[[dict], Any] = None):
        super().__init__()
        self.task_callback = task_callback  # 直接执行任务
        self.queue_callback = queue_callback  # 加入队列
        self.rules: Dict[str, WatchRule] = {}
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # 文件状态追踪
        self.file_states: Dict[str, FileState] = {}
        self.processed_files: Set[str] = set()

        # 配置
        self.scan_interval = 10  # 扫描间隔（秒）
        self.max_concurrent = 2  # 最大并发任务数
        self.current_tasks = 0

        # 日志
        self.logs: List[dict] = []
        self.max_logs = 100

        # 持久化已处理文件记录
        self.processed_file_path = ""

    def set_callbacks(self, task_callback: Callable = None,
                      queue_callback: Callable = None):
        """设置回调函数"""
        if task_callback:
            self.task_callback = task_callback
        if queue_callback:
            self.queue_callback = queue_callback

    def add_rule(self, rule: WatchRule) -> bool:
        """添加监控规则"""
        with self._lock:
            if rule.id in self.rules:
                return False

            # 确保监控目录存在
            if not os.path.exists(rule.watch_path):
                try:
                    os.makedirs(rule.watch_path)
                except OSError as e:
                    self._log("error", f"Cannot create watch directory: {e}")
                    return False

            # 确保完成目录存在
            if rule.done_path and not os.path.exists(rule.done_path):
                try:
                    os.makedirs(rule.done_path)
                except OSError:
                    pass

            self.rules[rule.id] = rule
            self._log("info", f"Watch rule added: {rule.watch_path}")
            return True

    def remove_rule(self, rule_id: str) -> bool:
        """移除监控规则"""
        with self._lock:
            if rule_id in self.rules:
                rule = self.rules.pop(rule_id)
                self._log("info", f"Watch rule removed: {rule.watch_path}")
                return True
            return False

    def update_rule(self, rule_id: str, **kwargs) -> bool:
        """更新监控规则"""
        with self._lock:
            if rule_id not in self.rules:
                return False

            rule = self.rules[rule_id]
            for key, value in kwargs.items():
                if hasattr(rule, key):
                    setattr(rule, key, value)
            return True

    def get_rule(self, rule_id: str) -> Optional[WatchRule]:
        """获取规则"""
        return self.rules.get(rule_id)

    def get_all_rules(self) -> List[WatchRule]:
        """获取所有规则"""
        return list(self.rules.values())

    def start(self):
        """启动监控"""
        if self.running:
            return

        self.running = True
        self._stop_event.clear()
        self._load_processed_files()
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        self._log("info", "Watch manager started")

    def stop(self):
        """停止监控"""
        if not self.running:
            return

        self.running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._save_processed_files()
        self._log("info", "Watch manager stopped")

    def _watch_loop(self):
        """监控主循环"""
        while not self._stop_event.is_set():
            try:
                with self._lock:
                    for rule in self.rules.values():
                        if rule.enabled:
                            self._scan_directory(rule)

                # 等待下一次扫描
                self._stop_event.wait(self.scan_interval)

            except Exception as e:
                self._log("error", f"Watch loop error: {e}")
                time.sleep(30)

    def _scan_directory(self, rule: WatchRule):
        """扫描目录"""
        try:
            if rule.recursive:
                files = self._scan_recursive(rule.watch_path, rule)
            else:
                files = self._scan_flat(rule.watch_path, rule)

            for file_path in files:
                self._process_file(file_path, rule)

        except Exception as e:
            self._log("error", f"Scan error for {rule.watch_path}: {e}")

    def _scan_flat(self, directory: str, rule: WatchRule) -> List[str]:
        """扫描单层目录"""
        result = []
        try:
            for entry in os.scandir(directory):
                if entry.is_file() and rule.matches_pattern(entry.name):
                    result.append(entry.path)
        except OSError:
            pass
        return result

    def _scan_recursive(self, directory: str, rule: WatchRule) -> List[str]:
        """递归扫描目录"""
        result = []
        try:
            for root, dirs, files in os.walk(directory):
                # 排除输出目录和完成目录
                dirs[:] = [d for d in dirs if
                           os.path.join(root, d) not in [rule.output_path, rule.done_path]]

                for filename in files:
                    if rule.matches_pattern(filename):
                        result.append(os.path.join(root, filename))
        except OSError:
            pass
        return result

    def _process_file(self, file_path: str, rule: WatchRule):
        """处理检测到的文件"""
        # 检查是否已处理
        file_key = self._get_file_key(file_path)
        if file_key in self.processed_files:
            return

        # 获取或创建文件状态
        if file_path not in self.file_states:
            self.file_states[file_path] = FileState(file_path)

        state = self.file_states[file_path]

        # 更新状态
        state.update()

        # 检查文件是否稳定
        if not state.is_stable(rule.debounce_seconds):
            return

        # 检查并发限制
        if self.current_tasks >= self.max_concurrent:
            return

        # 标记为处理中
        state.status = "processing"
        self.current_tasks += 1

        # 创建任务
        task_config = {
            "input_path": file_path,
            "output_path": rule.output_path or self._generate_output_path(file_path),
            "profile": rule.profile,
            "task_type": rule.task_type,
            "source": "watch",
            "rule_id": rule.id,
            "auto_start": rule.auto_start
        }

        self._log("info", f"New file detected: {os.path.basename(file_path)}")

        # 执行或加入队列
        if rule.auto_start and self.task_callback:
            # 在新线程中执行
            exec_thread = threading.Thread(
                target=self._execute_task,
                args=(file_path, rule, task_config),
                daemon=True
            )
            exec_thread.start()
        elif self.queue_callback:
            # 加入队列
            try:
                self.queue_callback(task_config)
                self._mark_processed(file_path, rule, "queued")
            except Exception as e:
                self._log("error", f"Failed to queue task: {e}")
                state.status = "error"
                self.current_tasks -= 1

    def _execute_task(self, file_path: str, rule: WatchRule, task_config: dict):
        """执行任务"""
        state = self.file_states.get(file_path)
        try:
            self.task_callback(task_config)
            self._mark_processed(file_path, rule, "done")
            self._log("info", f"Task completed: {os.path.basename(file_path)}")
        except Exception as e:
            self._log("error", f"Task failed: {os.path.basename(file_path)} - {e}")
            if state:
                state.status = "error"
        finally:
            self.current_tasks -= 1

    def _mark_processed(self, file_path: str, rule: WatchRule, status: str):
        """标记文件已处理"""
        file_key = self._get_file_key(file_path)
        self.processed_files.add(file_key)

        state = self.file_states.get(file_path)
        if state:
            state.status = status

        rule.files_processed += 1
        rule.last_activity = datetime.now()

        # 移动到完成目录
        if rule.move_to_done and rule.done_path and status == "done":
            try:
                dest = os.path.join(rule.done_path, os.path.basename(file_path))
                # 处理同名文件
                if os.path.exists(dest):
                    base, ext = os.path.splitext(dest)
                    dest = f"{base}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
                shutil.move(file_path, dest)
                self._log("info", f"Moved to done: {os.path.basename(file_path)}")
            except Exception as e:
                self._log("warning", f"Failed to move file: {e}")

        # 清理状态
        if file_path in self.file_states:
            del self.file_states[file_path]

    def _get_file_key(self, file_path: str) -> str:
        """生成文件唯一标识"""
        # 使用路径 + 修改时间 + 大小作为标识
        try:
            stat = os.stat(file_path)
            key_str = f"{file_path}:{stat.st_mtime}:{stat.st_size}"
            return hashlib.md5(key_str.encode()).hexdigest()
        except OSError:
            return hashlib.md5(file_path.encode()).hexdigest()

    def _generate_output_path(self, input_path: str) -> str:
        """生成输出路径"""
        parent = os.path.dirname(input_path)
        return os.path.join(parent, "output")

    def _load_processed_files(self):
        """加载已处理文件记录"""
        if not self.processed_file_path:
            return

        try:
            if os.path.exists(self.processed_file_path):
                with open(self.processed_file_path, 'r', encoding='utf-8') as f:
                    self.processed_files = set(line.strip() for line in f)
        except Exception:
            pass

    def _save_processed_files(self):
        """保存已处理文件记录"""
        if not self.processed_file_path:
            return

        try:
            with open(self.processed_file_path, 'w', encoding='utf-8') as f:
                for file_key in self.processed_files:
                    f.write(file_key + '\n')
        except Exception:
            pass

    def _log(self, level: str, message: str):
        """记录日志"""
        log_entry = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "level": level,
            "message": message
        }
        self.logs.append(log_entry)

        if len(self.logs) > self.max_logs:
            self.logs = self.logs[-self.max_logs:]

    def get_logs(self, limit: int = 20) -> List[dict]:
        """获取最近的日志"""
        return self.logs[-limit:]

    def load_from_config(self, config: dict):
        """从配置加载规则"""
        watch_config = config.get("watch_mode", {})

        self.scan_interval = watch_config.get("scan_interval", 10)
        self.max_concurrent = watch_config.get("max_concurrent", 2)

        rules_data = watch_config.get("rules", [])
        for rule_data in rules_data:
            try:
                rule = WatchRule.from_dict(rule_data)
                self.add_rule(rule)
            except Exception as e:
                self._log("error", f"Failed to load rule: {e}")

    def save_to_config(self, config: dict):
        """保存规则到配置"""
        if "watch_mode" not in config:
            config["watch_mode"] = {}

        config["watch_mode"]["rules"] = [
            rule.to_dict() for rule in self.rules.values()
        ]
        config["watch_mode"]["enabled"] = self.running
        config["watch_mode"]["scan_interval"] = self.scan_interval
        config["watch_mode"]["max_concurrent"] = self.max_concurrent

    def get_status(self) -> dict:
        """获取监控状态"""
        return {
            "running": self.running,
            "rule_count": len(self.rules),
            "enabled_count": sum(1 for r in self.rules.values() if r.enabled),
            "pending_files": len([s for s in self.file_states.values()
                                  if s.status == "pending"]),
            "current_tasks": self.current_tasks,
            "total_processed": sum(r.files_processed for r in self.rules.values())
        }

    def clear_processed_history(self):
        """清除已处理文件历史"""
        self.processed_files.clear()
        self.file_states.clear()
        self._log("info", "Processed history cleared")
