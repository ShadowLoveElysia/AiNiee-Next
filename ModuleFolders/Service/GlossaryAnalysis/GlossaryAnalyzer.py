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

    @property
    def PROJECT_ROOT(self):
        return self.cli.PROJECT_ROOT

    @property
    def file_reader(self):
        return self.cli.file_reader

    def save_config(self):
        self.cli.save_config()

    def execute_analysis(self, input_path, analysis_percent, analysis_lines, temp_config=None):
        """
        执行术语表分析的核心逻辑

        Args:
            input_path: 输入文件路径
            analysis_percent: 分析百分比
            analysis_lines: 分析行数（优先于百分比）
            temp_config: 临时API配置（可选）

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

        console.print(f"[green]{self.i18n.get('msg_total_lines') or '总行数'}: {total_lines}[/green]")
        console.print(f"[green]{self.i18n.get('msg_lines_to_analyze') or '将分析行数'}: {lines_to_analyze}[/green]")

        # 获取要分析的文本
        items_to_analyze = all_items[:lines_to_analyze]

        # 分批处理 (兼容lines和tokens两种模式)
        if self.config.get("tokens_limit_switch"):
            batch_size = self.config.get("tokens_limit") or 1000
        else:
            batch_size = self.config.get("lines_limit") or 20
        batches = [items_to_analyze[i:i+batch_size] for i in range(0, len(items_to_analyze), batch_size)]

        console.print(f"[cyan]{self.i18n.get('msg_batch_count') or '批次数量'}: {len(batches)}[/cyan]")

        # 准备提示词
        prompt_file = os.path.join(self.PROJECT_ROOT, "Resource", "Prompt", "System", "glossary_extract_zh.txt")
        if not os.path.exists(prompt_file):
            prompt_file = os.path.join(self.PROJECT_ROOT, "Resource", "Prompt", "System", "glossary_extract_en.txt")

        with open(prompt_file, 'r', encoding='utf-8') as f:
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

        # 获取用户配置的线程数 (临时配置优先)
        if temp_config and temp_config.get("thread_counts"):
            thread_count = temp_config.get("thread_counts")
        else:
            thread_count = task_config.actual_thread_counts
        console.print(f"[cyan]{self.i18n.get('msg_thread_count') or '并发线程数'}: {thread_count}[/cyan]")

        # 收集所有结果 (线程安全)
        all_terms = []
        terms_lock = threading.Lock()
        completed_count = [0]  # 使用列表以便在闭包中修改
        error_count = [0]

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
                        completed_count[0] += 1
                    console.print(f"[green]√ [{batch_idx+1:03d}] 完成 | 发现 {len(terms)} 个术语 | {prompt_tokens}+{completion_tokens}T[/green]")
                    return
                else:
                    with failed_lock:
                        failed_batches.append(batch_info)
                    hint = "，将在下一轮重试" if not is_last_round else ""
                    console.print(f"[red]✗ [{batch_idx+1:03d}] 失败{hint}[/red]")
            except Exception as e:
                with failed_lock:
                    failed_batches.append(batch_info)
                hint = "，将在下一轮重试" if not is_last_round else ""
                console.print(f"[red]✗ [{batch_idx+1:03d}] 错误: {e}{hint}[/red]")

        # 使用线程池并发执行
        console.print(f"\n[bold cyan]{self.i18n.get('msg_starting_concurrent') or '开始并发分析...'}[/bold cyan]\n")

        max_rounds = 3
        batch_infos = list(enumerate(batches))

        for round_num in range(max_rounds):
            is_last = (round_num == max_rounds - 1)
            if round_num > 0:
                batch_infos = failed_batches[:]
                failed_batches.clear()
                console.print(f"\n[yellow]⟳ 第{round_num+1}轮重试，剩余 {len(batch_infos)} 个失败批次...[/yellow]\n")

            with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
                list(executor.map(lambda b: analyze_batch(b, is_last), batch_infos))

            if not failed_batches:
                break

        error_count[0] = len(failed_batches)
        console.print(f"\n[cyan]完成: {completed_count[0]}/{len(batches)}, 失败: {error_count[0]}[/cyan]")

        # 统计词频
        term_freq = self._calculate_term_frequency(all_terms)

        if not term_freq:
            console.print(f"[yellow]{self.i18n.get('msg_no_terms_found') or '未找到专有名词'}[/yellow]")
            return None

        # 返回结果供菜单层处理
        return {
            'term_freq': term_freq,
            'input_path': input_path,
            'analysis_percent': analysis_percent,
            'analysis_lines': analysis_lines
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
            term_freq, filtered_terms, min_freq
        )

        console.print(f"[green]{self.i18n.get('msg_log_saved') or '分析日志已保存'}: {log_path}[/green]")

        return {
            'filtered_terms': filtered_terms,
            'glossary_data': glossary_data,
            'glossary_path': glossary_path
        }

    def save_glossary_directly(self, glossary_data):
        """直接保存术语表（无翻译）"""
        existing_data = self.config.get("prompt_dictionary_data", [])
        existing_data.extend(glossary_data)
        self.config["prompt_dictionary_data"] = existing_data
        self.config["prompt_dictionary_switch"] = True
        self.save_config()
        console.print(f"[bold green]{self.i18n.get('msg_glossary_imported') or '术语表已导入!'}[/bold green]")

    def multi_translate_and_select(self, filtered_terms, temp_config=None, rounds=3):
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

            multi_results.append({
                "src": src,
                "type": term_data.get("type", ""),
                "options": options,
                "selected_index": 0
            })

        if not multi_results:
            console.print(f"[yellow]{self.i18n.get('msg_no_translation_results') or '未获得翻译结果'}[/yellow]")
            return

        # 显示选择界面
        console.print(f"\n[green]{self.i18n.get('msg_translation_complete') or '翻译完成，请选择最佳译法'}[/green]")

        # 定义单条保存回调
        def save_single_term(term_data):
            existing_data = self.config.get("prompt_dictionary_data", [])
            existing_srcs = {item['src'] for item in existing_data}
            if term_data['src'] not in existing_srcs:
                existing_data.append(term_data)
                self.config["prompt_dictionary_data"] = existing_data
                self.config["prompt_dictionary_switch"] = True
                self.save_config()

        # 定义重试翻译回调
        def retry_translation(src, term_type, avoid_set=None):
            term_data = {"type": term_type}
            return self._request_term_translation(src, term_data, target_language, platform_config, avoid_set or set())

        selector = TermSelector(multi_results, request_callback=retry_translation, save_callback=save_single_term)
        selected_results = selector.show_selector()

        if not selected_results:
            console.print(f"[yellow]{self.i18n.get('msg_cancelled') or '已取消'}[/yellow]")
            return

        # 保存到术语表
        self._save_selected_translations(selected_results)

    def _save_selected_translations(self, selected_results):
        """保存用户选择的翻译到术语表"""
        existing_data = self.config.get("prompt_dictionary_data", [])
        existing_srcs = {item['src'] for item in existing_data}

        added_count = 0
        for item in selected_results:
            if item['src'] not in existing_srcs:
                existing_data.append(item)
                existing_srcs.add(item['src'])
                added_count += 1

        self.config["prompt_dictionary_data"] = existing_data
        self.config["prompt_dictionary_switch"] = True
        self.save_config()

        console.print(f"[bold green]{self.i18n.get('msg_terms_added') or '已添加'} {added_count} {self.i18n.get('msg_terms_to_glossary') or '个术语到术语表'}[/bold green]")

    def _request_term_translation(self, src, term_data, target_language, platform_config, avoid_set):
        """请求单个术语的翻译"""
        from ModuleFolders.Infrastructure.LLMRequester.LLMRequester import LLMRequester

        term_type = term_data.get("type", "专有名词")
        avoid_hint = ""
        if avoid_set:
            avoid_list = ", ".join(list(avoid_set)[:5])
            avoid_hint = f"\nPlease provide a different translation from: {avoid_list}"

        system_prompt = f"""You are a terminology translator. Translate the term into "{target_language}".
