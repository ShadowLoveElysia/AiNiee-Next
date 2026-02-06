"""
流式缓冲区模块 - 零碎片数据流合并方案

解决痛点：
- 100个并发回来时，避免多次内存分配和字符串拼接
- 预先申请内存缓冲区，每个请求带 chunk_id 直接写入对应位置
- 最后一个请求结束时，整本书已在内存中拼装完成
"""

import threading
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Callable
from collections import OrderedDict


@dataclass
class ChunkSlot:
    """单个数据槽位"""
    chunk_id: str
    status: int = 0  # 0=pending, 1=completed, 2=failed
    data: Any = None
    byte_size: int = 0


class StreamBuffer:
    """
    流式缓冲区 - 预分配槽位的零碎片合并器

    使用方式：
    1. 任务开始前调用 prepare() 预分配所有槽位
    2. 每个并发任务完成后调用 write_chunk() 写入对应槽位
    3. 所有任务完成后调用 finalize() 获取完整结果

    特点：
    - 预分配槽位，避免动态扩容
    - 直接写入对应位置，无需后期合并
    - 线程安全，支持高并发写入
    - 支持进度追踪和完成回调
    """

    def __init__(self, on_complete: Optional[Callable] = None):
        self._lock = threading.Lock()
        self._slots: OrderedDict[str, ChunkSlot] = OrderedDict()
        self._total_chunks = 0
        self._completed_chunks = 0
        self._failed_chunks = 0
        self._on_complete = on_complete
        self._is_finalized = False

    def prepare(self, chunk_ids: list[str]) -> None:
        """
        预分配所有槽位

        Args:
            chunk_ids: 所有 chunk 的 ID 列表，按顺序排列
        """
        with self._lock:
            self._slots.clear()
            self._total_chunks = len(chunk_ids)
            self._completed_chunks = 0
            self._failed_chunks = 0
            self._is_finalized = False

            for chunk_id in chunk_ids:
                self._slots[chunk_id] = ChunkSlot(chunk_id=chunk_id)

    def write_chunk(self, chunk_id: str, data: Any, success: bool = True) -> bool:
        """
        写入单个 chunk 的数据到对应槽位

        Args:
            chunk_id: chunk 的唯一标识
            data: 要写入的数据
            success: 是否成功

        Returns:
            bool: 是否所有 chunk 都已完成
        """
        all_done = False

        with self._lock:
            if chunk_id not in self._slots:
                return False

            slot = self._slots[chunk_id]
            slot.data = data
            slot.status = 1 if success else 2

            if success:
                self._completed_chunks += 1
            else:
                self._failed_chunks += 1

            # 检查是否全部完成
            all_done = (self._completed_chunks + self._failed_chunks) >= self._total_chunks

        # 在锁外触发回调，避免死锁
        if all_done and self._on_complete:
            self._on_complete(self)

        return all_done

    def get_progress(self) -> tuple[int, int, int]:
        """
        获取当前进度

        Returns:
            tuple: (已完成数, 失败数, 总数)
        """
        with self._lock:
            return (self._completed_chunks, self._failed_chunks, self._total_chunks)

    def is_all_done(self) -> bool:
        """检查是否所有 chunk 都已处理"""
        with self._lock:
            return (self._completed_chunks + self._failed_chunks) >= self._total_chunks

    def get_completed_data(self) -> list[Any]:
        """
        获取所有已完成的数据（按原始顺序）

        Returns:
            list: 所有成功完成的 chunk 数据
        """
        with self._lock:
            return [
                slot.data
                for slot in self._slots.values()
                if slot.status == 1 and slot.data is not None
            ]

    def get_all_data_ordered(self) -> OrderedDict[str, Any]:
        """
        获取所有数据（按原始顺序，包含失败的）

        Returns:
            OrderedDict: chunk_id -> data 的有序字典
        """
        with self._lock:
            return OrderedDict(
                (slot.chunk_id, slot.data)
                for slot in self._slots.values()
            )

    def finalize(self) -> dict:
        """
        完成缓冲区，返回统计信息

        Returns:
            dict: 包含完成统计的字典
        """
        with self._lock:
            self._is_finalized = True
            return {
                "total": self._total_chunks,
                "completed": self._completed_chunks,
                "failed": self._failed_chunks,
                "success_rate": self._completed_chunks / self._total_chunks if self._total_chunks > 0 else 0
            }

    def reset(self) -> None:
        """重置缓冲区"""
        with self._lock:
            self._slots.clear()
            self._total_chunks = 0
            self._completed_chunks = 0
            self._failed_chunks = 0
            self._is_finalized = False


