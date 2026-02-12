"""
定时任务调度管理器
支持 cron 表达式和简单时间规则
"""
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Any
from ModuleFolders.Base.Base import Base


class CronParser:
    """简单的 Cron 表达式解析器"""

    @staticmethod
    def parse(cron_expr: str) -> dict:
        """
        解析 cron 表达式: 分 时 日 月 周
        支持: *, */n, n, n-m, n,m,o
        """
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {cron_expr}")

        return {
            "minute": CronParser._parse_field(parts[0], 0, 59),
            "hour": CronParser._parse_field(parts[1], 0, 23),
            "day": CronParser._parse_field(parts[2], 1, 31),
            "month": CronParser._parse_field(parts[3], 1, 12),
            "weekday": CronParser._parse_field(parts[4], 0, 6),  # 0=周日
        }

    @staticmethod
    def _parse_field(field: str, min_val: int, max_val: int) -> set:
        """解析单个字段"""
        result = set()

        for part in field.split(","):
            if part == "*":
                result.update(range(min_val, max_val + 1))
            elif part.startswith("*/"):
                step = int(part[2:])
                result.update(range(min_val, max_val + 1, step))
            elif "-" in part:
                start, end = map(int, part.split("-"))
                result.update(range(start, end + 1))
            else:
                result.add(int(part))

        return result

    @staticmethod
    def matches(cron_dict: dict, dt: datetime) -> bool:
        """检查时间是否匹配 cron 规则"""
        return (
            dt.minute in cron_dict["minute"] and
            dt.hour in cron_dict["hour"] and
            dt.day in cron_dict["day"] and
            dt.month in cron_dict["month"] and
            dt.weekday() in cron_dict["weekday"]  # Python: 0=周一, 需要转换
        )


class ScheduledTask:
    """定时任务"""

    def __init__(self, task_id: str, name: str, schedule: str,
                 input_path: str, profile: str = "default",
                 task_type: str = "translation", enabled: bool = True,
                 output_path: str = "", **kwargs):
        self.id = task_id
        self.name = name
        self.schedule = schedule
        self.input_path = input_path
        self.output_path = output_path
        self.profile = profile
        self.task_type = task_type
        self.enabled = enabled
        self.extra = kwargs

        # 解析 cron 表达式
        self.cron_dict = CronParser.parse(schedule)

        # 运行状态
        self.last_run: Optional[datetime] = None
        self.next_run: Optional[datetime] = None
        self.run_count = 0
        self.last_status = ""

        self._calculate_next_run()

    def _calculate_next_run(self):
        """计算下次运行时间"""
        now = datetime.now()
        # 从下一分钟开始检查
        check_time = now.replace(second=0, microsecond=0) + timedelta(minutes=1)

        # 最多检查未来 7 天
        for _ in range(7 * 24 * 60):
            # 转换 weekday: Python 0=周一, cron 0=周日
            cron_weekday = (check_time.weekday() + 1) % 7

            if (check_time.minute in self.cron_dict["minute"] and
                check_time.hour in self.cron_dict["hour"] and
                check_time.day in self.cron_dict["day"] and
                check_time.month in self.cron_dict["month"] and
                cron_weekday in self.cron_dict["weekday"]):
                self.next_run = check_time
                return

            check_time += timedelta(minutes=1)

        self.next_run = None

    def should_run(self, current_time: datetime) -> bool:
        """检查是否应该运行"""
        if not self.enabled or not self.next_run:
            return False

        # 检查是否到达运行时间（允许 1 分钟误差）
        if current_time >= self.next_run:
            return True

        return False

    def mark_run(self, status: str = "success"):
        """标记已运行"""
        self.last_run = datetime.now()
        self.last_status = status
        self.run_count += 1
        self._calculate_next_run()

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "schedule": self.schedule,
            "input_path": self.input_path,
            "output_path": self.output_path,
            "profile": self.profile,
            "task_type": self.task_type,
            "enabled": self.enabled,
            **self.extra
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScheduledTask":
        """从字典创建"""
        return cls(
            task_id=data.get("id", ""),
            name=data.get("name", ""),
            schedule=data.get("schedule", "0 0 * * *"),
            input_path=data.get("input_path", ""),
            output_path=data.get("output_path", ""),
            profile=data.get("profile", "default"),
            task_type=data.get("task_type", "translation"),
            enabled=data.get("enabled", True)
        )


