"""
术语分析核心服务 - 从 ainiee_cli.py 分离
负责AI自动分析术语表的核心逻辑
"""
import os
import threading
import concurrent.futures
from datetime import datetime
import rapidjson as json

from rich.console import Console

console = Console()


class GlossaryAnalyzer:
    """术语分析器，处理AI自动分析术语表的核心逻辑"""

    def __init__(self, cli_menu):
        """
        初始化术语分析器

        Args:
            cli_menu: CLIMenu实例，用于访问配置和其他依赖
        """
        self.cli = cli_menu

    @property
    def config(self):
        return self.cli.config

    @property
    def i18n(self):
        return self.cli.i18n

    def _tr(self, key, default=None, *args):
        value = self.i18n.get(key) if self.i18n else None
        if not value or value == key:
            value = default if default is not None else key
        if args:
            try:
                return value.format(*args)
            except Exception:
                return value
        return value

    @property
    def PROJECT_ROOT(self):
        return self.cli.PROJECT_ROOT

    @property
    def file_reader(self):
        return self.cli.file_reader

    def save_config(self):
        self.cli.save_config()

    def execute_analysis(
        self,
        input_path,
        analysis_percent,
        analysis_lines,
        temp_config=None,
        analysis_mode="full",
        prompt_file=None,
    ):
        """
        执行术语表分析的核心逻辑

        Args:
            input_path: 输入文件路径
            analysis_percent: 分析百分比
            analysis_lines: 分析行数（优先于百分比）
            temp_config: 临时API配置（可选）
            analysis_mode: full=全本/按比例单次提取，split=按行拆分提取
            prompt_file: 自定义术语分析提示词路径（可选）

        Returns:
            tuple: (filtered_terms, glossary_data) 或 None（如果失败）
        """
        from ModuleFolders.Infrastructure.LLMRequester.LLMRequester import LLMRequester
        from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig
        from ModuleFolders.Infrastructure.TaskConfig.TaskType import TaskType

        # 读取文件内容
        console.print(f"[cyan]{self.i18n.get('msg_reading_file') or '正在读取文件...'}[/cyan]")

        project_type = self.config.get("translation_project", "auto")
        cache_data = self.file_reader.read_files(project_type, input_path, "")

        if not cache_data:
            console.print(f"[red]{self.i18n.get('msg_no_content') or '无法读取文件内容'}[/red]")
            return None

        # 获取所有文本行
        all_items = list(cache_data.items_iter())
        total_lines = len(all_items)

        if total_lines == 0:
            console.print(f"[red]{self.i18n.get('msg_no_text_found') or '未找到可分析的文本'}[/red]")
            return None

        # 计算要分析的行数
        if analysis_lines:
            lines_to_analyze = min(analysis_lines, total_lines)
        else:
            lines_to_analyze = int(total_lines * analysis_percent / 100)

        lines_to_analyze = max(1, lines_to_analyze)

        # 获取要分析的文本
        items_to_analyze = all_items[:lines_to_analyze]
        selected_text = "\n".join([item.source_text for item in items_to_analyze])
        estimated_tokens = self._estimate_token_count(selected_text)
        normalized_mode = "split" if analysis_mode == "split" else "full"

        console.print(f"[green]{self.i18n.get('msg_total_lines') or '总行数'}: {total_lines}[/green]")
        console.print(f"[green]{self.i18n.get('msg_lines_to_analyze') or '将分析行数'}: {lines_to_analyze}[/green]")
        console.print(
            f"[green]{self.i18n.get('msg_estimated_tokens') or '预估Token'}: "
            f"{estimated_tokens:,}[/green]"
        )
        console.print(
            f"[dim]{self.i18n.get('msg_token_reference_note') or 'Token仅用于参考；实际范围仍按行数/比例截取。'}[/dim]"
        )

        if normalized_mode == "full":
            console.print(
                f"[cyan]{self.i18n.get('msg_single_request_analysis') or '全本/按比例提取：将所选文本一次性发送给LLM。'}[/cyan]"
            )
        else:
            console.print(
                f"[yellow]{self.i18n.get('msg_split_request_analysis') or '拆分提取：将所选文本按行数拆分成多个批次。'}[/yellow]"
            )

        # 准备提示词
        prompt_path = self._resolve_prompt_file(prompt_file)
        console.print(
            f"[cyan]{self.i18n.get('msg_selected_prompt') or '已选提示词'}: "
            f"{prompt_path}[/cyan]"
        )

        with open(prompt_path, 'r', encoding='utf-8') as f:
            system_prompt = f.read()

        # 配置请求
        task_config = TaskConfig()
        task_config.load_config_from_dict(self.config)
        task_config.prepare_for_translation(TaskType.TRANSLATION)

        # 使用临时配置或当前配置
        if temp_config:
            platform_config = temp_config
            console.print(f"[cyan]{self.i18n.get('msg_using_temp_config') or '使用临时API配置'}: {temp_config.get('target_platform')}[/cyan]")
        else:
            platform_config = task_config.get_platform_configuration("translationReq")
            console.print(f"[cyan]{self.i18n.get('msg_using_current_config') or '使用当前配置'}: {platform_config.get('target_platform')}[/cyan]")

        all_terms = []
        completed_count = 0
        error_count = 0

        if normalized_mode == "full":
            messages = [{"role": "user", "content": selected_text}]
            try:
                requester = LLMRequester()
                skip, _, response, prompt_tokens, completion_tokens = requester.sent_request(
                    messages, system_prompt, platform_config
                )
                if not skip and response:
                    terms = self._parse_glossary_response(response)
                    all_terms.extend(terms)
                    completed_count = 1
                    console.print(
                        f"[green]√ {self._tr('msg_analysis_complete', '分析完成!')} "
                        f"| {self._tr('msg_found_terms', '发现专有名词')} {len(terms)} "
                        f"| {prompt_tokens}+{completion_tokens}T[/green]"
                    )
                else:
                    error_count = 1
                    console.print(f"[red]✗ {self.i18n.get('msg_analysis_error') or '分析出错'}[/red]")
            except Exception as e:
                error_count = 1
                console.print(f"[red]✗ {self.i18n.get('msg_analysis_error') or '分析出错'}: {e}[/red]")
        else:
            batch_size = self._get_split_batch_size()
            batches = [items_to_analyze[i:i+batch_size] for i in range(0, len(items_to_analyze), batch_size)]

            console.print(f"[cyan]{self.i18n.get('msg_batch_count') or '批次数量'}: {len(batches)}[/cyan]")

            # 获取用户配置的线程数 (临时配置优先)
            if temp_config and temp_config.get("thread_counts"):
                thread_count = temp_config.get("thread_counts")
            else:
                thread_count = task_config.actual_thread_counts
            console.print(f"[cyan]{self.i18n.get('msg_thread_count') or '并发线程数'}: {thread_count}[/cyan]")

            # 收集所有结果 (线程安全)
            terms_lock = threading.Lock()
            completed_counter = [0]  # 使用列表以便在闭包中修改
            failed_batches = []
            failed_lock = threading.Lock()

            def analyze_batch(batch_info, is_last_round=False):
                """单个批次的分析任务"""
                batch_idx, batch = batch_info
                text_content = "\n".join([item.source_text for item in batch])
                messages = [{"role": "user", "content": text_content}]

                try:
                    requester = LLMRequester()
                    skip, _, response, prompt_tokens, completion_tokens = requester.sent_request(
                        messages, system_prompt, platform_config
                    )

                    if not skip and response:
                        terms = self._parse_glossary_response(response)
                        with terms_lock:
                            all_terms.extend(terms)
                            completed_counter[0] += 1
                        console.print(
                            f"[green]√ [{batch_idx+1:03d}] "
                            f"{self._tr('glossary_log_batch_completed', '完成')} | "
                            f"{self._tr('msg_found_terms', '发现专有名词')} {len(terms)} | "
                            f"{prompt_tokens}+{completion_tokens}T[/green]"
                        )
                        return
                    else:
                        with failed_lock:
                            failed_batches.append(batch_info)
                        hint = self._tr('glossary_log_retry_suffix', '，将在下一轮重试') if not is_last_round else ""
                        console.print(f"[red]✗ [{batch_idx+1:03d}] {self._tr('glossary_log_batch_failed', '失败')}{hint}[/red]")
                except Exception as e:
                    with failed_lock:
                        failed_batches.append(batch_info)
                    hint = self._tr('glossary_log_retry_suffix', '，将在下一轮重试') if not is_last_round else ""
                    console.print(f"[red]✗ [{batch_idx+1:03d}] {self._tr('glossary_log_error', '错误')}: {e}{hint}[/red]")

            # 使用线程池并发执行
            console.print(f"\n[bold cyan]{self.i18n.get('msg_starting_concurrent') or '开始并发分析...'}[/bold cyan]\n")

            max_rounds = 3
            batch_infos = list(enumerate(batches))

            for round_num in range(max_rounds):
                is_last = (round_num == max_rounds - 1)
                if round_num > 0:
                    batch_infos = failed_batches[:]
                    failed_batches.clear()
                    console.print(
                        f"\n[yellow]⟳ "
                        f"{self._tr('glossary_log_retry_round_remaining', '第{}轮重试，剩余 {} 个失败批次...', round_num + 1, len(batch_infos))}"
                        f"[/yellow]\n"
                    )

                with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
                    list(executor.map(lambda b: analyze_batch(b, is_last), batch_infos))

                if not failed_batches:
                    break

            completed_count = completed_counter[0]
            error_count = len(failed_batches)
            console.print(
                f"\n[cyan]{self._tr('glossary_log_batch_summary', '完成: {}/{}, 失败: {}', completed_count, len(batches), error_count)}[/cyan]"
            )

        # 统计词频
        term_freq = self._calculate_term_frequency(all_terms, selected_text)

        if not term_freq:
            console.print(f"[yellow]{self.i18n.get('msg_no_terms_found') or '未找到专有名词'}[/yellow]")
            return None

        # 返回结果供菜单层处理
        return {
            'term_freq': term_freq,
            'input_path': input_path,
            'analysis_percent': analysis_percent,
            'analysis_lines': analysis_lines,
            'analysis_mode': normalized_mode,
            'estimated_tokens': estimated_tokens,
            'prompt_file': prompt_path,
        }

    def filter_and_save(self, analysis_result, min_freq):
        """
        过滤低频词并保存结果

        Args:
            analysis_result: execute_analysis 返回的结果
            min_freq: 最低词频阈值

        Returns:
            tuple: (filtered_terms, glossary_data, glossary_path)
        """
        term_freq = analysis_result['term_freq']
        input_path = analysis_result['input_path']
        analysis_percent = analysis_result['analysis_percent']
        analysis_lines = analysis_result['analysis_lines']
        analysis_mode = analysis_result.get('analysis_mode', 'full')
        estimated_tokens = analysis_result.get('estimated_tokens', 0)
        prompt_file = analysis_result.get('prompt_file', '')

        # 过滤低频词
        filtered_terms = {k: v for k, v in term_freq.items() if v['count'] >= min_freq}

        console.print(f"[green]{self.i18n.get('msg_before_filter') or '过滤前'}: {len(term_freq)}[/green]")
        console.print(f"[green]{self.i18n.get('msg_after_filter') or '过滤后'}: {len(filtered_terms)}[/green]")

        if not filtered_terms:
            console.print(f"[yellow]{self.i18n.get('msg_no_terms_after_filter') or '过滤后无剩余词条'}[/yellow]")
            return None

        # 生成术语表文件
        input_basename = os.path.splitext(os.path.basename(input_path))[0]
        input_dir = os.path.dirname(input_path) or "."

        glossary_path = os.path.join(input_dir, f"{input_basename}_自动术语.json")
        log_path = os.path.join(input_dir, f"{input_basename}_分析日志.txt")

        # 保存术语表
        glossary_data = self._generate_glossary_json(filtered_terms)
        with open(glossary_path, 'w', encoding='utf-8') as f:
            json.dump(glossary_data, f, indent=2, ensure_ascii=False)

        console.print(f"[bold green]{self.i18n.get('msg_glossary_saved') or '术语表已保存'}: {glossary_path}[/bold green]")

        # 保存分析日志
        self._save_glossary_analysis_log(
            log_path, input_path, analysis_percent, analysis_lines,
            term_freq, filtered_terms, min_freq,
            analysis_mode=analysis_mode,
            estimated_tokens=estimated_tokens,
            prompt_file=prompt_file,
        )

        console.print(f"[green]{self.i18n.get('msg_log_saved') or '分析日志已保存'}: {log_path}[/green]")

        return {
            'filtered_terms': filtered_terms,
            'glossary_data': glossary_data,
            'glossary_path': glossary_path
        }

    def save_glossary_directly(self, glossary_data, save_mode="import", base_glossary_path=None):
        """直接保存术语表（无翻译）"""
        if save_mode in ("import", "both"):
            existing_data = self.config.get("prompt_dictionary_data", [])
            existing_data.extend(glossary_data)
            self.config["prompt_dictionary_data"] = existing_data
            self.config["prompt_dictionary_switch"] = True
            self.save_config()
            console.print(f"[bold green]{self.i18n.get('msg_glossary_imported') or '术语表已导入!'}[/bold green]")

        if save_mode in ("standalone", "both"):
            save_path = self._build_output_glossary_path(base_glossary_path, "_独立术语表")
            self._save_glossary_json_to_path(glossary_data, save_path)
            console.print(f"[bold green]{self.i18n.get('msg_glossary_saved') or '术语表已保存'}: {save_path}[/bold green]")

    def multi_translate_and_select(self, filtered_terms, temp_config=None, rounds=3, save_mode="import", base_glossary_path=None):
        """
        多翻译选择功能

        Args:
            filtered_terms: 过滤后的术语字典
            temp_config: 临时API配置
            rounds: 翻译轮询次数
        """
        from ModuleFolders.UserInterface.TermSelector.TermSelector import TermSelector
        from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig
        from ModuleFolders.Infrastructure.TaskConfig.TaskType import TaskType

        console.print(f"\n[cyan]{self.i18n.get('msg_starting_multi_translate') or '开始多翻译请求...'}[/cyan]")
        console.print(f"[dim]{self.i18n.get('msg_rounds')}: {rounds}[/dim]")

        # 准备配置
        task_config = TaskConfig()
        task_config.load_config_from_dict(self.config)
        task_config.prepare_for_translation(TaskType.TRANSLATION)

        if temp_config:
            platform_config = temp_config
        else:
            platform_config = task_config.get_platform_configuration("translationReq")

        target_language = task_config.target_language

        # 为每个术语请求多次翻译
        multi_results = []
        total = len(filtered_terms)

        for idx, (src, term_data) in enumerate(filtered_terms.items(), 1):
            console.print(f"[{idx}/{total}] {self.i18n.get('msg_translating') or '正在翻译'}: {src}")

            options = []
            seen = set()

            for r in range(rounds):
                result = self._request_term_translation(src, term_data, target_language, platform_config, seen)
                if result and result['dst'] not in seen:
                    seen.add(result['dst'])
                    options.append(result)

            if options:
                multi_results.append({
                    "src": src,
                    "type": term_data.get("type", ""),
                    "analysis_info": term_data.get("info", "null"),
                    "options": options,
                    "selected_index": 0
                })
            else:
                console.print(f"[red]✗ {src} {self.i18n.get('msg_term_all_failed')}[/red]")

        skipped = total - len(multi_results)
        if skipped > 0:
            console.print(f"\n[yellow]⚠ {skipped} {self.i18n.get('msg_term_skipped_count')}[/yellow]")

        if not multi_results:
            console.print(f"[yellow]{self.i18n.get('msg_no_translation_results') or '未获得翻译结果'}[/yellow]")
            fallback_glossary = self._generate_glossary_json(filtered_terms)
            fallback_path = self._build_output_glossary_path(base_glossary_path, "_翻译失败原文回退")
            self._save_glossary_json_to_path(fallback_glossary, fallback_path)
            console.print(f"[yellow]{self.i18n.get('msg_glossary_saved') or '术语表已保存'}: {fallback_path}[/yellow]")
            return

        # 显示选择界面
        console.print(f"\n[green]{self.i18n.get('msg_translation_complete') or '翻译完成，请选择最佳译法'}[/green]")

        # 定义单条保存回调
        def save_single_term(term_data):
            if save_mode not in ("import", "both"):
                return
            existing_data = self.config.get("prompt_dictionary_data", [])
            existing_srcs = {item['src'] for item in existing_data}
            if term_data['src'] not in existing_srcs:
                existing_data.append(term_data)
                self.config["prompt_dictionary_data"] = existing_data
                self.config["prompt_dictionary_switch"] = True
                self.save_config()

        # 定义重试翻译回调
        def retry_translation(src, term_type, avoid_set=None):
            source = filtered_terms.get(src, {})
            term_data = {"type": term_type, "info": source.get("info", "null")}
            return self._request_term_translation(src, term_data, target_language, platform_config, avoid_set or set())

        selector = TermSelector(multi_results, request_callback=retry_translation, save_callback=save_single_term)
        selected_results = selector.show_selector()

        if not selected_results:
            console.print(f"[yellow]{self.i18n.get('msg_cancelled') or '已取消'}[/yellow]")
            return

        # 保存到术语表
        self._save_selected_translations(
            selected_results,
            filtered_terms,
            save_mode=save_mode,
            base_glossary_path=base_glossary_path
        )

    def batch_translate_and_select(self, filtered_terms, temp_config=None, save_mode="import", base_glossary_path=None):
        """批量翻译 - 所有术语一次性发送给AI"""
        from ModuleFolders.UserInterface.TermSelector.TermSelector import TermSelector
        from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig
        from ModuleFolders.Infrastructure.TaskConfig.TaskType import TaskType
        from ModuleFolders.Infrastructure.LLMRequester.LLMRequester import LLMRequester
        import re

        console.print(f"\n[cyan]{self.i18n.get('msg_starting_batch_translate')}[/cyan]")

        task_config = TaskConfig()
        task_config.load_config_from_dict(self.config)
        task_config.prepare_for_translation(TaskType.TRANSLATION)

        platform_config = temp_config if temp_config else task_config.get_platform_configuration("translationReq")
        target_language = task_config.target_language

        # 构建批量请求
        term_list = []
        for src, data in filtered_terms.items():
            term_list.append({
                "src": src,
                "type": data.get("type", "专有名词"),
                "info": data.get("info", "null")
            })

        system_prompt = f"""You are a terminology translator. Translate all terms into "{target_language}".
Each input item may include an "info" field with context from glossary analysis. Use it to keep names, character voice, places, items, and setting terms consistent.

Output a JSON array, each element: {{"src": "original", "dst": "translation", "info": "note"}}
Only output the JSON array, no other text."""

        user_content = json.dumps(term_list, ensure_ascii=False)
        messages = [{"role": "user", "content": user_content}]

        requester = LLMRequester()
        skip, _, response, pt, ct = requester.sent_request(messages, system_prompt, platform_config)

        if skip or not response:
            console.print(f"[red]{self.i18n.get('msg_no_translation_results')}[/red]")
            return

        console.print(f"[green]{self.i18n.get('msg_batch_translate_complete')} | {pt}+{ct}T[/green]")

        # 解析批量响应
        translated = {}
        try:
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                parsed = json.loads(json_match.group())
                for item in parsed:
                    if isinstance(item, dict) and 'src' in item and 'dst' in item:
                        translated[item['src']] = {"dst": item['dst'], "info": item.get('info', '')}
        except Exception:
            pass

        # 构建结果
        multi_results = []
        for src, data in filtered_terms.items():
            t = translated.get(src)
            options = [t] if t and t['dst'] else []
            if options:
                multi_results.append({
                    "src": src,
                    "type": data.get("type", ""),
                    "analysis_info": data.get("info", "null"),
                    "options": options,
                    "selected_index": 0
                })
            else:
                console.print(f"[red]✗ {src} {self.i18n.get('msg_term_all_failed')}[/red]")

        skipped = len(filtered_terms) - len(multi_results)
        if skipped > 0:
            console.print(f"\n[yellow]⚠ {skipped} {self.i18n.get('msg_term_skipped_count')}[/yellow]")

        if not multi_results:
            console.print(f"[yellow]{self.i18n.get('msg_no_translation_results')}[/yellow]")
            fallback_glossary = self._generate_glossary_json(filtered_terms)
            fallback_path = self._build_output_glossary_path(base_glossary_path, "_翻译失败原文回退")
            self._save_glossary_json_to_path(fallback_glossary, fallback_path)
            console.print(f"[yellow]{self.i18n.get('msg_glossary_saved') or '术语表已保存'}: {fallback_path}[/yellow]")
            return

        # 定义回调
        def save_single_term(term_data):
            if save_mode not in ("import", "both"):
                return
            existing_data = self.config.get("prompt_dictionary_data", [])
            existing_srcs = {item['src'] for item in existing_data}
            if term_data['src'] not in existing_srcs:
                existing_data.append(term_data)
                self.config["prompt_dictionary_data"] = existing_data
                self.config["prompt_dictionary_switch"] = True
                self.save_config()

        def retry_translation(src, term_type, avoid_set=None):
            source = filtered_terms.get(src, {})
            term_data = {"type": term_type, "info": source.get("info", "null")}
            return self._request_term_translation(src, term_data, target_language, platform_config, avoid_set or set())

        selector = TermSelector(multi_results, request_callback=retry_translation, save_callback=save_single_term)
        selected_results = selector.show_selector()

        if not selected_results:
            console.print(f"[yellow]{self.i18n.get('msg_cancelled')}[/yellow]")
            return

        self._save_selected_translations(
            selected_results,
            filtered_terms,
            save_mode=save_mode,
            base_glossary_path=base_glossary_path
        )

    def _save_selected_translations(self, selected_results, filtered_terms, save_mode="import", base_glossary_path=None):
        """保存用户选择的翻译到术语表"""
        added_count = 0
        if save_mode in ("import", "both"):
            existing_data = self.config.get("prompt_dictionary_data", [])
            existing_srcs = {item['src'] for item in existing_data}
            for item in selected_results:
                if item['src'] not in existing_srcs:
                    existing_data.append(item)
                    existing_srcs.add(item['src'])
                    added_count += 1

            self.config["prompt_dictionary_data"] = existing_data
            self.config["prompt_dictionary_switch"] = True
            self.save_config()
            console.print(f"[bold green]{self.i18n.get('msg_terms_added') or '已添加'} {added_count} {self.i18n.get('msg_terms_to_glossary') or '个术语到术语表'}[/bold green]")

        if save_mode in ("standalone", "both"):
            selected_map = {item.get("src"): item for item in selected_results if item.get("src")}
            merged_glossary = []
            for src, meta in filtered_terms.items():
                selected = selected_map.get(src)
                if selected:
                    merged_glossary.append({
                        "src": src,
                        "dst": selected.get("dst", ""),
                        "info": selected.get("info") or self._format_glossary_info(meta.get("type"), meta.get("info"))
                    })
                else:
                    merged_glossary.append({
                        "src": src,
                        "dst": "",
                        "info": self._format_glossary_info(meta.get("type"), meta.get("info"))
                    })

            save_path = self._build_output_glossary_path(base_glossary_path, "_独立术语表_翻译结果")
            self._save_glossary_json_to_path(merged_glossary, save_path)
            console.print(f"[bold green]{self.i18n.get('msg_glossary_saved') or '术语表已保存'}: {save_path}[/bold green]")

    def _save_glossary_json_to_path(self, glossary_data, output_path):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(glossary_data, f, indent=2, ensure_ascii=False)

    def _build_output_glossary_path(self, base_glossary_path=None, suffix="_独立术语表"):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if base_glossary_path:
            base_dir = os.path.dirname(base_glossary_path) or "."
            base_name = os.path.splitext(os.path.basename(base_glossary_path))[0]
            if base_name.endswith("_自动术语"):
                base_name = base_name[:-5]
        else:
            base_dir = "."
            base_name = "glossary"
        return os.path.join(base_dir, f"{base_name}{suffix}_{timestamp}.json")

    def _request_term_translation(self, src, term_data, target_language, platform_config, avoid_set):
        """请求单个术语的翻译"""
        from ModuleFolders.Infrastructure.LLMRequester.LLMRequester import LLMRequester

        term_type = term_data.get("type", "专有名词")
        term_info = term_data.get("info", "null")
        avoid_hint = ""
        if avoid_set:
            avoid_list = ", ".join(list(avoid_set)[:5])
            avoid_hint = f"\nPlease provide a different translation from: {avoid_list}"

        system_prompt = f"""You are a terminology translator. Translate the term into "{target_language}".
Term type: {term_type}
Known context: {term_info}
{avoid_hint}

Output format (use | as separator):
Translation|Note"""

        messages = [{"role": "user", "content": src}]

        try:
            requester = LLMRequester()
            skip, _, response, _, _ = requester.sent_request(messages, system_prompt, platform_config)

            if skip or not response:
                return None

            response = response.strip()
            if '|' in response:
                parts = response.split('|', 1)
                dst = parts[0].strip()
                info = parts[1].strip() if len(parts) > 1 else ""
            else:
                dst = response.strip()
                info = ""

            if dst and dst != src:
                return {"dst": dst, "info": info}
        except Exception as e:
            console.print(f"[red]{self.i18n.get('msg_translation_error') or '翻译错误'}: {e}[/red]")

        return None

    def _parse_glossary_response(self, response):
        """解析LLM返回的术语表JSON"""
        import re
        terms = []

        try:
            # 尝试提取JSON数组
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                json_str = json_match.group()
                parsed = json.loads(json_str)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict) and 'src' in item:
                            terms.append({
                                'src': item.get('src', ''),
                                'type': self._normalize_glossary_text(item.get('type'), '专有名词'),
                                'info': self._normalize_glossary_info(item)
                            })
        except json.JSONDecodeError:
            pass
        except Exception:
            pass

        return terms

    def _normalize_glossary_text(self, value, default=""):
        if value is None:
            return default
        text = str(value).strip()
        return text if text else default

    def _normalize_glossary_info(self, item):
        for key in ("info", "description", "desc"):
            if key in item:
                value = item.get(key)
                if value is None:
                    return "null"
                text = str(value).strip()
                return text if text else "null"
        return "null"

    def _format_glossary_info(self, term_type, info):
        term_type = self._normalize_glossary_text(term_type, "专有名词")
        info = self._normalize_glossary_text(info, "null")
        if info.lower() in ("null", "none"):
            return f"{term_type} | null"
        return f"{term_type} | {info}"

    def _resolve_prompt_file(self, prompt_file=None):
        if prompt_file and os.path.exists(prompt_file):
            return prompt_file

        configured_prompt = self.config.get("glossary_analysis_prompt_file")
        if configured_prompt and os.path.exists(configured_prompt):
            return configured_prompt

        lang = getattr(self.i18n, "lang", "zh_CN")
        default_prompt = "glossary_extract_zh.txt" if str(lang).startswith("zh") else "glossary_extract_en.txt"
        prompt_file = os.path.join(self.PROJECT_ROOT, "Resource", "Prompt", "System", default_prompt)
        if not os.path.exists(prompt_file):
            fallback_prompt = "glossary_extract_en.txt" if default_prompt != "glossary_extract_en.txt" else "glossary_extract_zh.txt"
            prompt_file = os.path.join(self.PROJECT_ROOT, "Resource", "Prompt", "System", fallback_prompt)
        return prompt_file

    def _get_split_batch_size(self):
        try:
            batch_size = int(self.config.get("glossary_analysis_split_lines") or 0)
        except (TypeError, ValueError):
            batch_size = 0

        if batch_size <= 0:
            try:
                batch_size = int(self.config.get("lines_limit") or 20)
            except (TypeError, ValueError):
                batch_size = 20

        return max(1, batch_size)

    def _estimate_token_count(self, text):
        try:
            from ModuleFolders.Infrastructure.Cache.CacheItem import CacheItem
            return CacheItem.get_token_count(text)
        except Exception:
            if not text:
                return 0
            ascii_count = sum(1 for c in text if ord(c) < 128)
            non_ascii_count = len(text) - ascii_count
            return max(1, int(ascii_count / 4 + non_ascii_count / 1.5))

    def _calculate_term_frequency(self, terms, source_text=None):
        """计算词频统计"""
        freq = {}
        for term in terms:
            src = term.get('src', '').strip()
            if not src:
                continue

            count = self._count_term_occurrences(source_text, src) if source_text else 1
            count = max(1, count)

            if src in freq:
                freq[src]['count'] = max(freq[src]['count'], count)
                if freq[src].get('info') in ("", "null") and term.get('info') not in ("", None, "null"):
                    freq[src]['info'] = term.get('info')
            else:
                freq[src] = {
                    'count': count,
                    'type': term.get('type', '专有名词'),
                    'info': term.get('info', 'null')
                }

        # 按词频排序
        sorted_freq = dict(sorted(freq.items(), key=lambda x: x[1]['count'], reverse=True))
        return sorted_freq

    def _count_term_occurrences(self, text, term):
        if not text or not term:
            return 0
        return text.count(term)

    def _generate_glossary_json(self, filtered_terms):
        """生成标准术语表JSON格式"""
        glossary = []
        for term, data in filtered_terms.items():
            glossary.append({
                "src": term,
                "dst": "",
                "info": self._format_glossary_info(data.get('type'), data.get('info'))
            })
        return glossary

    def _save_glossary_analysis_log(
        self,
        log_path,
        input_path,
        percent,
        lines,
        all_terms,
        filtered,
        threshold,
        analysis_mode="full",
        estimated_tokens=0,
        prompt_file="",
    ):
        """保存分析日志文件"""
        range_str = (
            self._tr("glossary_log_range_lines", "前{}行", lines)
            if lines
            else self._tr("glossary_log_range_percent", "前{}%", percent)
        )
        mode_label = (
            self._tr("glossary_log_mode_full", "全本/按比例提取（推荐）")
            if analysis_mode == "full"
            else self._tr("glossary_log_mode_split", "拆分提取（不推荐）")
        )
        prompt_label = prompt_file or self._tr("glossary_log_default_prompt", "默认")

        log_lines = [
            f"=== {self._tr('glossary_log_title', 'AI术语表分析日志')} ===",
            f"{self._tr('glossary_log_analysis_time', '分析时间')}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"{self._tr('glossary_log_analysis_file', '分析文件')}: {os.path.basename(input_path)}",
            f"{self._tr('glossary_log_analysis_range', '分析范围')}: {range_str}",
            f"{self._tr('glossary_log_analysis_mode', '分析模式')}: {mode_label}",
            f"{self._tr('glossary_log_estimated_tokens', '预估Token')}: {estimated_tokens}",
            f"{self._tr('glossary_log_prompt_file', '提示词文件')}: {prompt_label}",
            "",
            f"【{self._tr('glossary_log_notice_title', '重要提示')}】",
            self._tr(
                "glossary_log_notice",
                "分析结果的准确程度取决于您使用的API模型能力，此功能仅提供初步分析结果。建议人工审核后再使用，不建议直接作为最终术语表。"
            ),
            "",
            f"=== {self._tr('glossary_log_term_frequency_title', '词频统计')} ===",
        ]
        for term, data in all_terms.items():
            type_info = self._format_glossary_info(data.get('type'), data.get('info'))
            log_lines.append(self._tr("glossary_log_term_line", "{} ({}): 出现 {} 次", term, type_info, data['count']))

        log_lines.extend([
            "",
            f"=== {self._tr('glossary_log_filter_title', '过滤设置')} ===",
            self._tr("glossary_log_min_frequency", "最低词频阈值: {}次", threshold),
            self._tr("glossary_log_total_before_filter", "过滤前总数: {}", len(all_terms)),
            self._tr("glossary_log_total_after_filter", "过滤后总数: {}", len(filtered)),
        ])

        with open(log_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(log_lines) + "\n")
