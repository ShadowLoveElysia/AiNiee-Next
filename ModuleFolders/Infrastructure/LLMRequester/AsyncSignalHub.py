"""
Async Signal Hub - 异步信号广播中心

功能：
- 全局状态广播（暂停、恢复、降级）
- 并发任务间的协调通信
- 错误状态的集体感知
"""

import asyncio
import threading
from typing import Optional, Dict, Set, Callable, Any
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime


class SignalType(Enum):
    """信号类型"""
    PAUSE = "pause"              # 暂停所有任务
    RESUME = "resume"            # 恢复所有任务
    STOP = "stop"                # 停止所有任务
    REDUCE_CONCURRENCY = "reduce_concurrency"  # 降低并发
    DISABLE_CACHE = "disable_cache"  # 禁用缓存
    SWITCH_API = "switch_api"    # 切换 API
    RATE_LIMIT_HIT = "rate_limit_hit"  # 触发限流


@dataclass
class Signal:
    """信号数据"""
    signal_type: SignalType
    timestamp: datetime = field(default_factory=datetime.now)
    data: Dict[str, Any] = field(default_factory=dict)
    source: str = ""


class AsyncSignalHub:
    """异步信号广播中心（单例）"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # 全局状态标志
        self._paused = asyncio.Event()
        self._stopped = asyncio.Event()
        self._cache_disabled = asyncio.Event()

        # 默认状态：未暂停、未停止、缓存启用
        self._paused.set()  # set = not paused (可以继续)
        self._stopped.clear()  # clear = not stopped
        self._cache_disabled.clear()  # clear = cache enabled

        # 信号历史（用于调试）
        self._signal_history: list = []
        self._max_history = 100

        # 订阅者
        self._subscribers: Dict[SignalType, Set[Callable]] = {}

        # 并发控制
        self._concurrency_semaphore: Optional[asyncio.Semaphore] = None
        self._current_concurrency = 0

        self._initialized = True

    def reset(self) -> None:
        """重置所有状态"""
        self._paused.set()
        self._stopped.clear()
        self._cache_disabled.clear()
        self._signal_history.clear()

    # ========== 状态控制 ==========

    def pause(self) -> None:
        """暂停所有任务"""
        self._paused.clear()
        self._broadcast(Signal(SignalType.PAUSE))

    def resume(self) -> None:
        """恢复所有任务"""
        self._paused.set()
        self._broadcast(Signal(SignalType.RESUME))

    def stop(self) -> None:
        """停止所有任务"""
        self._stopped.set()
        self._broadcast(Signal(SignalType.STOP))

    def disable_cache(self) -> None:
        """禁用缓存"""
        self._cache_disabled.set()
        self._broadcast(Signal(SignalType.DISABLE_CACHE))

    def enable_cache(self) -> None:
        """启用缓存"""
        self._cache_disabled.clear()

    # ========== 状态查询 ==========

    def is_paused(self) -> bool:
        """是否处于暂停状态"""
        return not self._paused.is_set()

    def is_stopped(self) -> bool:
        """是否处于停止状态"""
        return self._stopped.is_set()

    def is_cache_disabled(self) -> bool:
        """缓存是否被禁用"""
        return self._cache_disabled.is_set()

    # ========== 异步等待 ==========

    async def wait_if_paused(self) -> None:
        """如果暂停则等待恢复"""
        await self._paused.wait()

    async def check_stop(self) -> bool:
        """检查是否应该停止"""
        return self._stopped.is_set()

    # ========== 并发控制 ==========

    def set_concurrency(self, limit: int) -> None:
        """设置并发限制"""
        self._concurrency_semaphore = asyncio.Semaphore(limit)
        self._current_concurrency = limit

    def get_concurrency(self) -> int:
        """获取当前并发限制"""
        return self._current_concurrency

    async def acquire_slot(self) -> bool:
        """获取执行槽位"""
        if self._concurrency_semaphore is None:
            return True
        await self._concurrency_semaphore.acquire()
        return True

    def release_slot(self) -> None:
        """释放执行槽位"""
        if self._concurrency_semaphore is not None:
            self._concurrency_semaphore.release()

    # ========== 信号广播 ==========

    def _broadcast(self, signal: Signal) -> None:
        """广播信号给所有订阅者"""
        self._signal_history.append(signal)
        if len(self._signal_history) > self._max_history:
            self._signal_history.pop(0)

        subscribers = self._subscribers.get(signal.signal_type, set())
        for callback in subscribers:
            try:
                callback(signal)
            except Exception:
                pass

    def subscribe(self, signal_type: SignalType, callback: Callable) -> None:
        """订阅信号"""
        if signal_type not in self._subscribers:
            self._subscribers[signal_type] = set()
        self._subscribers[signal_type].add(callback)

    def unsubscribe(self, signal_type: SignalType, callback: Callable) -> None:
        """取消订阅"""
        if signal_type in self._subscribers:
            self._subscribers[signal_type].discard(callback)

    def broadcast_rate_limit(self, api_url: str, retry_after: int = 0) -> None:
        """广播限流信号"""
        self._broadcast(Signal(
            SignalType.RATE_LIMIT_HIT,
            data={"api_url": api_url, "retry_after": retry_after}
        ))

    def broadcast_api_switch(self, old_api: str, new_api: str) -> None:
        """广播 API 切换信号"""
        self._broadcast(Signal(
            SignalType.SWITCH_API,
            data={"old_api": old_api, "new_api": new_api}
        ))

    def get_signal_history(self) -> list:
        """获取信号历史"""
        return list(self._signal_history)


# 全局单例访问
def get_signal_hub() -> AsyncSignalHub:
    """获取全局信号中心实例"""
    return AsyncSignalHub()