class SchedulerManager(Base):
    """定时任务调度管理器"""

    def __init__(self, execute_callback: Callable[[dict], Any] = None):
        super().__init__()
        self.execute_callback = execute_callback
        self.tasks: Dict[str, ScheduledTask] = {}
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # 日志
        self.logs: List[dict] = []
        self.max_logs = 100

    def set_callback(self, callback: Callable[[dict], Any]):
        """设置执行回调"""
        self.execute_callback = callback

    def add_task(self, task: ScheduledTask) -> bool:
        """添加定时任务"""
        with self._lock:
            if task.id in self.tasks:
                return False
            self.tasks[task.id] = task
            self._log("info", f"Task added: {task.name} ({task.schedule})")
            return True

    def remove_task(self, task_id: str) -> bool:
        """移除定时任务"""
        with self._lock:
            if task_id in self.tasks:
                task = self.tasks.pop(task_id)
                self._log("info", f"Task removed: {task.name}")
                return True
            return False

    def update_task(self, task_id: str, **kwargs) -> bool:
        """更新任务配置"""
        with self._lock:
            if task_id not in self.tasks:
                return False

            task = self.tasks[task_id]
            for key, value in kwargs.items():
                if hasattr(task, key):
                    setattr(task, key, value)

            # 如果更新了 schedule，重新解析
            if "schedule" in kwargs:
                task.cron_dict = CronParser.parse(kwargs["schedule"])
                task._calculate_next_run()

            return True

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """获取任务"""
        return self.tasks.get(task_id)

    def get_all_tasks(self) -> List[ScheduledTask]:
        """获取所有任务"""
        return list(self.tasks.values())

    def start(self):
        """启动调度器"""
        if self.running:
            return

        self.running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._log("info", "Scheduler started")

    def stop(self):
        """停止调度器"""
        if not self.running:
            return

        self.running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._log("info", "Scheduler stopped")

    def _run_loop(self):
        """调度主循环"""
        while not self._stop_event.is_set():
            try:
                now = datetime.now()

                with self._lock:
                    for task in self.tasks.values():
                        if task.should_run(now):
                            self._execute_task(task)

                # 每 30 秒检查一次
                self._stop_event.wait(30)

            except Exception as e:
                self._log("error", f"Scheduler error: {e}")
                time.sleep(60)

    def _execute_task(self, task: ScheduledTask):
        """执行任务"""
        self._log("info", f"Executing task: {task.name}")

        try:
            if self.execute_callback:
                task_config = {
                    "input_path": task.input_path,
                    "output_path": task.output_path,
                    "profile": task.profile,
                    "task_type": task.task_type,
                    "task_id": task.id,
                    "task_name": task.name
                }

                # 在新线程中执行，避免阻塞调度器
                exec_thread = threading.Thread(
                    target=self._run_task_thread,
                    args=(task, task_config),
                    daemon=True
                )
                exec_thread.start()
            else:
                self._log("warning", "No execute callback configured")
                task.mark_run("skipped")

        except Exception as e:
            self._log("error", f"Task execution failed: {task.name} - {e}")
            task.mark_run("error")

    def _run_task_thread(self, task: ScheduledTask, task_config: dict):
        """在线程中执行任务"""
        try:
            self.execute_callback(task_config)
            task.mark_run("success")
            self._log("info", f"Task completed: {task.name}")
        except Exception as e:
            task.mark_run("error")
            self._log("error", f"Task failed: {task.name} - {e}")

    def _log(self, level: str, message: str):
        """记录日志"""
        log_entry = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "level": level,
            "message": message
        }
        self.logs.append(log_entry)

        # 限制日志数量
        if len(self.logs) > self.max_logs:
            self.logs = self.logs[-self.max_logs:]

    def get_logs(self, limit: int = 20) -> List[dict]:
        """获取最近的日志"""
        return self.logs[-limit:]

    def load_from_config(self, config: dict):
        """从配置加载任务"""
        scheduler_config = config.get("scheduler", {})
        tasks_data = scheduler_config.get("tasks", [])

        for task_data in tasks_data:
            try:
                task = ScheduledTask.from_dict(task_data)
                self.add_task(task)
            except Exception as e:
                self._log("error", f"Failed to load task: {e}")

    def save_to_config(self, config: dict):
        """保存任务到配置"""
        if "scheduler" not in config:
            config["scheduler"] = {}

        config["scheduler"]["tasks"] = [
            task.to_dict() for task in self.tasks.values()
        ]
        config["scheduler"]["enabled"] = self.running

    def get_status(self) -> dict:
        """获取调度器状态"""
        return {
            "running": self.running,
            "task_count": len(self.tasks),
            "enabled_count": sum(1 for t in self.tasks.values() if t.enabled),
            "next_task": self._get_next_task_info()
        }

    def _get_next_task_info(self) -> Optional[dict]:
        """获取下一个要执行的任务信息"""
        next_task = None
        next_time = None

        for task in self.tasks.values():
            if task.enabled and task.next_run:
                if next_time is None or task.next_run < next_time:
                    next_time = task.next_run
                    next_task = task

        if next_task:
            return {
                "id": next_task.id,
                "name": next_task.name,
                "next_run": next_task.next_run.strftime("%Y-%m-%d %H:%M")
            }
        return None
