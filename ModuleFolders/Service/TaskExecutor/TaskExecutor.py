import time
import os
import threading
import concurrent.futures

import opencc

from ModuleFolders.Base.Base import Base
from ModuleFolders.Infrastructure.Cache.CacheItem import TranslationStatus
from ModuleFolders.Infrastructure.Cache.CacheManager import CacheManager
from ModuleFolders.Infrastructure.Cache.CacheProject import CacheProjectStatistics
from ModuleFolders.Infrastructure.TaskConfig.TaskType import TaskType
from ModuleFolders.Service.TaskExecutor.TranslatorTask import TranslatorTask
from ModuleFolders.Service.TaskExecutor.PolisherTask import PolisherTask
from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig
from ModuleFolders.Domain.PromptBuilder.PromptBuilder import PromptBuilder
from ModuleFolders.Domain.PromptBuilder.PromptBuilderPolishing import PromptBuilderPolishing
from ModuleFolders.Domain.PromptBuilder.PromptBuilderEnum import PromptBuilderEnum
from ModuleFolders.Domain.PromptBuilder.PromptBuilderLocal import PromptBuilderLocal
from ModuleFolders.Domain.PromptBuilder.PromptBuilderSakura import PromptBuilderSakura
from ModuleFolders.Infrastructure.RequestLimiter.RequestLimiter import RequestLimiter
from ModuleFolders.Service.TaskExecutor.TranslatorUtil import get_source_language_for_file


