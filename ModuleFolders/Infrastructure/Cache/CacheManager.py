from collections import defaultdict
import os
import re
import threading
import time
from dataclasses import fields
from typing import Dict, List, Tuple

import msgspec
import rapidjson as json

from ModuleFolders.Base.Base import Base
from ModuleFolders.Infrastructure.TaskConfig.TaskType import TaskType
from ModuleFolders.Infrastructure.Cache.CacheFile import CacheFile
from ModuleFolders.Infrastructure.Cache.CacheItem import CacheItem, TranslationStatus
from ModuleFolders.Infrastructure.Cache.CacheProject import (
    CacheProject,
    CacheProjectStatistics
)


class CacheManager(Base):
    SAVE_INTERVAL = 8  # 缓存保存间隔（秒）

    def __init__(self) -> None:
        super().__init__()

        # 线程锁
        self.file_lock = threading.Lock()
        self._save_thread_lock = threading.Lock()
        self._save_thread = None
        self.save_to_file_stop_flag = False
        self.save_to_file_require_flag = False
        self.save_to_file_require_path = ""

        self.project = CacheProject()
        self.project.stats_data = CacheProjectStatistics()

        # 注册事件
        self.subscribe(Base.EVENT.TASK_START, self.start_interval_saving)
        self.subscribe(Base.EVENT.APP_SHUT_DOWN, self.app_shut_down)
        self.subscribe(Base.EVENT.TASK_MANUAL_SAVE_CACHE, self.on_manual_save_cache_requested)
        
    def start_interval_saving(self, event: int, data: dict):
        # Prefer runtime path from event to avoid loading stale output directory.
        output_path = data.get("session_output_path")
        if not output_path:
            config = self.load_config()
            output_path = config.get("label_output_path", "./output")

        # Align memory state and disk state before resuming.
        if data.get("continue_status") is True and output_path and os.path.isdir(output_path):
            cache_path = os.path.join(output_path, "cache", "AinieeCacheData.json")
            if hasattr(self, "project") and self.project is not None and self.get_item_count() > 0:
                try:
                    self.save_to_file_require_path = output_path
                    self.save_to_file()
                except Exception as e:
                    self.warning(f"Pre-resume cache flush failed: {e}")
            if os.path.isfile(cache_path):
                try:
                    self.load_from_file(output_path)
                except Exception as e:
                    self.warning(f"Pre-resume cache reload failed: {e}")

        # Start save thread once.
        self.save_to_file_stop_flag = False
        with self._save_thread_lock:
            if self._save_thread is None or not self._save_thread.is_alive():
                self._save_thread = threading.Thread(
                    target=self.save_to_file_tick,
                    daemon=True,
                    name="cache-save-tick",
                )
                self._save_thread.start()

    # 应用关闭事件
    def app_shut_down(self, event: int, data: dict) -> None:
        self.save_to_file_stop_flag = True
        self.flush_pending_save()

    # 手动保存缓存请求事件
    def on_manual_save_cache_requested(self, event: int, data: dict) -> None:
        """处理手动保存缓存的请求"""
        output_path = data.get("output_path")
        if output_path and hasattr(self, "project") and self.project != None:
            # 设置保存路径并立即执行保存
            self.save_to_file_require_path = output_path
            self.save_to_file()
            self.info("缓存文件已通过手动请求保存。")
        elif not hasattr(self, "project") or self.project is None:
             self.warning("手动保存缓存失败：项目数据尚未加载。")
        else:
            self.warning("手动保存缓存失败：未提供有效的 'output_path'。")

    # 保存缓存到文件
    def save_to_file(self) -> None:
        """保存缓存到文件，采用原子写入方式防止竞态条件
        缓存结构：
        {
            "project_id": "aaa",
            "project_type": "Type",
            "files": {
                "path/to/file1.txt": {
                    "storage_path": "...",
                    "file_name": "...",
                    "items": {
                        1: {"text_index": 1, "source_text": "...", ...},
                        2: {"text_index": 2, "source_text": "...", ...},
                    }
                },
                "path/to/file2.txt": { ... }
            }
        }
        """
        cache_dir = os.path.join(self.save_to_file_require_path, "cache")
        path = os.path.join(cache_dir, "AinieeCacheData.json")
        # 定义临时文件路径，确保在同一文件系统下以支持原子性替换
        tmp_path = path + f".{os.getpid()}.tmp"

        with self.file_lock:
            try:
                os.makedirs(cache_dir, exist_ok=True)
                content_bytes = msgspec.json.encode(self.project)

                # 先将完整内容写入临时文件
                with open(tmp_path, "wb") as writer:
                    writer.write(content_bytes)

                # 使用原子操作替换旧文件。这能保证其他进程/线程
                # 要么读到旧的完整文件，要么读到新的完整文件，绝不会读到一半。
                os.replace(tmp_path, path)

                # --- NEW: Optional Backup Logic ---
                config = self.load_config()
                if config.get("enable_cache_backup", False):
                    # Create timestamped backup
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    backup_dir = os.path.join(cache_dir, "backups")
                    os.makedirs(backup_dir, exist_ok=True)
                    backup_path = os.path.join(backup_dir, f"AinieeCacheData_{timestamp}.json")
                    
                    import shutil
                    shutil.copy2(path, backup_path)
                    
                    # Enforce backup limit
                    limit = config.get("cache_backup_limit", 10)
                    if limit > 0:
                        try:
                            backups = sorted(
                                [os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.startswith("AinieeCacheData_")],
                                key=os.path.getmtime
                            )
                            while len(backups) > limit:
                                os.remove(backups.pop(0))
                        except Exception as e:
                            self.debug(f"Backup rotation failed: {e}")
                # --- END Backup Logic ---

                # 写入项目整体翻译状态文件
                if self.project and self.project.stats_data:
                    total_line = self.project.stats_data.total_line # 获取需翻译总行数
                    line = self.project.stats_data.line # 获取已翻译行数
                    project_name = self.project.project_name # 获取项目名字
                    json_data = {"total_line": total_line, "line": line, "project_name": project_name}

                    json_path = os.path.join(cache_dir, "ProjectStatistics.json")
                    json_tmp_path = json_path + f".{os.getpid()}.tmp"
                    try:
                        with open(json_tmp_path, "w", encoding="utf-8") as writer:
                            json.dump(json_data, writer, ensure_ascii=False, indent=4)
                        os.replace(json_tmp_path, json_path)
                    finally:
                        if os.path.exists(json_tmp_path):
                            try:
                                os.remove(json_tmp_path)
                            except OSError:
                                pass
                else:
                    # 如果stats_data不存在，则调用 Base 类中的 warning 方法打印警告并跳过
                    self.warning(f"CacheManager: self.project.stats_data is None. Skipping ProjectStatistics.json update.")
            finally:
                # 确保临时文件在任何情况下（包括异常）都会被清理
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)


    # 保存缓存到文件的定时任务
    def save_to_file_tick(self) -> None:
        """定时保存任务"""
        while not self.save_to_file_stop_flag:
            time.sleep(self.SAVE_INTERVAL)
            self.flush_pending_save()

    # 请求保存缓存到文件
    def require_save_to_file(self, output_path: str) -> None:
        """请求保存缓存"""
        if not output_path:
            return
        self.save_to_file_require_path = output_path
        self.save_to_file_require_flag = True

    def flush_pending_save(self) -> None:
        if not getattr(self, "save_to_file_require_flag", False):
            return
        if not getattr(self, "save_to_file_require_path", ""):
            return
        self.save_to_file()
        self.save_to_file_require_flag = False

    # 从项目中加载
    def load_from_project(self, data: CacheProject):
        self.project = data
        self._normalize_project_state()

    # 从缓存文件读取数据
    def load_from_file(self, output_path: str) -> None:
        """从文件加载数据"""
        path = os.path.join(output_path, "cache", "AinieeCacheData.json")
        with self.file_lock:
            if os.path.isfile(path):
                try:
                    self.project = self.read_from_file(path)
                    self._normalize_project_state()
                except Exception as e:
                    # Auto-Heal logic
                    config = self.load_config()
                    if config.get("enable_auto_heal", True):
                        self.print(f"[[red]ERROR[/]] {self.tra('msg_cache_corrupted')}")
                        backup_dir = os.path.join(output_path, "cache", "backups")
                        if os.path.exists(backup_dir):
                            # Find newest backup
                            backups = sorted([os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.startswith("AinieeCacheData_")], 
                                            key=lambda x: os.path.getmtime(x), reverse=True)
                            for b_path in backups:
                                try:
                                    self.project = self.read_from_file(b_path)
                                    self._normalize_project_state()
                                    self.print(f"[[green]SUCCESS[/]] {self.tra('msg_cache_healed').format(os.path.basename(b_path))}")
                                    # Copy healed backup to main path
                                    import shutil
                                    shutil.copy2(b_path, path)
                                    return
                                except:
                                    continue
                        self.print(f"[[red]CRITICAL[/]] {self.tra('msg_cache_heal_fail')}")
                    raise e

    def _normalize_project_state(self) -> None:
        if not self.project:
            self.project = CacheProject()

        if self.project.stats_data is None:
            self.project.stats_data = CacheProjectStatistics()

        valid_statuses = {
            TranslationStatus.UNTRANSLATED,
            TranslationStatus.TRANSLATED,
            TranslationStatus.POLISHED,
            TranslationStatus.USER_PROOFREAD,
            TranslationStatus.AI_PROOFREAD,
            TranslationStatus.EXCLUDED,
        }

        for item in self.project.items_iter():
            if item.source_text is None:
                item.source_text = ""
            elif not isinstance(item.source_text, str):
                item.source_text = str(item.source_text)
            if item.translated_text is None:
                item.translated_text = ""
            elif not isinstance(item.translated_text, str):
                item.translated_text = str(item.translated_text)
            if item.polished_text is None:
                item.polished_text = ""
            elif not isinstance(item.polished_text, str):
                item.polished_text = str(item.polished_text)

            if item.translation_status not in valid_statuses:
                item.translation_status = TranslationStatus.UNTRANSLATED
                continue

            if item.translation_status == TranslationStatus.POLISHED and not item.polished_text.strip():
                item.translation_status = (
                    TranslationStatus.TRANSLATED
                    if item.translated_text.strip()
                    else TranslationStatus.UNTRANSLATED
                )
            elif item.translation_status == TranslationStatus.TRANSLATED and not item.translated_text.strip():
                item.translation_status = TranslationStatus.UNTRANSLATED
            elif item.translation_status == TranslationStatus.UNTRANSLATED and item.translated_text.strip():
                item.translation_status = TranslationStatus.TRANSLATED

        stats = self.project.stats_data
        total_count = self.get_item_count()
        stats.total_line = max(total_count, 0)
        stats.line = min(max(stats.line, 0), stats.total_line)
        stats.token = max(stats.token, 0)
        stats.total_completion_tokens = max(stats.total_completion_tokens, 0)
        stats.success_requests = max(stats.success_requests, 0)
        stats.error_requests = max(stats.error_requests, 0)
        stats.total_requests = max(
            stats.total_requests,
            stats.success_requests + stats.error_requests,
        )

    @classmethod
    def read_from_file(cls, cache_path) -> CacheProject:
        with open(cache_path, "rb") as reader:
            content_bytes = reader.read()
        try:
            # 反序列化严格按照dataclass定义，如source_text这种非optional类型不能为None，否则反序列化失败
            return msgspec.json.decode(content_bytes, type=CacheProject)
        except msgspec.ValidationError:
            content = json.loads(content_bytes.decode('utf-8'))
            if isinstance(content, dict):
                return CacheProject.from_dict(content)
            else:
                return cls._read_from_old_content(content)

    @classmethod
    def _read_from_old_content(cls, content: list) -> CacheProject:
        # 兼容旧版缓存
        data_iter = iter(content)
        project_data = next(data_iter)
        init_data = {
            "project_id": project_data["project_id"],
            "project_type": project_data["project_type"],
        }
        CacheProject().detected_line_ending
        if "data" in project_data:
            init_data["stats_data"] = CacheProjectStatistics.from_dict(project_data["data"])
        else:
            init_data["stats_data"] = CacheProjectStatistics() # Ensure stats_data is always initialized
        if "file_encoding" in project_data:
            init_data["detected_encoding"] = project_data["file_encoding"]
        if "line_ending" in project_data:
            init_data["detected_line_ending"] = project_data["line_ending"]
        files_props = {}
        new_item_fields = set(fld.name for fld in fields(CacheItem))
        # 这两个属性之前是放item，现在放file
        file_extra_keys = set(["subtitle_title", "top_text"])
        file_prop_keys = set(["file_project_type"])
        for old_item in data_iter:
            storage_path = old_item["storage_path"]
            if storage_path not in files_props:
                files_props[storage_path] = {
                    "items": [],
                    "extra": {},
                    "file_project_type": project_data["project_type"],
                    'storage_path': storage_path,
                }
            new_item = CacheItem.from_dict(old_item)
            for k, v in old_item.items():
                if k == 'file_name':
                    continue
                if k not in new_item_fields:
                    if k in file_prop_keys:
                        files_props[storage_path][k] = v
                    elif k in file_extra_keys:
                        files_props[storage_path]["extra"][k] = v
                    else:
                        new_item.set_extra(k, v)
            files_props[storage_path]["items"].append(new_item)

        init_data["files"] = {
            k: CacheFile(**v)
            for k, v in files_props.items()
        }
        return CacheProject(**init_data)

    # 获取缓存内全部文本对数量
    def get_item_count(self) -> int:
        """获取总缓存项数量"""
        if not hasattr(self, "project") or self.project is None:
            return 0
        return self.project.count_items()

    # 获取某翻译状态的条目数量
    def get_item_count_by_status(self, status: int) -> int:
        if not self.project:
            return 0
        return self.project.count_items(status)

    # 检测是否存在需要翻译的条目
    def get_continue_status(self) -> bool:
        """检查是否存在可继续翻译的状态"""
        if not self.project:
            return False
        
        has_translated = False
        has_untranslated = False
        for item in self.project.items_iter():
            status = item.translation_status
            if status == TranslationStatus.TRANSLATED:
                has_translated = True
            elif status == TranslationStatus.UNTRANSLATED:
                has_untranslated = True
            if has_translated and has_untranslated:
                return True
        return has_translated and has_untranslated

    # 生成上文数据条目片段
    def generate_previous_chunks(self, all_items: list[CacheItem], previous_item_count: int, start_idx: int) -> List[CacheItem]:

        # 如果没有条目，或者上文条目数小于等于0，或者起始索引小于等于0，则返回空列表
        if not all_items or previous_item_count <= 0 or start_idx <= 0:
            return []

        # 计算实际要获取的上文的起始索引 (包含)
        from_idx = max(0, start_idx - previous_item_count)

        # 计算实际要获取的上文的结束索引 (不包含)
        to_idx = min(start_idx, len(all_items)) # 通常就是 start_idx

        # 如果计算出的范围无效，返回空列表
        if from_idx >= to_idx:
            return []

        # 直接切片获取所需范围的条目，切片会自动处理边界情况，例如 from_idx=0
        collected = all_items[from_idx:to_idx]

        return collected

    # 生成原文上下文数据条目片段
    def generate_source_context(self, all_items: list[CacheItem], start_idx: int, context_count: int) -> List[CacheItem]:
        """
        获取当前chunk之前的原文上下文，用于帮助LLM理解段落连贯性

        Args:
            all_items: 文件的所有条目列表
            start_idx: 当前chunk第一个条目在all_items中的索引
            context_count: 要获取的上下文行数

        Returns:
            包含上下文条目的列表（用于提取source_text）
        """
        if not all_items or context_count <= 0 or start_idx <= 0:
            return []

        from_idx = max(0, start_idx - context_count)
        to_idx = min(start_idx, len(all_items))

        if from_idx >= to_idx:
            return []

        return all_items[from_idx:to_idx]

    # 生成待翻译片段
    def generate_item_chunks(self, limit_type: str, limit_count: int, previous_line_count: int, task_mode,
                              enable_context_enhancement: bool = False, context_line_count: int = 5) -> \
            Tuple[List[List[CacheItem]], List[List[CacheItem]], List[str], List[List[CacheItem]]]:
        chunks, previous_chunks, file_paths, source_context_chunks = [], [], [], []

        for file in self.project.files.values():
            # 1. 筛选出当前任务需要的条目
            if task_mode == TaskType.TRANSLATION:
                items = [item for item in file.items if item.translation_status == TranslationStatus.UNTRANSLATED]
            elif task_mode == TaskType.POLISH:
                items = [item for item in file.items if item.translation_status == TranslationStatus.TRANSLATED]
            else:
                items = []

            if not items:
                continue

            current_chunk, current_length = [], 0
            # 记录当前 chunk 的第一个条目，用于在原始列表中定位上下文
            first_item_in_chunk = None

            # 3. 使用 enumerate 获取条目
            for i, item in enumerate(items):
                item_length = item.get_token_count(item.source_text) if limit_type == "token" else 1

                # 当一个新 chunk 开始时，记录它的第一个条目
                if not current_chunk:
                    first_item_in_chunk = item

                # 如果当前 chunk 满了，提交它
                if current_chunk and (current_length + item_length > limit_count):
                    chunks.append(current_chunk)

                    # 关键修复：从原始完整列表 (file.items) 中获取真实的上文
                    # 这样即便断点续传，AI 也能看到前一页已经翻译过的内容
                    real_idx = file.index_of(first_item_in_chunk.text_index)
                    previous_chunks.append(
                        self.generate_previous_chunks(file.items, previous_line_count, real_idx)
                    )
                    file_paths.append(file.storage_path)

                    # 上下文增强：获取当前chunk之前的原文上下文
                    if enable_context_enhancement:
                        source_context_chunks.append(
                            self.generate_source_context(file.items, real_idx, context_line_count)
                        )
                    else:
                        source_context_chunks.append([])

                    # 重置，为下一个 chunk 做准备
                    current_chunk, current_length = [], 0
                    first_item_in_chunk = item

                # 添加当前条目到 chunk
                current_chunk.append(item)
                current_length += item_length

            # 处理循环结束后剩余的最后一个 chunk
            if current_chunk:
                chunks.append(current_chunk)
                # 同样从原始列表中获取上下文
                real_idx = file.index_of(first_item_in_chunk.text_index)
                previous_chunks.append(
                    self.generate_previous_chunks(file.items, previous_line_count, real_idx)
                )
                file_paths.append(file.storage_path)
                # 上下文增强：获取当前chunk之前的原文上下文
                if enable_context_enhancement:
                    source_context_chunks.append(
                        self.generate_source_context(file.items, real_idx, context_line_count)
                    )
                else:
                    source_context_chunks.append([])

        return chunks, previous_chunks, file_paths, source_context_chunks


    # 获取文件层级结构
    def get_file_hierarchy(self) -> Dict[str, List[str]]:
        """
        从缓存中读取文件列表，并按文件夹层级组织。
        """
        hierarchy = defaultdict(list)
        if not self.project or not self.project.files:
            return {}
            
        with self.file_lock:
            for file_path in self.project.files.keys():
                # os.path.split 将路径分割成 (目录, 文件名)
                directory, filename = os.path.split(file_path)
                # 如果文件在根目录，directory会是空字符串，用'.'代替
                if not directory:
                    directory = '.'
                hierarchy[directory].append(filename)

        # 对每个文件夹下的文件名进行排序
        for dir_path in hierarchy:
            hierarchy[dir_path].sort()
            
        return dict(hierarchy)

    # 更新缓存中的特定文本项
    def update_item_text(self, storage_path: str, text_index: int, field_name: str, new_text: str) -> None:
        """
        更新缓存中指定文件、指定索引的文本项的某个字段。
        """
        with self.file_lock:
            cache_file = self.project.get_file(storage_path)
            if not cache_file:
                print(f"Error: 找不到文件 {storage_path}")
                return
            
            item_to_update = cache_file.get_item(text_index)
            
            # 修改原文
            if field_name == 'source_text':
                if new_text and new_text.strip():
                    if item_to_update.source_text != new_text:
                        item_to_update.source_text = new_text

            # 修改译文
            elif field_name == 'translated_text':
                item_to_update.translated_text = new_text
                # 如果译文被清空，状态应重置为未翻译，同时清空润文
                if not new_text or not new_text.strip():
                    item_to_update.translation_status = TranslationStatus.UNTRANSLATED
                    item_to_update.polished_text = ""
                # 如果有译文内容，则标记为已翻译
                else:
                    item_to_update.translation_status = TranslationStatus.TRANSLATED

            # 修改润文
            elif field_name == 'polished_text':
                item_to_update.polished_text = new_text
                # 如果润文被清空，状态应回退到已翻译
                if not new_text or not new_text.strip():
                    item_to_update.translation_status = TranslationStatus.TRANSLATED
                # 如果有润文内容，则标记为已润色
                else:
                    item_to_update.translation_status = TranslationStatus.POLISHED

    # 缓存全搜索方法
    def search_items(self, query: str, scope: str, is_regex: bool, search_flagged: bool) -> list:
        """
        在整个项目中搜索条目。

        Args:
            query (str): 搜索查询字符串。
            scope (str): 搜索范围 ('all', 'source_text', 'translated_text', 'polished_text')。
            is_regex (bool): 是否使用正则表达式。
            search_flagged (bool): 是否仅搜索被标记的行。

        Returns:
            list: 包含元组 (file_path, original_row_num, CacheItem) 的结果列表。
        """
        results = []
        fields_to_check = []

        if scope == 'all':
            fields_to_check = ['source_text', 'translated_text', 'polished_text']
        else:
            fields_to_check = [scope]

        try:
            if is_regex:
                # 预编译正则表达式以提高效率
                regex = re.compile(query)
                matcher = lambda text: regex.search(text)
            else:
                matcher = lambda text: query in text
        except re.error as e:
            # 正则表达式无效，可以发出一个错误信号或直接返回空
            self.error(f"无效的正则表达式: {e}")
            # 这里可以向UI发送一个错误提示
            return []

        with self.file_lock:
            for file_path, cache_file in self.project.files.items():
                for item_index, item in enumerate(cache_file.items):
                    # 如果要求搜索标记行，则先进行标记过滤
                    if search_flagged:
                        is_item_flagged = False
                        if item.extra:
                            if scope == 'translated_text':
                                is_item_flagged = item.extra.get('language_mismatch_translation', False)
                            elif scope == 'polished_text':
                                is_item_flagged = item.extra.get('language_mismatch_polish', False)
                            elif scope == 'all':
                                is_item_flagged = (item.extra.get('language_mismatch_translation', False) or
                                                   item.extra.get('language_mismatch_polish', False))
                            # 对于 'source_text' 范围, is_item_flagged 保持 False, 自动跳过

                        if not is_item_flagged:
                            continue  # 如果不满足标记条件，则直接跳到下一个条目

                    # 通过标记过滤后，再执行文本/正则搜索
                    # 如果查询为空，则所有通过标记过滤的条目都匹配
                    if not query.strip():
                        # 仅在search_flagged为True时，空查询才有意义（即列出所有标记行）
                        if search_flagged:
                             results.append((file_path, item_index + 1, item))
                        continue # 否则，空查询不匹配任何内容                    
                    found = False
                    for field_name in fields_to_check:
                        text_to_check = getattr(item, field_name, None)
                        if text_to_check and matcher(text_to_check):
                            # (文件路径, 原始行号, 完整的CacheItem对象)
                            results.append((file_path, item_index + 1, item))
                            found = True
                            break  # 找到一个匹配就跳出字段循环，避免重复添加
                    if found:
                        continue
        return results

    # 获取全部的原文与文件路径
    def get_all_source_items(self) -> list:
        """
        获取项目中所有文件的所有原文文本项。
        Returns:
            list: 包含字典的列表，每个字典代表一个需要处理的条目。
                  格式: [{"source_text": str, "file_path": str}, ...]
        """
        all_items_data = []
        with self.file_lock:
            for file_path, cache_file in self.project.files.items():
                for item in cache_file.items:
                    # 只添加包含有效原文的条目
                    if item.source_text and item.source_text.strip():
                        all_items_data.append({
                            "source_text": item.source_text,
                            "file_path": file_path
                        })
        return all_items_data
