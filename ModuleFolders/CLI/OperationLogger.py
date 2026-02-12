"""
用户操作记录器模块
记录用户在程序中的操作流程，用于LLM分析和问题诊断
"""

import threading
import collections
from datetime import datetime


class OperationLogger:
    """用户操作记录器 - 记录用户在程序中的操作流程，用于LLM分析"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, max_records=50):
        """单例模式，确保全局只有一个实例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, max_records=50):
        if self._initialized:
            return
        self._rlock = threading.RLock()
        self._records = collections.deque(maxlen=max_records)
        self._enabled = False
        self._start_time = None
        self._initialized = True

    @classmethod
    def get_instance(cls):
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def enable(self):
        """启用操作记录"""
        with self._rlock:
            self._enabled = True
            self._start_time = datetime.now()
            self._records.clear()
            self.log("程序启动", "APP_START")

    def disable(self):
        """禁用操作记录"""
        with self._rlock:
            self._enabled = False
            self._records.clear()
            self._start_time = None

    def is_enabled(self):
        """检查是否启用"""
        return self._enabled

    def log(self, action: str, category: str = "MENU"):
        """记录一条操作

        Args:
            action: 操作描述
            category: 操作类别 (MENU, TASK, ERROR, APP_START, CONFIG 等)
        """
        if not self._enabled:
            return
        with self._rlock:
            timestamp = datetime.now().strftime("%H:%M:%S")
            self._records.append({
                "time": timestamp,
                "category": category,
                "action": action
            })

    def get_records(self) -> list:
        """获取所有记录"""
        with self._rlock:
            return list(self._records)

    def get_formatted_log(self) -> str:
        """获取格式化的操作日志，用于发送给LLM"""
        with self._rlock:
            if not self._records:
                return "无操作记录"

            lines = ["用户操作流程:"]
            for i, rec in enumerate(self._records, 1):
                lines.append(f"  {i}. [{rec['time']}] [{rec['category']}] {rec['action']}")
            return "\n".join(lines)

    def clear(self):
        """清空记录"""
        with self._rlock:
            self._records.clear()


# 便捷函数，供外部直接调用
def log_operation(action: str, category: str = "MENU"):
    """记录一条操作（便捷函数）"""
    OperationLogger.get_instance().log(action, category)


def get_operation_log() -> str:
    """获取格式化的操作日志（便捷函数）"""
    return OperationLogger.get_instance().get_formatted_log()


def is_logging_enabled() -> bool:
    """检查操作记录是否启用（便捷函数）"""
    return OperationLogger.get_instance().is_enabled()
