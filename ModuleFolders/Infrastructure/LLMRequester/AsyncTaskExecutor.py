"""
异步任务执行器 - 基于 asyncio + aiohttp 的高并发翻译引擎

核心特性：
- 使用 asyncio 事件循环管理所有并发任务
- 复用 aiohttp 连接池，减少 TCP 握手开销
- 集成 StreamBuffer 实现零碎片数据流合并
- 支持动态并发控制和优雅停止
"""

import asyncio
import time
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field

from ModuleFolders.Base.Base import Base
from ModuleFolders.Infrastructure.Cache.CacheItem import CacheItem, TranslationStatus
from ModuleFolders.Infrastructure.Cache.StreamBuffer import StreamBuffer
from ModuleFolders.Infrastructure.LLMRequester.AsyncOpenaiRequester import AsyncOpenaiRequester


@dataclass
class AsyncTaskResult:
    """异步任务结果"""
    task_id: str
    success: bool
    row_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error_message: str = ""
    translated_items: Dict[int, str] = field(default_factory=dict)


class AsyncTaskExecutor(Base):
    """
    异步任务执行器

    使用方式：
    1. 创建实例并配置
    2. 调用 execute_tasks() 执行所有任务
    3. 通过回调获取进度更新
    """

    def __init__(
        self,
        max_concurrency: int = 100,
        on_task_complete: Optional[Callable[[AsyncTaskResult], None]] = None,
        on_progress_update: Optional[Callable[[int, int], None]] = None,
    ):
        super().__init__()
        self._max_concurrency = max_concurrency
        self._on_task_complete = on_task_complete
        self._on_progress_update = on_progress_update

        # 并发控制
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._running = False
        self._stop_requested = False

        # 统计数据
        self._total_tasks = 0
        self._completed_tasks = 0
        self._failed_tasks = 0

        # 流式缓冲区
        self._stream_buffer = StreamBuffer()

    @property
    def max_concurrency(self) -> int:
        return self._max_concurrency

    @max_concurrency.setter
    def max_concurrency(self, value: int) -> None:
        """动态调整并发数"""
        self._max_concurrency = max(1, min(value, 500))
        # 注意：已创建的 semaphore 不会自动更新
        # 新的限制将在下一批任务中生效

    def request_stop(self) -> None:
        """请求停止执行"""
        self._stop_requested = True

    async def _execute_single_task(
        self,
        task_id: str,
        items: List[CacheItem],
        messages: list,
        system_prompt: str,
        platform_config: dict,
    ) -> AsyncTaskResult:
        """执行单个翻译任务"""
        result = AsyncTaskResult(task_id=task_id, success=False)

        if self._stop_requested:
            result.error_message = "Task cancelled"
            return result

        try:
            # 获取信号量（控制并发）
            async with self._semaphore:
                if self._stop_requested:
                    result.error_message = "Task cancelled"
                    return result

                # 发起异步请求
                requester = AsyncOpenaiRequester()
                skip, think, content, pt, ct = await requester.request_openai_async(
                    messages, system_prompt, platform_config
                )

                result.prompt_tokens = pt
                result.completion_tokens = ct

                if skip:
                    result.error_message = content
                    return result

                # 简单的结果提取（实际应使用 ResponseExtractor）
                if content:
                    result.success = True
                    result.row_count = len(items)

                    # 将结果写入 items
                    lines = content.strip().split('\n')
                    for i, item in enumerate(items):
                        if i < len(lines):
                            result.translated_items[item.text_index] = lines[i]

                return result

        except Exception as e:
            result.error_message = str(e)
            return result

    async def _task_wrapper(
        self,
        task_id: str,
        items: List[CacheItem],
        messages: list,
        system_prompt: str,
        platform_config: dict,
    ) -> AsyncTaskResult:
        """任务包装器，处理回调和统计"""
        result = await self._execute_single_task(
            task_id, items, messages, system_prompt, platform_config
        )

        # 更新统计
        if result.success:
            self._completed_tasks += 1
        else:
            self._failed_tasks += 1

        # 写入流式缓冲区
        self._stream_buffer.write_chunk(task_id, result, result.success)

        # 触发回调
        if self._on_task_complete:
            try:
                self._on_task_complete(result)
            except Exception as e:
                self.error(f"Task callback error: {e}")

        if self._on_progress_update:
            try:
                total_done = self._completed_tasks + self._failed_tasks
                self._on_progress_update(total_done, self._total_tasks)
            except Exception:
                pass

        return result

    async def execute_tasks_async(
        self,
        tasks: List[Dict[str, Any]],
    ) -> List[AsyncTaskResult]:
        """
        异步执行所有任务

        Args:
            tasks: 任务列表，每个任务包含:
                - task_id: 任务ID
                - items: CacheItem 列表
                - messages: 消息列表
                - system_prompt: 系统提示词
                - platform_config: 平台配置

        Returns:
            所有任务的结果列表
        """
        self._running = True
        self._stop_requested = False
        self._total_tasks = len(tasks)
        self._completed_tasks = 0
        self._failed_tasks = 0

        # 创建信号量
        self._semaphore = asyncio.Semaphore(self._max_concurrency)

        # 预分配流式缓冲区
        task_ids = [t["task_id"] for t in tasks]
        self._stream_buffer.prepare(task_ids)

        # 创建所有协程任务
        coroutines = [
            self._task_wrapper(
                task["task_id"],
                task["items"],
                task["messages"],
                task["system_prompt"],
                task["platform_config"],
            )
            for task in tasks
        ]

        # 并发执行所有任务
        results = await asyncio.gather(*coroutines, return_exceptions=True)

        # 处理异常结果
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append(AsyncTaskResult(
                    task_id=tasks[i]["task_id"],
                    success=False,
                    error_message=str(result)
                ))
            else:
                final_results.append(result)

        self._running = False

        # 关闭连接池
        await AsyncOpenaiRequester.close_session()

        return final_results

    def execute_tasks(self, tasks: List[Dict[str, Any]]) -> List[AsyncTaskResult]:
        """
        同步接口：执行所有任务

        这是对 execute_tasks_async 的同步包装，
        方便在非异步代码中调用。
        """
        return asyncio.run(self.execute_tasks_async(tasks))

    def get_statistics(self) -> Dict[str, Any]:
        """获取执行统计"""
        return {
            "total": self._total_tasks,
            "completed": self._completed_tasks,
            "failed": self._failed_tasks,
            "running": self._running,
            "buffer_stats": self._stream_buffer.finalize() if not self._running else None
        }
