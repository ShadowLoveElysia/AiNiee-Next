"""
术语/规则菜单模块 - 从 ainiee_cli.py 分离
负责术语表、提示词、规则等相关的菜单交互逻辑
"""
import os
import json
import time
import subprocess

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.table import Table

console = Console()

# 特性数据的必需键
FEATURE_REQUIRED_KEYS = {
    "characterization_data": {"original_name", "translated_name"},
    "translation_example_data": {"src", "dst"}
}

def open_in_editor(file_path):
    """在系统默认编辑器中打开文件"""
    import platform
    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(file_path)
        elif system == "Darwin":
            subprocess.run(["open", file_path])
        else:
            subprocess.run(["xdg-open", file_path])
        return True
    except Exception:
        return False


class GlossaryMenu:
    """术语/规则菜单，处理术语表、提示词、规则等相关的菜单交互"""

    def __init__(self, cli_menu):
        """
        初始化术语/规则菜单

        Args:
            cli_menu: CLIMenu实例，用于访问配置和其他依赖
        """
        self.cli = cli_menu
        # 延迟导入避免循环依赖
        self._analyzer = None

    @property
    def analyzer(self):
        """懒加载术语分析器"""
        if self._analyzer is None:
            from ModuleFolders.Service.GlossaryAnalysis import GlossaryAnalyzer
            self._analyzer = GlossaryAnalyzer(self.cli)
        return self._analyzer

    @property
    def config(self):
        return self.cli.config

    @property
    def i18n(self):
        return self.cli.i18n

    @property
    def file_selector(self):
        return self.cli.file_selector

    @property
    def api_manager(self):
        return self.cli.api_manager

    @property
    def active_rules_profile_name(self):
        return self.cli.active_rules_profile_name

    def save_config(self):
        self.cli.save_config()

    def display_banner(self):
        self.cli.display_banner()

    def prompt_menu(self):
        """术语/规则主菜单"""
        while True:
            self.display_banner()
            console.print(Panel(f"[bold]{self.i18n.get('menu_glossary_rules')}[/bold]"))

            target_platform = str(self.config.get("target_platform", "")).lower()
            is_local = any(k in target_platform for k in ["local", "sakura"])

            if is_local:
                console.print(Panel(f"[bold yellow]⚠ {self.i18n.get('msg_online_features_warning')}[/bold yellow]", border_style="yellow"))

            trans_sel = self.config.get("translation_prompt_selection", {}).get("last_selected_id", "common")
            polish_sel = self.config.get("polishing_prompt_selection", {}).get("last_selected_id", "common")

            dict_sw = self.config.get("prompt_dictionary_switch", False)
            excl_sw = self.config.get("exclusion_list_switch", False)
            char_sw = self.config.get("characterization_switch", False)
            world_sw = self.config.get("world_building_switch", False)
            style_sw = self.config.get("writing_style_switch", False)
            examp_sw = self.config.get("translation_example_switch", False)

            dict_len = len(self.config.get("prompt_dictionary_data", []))
            excl_len = len(self.config.get("exclusion_list_data", []))
            char_len = len(self.config.get("characterization_data", []))
            examp_len = len(self.config.get("translation_example_data", []))

            table = Table(show_header=False, box=None)
            table.add_row("[cyan]1.[/]", f"{self.i18n.get('menu_select_trans_prompt')} ([green]{trans_sel}[/green])")
            table.add_row("[cyan]2.[/]", f"{self.i18n.get('menu_select_polish_prompt')} ([green]{polish_sel}[/green])")
            table.add_row("[cyan]3.[/]", f"{self.i18n.get('menu_dict_settings')} ([green]{'ON' if dict_sw else 'OFF'}[/green] | {dict_len} items)")
            table.add_row("[cyan]4.[/]", f"{self.i18n.get('menu_exclusion_settings')} ([green]{'ON' if excl_sw else 'OFF'}[/green] | {excl_len} items)")

            table.add_section()
            online_suffix = f" [dim]({self.i18n.get('label_online_only')})[/dim]"
            table.add_row("[cyan]5.[/]", f"{self.i18n.get('feature_characterization_switch')} ([green]{'ON' if char_sw else 'OFF'}[/green] | {char_len} items){online_suffix}")
            table.add_row("[cyan]6.[/]", f"{self.i18n.get('feature_world_building_switch')} ([green]{'ON' if world_sw else 'OFF'}[/green]){online_suffix}")
            table.add_row("[cyan]7.[/]", f"{self.i18n.get('feature_writing_style_switch')} ([green]{'ON' if style_sw else 'OFF'}[/green]){online_suffix}")
            table.add_row("[cyan]8.[/]", f"{self.i18n.get('feature_translation_example_switch')} ([green]{'ON' if examp_sw else 'OFF'}[/green] | {examp_len} items){online_suffix}")

            table.add_section()
            table.add_row("[cyan]9.[/]", f"{self.i18n.get('menu_switch_profile_short')} ([yellow]{self.active_rules_profile_name}[/yellow])")
            table.add_row("[cyan]10.[/]", f"{self.i18n.get('menu_system_prompts') or 'System Prompts'} ([dim]{self.i18n.get('label_readonly') or 'Read Only'}[/dim])")
            table.add_row("[cyan]11.[/]", f"{self.i18n.get('menu_ai_glossary_analysis') or 'AI自动分析术语表'}")

            console.print(table)
            console.print(f"\n[dim]0. {self.i18n.get('menu_exit')}[/dim]")

            choice = IntPrompt.ask(self.i18n.get('prompt_select'), choices=[str(i) for i in range(12)], show_choices=False)
            console.print("\n")

            if choice == 0:
                break
            elif choice == 1:
                self.select_prompt_template("Translate", "translation_prompt_selection")
            elif choice == 2:
                self.select_prompt_template("Polishing", "polishing_prompt_selection")
            elif choice == 3:
                self.manage_text_rule("prompt_dictionary_switch", "prompt_dictionary_data", self.i18n.get("menu_dict_settings"))
            elif choice == 4:
                self.manage_text_rule("exclusion_list_switch", "exclusion_list_data", self.i18n.get("menu_exclusion_settings"))
            elif choice == 5:
                self.manage_feature_content("characterization_switch", "characterization_data", self.i18n.get("feature_characterization_switch"), is_list=True)
            elif choice == 6:
                self.manage_feature_content("world_building_switch", "world_building_content", self.i18n.get("feature_world_building_switch"), is_list=False)
            elif choice == 7:
                self.manage_feature_content("writing_style_switch", "writing_style_content", self.i18n.get("feature_writing_style_switch"), is_list=False)
            elif choice == 8:
                self.manage_feature_content("translation_example_switch", "translation_example_data", self.i18n.get("feature_translation_example_switch"), is_list=True)
            elif choice == 9:
                self.rules_profiles_menu()
            elif choice == 10:
                self.select_prompt_template("System", None)
            elif choice == 11:
                self.run_glossary_analysis_task()

    def run_glossary_analysis_task(self):
        """AI自动分析术语表功能入口"""
        self.display_banner()
        console.print(Panel(f"[bold]{self.i18n.get('menu_ai_glossary_analysis') or 'AI自动分析术语表'}[/bold]"))

        # 显示警告信息
        console.print(Panel(
            f"[bold yellow]⚠ {self.i18n.get('msg_glossary_analysis_warning') or '当前暂不建议使用本地LLM进行分析，可能存在质量问题。'}[/bold yellow]\n"
            f"[yellow]{self.i18n.get('msg_glossary_analysis_hint') or '尽可能使用在线API进行分析，但可能会产生相关API费用。'}[/yellow]\n\n"
            f"[dim]{self.i18n.get('msg_glossary_accuracy_note') or '注意：分析结果的准确程度取决于您使用的API模型能力，此功能仅提供初步分析结果，建议人工审核后再使用。'}[/dim]",
            border_style="yellow"
        ))

        # 选择文件
        console.print(f"\n[cyan]{self.i18n.get('prompt_select_file_to_analyze') or '请选择要分析的文件:'}[/cyan]")
        selected_path = self.file_selector.select_path(select_file=True, select_dir=True)

        if not selected_path or not os.path.exists(selected_path):
            console.print(f"[red]{self.i18n.get('err_not_file') or '错误: 路径不存在'}[/red]")
            Prompt.ask(f"\n{self.i18n.get('msg_press_enter')}")
            return

        # 选择分析范围
        console.print(f"\n[cyan]{self.i18n.get('prompt_select_analysis_range') or '请选择分析范围:'}[/cyan]")
        table = Table(show_header=False, box=None)
        table.add_row("[cyan]1.[/]", self.i18n.get('option_full_book') or "整本书 (100%)")
        table.add_row("[cyan]2.[/]", self.i18n.get('option_half_book') or "一半 (50%)")
        table.add_row("[cyan]3.[/]", self.i18n.get('option_custom_percent') or "自定义比例")
        table.add_row("[cyan]4.[/]", self.i18n.get('option_custom_lines') or "自定义行数")
        console.print(table)
        console.print(f"\n[dim]0. {self.i18n.get('menu_back')}[/dim]")

        range_choice = IntPrompt.ask(self.i18n.get('prompt_select'), choices=["0", "1", "2", "3", "4"], show_choices=False)

        if range_choice == 0:
            return

        analysis_percent = 100
        analysis_lines = None

        if range_choice == 2:
            analysis_percent = 50
        elif range_choice == 3:
            analysis_percent = IntPrompt.ask(
                self.i18n.get('prompt_input_percent') or "请输入百分比 (1-100)",
                default=30
            )
            analysis_percent = max(1, min(100, analysis_percent))
        elif range_choice == 4:
            analysis_lines = IntPrompt.ask(
                self.i18n.get('prompt_input_lines') or "请输入行数",
                default=100
            )
            analysis_lines = max(1, analysis_lines)

        # 选择API配置
        console.print(f"\n[cyan]{self.i18n.get('prompt_select_api_config') or '请选择API配置:'}[/cyan]")
        table = Table(show_header=False, box=None)
        table.add_row("[cyan]1.[/]", self.i18n.get('option_use_current_config') or "使用当前配置")
        table.add_row("[cyan]2.[/]", self.i18n.get('option_use_temp_config') or "使用临时配置")
        console.print(table)

        api_choice = IntPrompt.ask(self.i18n.get('prompt_select'), choices=["1", "2"], show_choices=False, default=1)

        temp_platform_config = None
        if api_choice == 2:
            temp_platform_config = self.api_manager.configure_temp_api_for_analysis()
            if not temp_platform_config:
                console.print(f"[yellow]{self.i18n.get('msg_using_current_config') or '未配置临时API，将使用当前配置'}[/yellow]")

        # 开始分析
        console.print(f"\n[bold green]{self.i18n.get('msg_starting_analysis') or '开始分析...'}[/bold green]")

        try:
            # 执行分析
            analysis_result = self.analyzer.execute_analysis(
                selected_path,
                analysis_percent,
                analysis_lines,
                temp_platform_config
            )

            if analysis_result is None:
                Prompt.ask(f"\n{self.i18n.get('msg_press_enter')}")
                return

            # 显示统计结果
            console.print(f"\n[bold green]{self.i18n.get('msg_analysis_complete') or '分析完成!'}[/bold green]")
            console.print(f"[cyan]{self.i18n.get('msg_found_terms') or '发现专有名词'}: {len(analysis_result['term_freq'])}[/cyan]")

            # 显示词频统计表
            self._display_term_frequency(analysis_result['term_freq'])

            # 让用户选择最低词频阈值
            console.print(f"\n[cyan]{self.i18n.get('prompt_min_frequency') or '请输入最低词频阈值 (保留出现次数>=该值的词):'}[/cyan]")
            min_freq = IntPrompt.ask(self.i18n.get('prompt_threshold') or "阈值", default=2)

            # 过滤并保存
            save_result = self.analyzer.filter_and_save(analysis_result, min_freq)

            if save_result is None:
                Prompt.ask(f"\n{self.i18n.get('msg_press_enter')}")
                return

            # 显示操作菜单
            self._show_glossary_action_menu(
                save_result['filtered_terms'],
                save_result['glossary_data'],
                temp_platform_config
            )

        except Exception as e:
            console.print(f"[red]{self.i18n.get('msg_analysis_error') or '分析出错'}: {e}[/red]")
            import traceback
            traceback.print_exc()

        Prompt.ask(f"\n{self.i18n.get('msg_press_enter')}")

    def _display_term_frequency(self, term_freq):
        """显示词频统计表"""
        table = Table(title=self.i18n.get('label_term_frequency') or "词频统计", show_lines=True)
        table.add_column(self.i18n.get('label_term') or "专有名词", style="cyan")
        table.add_column(self.i18n.get('label_type') or "类型", style="green")
        table.add_column(self.i18n.get('label_frequency') or "出现次数", style="yellow", justify="right")

        # 只显示前20个
        for i, (term, data) in enumerate(term_freq.items()):
            if i >= 20:
                table.add_row("...", "...", f"(还有 {len(term_freq) - 20} 项)")
                break
            table.add_row(term, data['type'], str(data['count']))

        console.print(table)

    def _show_glossary_action_menu(self, filtered_terms, glossary_data, temp_config=None):
        """显示术语表操作菜单"""
        console.print(f"\n[cyan]{self.i18n.get('prompt_select_action') or '请选择操作:'}[/cyan]")
        table = Table(show_header=False, box=None)
        table.add_row("[cyan]1.[/]", self.i18n.get('option_save_without_translation') or "直接保存到术语表（无翻译）")
        table.add_row("[cyan]2.[/]", (self.i18n.get('option_multi_translate') or "多翻译选择") + " (当前配置)")
        table.add_row("[cyan]3.[/]", (self.i18n.get('option_multi_translate') or "多翻译选择") + " (临时API)")
        table.add_row("[cyan]4.[/]", (self.i18n.get('option_set_rounds') or "设置轮询次数") + " (当前配置)")
        table.add_row("[cyan]5.[/]", (self.i18n.get('option_set_rounds') or "设置轮询次数") + " (临时API)")
        console.print(table)
        console.print(f"\n[dim]0. {self.i18n.get('menu_back')}[/dim]")

        choice = IntPrompt.ask(self.i18n.get('prompt_select'), choices=["0", "1", "2", "3", "4", "5"], show_choices=False, default=2)

        if choice == 0:
            return
        elif choice == 1:
            self.analyzer.save_glossary_directly(glossary_data)
        elif choice == 2:
            # 多翻译选择（当前配置）
            rounds = self.config.get("term_translation_rounds", 3)
            self.analyzer.multi_translate_and_select(filtered_terms, None, rounds)
        elif choice == 3:
            # 多翻译选择（临时API）
            translate_config = self.api_manager.configure_temp_api_for_analysis()
            if translate_config:
                rounds = self.config.get("term_translation_rounds", 3)
                self.analyzer.multi_translate_and_select(filtered_terms, translate_config, rounds)
        elif choice == 4:
            # 设置轮询次数（当前配置）
            rounds = IntPrompt.ask(
                self.i18n.get('prompt_translation_rounds') or "翻译轮询次数",
                default=self.config.get("term_translation_rounds", 3)
            )
            rounds = max(1, min(10, rounds))
            self.config["term_translation_rounds"] = rounds
            self.save_config()
            self.analyzer.multi_translate_and_select(filtered_terms, None, rounds)
        elif choice == 5:
            # 设置轮询次数（临时API）
            translate_config = self.api_manager.configure_temp_api_for_analysis()
            if translate_config:
                rounds = IntPrompt.ask(
                    self.i18n.get('prompt_translation_rounds') or "翻译轮询次数",
                    default=self.config.get("term_translation_rounds", 3)
                )
                rounds = max(1, min(10, rounds))
                self.config["term_translation_rounds"] = rounds
                self.save_config()
                self.analyzer.multi_translate_and_select(filtered_terms, translate_config, rounds)

    def rules_profiles_menu(self):
        """规则配置文件菜单"""
        while True:
            self.display_banner()
            console.print(Panel(f"[bold]{self.i18n.get('menu_switch_profile_short')}[/bold]"))

            profiles = [f.replace(".json", "") for f in os.listdir(self.cli.rules_profiles_dir) if f.endswith(".json")]
            if not profiles: profiles = ["default"]

            # 始终包含 "None" 选项
            all_options = ["None"] + profiles

            p_table = Table(show_header=False, box=None)
            for i, p in enumerate(all_options):
                display_name = self.i18n.get("opt_none") if p == "None" else p
                is_active = p == self.active_rules_profile_name
                p_table.add_row(f"[cyan]{i+1}.[/]", display_name + (" [green](Active)[/]" if is_active else ""))
            console.print(p_table)

            console.print(f"\n[cyan]A.[/] {self.i18n.get('menu_profile_create')}")
            console.print(f"[dim]0. {self.i18n.get('menu_back')}[/dim]")

            choice_str = Prompt.ask(self.i18n.get('prompt_select')).upper()

            if choice_str == '0': break
            elif choice_str == 'A':
                new_name = Prompt.ask(self.i18n.get("prompt_profile_name")).strip()
                if new_name:
                    if new_name.lower() == "none":
                        console.print("[red]Reserved name 'None' cannot be used.[/red]")
                        time.sleep(1)
                        continue
                    path = os.path.join(self.cli.rules_profiles_dir, f"{new_name}.json")
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump({}, f)
                    console.print(f"[green]Rules Profile '{new_name}' created.[/green]")
                    time.sleep(1)
            elif choice_str.isdigit():
                sel_idx = int(choice_str)
                if 1 <= sel_idx <= len(all_options):
                    sel = all_options[sel_idx - 1]
                    self.cli.active_rules_profile_name = sel
                    self.cli.root_config["active_rules_profile"] = sel
                    self.cli.save_config(save_root=True)
                    self.cli.load_config() # Reload everything to merge correctly
                    console.print(f"[green]Switched to Rules Profile: {sel}[/green]")
                    time.sleep(1)
                    break

    def manage_text_rule(self, switch_key, data_key, title):
        """管理文本规则（术语表/排除列表）"""
        while True:
            sw = self.config.get(switch_key, False)
            data = self.config.get(data_key, [])

            panel_title = f"[bold]{title}[/bold]"
            if "exclusion" in data_key:
                panel_title += self.i18n.get("tip_exclusion_regex")

            console.print(Panel(panel_title))
            table = Table(show_header=False, box=None)
            table.add_row("[cyan]1.[/]", f"{self.i18n.get('menu_toggle_switch')} (Current: [green]{'ON' if sw else 'OFF'}[/green])")
            table.add_row("[cyan]2.[/]", f"{self.i18n.get('menu_dict_import' if 'dict' in switch_key else 'menu_exclusion_import')} (Current items: {len(data)})")
            table.add_row("[cyan]3.[/]", f"{self.i18n.get('menu_edit_in_editor')}")
            table.add_row("[cyan]4.[/]", f"{self.i18n.get('menu_clear_data')}")
            console.print(table)
            console.print(f"\n[dim]0. {self.i18n.get('menu_back')}[/dim]")

            c = IntPrompt.ask(self.i18n.get('prompt_select'), choices=["0", "1", "2", "3", "4"], show_choices=False)

            if c == 0: break
            elif c == 1:
                self.config[switch_key] = not sw
            elif c == 2:
                path = Prompt.ask(self.i18n.get('prompt_json_path')).strip().strip('"').strip("'")
                if os.path.exists(path):
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            content = f.read()

                        # Try standard load first
                        try:
                            new_data = json.loads(content)
                        except json.JSONDecodeError as e:
                            new_data = None
                            console.print(f"[red]JSON Syntax Error: {e}[/red]")
                            if Confirm.ask("Format invalid. Attempt auto-repair using json_repair library?", default=True):
                                try:
                                    import json_repair
                                except ImportError:
                                    console.print("[yellow]Installing json_repair using uv...[/yellow]")
                                    subprocess.check_call(["uv", "add", "json_repair"])
                                    import json_repair

                                try:
                                    new_data = json_repair.loads(content)
                                    console.print("[green]Repaired successfully![/green]")
                                except Exception as repair_err:
                                    console.print(f"[red]Repair failed: {repair_err}[/red]")

                        if new_data is not None:
                            if isinstance(new_data, list):
                                # Format Validation
                                is_glossary = "dict" in switch_key
                                required_keys = {"src", "dst", "info"} if is_glossary else {"markers", "info", "regex"}

                                valid_items = []
                                for item in new_data:
                                    if isinstance(item, dict) and all(k in item for k in required_keys):
                                        valid_items.append(item)

                                if len(valid_items) == len(new_data):
                                    self.config[data_key] = new_data
                                    console.print(f"[green]{self.i18n.get('msg_data_loaded').format(len(new_data))}[/green]")
                                else:
                                    console.print(f"[yellow]Loaded {len(new_data)} items, but only {len(valid_items)} matched the required format: {required_keys}[/yellow]")
                                    if len(valid_items) > 0 and Confirm.ask("Load valid items only?", default=True):
                                        self.config[data_key] = valid_items
                                        console.print(f"[green]Loaded {len(valid_items)} valid items.[/green]")
                                    else:
                                        console.print("[red]Import cancelled (format mismatch).[/red]")
                            else:
                                console.print(f"[red]{self.i18n.get('msg_json_root_error')}[/red]")
                    except Exception as e:
                        console.print(f"[red]Error loading file: {e}[/red]")
                else:
                    console.print(f"[red]{self.i18n.get('err_not_file')}[/red]")
                time.sleep(1)
            elif c == 3: # Edit in Editor
                temp_dir = os.path.join(self.cli.PROJECT_ROOT, "output", "temp_edit")
                os.makedirs(temp_dir, exist_ok=True)
                temp_path = os.path.join(temp_dir, f"{data_key}.json")

                try:
                    with open(temp_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=4, ensure_ascii=False)

                    if open_in_editor(temp_path):
                        Prompt.ask(f"\n{self.i18n.get('msg_press_enter_after_save')}")
                        with open(temp_path, 'r', encoding='utf-8') as f:
                            new_data = json.load(f)
                            if isinstance(new_data, list):
                                self.config[data_key] = new_data
                                console.print(f"[green]{self.i18n.get('msg_data_loaded').format(len(new_data))}[/green]")
                            else:
                                console.print(f"[red]{self.i18n.get('msg_json_root_error')}[/red]")

                except Exception as e:
                    console.print(f"[red]Error during editing: {e}[/red]")
                finally:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                time.sleep(1)

            elif c == 4:
                if Confirm.ask(self.i18n.get("menu_clear_data") + "?"):
                    self.config[data_key] = []
                    console.print(f"[yellow]{self.i18n.get('msg_data_cleared')}[/yellow]")
            self.save_config()

    def manage_feature_content(self, switch_key, data_key, title, is_list=False):
        """管理特性内容（角色设定/世界观/写作风格/翻译示例）"""
        while True:
            sw = self.config.get(switch_key, False)
            data = self.config.get(data_key, [] if is_list else "")

            # 定义模板
            templates = {
                "characterization_data": [{
                    "original_name": "", "translated_name": "", "gender": "",
                    "age": "", "personality": "", "speech_style": "", "additional_info": ""
                }],
                "translation_example_data": [{"src": "", "dst": ""}]
            }

            console.print(Panel(f"[bold]{title}[/bold]"))
            table = Table(show_header=False, box=None)
            table.add_row("[cyan]1.[/]", f"{self.i18n.get('menu_toggle_switch')} (Current: [green]{'ON' if sw else 'OFF'}[/green])")

            info_text = f"Items: {len(data)}" if is_list else f"Length: {len(data)} chars"
            if not is_list and len(data) > 50: info_text += f" ({data[:47]}...)"

            table.add_row("[cyan]2.[/]", f"{self.i18n.get('menu_edit_content')} ({info_text})")
            table.add_row("[cyan]3.[/]", f"{self.i18n.get('menu_clear_data')}")
            console.print(table)
            console.print(f"\n[dim]0. {self.i18n.get('menu_back')}[/dim]")

            c = IntPrompt.ask(self.i18n.get('prompt_select'), choices=["0", "1", "2", "3"], show_choices=False)

            if c == 0: break
            elif c == 1:
                self.config[switch_key] = not sw
            elif c == 2:
                if is_list:
                    temp_dir = os.path.join(self.cli.PROJECT_ROOT, "output", "temp_edit")
                    os.makedirs(temp_dir, exist_ok=True)
                    temp_path = os.path.join(temp_dir, f"{data_key}.json")

                    # 如果数据为空，则写入模板
                    edit_data = data if data else templates.get(data_key, [])

                    try:
                        with open(temp_path, 'w', encoding='utf-8') as f:
                            json.dump(edit_data, f, indent=4, ensure_ascii=False)

                        if open_in_editor(temp_path):
                            Prompt.ask(f"\n{self.i18n.get('msg_press_enter_after_save')}")
                            with open(temp_path, 'r', encoding='utf-8') as f:
                                new_data = json.load(f)
                                if isinstance(new_data, list):
                                    # 简单格式校验
                                    required = FEATURE_REQUIRED_KEYS.get(data_key)
                                    if required and new_data:
                                        valid = all(isinstance(item, dict) and required.issubset(item.keys()) for item in new_data if any(item.values()))
                                        if not valid:
                                            console.print(f"[yellow]Warning: Some items might be missing required keys: {required}[/yellow]")
                                            if not Confirm.ask("Save anyway?", default=True):
                                                continue

                                    # 过滤掉全空的占位项
                                    if required:
                                        new_data = [item for item in new_data if any(str(v).strip() for v in item.values())]

                                    self.config[data_key] = new_data
                                    console.print(f"[green]Data updated ({len(new_data)} items).[/green]")
                                else:
                                    console.print(f"[red]{self.i18n.get('msg_json_root_error')}[/red]")
                    except Exception as e:
                        console.print(f"[red]Error: {e}[/red]")
                    finally:
                        if os.path.exists(temp_path): os.remove(temp_path)
                else:
                    console.print(f"\n[cyan]1. {self.i18n.get('menu_edit_in_editor')}[/cyan]")
                    console.print(f"[cyan]2. {self.i18n.get('menu_enter_manually')}[/cyan]")
                    sc = IntPrompt.ask(self.i18n.get('prompt_select'), choices=["1", "2"], default=1, show_choices=False)
                    if sc == 1:
                        temp_dir = os.path.join(self.cli.PROJECT_ROOT, "output", "temp_edit")
                        os.makedirs(temp_dir, exist_ok=True)
                        temp_path = os.path.join(temp_dir, f"{data_key}.txt")
                        try:
                            with open(temp_path, 'w', encoding='utf-8') as f:
                                f.write(data)
                            if open_in_editor(temp_path):
                                Prompt.ask(f"\n{self.i18n.get('msg_press_enter_after_save')}")
                                with open(temp_path, 'r', encoding='utf-8') as f:
                                    self.config[data_key] = f.read()
                                console.print(f"[green]Data updated.[/green]")
                        except Exception as e:
                            console.print(f"[red]Error: {e}[/red]")
                        finally:
                            if os.path.exists(temp_path): os.remove(temp_path)
                    else:
                        console.print(f"\n[dim]Current: {data}[/dim]")
                        self.config[data_key] = Prompt.ask(self.i18n.get('prompt_enter_content')).strip()
            elif c == 3:
                if Confirm.ask(self.i18n.get("menu_clear_data") + "?"):
                    self.config[data_key] = [] if is_list else ""
                    console.print(f"[yellow]{self.i18n.get('msg_data_cleared')}[/yellow]")
            self.save_config()

    def select_prompt_template(self, folder, key):
        """选择提示词模板"""
        prompt_dir = os.path.join(self.cli.PROJECT_ROOT, "Resource", "Prompt", folder)
        if not os.path.exists(prompt_dir): return
        files = [f for f in os.listdir(prompt_dir) if f.endswith((".txt", ".json"))]
        if not files: return

        is_readonly = (folder == "System" or key is None)

        for i, f in enumerate(files): console.print(f"{i+1}. {f}")

        # Add "Create New" option if not readonly
        if not is_readonly:
            console.print(f"[cyan]N.[/] {self.i18n.get('menu_prompt_create')}")

        console.print(f"[dim]0. {self.i18n.get('menu_cancel')}[/dim]")

        choices = [str(i+1) for i in range(len(files))] + ["0"]
        if not is_readonly: choices += ["N", "n"]

        choice_str = Prompt.ask(f"\n{self.i18n.get('prompt_template_select')}", choices=choices, show_choices=False)

        if choice_str == "0": return

        if not is_readonly and choice_str.lower() == "n":
            new_name = Prompt.ask(self.i18n.get('prompt_new_prompt_name')).strip()
            if not new_name: return
            if not new_name.endswith(".txt"): new_name += ".txt"
            new_path = os.path.join(prompt_dir, new_name)
            if os.path.exists(new_path):
                console.print(f"[red]{self.i18n.get('msg_file_exists')}[/red]")
                time.sleep(1)
                return

            # Create empty file
            try:
                with open(new_path, 'w', encoding='utf-8') as f: f.write("")
                console.print(f"[green]{self.i18n.get('msg_file_created')}[/green]")

                # Open in editor
                if open_in_editor(new_path):
                     Prompt.ask(f"\n{self.i18n.get('msg_press_enter_after_save')}")

                # Recursive call to refresh list
                self.select_prompt_template(folder, key)
                return
            except Exception as e:
                console.print(f"[red]Error creating file: {e}[/red]")
                time.sleep(2)
                return

        f_name = files[int(choice_str)-1]
        file_path = os.path.join(prompt_dir, f_name)

        try:
            with open(file_path, 'r', encoding='utf-8') as f: content = f.read()

            # Preview
            console.print(Panel(content, title=f"Preview: {f_name} {'[READ ONLY]' if is_readonly else ''}", border_style="blue", height=15))

            # Action Menu
            if not is_readonly:
                console.print(f"[bold cyan]1.[/] {self.i18n.get('opt_apply')}")
                console.print(f"[bold cyan]2.[/] {self.i18n.get('opt_edit_in_editor')}")
                console.print(f"[bold cyan]3.[/] {self.i18n.get('opt_edit_direct')}")

            console.print(f"[dim]0. {self.i18n.get('menu_cancel') if not is_readonly else self.i18n.get('menu_back')}[/dim]")

            action_choices = ["0"] if is_readonly else ["0", "1", "2", "3"]
            action = IntPrompt.ask(self.i18n.get('prompt_select'), choices=action_choices, default=0 if is_readonly else 1, show_choices=False)

            if action == 1 and not is_readonly:
                self.config[key] = {"last_selected_id": f_name.replace(".txt", ""), "prompt_content": content}
                self.save_config()
                console.print(f"[green]{self.i18n.get('msg_prompt_updated')}[/green]")
            elif action == 2 and not is_readonly:
                if open_in_editor(file_path):
                    Prompt.ask(f"\n{self.i18n.get('msg_press_enter_after_save')}")
                    self.select_prompt_template(folder, key)
                    return
            elif action == 3 and not is_readonly:
                console.print(f"\n[yellow]{self.i18n.get('msg_multi_line_hint')}[/yellow]")
                lines = []
                while True:
                    try:
                        line = input()
                        if line.strip().upper() == "EOF": break
                        lines.append(line)
                    except EOFError: break

                new_content = "\n".join(lines)
                if not lines:
                    if not Confirm.ask(self.i18n.get('msg_confirm_clear_file') or "Content is empty. Clear file?", default=False):
                        console.print("[yellow]Cancelled save.[/yellow]")
                        self.select_prompt_template(folder, key)
                        return

                try:
                    with open(file_path, 'w', encoding='utf-8') as f: f.write(new_content)
                    console.print(f"[green]{self.i18n.get('msg_saved')}[/green]")
                    self.select_prompt_template(folder, key)
                    return
                except Exception as e:
                    console.print(f"[red]Error saving: {e}[/red]"); time.sleep(2)
            else:
                # Return to list if readonly or cancelled
                if is_readonly:
                    self.select_prompt_template(folder, key)
                    return
                console.print("[yellow]Cancelled.[/yellow]")
            time.sleep(1)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]"); time.sleep(2)