Term type: {term_type}
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
                                'type': item.get('type', '专有名词')
                            })
        except json.JSONDecodeError:
            pass
        except Exception:
            pass

        return terms

    def _calculate_term_frequency(self, terms):
        """计算词频统计"""
        freq = {}
        for term in terms:
            src = term.get('src', '').strip()
            if not src:
                continue

            if src in freq:
                freq[src]['count'] += 1
            else:
                freq[src] = {
                    'count': 1,
                    'type': term.get('type', '专有名词')
                }

        # 按词频排序
        sorted_freq = dict(sorted(freq.items(), key=lambda x: x[1]['count'], reverse=True))
        return sorted_freq

    def _generate_glossary_json(self, filtered_terms):
        """生成标准术语表JSON格式"""
        glossary = []
        for term, data in filtered_terms.items():
            glossary.append({
                "src": term,
                "dst": "",
                "info": data['type']
            })
        return glossary

    def _save_glossary_analysis_log(self, log_path, input_path, percent, lines, all_terms, filtered, threshold):
        """保存分析日志文件"""
        range_str = f"前{lines}行" if lines else f"前{percent}%"

        log_content = f"""=== AI术语表分析日志 ===
分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
分析文件: {os.path.basename(input_path)}
分析范围: {range_str}

【重要提示】
分析结果的准确程度取决于您使用的API模型能力，此功能仅提供初步分析结果。
建议人工审核后再使用，不建议直接作为最终术语表。

=== 词频统计 ===
"""
        for term, data in all_terms.items():
            log_content += f"{term} ({data['type']}): 出现 {data['count']} 次\n"

        log_content += f"""
=== 过滤设置 ===
最低词频阈值: {threshold}次
过滤前总数: {len(all_terms)}
过滤后总数: {len(filtered)}
"""

        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(log_content)