# 翻译器
class TaskExecutor(Base):

    def __init__(self, plugin_manager,cache_manager, file_reader, file_writer) -> None:
        super().__init__()

        # 初始化
        self.plugin_manager = plugin_manager
        self.cache_manager = cache_manager
        self.file_reader = file_reader
        self.file_writer = file_writer
        self.config = TaskConfig()
        self.request_limiter = RequestLimiter()

        # 注册事件
        self.subscribe(Base.EVENT.TASK_STOP, self.task_stop)
        self.subscribe(Base.EVENT.TASK_START, self.task_start)
        self.subscribe(Base.EVENT.TASK_MANUAL_EXPORT, self.task_manual_export)
        self.subscribe(Base.EVENT.TASK_API_STATUS_REPORT, self.on_api_status_report)
        self.subscribe("TASK_SKIP_FILE_REQUEST", self.on_skip_file_request)
        self.subscribe(Base.EVENT.APP_SHUT_DOWN, self.app_shut_down)

        # Skip File state
        self.skipped_files = set()
        self._skip_lock = threading.Lock()

        # Failover state
        self.global_consecutive_api_errors = 0
        self._api_error_lock = threading.Lock()
        self.api_pipeline = []
        self.current_api_index = 0
        self.current_mode = None
        
        # Concurrency Control for Mission Control
        self._concurrency_lock = threading.Lock()
        self._current_active = 0
        self.executor = None

    # API 状态报告事件处理
    def on_api_status_report(self, event: int, data: dict) -> None:
        is_success = data.get("is_success", False)
        force_switch = data.get("force_switch", False)
        
        if force_switch:
            with self._api_error_lock:
                self._switch_api()
                self.consecutive_errors = 0 # Reset on manual switch
            return

        with self._api_error_lock:
            if is_success:
                self.consecutive_errors = 0
            else:
                self.consecutive_errors += 1
                
                # Check for critical error threshold
                threshold = self.config.critical_error_threshold or 5
                if self.consecutive_errors >= threshold:
                    self.error(f"Critical error threshold ({threshold}) reached. Pausing task.")
                    self.emit(Base.EVENT.SYSTEM_STATUS_UPDATE, {"status": "critical_error"})
                    self.emit(Base.EVENT.TASK_STOP, {})
                    self.consecutive_errors = 0 # Reset after triggering
                    return # Stop further processing to avoid conflict with failover

                # Standard failover logic
                if self.config.enable_api_failover and self.api_pipeline:
                    failover_threshold = self.config.api_failover_threshold
                    if self.consecutive_errors >= failover_threshold:
                        self.warning(f"API consecutive errors ({self.consecutive_errors}) reached failover threshold ({failover_threshold}). Switching API...")
                        self._switch_api()
                        self.consecutive_errors = 0

    def on_skip_file_request(self, event, data):
        with self._skip_lock:
            path = data.get("file_path_full")
            if path:
                self.skipped_files.add(path)
                self.print(f"[bold yellow]Skip request received for {os.path.basename(path)}. New tasks for this file will be ignored.[/bold yellow]")

    def _gated_run(self, task):
        """指挥中心：动态门禁控制"""
        while True:
            if Base.work_status == Base.STATUS.STOPING: return None
            with self._concurrency_lock:
                # 实时检查配置中的线程限制
                if self._current_active < self.config.actual_thread_counts:
                    self._current_active += 1
                    break
            time.sleep(0.01)
        
        if Base.work_status == Base.STATUS.STOPING:
            with self._concurrency_lock: self._current_active -= 1
            return {}

        try:
            with self._skip_lock:
                if hasattr(task, 'file_path_full') and task.file_path_full in self.skipped_files:
                    return None # Skip execution
            return task.start()
        finally:
            with self._concurrency_lock:
                self._current_active -= 1

    def _execute_tasks_async(self, tasks_list):
        """异步执行模式：使用 aiohttp 处理高并发请求"""
        import asyncio
        from ModuleFolders.Infrastructure.LLMRequester.AsyncLLMRequester import AsyncLLMRequester
        from ModuleFolders.Infrastructure.LLMRequester.AsyncSignalHub import get_signal_hub
        from ModuleFolders.Infrastructure.LLMRequester.ErrorClassifier import ErrorClassifier, ErrorType

        # 获取用户设置的并发数
        max_concurrency = self.config.actual_thread_counts
        signal_hub = get_signal_hub()
        signal_hub.reset()  # 重置信号状态
        signal_hub.set_concurrency(max_concurrency)

        # 引用 self 以便在异步函数中使用
        executor_self = self

        async def run_single_task(task, semaphore):
            """执行单个异步任务"""
            import time as time_module
            task_start = time_module.time()

            if Base.work_status == Base.STATUS.STOPING:
                return None

            # 等待暂停恢复
            await signal_hub.wait_if_paused()

            # 信号量控制：保护本地系统资源
            async with semaphore:
                if Base.work_status == Base.STATUS.STOPING:
                    return None

                # 检查是否跳过
                with executor_self._skip_lock:
                    if hasattr(task, 'file_path_full') and task.file_path_full in executor_self.skipped_files:
                        return None

                # 打印任务开始日志
                task_id = getattr(task, 'task_id', '???')
                preview = str(list(task.source_text_dict.values())[:1])[:50] if hasattr(task, 'source_text_dict') else ''
                executor_self.print(f"[dim][{task_id}] Translating: {preview}...[/dim]")

                # 获取平台配置
                platform_config = executor_self.config.get_platform_configuration("translationReq")

                # 发起异步请求
                requester = AsyncLLMRequester()
                skip, error_type, content, pt, ct = await requester.send_request_async(
                    task.messages, task.system_prompt, platform_config
                )

                elapsed = time_module.time() - task_start

                if skip:
                    # 上报错误状态
                    executor_self.report_api_status(False)
                    # 打印错误日志
                    executor_self.print(f"[red]✗ [{task_id}] Failed ({error_type}) | {elapsed:.2f}s[/red]")
                    # 检查是否为软伤错误（可重试）
                    err_type, _ = ErrorClassifier.classify(content)
                    if err_type == ErrorType.SOFT_ERROR:
                        if ErrorClassifier.should_reduce_concurrency(content):
                            signal_hub.broadcast_rate_limit(platform_config.get("api_url", ""))
                    return {"check_result": False, "row_count": 0, "prompt_tokens": pt, "completion_tokens": ct, "error_type": error_type}

                # 上报成功状态
                executor_self.report_api_status(True)

                # 结果处理
                if content:
                    from ModuleFolders.Domain.ResponseExtractor.ResponseExtractor import ResponseExtractor
                    response_dict = ResponseExtractor.text_extraction(task, task.source_text_dict, content)

                    if response_dict:
                        for item, response in zip(task.items, response_dict.values()):
                            with item.atomic_scope():
                                item.model = executor_self.config.model
                                item.translated_text = response
                                item.translation_status = TranslationStatus.TRANSLATED

                        # 打印成功日志
                        executor_self.print(f"[green]√ [{task_id}] Done ({len(task.items)} lines) | {elapsed:.2f}s | {pt}+{ct}T[/green]")

                        return {
                            "check_result": True,
                            "row_count": len(task.items),
                            "prompt_tokens": pt,
                            "completion_tokens": ct,
                            "extra_info": getattr(task, "extra_info", {})
                        }

                return {"check_result": False, "row_count": 0, "prompt_tokens": pt, "completion_tokens": ct}

        async def run_all_tasks():
            """运行所有异步任务"""
            # 初始化连接池，传入线程数以保护系统资源
            await AsyncLLMRequester.get_session(max_concurrency)

            # 信号量控制并发数，保护文件描述符和端口资源
            semaphore = asyncio.Semaphore(max_concurrency)
            tasks = [run_single_task(task, semaphore) for task in tasks_list]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 处理结果
            for result in results:
                if isinstance(result, Exception):
                    self.error(f"Async task error: {result}")
                elif result:
                    self._process_async_result(result)

            # 关闭连接池
            await AsyncLLMRequester.close_session()

        self.info(f"[bold cyan]使用异步模式执行任务 (并发数: {max_concurrency})...[/bold cyan]")
        asyncio.run(run_all_tasks())

    def _process_async_result(self, result):
        """处理异步任务结果"""
        if not result or not isinstance(result, dict):
            return

        with self.project_status_data.atomic_scope():
            self.project_status_data.total_requests += 1
            is_error = not result.get("check_result")
            self.project_status_data.error_requests += 1 if is_error else 0
            self.project_status_data.success_requests += 0 if is_error else 1
            self.project_status_data.line += result.get("row_count", 0)
            self.project_status_data.token += result.get("prompt_tokens", 0) + result.get("completion_tokens", 0)
            self.project_status_data.total_completion_tokens += result.get("completion_tokens", 0)
            self.project_status_data.time = time.time() - self.project_status_data.start_time

        self.cache_manager.require_save_to_file(self.session_output_path)
        self.emit(Base.EVENT.TASK_UPDATE, self.project_status_data.to_dict())

    # API 状态上报与轮转逻辑
    def report_api_status(self, is_success: bool) -> None:
        if not self.config.enable_api_failover or not self.api_pipeline:
            return

        with self._api_error_lock:
            if is_success:
                if self.global_consecutive_api_errors > 0:
                    self.global_consecutive_api_errors = 0
            else:
                self.global_consecutive_api_errors += 1
                threshold = self.config.api_failover_threshold
                if self.global_consecutive_api_errors >= threshold:
                    self.warning(f"API consecutive errors ({self.global_consecutive_api_errors}) reached threshold ({threshold}). Switching API...")
                    self._switch_api()
                    self.global_consecutive_api_errors = 0

    def _switch_api(self) -> None:
        try:
            if len(self.api_pipeline) <= 1:
                self.warning("No backup APIs available in pool.")
                return

            # Rotate pipeline
            self.current_api_index = (self.current_api_index + 1) % len(self.api_pipeline)
            new_api = self.api_pipeline[self.current_api_index]
            
            self.print(f"[bold yellow]↺ Switching API to: {new_api}[/bold yellow]")
            
            # Update Config safely
            # Note: TaskConfig is shared, but we need to ensure atomic update if possible
            # Or just rely on Python's GIL for dict updates
            if self.current_mode == TaskType.TRANSLATION:
                self.config.api_settings["translate"] = new_api
            elif self.current_mode == TaskType.POLISH:
                self.config.api_settings["polish"] = new_api
            
            # Re-prepare configuration (updates base_url, keys, models, etc.)
            self.config.prepare_for_translation(self.current_mode)
            
            # Update limiter with new limits
            self.request_limiter.set_limit(self.config.tpm_limit, self.config.rpm_limit)
            
            self.info(f"Successfully switched to {new_api}. New Model: {self.config.model}")
            
        except Exception as e:
            self.error(f"Failed to switch API: {e}")

    # 应用关闭事件
    def app_shut_down(self, event: int, data: dict) -> None:
        Base.work_status = Base.STATUS.STOPING

    # 手动导出事件
    def task_manual_export(self, event: int, data: dict) -> None:

        self.print("")
        self.info(f"正在读取数据，准备输出中 ...")
        self.print("")

        # 获取配置信息，此时 config 是一个字典，后面需要使用get
        config = self.load_config()
        
        output_path = data.get("export_path")
        inpput_path = config.get("label_input_path")

        # 触发手动导出插件事件
        self.plugin_manager.broadcast_event("manual_export", config, self.cache_manager.project)

        # 如果开启了转换简繁开关功能，则进行文本转换
        if config.get("response_conversion_toggle"):  # 使用 .get()
            self.print("")

            self.info(f"已启动自动简繁转换功能，正在使用 {config.get('opencc_preset')} 配置进行字形转换 ...")
            self.print("")

            converter = opencc.OpenCC(config.get('opencc_preset'))
            cache_list = self.cache_manager.project.items_iter()
            for item in cache_list:
                if item.translation_status == TranslationStatus.TRANSLATED:
                    item.translated_text = converter.convert(item.translated_text)
                if item.translation_status == TranslationStatus.POLISHED:
                    item.polished_text = converter.convert(item.polished_text)
            self.print("")
            self.info(f"简繁转换完成。")
            self.print("")

        # 输出配置包
        output_config = {
            "translated_suffix": config.get('output_filename_suffix'),
            "bilingual_suffix": "_bilingual",
            "bilingual_order": config.get('bilingual_text_order','translation_first'),
            "enable_bilingual_output": config.get('enable_bilingual_output', False)
        }

        # 写入文件
        self.file_writer.output_translated_content(
            self.cache_manager.project,
            output_path,
            inpput_path, 
            output_config, 
        )

        self.print("")
        self.info(f"翻译结果已成功保存至 {output_path} 目录。")
        self.print("")

    # 任务停止事件
    def task_stop(self, event: int, data: dict) -> None:
        # 如果已经是停止中或已停止，则跳过
        if Base.work_status in [Base.STATUS.STOPING, Base.STATUS.TASKSTOPPED]:
            return

        # 设置运行状态为停止中
        Base.work_status = Base.STATUS.STOPING
        
        # 如果存在执行器，尝试停止接收新任务
        if self.executor:
            try:
                self.executor.shutdown(wait=False)
            except: pass

        def target() -> None:
            # 增加超时退出机制，防止死锁
            start_wait = time.time()
            while True:
                time.sleep(0.5)
                if Base.work_status == Base.STATUS.TASKSTOPPED or time.time() - start_wait > 30:
                    if Base.work_status != Base.STATUS.TASKSTOPPED:
                         Base.work_status = Base.STATUS.TASKSTOPPED
                    self.print("")
                    self.info("翻译任务已停止 ...")
                    self.print("")
                    self.emit(Base.EVENT.TASK_STOP_DONE, {})
                    break

        # 子线程循环检测停止状态
        threading.Thread(target = target, daemon=True).start()

    # 任务开始事件
    def task_start(self, event: int, data: dict) -> None:
        # 如果正在停止中，不接受新任务
        if Base.work_status == Base.STATUS.STOPING:
            self.warning("系统正在停止中，无法开始新任务。")
            return
            
        # Reset error counter at the very beginning of a new task
        self.consecutive_errors = 0
        if not data.get("silent", False): # Don't reset status on silent resume
            self.emit(Base.EVENT.SYSTEM_STATUS_UPDATE, {"status": "normal"})

        # Clear skipped files list for the new session
        with self._skip_lock:
            self.skipped_files.clear()

        # 获取配置信息
        continue_status = data.get("continue_status")
        current_mode = data.get("current_mode")
        self.current_mode = current_mode
        self.session_input_path = data.get("session_input_path")
        self.session_output_path = data.get("session_output_path")

        # 翻译任务
        if current_mode == TaskType.TRANSLATION:
            threading.Thread(
                target = self.translation_start_target,
                args = (continue_status,),
            ).start()
        
        # 润色任务
        elif current_mode == TaskType.POLISH:
            threading.Thread(
                target = self.polish_start_target,
                args = (continue_status,),
            ).start()

        else:
            self.print("")
            self.error(f"非法的翻译模式：{current_mode}，请检查配置文件 ...")
            self.print("")
            return None

    # 翻译主流程
    def translation_start_target(self, continue_status: bool) -> None:
        try:
            # 设置翻译状态为正在翻译状态
            Base.work_status = Base.STATUS.TASKING

            # Initialize failover before preparing translation
            self._initialize_failover()

            # 配置翻译平台信息
            self.config.prepare_for_translation(TaskType.TRANSLATION)

            # 配置请求限制器
            self.request_limiter.set_limit(self.config.tpm_limit, self.config.rpm_limit)

            # --- 修复：确保总行数始终被正确初始化 ---
            if continue_status == False or self.cache_manager.project.stats_data is None:
                self.project_status_data = CacheProjectStatistics()
                self.cache_manager.project.stats_data = self.project_status_data
                self.project_status_data.total_line = self.cache_manager.get_item_count()
            else:
                self.project_status_data = self.cache_manager.project.stats_data
                self.project_status_data.total_line = self.cache_manager.get_item_count()
                self.project_status_data.start_time = time.time() # 重置开始时间
                self.project_status_data.total_completion_tokens = 0 # 重置完成的token数量
                
                # --- Fix RPM/TPM calculation for resumed tasks ---
                # We need to offset the lines/tokens already processed in previous sessions
                # so that the current session's RPM/TPM is calculated based on current session's delta.
                self.project_status_data.resume_offset_line = self.project_status_data.line
                self.project_status_data.resume_offset_token = self.project_status_data.token
                self.project_status_data.resume_offset_requests = self.project_status_data.total_requests
            # ----------------------------------------------------------------
            # ----------------------------------------------------------------

            # 初始同步一次数据到 UI，确保不会显示为 0/0
            self.project_status_data.line = self.cache_manager.get_item_count_by_status(TranslationStatus.TRANSLATED)
            stats_dict = self.project_status_data.to_dict()
            stats_dict['is_start'] = True
            self.emit(Base.EVENT.TASK_UPDATE, stats_dict)

            # 触发插件事件
            self.plugin_manager.broadcast_event("text_filter", self.config, self.cache_manager.project)
            self.plugin_manager.broadcast_event("preproces_text", self.config, self.cache_manager.project)

            # 根据最大轮次循环
            for current_round in range(self.config.round_limit + 1):
                # 检测是否需要停止任务
                if Base.work_status == Base.STATUS.STOPING:
                    # 循环次数比实际最大轮次要多一轮，当触发停止翻译的事件时，最后都会从这里退出任务
                    # 执行到这里说明停止任意的任务已经执行完毕，可以重置内部状态了
                    Base.work_status = Base.STATUS.TASKSTOPPED
                    return None

                # 获取 待翻译 状态的条目数量
                item_count_status_untranslated = self.cache_manager.get_item_count_by_status(TranslationStatus.UNTRANSLATED)

                # 判断是否需要继续翻译
                if item_count_status_untranslated == 0:
                    self.print("")
                    self.info("所有文本均已翻译，翻译任务已结束 ...")
                    self.print("")
                    break

                # 达到最大翻译轮次时
                if item_count_status_untranslated > 0:
                    if self.config.enable_smart_round_limit and current_round == self.config.round_limit:
                        # 动态增加 round_limit
                        self.config.round_limit = int(self.config.round_limit * self.config.smart_round_limit_multiplier)
                        self.warning(f"已达到最大翻译轮次，但仍有未翻译文本。智能轮次限制已将最大轮次增加到 {self.config.round_limit} ...")
                        # 不中断循环，继续进行翻译
                    elif not self.config.enable_smart_round_limit and current_round == self.config.round_limit:
                        self.print("")
                        self.warning("已达到最大翻译轮次，仍有部分文本未翻译，请检查结果 ...")
                        self.print("")
                        break


                # 第二轮开始对半切分
                if current_round > 0:
                    if self.config.tokens_limit_switch:
                        if hasattr(self.config, 'tokens_limit'):
                            self.config.tokens_limit = max(100, int(self.config.tokens_limit / 2))
                    else:
                        self.config.lines_limit = max(1, int(self.config.lines_limit / 2))

                # 生成缓存数据条目片段的合集列表，原文列表与上文列表一一对应
                chunks, previous_chunks, file_paths = self.cache_manager.generate_item_chunks(
                    "line" if self.config.tokens_limit_switch == False else "token",
                    self.config.lines_limit if self.config.tokens_limit_switch == False else self.config.tokens_limit,
                    self.config.pre_line_counts,
                    TaskType.TRANSLATION
                )

                # 生成翻译任务合集列表
                tasks_list = []
                self.print("")
                self.info(f"正在生成翻译任务 ...")
                
                # Pre-calculate file stats for UI
                unique_files = list(dict.fromkeys(file_paths))
                file_info_map = {path: {"name": os.path.basename(path), "index": i} for i, path in enumerate(unique_files, 1)}
                total_files = len(unique_files)

                for i, (chunk, previous_chunk, file_path) in enumerate(zip(chunks, previous_chunks, file_paths), 1):
                    # Skip task creation if file is marked for skipping
                    with self._skip_lock:
                        if file_path in self.skipped_files:
                            continue

                    # 确定该任务的主语言
                    language_stats = self.cache_manager.project.get_file(file_path).language_stats # 获取该文件的语言检测数据
                    file_source_lang = get_source_language_for_file(self.config.source_language,self.config.target_language,language_stats)

                    task = TranslatorTask(self.config, self.plugin_manager, self.request_limiter, file_source_lang)  # 实例化
                    task.task_id = f"{current_round + 1:02d}-{i:03d}"
                    task.file_path_full = file_path
                    
                    # Store file info in task for callback
                    f_info = file_info_map.get(file_path)
                    task.extra_info = {
                        "file_name": f_info["name"],
                        "file_index": f_info["index"],
                        "total_files": total_files,
                        "file_path_full": file_path
                    }

                    task.set_items(chunk)  # 传入该任务待翻译原文
                    task.set_previous_items(previous_chunk)  # 传入该任务待翻译原文的上文
                    task.prepare(self.config.target_platform)  # 预先构建消息列表
                    tasks_list.append(task)
                self.info(f"已经生成全部翻译任务 ...")
                self.print("")

                # 输出开始翻译的日志
                self.print("")

                # 如果是断点续传，抑制重复的基础环境信息输出
                if not continue_status:
                    self.info(f"最大轮次 - {self.config.round_limit}")
                    self.info(f"项目类型 - {self.config.translation_project}")
                    self.info(f"原文语言 - {self.config.source_language}")
                    self.info(f"译文语言 - {self.config.target_language}")
                    
                    platform_name = self.config.platforms.get(self.config.target_platform, {}).get('name', '未知')
                    self.info(f"接口名称 - {platform_name}")
                    self.info(f"接口地址 - {self.config.base_url}")
                    self.info(f"模型名称 - {self.config.model}")
                    
                    self.info(f"RPM 限额 - {self.config.rpm_limit}")
                    self.info(f"TPM 限额 - {self.config.tpm_limit}")

                    # 打印提示词模式信息
                    s_lang = self.config.source_language
                    if self.config.target_platform == "LocalLLM":
                        system = PromptBuilderLocal.build_system(self.config, s_lang)
                    elif self.config.target_platform == "sakura":
                        system = PromptBuilderSakura.build_system(self.config, s_lang)
                    elif self.config.translation_prompt_selection["last_selected_id"] in (PromptBuilderEnum.COMMON, PromptBuilderEnum.COT, PromptBuilderEnum.THINK):
                        system = PromptBuilder.build_system(self.config, s_lang)
                    else:
                        system = self.config.translation_prompt_selection["prompt_content"]
                    
                    self.info(f"并发请求 - {self.config.actual_thread_counts} 线程")

                    # 高并发时建议使用异步模式
                    if self.config.actual_thread_counts >= 15 and not getattr(self.config, 'enable_async_mode', False):
                        hint_msg = self.tra('msg_high_concurrency_hint').format(self.config.actual_thread_counts)
                        self.print(f"[bold yellow]{hint_msg}[/bold yellow]")
                else:
                    # 仅在第一轮显示恢复提示
                    if current_round == 0:
                        self.info(f"[bold yellow]检测到断点续传：正在恢复 {os.path.basename(self.config.label_input_path)} 的任务状态...[/bold yellow]")

                self.info(f"即将开始执行任务，预计任务总数为 {len(tasks_list)}，请注意保持网络通畅 ...")
                time.sleep(3)
                self.print("")

                # 根据配置选择同步或异步执行模式
                if getattr(self.config, 'enable_async_mode', False):
                    self._execute_tasks_async(tasks_list)
                else:
                    # 重置并发计数器，防止上一轮异常退出后卡死
                    with self._concurrency_lock:
                        self._current_active = 0
                    # 开始执行翻译任务,构建异步线程池 (使用 100 高限额，由 gated_run 实际控制并发)
                    self.executor = concurrent.futures.ThreadPoolExecutor(max_workers = 100, thread_name_prefix = "translator")
                    try:
                        with self.executor as executor:
                            for task in tasks_list:
                                if Base.work_status == Base.STATUS.STOPING: break
                                future = executor.submit(self._gated_run, task)
                                future.add_done_callback(self.task_done_callback)  # 为future对象添加一个回调函数，当任务完成时会被调用，更新数据
                    finally:
                        self.executor = None

            # 等待可能存在的缓存文件写入请求处理完毕
            time.sleep(CacheManager.SAVE_INTERVAL)

            # 触发插件事件
            self.plugin_manager.broadcast_event("postprocess_text", self.config, self.cache_manager.project)

            # 如果开启了转换简繁开关功能，则进行文本转换
            if self.config.response_conversion_toggle:

                self.print("")
                self.info(f"已启动自动简繁转换功能，正在使用 {self.config.opencc_preset} 配置进行字形转换 ...")
                self.print("")

                converter = opencc.OpenCC(self.config.opencc_preset)
                cache_list = self.cache_manager.project.items_iter()
                for item in cache_list:
                    if item.translation_status == TranslationStatus.TRANSLATED:
                        item.translated_text = converter.convert(item.translated_text)
                    if item.translation_status == TranslationStatus.POLISHED:
                        item.polished_text = converter.convert(item.polished_text)

            # 输出配置包
            output_config = {
                "translated_suffix": self.config.output_filename_suffix,
                "bilingual_suffix": "_bilingual",
                "bilingual_order": self.config.bilingual_text_order,
                "enable_bilingual_output": self.config.enable_bilingual_output
            }

            # 写入文件
            self.file_writer.output_translated_content(
                self.cache_manager.project,
                self.session_output_path,
                self.session_input_path,
                output_config,
                self.config
            )
            self.print("")
            self.info(f"翻译结果已保存至 {self.session_output_path} 目录 ...")
            self.print("")

            # 重置内部状态（正常完成翻译）
            Base.work_status = Base.STATUS.TASKSTOPPED

            # 触发翻译停止完成的事件
            self.plugin_manager.broadcast_event("translation_completed", self.config, self.cache_manager.project)

            # 触发翻译完成事件
            self.emit(Base.EVENT.TASK_COMPLETED, {})
        except Exception as e:
            self.error(f"翻译任务异常终止: {e}", e)
            Base.work_status = Base.STATUS.TASKSTOPPED
            self.emit(Base.EVENT.TASK_STOP_DONE, {})

    def _initialize_failover(self):
        self.consecutive_errors = 0
        self.api_pipeline = []
        self.current_api_index = 0
        if self.config.enable_api_failover:
            primary_api = self.config.api_settings.get("translate")
            if primary_api:
                self.api_pipeline.append(primary_api)
            
            backup_apis = self.config.backup_apis or []
            for api in backup_apis:
                if api not in self.api_pipeline:
                    self.api_pipeline.append(api)
            
            if len(self.api_pipeline) > 1:
                self.info(f"API Failover enabled. Pipeline: {' -> '.join(self.api_pipeline)}")

    # 润色主流程
    def polish_start_target(self, continue_status: bool, silent: bool = False) -> None:
        try:
            # 设置翻译状态为正在翻译状态
            Base.work_status = Base.STATUS.TASKING


            # 配置翻译平台信息
            self.config.prepare_for_translation(TaskType.POLISH)

            # 配置请求限制器
            self.request_limiter.set_limit(self.config.tpm_limit, self.config.rpm_limit)

            # --- 修复：确保总行数始终被正确初始化 ---
            if continue_status == False or self.cache_manager.project.stats_data is None:
                self.project_status_data = CacheProjectStatistics()
                self.cache_manager.project.stats_data = self.project_status_data
                self.project_status_data.total_line = self.cache_manager.get_item_count()
            else:
                self.project_status_data = self.cache_manager.project.stats_data
                self.project_status_data.total_line = self.cache_manager.get_item_count()
                self.project_status_data.start_time = time.time() # 重置开始时间
                self.project_status_data.total_completion_tokens = 0 # 重置完成的token数量

                # --- Fix RPM/TPM calculation for resumed tasks ---
                self.project_status_data.resume_offset_line = self.project_status_data.line
                self.project_status_data.resume_offset_token = self.project_status_data.token
                self.project_status_data.resume_offset_requests = self.project_status_data.total_requests
            # ----------------------------------------------------------------

            # 更新初始进度
            if self.config.polishing_mode_selection == "source_text_polish":
                self.project_status_data.line = self.cache_manager.get_item_count_by_status(TranslationStatus.UNTRANSLATED)
            else:
                self.project_status_data.line = self.cache_manager.get_item_count_by_status(TranslationStatus.POLISHED)

            # 更新监控面板信息
            stats_dict = self.project_status_data.to_dict()
            stats_dict['is_start'] = True
            self.emit(Base.EVENT.TASK_UPDATE, stats_dict)

            # 触发插件事件
            self.plugin_manager.broadcast_event("text_filter", self.config, self.cache_manager.project)


            # 根据最大轮次循环
            for current_round in range(self.config.round_limit + 1):
                # 检测是否需要停止任务
                if Base.work_status == Base.STATUS.STOPING:
                    # 循环次数比实际最大轮次要多一轮，当触发停止翻译的事件时，最后都会从这里退出任务
                    # 执行到这里说明停止任意的任务已经执行完毕，可以重置内部状态了
                    Base.work_status = Base.STATUS.TASKSTOPPED
                    return None

                # 根据润色模式，获取可润色的条目数量
                if self.config.polishing_mode_selection == "source_text_polish":
                    item_count_status_unpolishd = self.cache_manager.get_item_count_by_status(TranslationStatus.UNTRANSLATED)
                elif self.config.polishing_mode_selection == "translated_text_polish":
                    item_count_status_unpolishd = self.cache_manager.get_item_count_by_status(TranslationStatus.TRANSLATED)

                # 判断是否需要继续润色
                if item_count_status_unpolishd == 0:
                    if not silent:
                        self.print("")
                        self.info("所有文本均已润色，润色任务已结束 ...")
                        self.print("")
                    break

                # 达到最大任务轮次时
                if item_count_status_unpolishd > 0:
                    if self.config.enable_smart_round_limit and current_round == self.config.round_limit:
                        # 动态增加 round_limit
                        self.config.round_limit = int(self.config.round_limit * self.config.smart_round_limit_multiplier)
                        self.warning(f"已达到最大任务轮次，但仍有未润色文本。智能轮次限制已将最大轮次增加到 {self.config.round_limit} ...")
                        # 不中断循环，继续进行润色
                    elif not self.config.enable_smart_round_limit and current_round == self.config.round_limit:
                        self.print("")
                        self.warning("已达到最大任务轮次，仍有部分文本未翻译，请检查结果 ...")
                        self.print("")
                        break


                # 第一轮时且不是继续润色时，记录总行数
                if current_round == 0 and continue_status == False:
                 self.project_status_data.total_line = item_count_status_unpolishd
                 # 立即同步总行数到 UI
                 self.emit(Base.EVENT.TASK_UPDATE, self.project_status_data.to_dict())

                # 第二轮开始对半切分
                if current_round > 0:
                    if self.config.tokens_limit_switch:
                        if hasattr(self.config, 'tokens_limit'):
                            self.config.tokens_limit = max(100, int(self.config.tokens_limit / 2))
                    else:
                        self.config.lines_limit = max(1, int(self.config.lines_limit / 2))

                # 生成缓存数据条目片段的合集列表
                if self.config.polishing_mode_selection == "source_text_polish":
                    chunks, previous_chunks, file_paths = self.cache_manager.generate_item_chunks(
                        "line" if self.config.tokens_limit_switch == False else "token",
                        self.config.lines_limit if self.config.tokens_limit_switch == False else self.config.tokens_limit,
                        self.config.polishing_pre_line_counts,
                        TaskType.TRANSLATION
                    )
                elif self.config.polishing_mode_selection == "translated_text_polish":
                    chunks, previous_chunks, file_paths = self.cache_manager.generate_item_chunks(
                        "line" if self.config.tokens_limit_switch == False else "token",
                        self.config.lines_limit if self.config.tokens_limit_switch == False else self.config.tokens_limit,
                        self.config.polishing_pre_line_counts,
                        TaskType.POLISH
                    )

                # 生成润色任务合集列表
                tasks_list = []
                if not silent:
                    self.print("")
                    self.info(f"正在生成润色任务 ...")
                for i, (chunk, previous_chunk, file_path) in enumerate(zip(chunks, previous_chunks, file_paths), 1):
                    task = PolisherTask(self.config, self.plugin_manager, self.request_limiter)  # 实例化
                    task.task_id = f"{current_round + 1:02d}-{i:03d}"
                    task.set_items(chunk)  # 传入该任务待润色文
                    task.set_previous_items(previous_chunk)  # 传入该任务待润色文的上文
                    task.prepare()  # 预先构建消息列表
                    tasks_list.append(task)
                
                if not silent:
                    self.info(f"已经生成全部润色任务 ...")
                    self.print("")

                    # 输出开始翻译的日志
                    self.print("")
                    self.info(f"当前轮次 - {current_round + 1}")
                    self.info(f"最大轮次 - {self.config.round_limit}")
                    self.info(f"项目类型 - {self.config.translation_project}")
                    self.print("")
                    self.info(f"接口名称 - {self.config.platforms.get(self.config.target_platform, {}).get('name', '未知')}")
                    self.info(f"接口地址 - {self.config.base_url}")
                    self.info(f"模型名称 - {self.config.model}")
                    self.print("")
                    self.info(f"RPM 限额 - {self.config.rpm_limit}")
                    self.info(f"TPM 限额 - {self.config.tpm_limit}")

                    # 根据提示词规则打印基础指令
                    system = ""
                    if self.config.polishing_prompt_selection["last_selected_id"] == PromptBuilderEnum.POLISH_COMMON:
                        system = PromptBuilderPolishing.build_system(self.config)
                    else:
                        system = self.config.polishing_prompt_selection["prompt_content"]
                    self.print("")
                    if system:
                        self.info(f"本次任务使用以下基础提示词：\n{system}\n") 

                    self.info(f"即将开始执行润色任务，预计任务总数为 {len(tasks_list)}, 同时执行的任务数量为 {self.config.actual_thread_counts}，请注意保持网络通畅 ...")
                    time.sleep(3)
                    self.print("")

                # 重置并发计数器，防止上一轮异常退出后卡死
                with self._concurrency_lock:
                    self._current_active = 0
                # 开始执行润色务,构建异步线程池 (使用 100 高限额，由 gated_run 实际控制并发)
                self.executor = concurrent.futures.ThreadPoolExecutor(max_workers = 100, thread_name_prefix = "translator")
                try:
                    with self.executor as executor:
                        for task in tasks_list:
                            if Base.work_status == Base.STATUS.STOPING: break
                            future = executor.submit(self._gated_run, task)
                            future.add_done_callback(self.task_done_callback)  # 为future对象添加一个回调函数，当任务完成时会被调用，更新数据
                finally:
                    self.executor = None

            # 等待可能存在的缓存文件写入请求处理完毕
            time.sleep(CacheManager.SAVE_INTERVAL)

            # 输出配置包
            output_config = {
                "translated_suffix": self.config.output_filename_suffix,
                "bilingual_suffix": "_bilingual",
                "bilingual_order": self.config.bilingual_text_order,
                "enable_bilingual_output": self.config.enable_bilingual_output
            }

            # 写入文件
            self.file_writer.output_translated_content(
                self.cache_manager.project,
                self.config.polishing_output_path,
                self.config.label_input_path,
                output_config,
            )
            self.print("")
            self.info(f"润色结果已保存至 {self.config.polishing_output_path} 目录 ...")
            self.print("")

            # 重置内部状态
            Base.work_status = Base.STATUS.TASKSTOPPED

            # 触发事件
            self.plugin_manager.broadcast_event("polish_completed", self.config, self.cache_manager.project)
            self.emit(Base.EVENT.TASK_COMPLETED, {})     # 翻译完成事件
        except Exception as e:
            self.error(f"润色任务异常终止: {e}", e)
            Base.work_status = Base.STATUS.TASKSTOPPED
            self.emit(Base.EVENT.TASK_STOP_DONE, {})



    # 单个翻译任务完成时,更新项目进度状态
    def task_done_callback(self, future: concurrent.futures.Future) -> None:
        try:
            result = future.result()

            if result is None or len(result) == 0:
                return

            # 确保 result 是字典类型
            if not isinstance(result, dict):
                return

            with self.project_status_data.atomic_scope():
                self.project_status_data.total_requests += 1
                is_error = not result.get("check_result")
                self.project_status_data.error_requests += 1 if is_error else 0
                self.project_status_data.success_requests += 0 if is_error else 1
                self.project_status_data.line += result.get("row_count", 0)
                self.project_status_data.token += result.get("prompt_tokens", 0) + result.get("completion_tokens", 0)
                self.project_status_data.total_completion_tokens += result.get("completion_tokens", 0)
                self.project_status_data.time = time.time() - self.project_status_data.start_time
                stats_dict = self.project_status_data.to_dict()
                
                if "extra_info" in result:
                    stats_dict.update(result["extra_info"])
                
                # Add session-specific metrics for correct Rate calculation (Resume Fix)
                stats_dict['session_token'] = self.project_status_data.token - self.project_status_data.resume_offset_token
                stats_dict['session_requests'] = self.project_status_data.total_requests - self.project_status_data.resume_offset_requests

            self.cache_manager.require_save_to_file(self.session_output_path)
            self.emit(Base.EVENT.TASK_UPDATE, stats_dict)

        except Exception as e:
            self.error(f"Task callback error: {e}", e if self.is_debug() else None)