class IndexedResultBuffer:
    """
    索引结果缓冲区 - 基于文本索引的预分配方案

    专门用于翻译结果的零碎片合并：
    - 预先知道所有 text_index
    - 每个翻译结果直接写入对应索引位置
    - 支持按文件分组的结果收集
    """

    def __init__(self):
        self._lock = threading.Lock()
        # 结构: {file_path: {text_index: translated_text}}
        self._buffers: Dict[str, Dict[int, str]] =
        self._pending_counts: Dict[str, int] = {}
        self._completed_counts: Dict[str, int] = {}

    def prepare_file(self, file_path: str, text_indices: list[int]) -> None:
        """
        为单个文件预分配缓冲区

        Args:
            file_path: 文件路径
            text_indices: 该文件中所有待翻译的 text_index 列表
        """
        with self._lock:
            self._buffers[file_path] = {idx: None for idx in text_indices}
            self._pending_counts[file_path] = len(text_indices)
            self._completed_counts[file_path] = 0

    def write_result(self, file_path: str, text_index: int, translated_text: str) -> bool:
        """
        写入单个翻译结果

        Args:
            file_path: 文件路径
            text_index: 文本索引
            translated_text: 翻译结果

        Returns:
            bool: 该文件是否全部完成
        """
        with self._lock:
            if file_path not in self._buffers:
                return False
            if text_index not in self._buffers[file_path]:
                return False

            # 只有首次写入才计数
            if self._buffers[file_path][text_index] is None:
                self._completed_counts[file_path] += 1

            self._buffers[file_path][text_index] = translated_text

            return self._completed_counts[file_path] >= self._pending_counts[file_path]

    def write_batch(self, file_path: str, results: Dict[int, str]) -> bool:
        """
        批量写入翻译结果

        Args:
            file_path: 文件路径
            results: {text_index: translated_text} 字典

        Returns:
            bool: 该文件是否全部完成
        """
        with self._lock:
            if file_path not in self._buffers:
                return False

            for text_index, translated_text in results.items():
                if text_index in self._buffers[file_path]:
                    if self._buffers[file_path][text_index] is None:
                        self._completed_counts[file_path] += 1
                    self._buffers[file_path][text_index] = translated_text

            return self._completed_counts[file_path] >= self._pending_counts[file_path]

    def get_file_progress(self, file_path: str) -> tuple[int, int]:
        """
        获取单个文件的进度

        Returns:
            tuple: (已完成数, 总数)
        """
        with self._lock:
            if file_path not in self._buffers:
                return (0, 0)
            return (
                self._completed_counts.get(file_path, 0),
                self._pending_counts.get(file_path, 0)
            )

    def get_file_results(self, file_path: str) -> Dict[int, str]:
        """
        获取单个文件的所有结果

        Returns:
            dict: {text_index: translated_text}
        """
        with self._lock:
            return dict(self._buffers.get(file_path, {}))

    def is_file_complete(self, file_path: str) -> bool:
        """检查单个文件是否全部完成"""
        with self._lock:
            if file_path not in self._buffers:
                return False
            return self._completed_counts[file_path] >= self._pending_counts[file_path]

    def get_total_progress(self) -> tuple[int, int]:
        """
        获取总体进度

        Returns:
            tuple: (已完成总数, 总数)
        """
        with self._lock:
            total_completed = sum(self._completed_counts.values())
            total_pending = sum(self._pending_counts.values())
            return (total_completed, total_pending)

    def clear(self) -> None:
        """清空所有缓冲区"""
        with self._lock:
            self._buffers.clear()
            self._pending_counts.clear()
            self._completed_counts.clear()
