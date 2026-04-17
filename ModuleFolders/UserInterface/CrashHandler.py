"""
崩溃处理模块
从 ainiee_cli.py 分离
"""
import os
import sys
import time
from datetime import datetime

import rapidjson as json

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.table import Table

from ModuleFolders.Base.Base import Base


console = Console()


class CrashHandler:
    """崩溃处理与错误分析。"""

    def __init__(self, host):
        self.host = host

    @property
    def i18n(self):
        return self.host.i18n

    @property
    def project_root(self):
        return self.host.PROJECT_ROOT

    def handle_crash(self, error_msg, temp_config=None):
        """错误处理菜单。"""
        self.host.task_running = False
        self.host.operation_logger.log(f"出现报错: {error_msg[:100]}...", "ERROR")

        console.print("\n")
        console.print(
            Panel(
                f"[bold yellow]{self.i18n.get('msg_program_error')}[/bold yellow]",
                border_style="yellow",
            )
        )

        diag_result = self.host.smart_diagnostic.diagnose(error_msg)
        if diag_result.is_matched:
            formatted = self.host._format_diagnostic_result(diag_result)
            console.print(
                Panel(
                    formatted,
                    title=f"[bold cyan]{self.i18n.get('msg_diagnostic_result')}[/bold cyan]",
                    border_style="cyan",
                )
            )
            console.print("")
        else:
            transient_keywords = [
                "401",
                "403",
                "429",
                "500",
                "Timeout",
                "Connection",
                "SSL",
                "rate_limit",
                "bad request",
            ]
            if any(keyword.lower() in error_msg.lower() for keyword in transient_keywords):
                console.print(
                    f"[bold yellow]![/] [yellow]{self.i18n.get('msg_api_transient_error')}[/yellow]\n"
                )

        current_platform = temp_config["target_platform"] if temp_config else self.host.config.get("target_platform", "None")
        current_model = temp_config["model"] if temp_config else self.host.config.get("model", "None")
        temp_suffix = " [yellow](Temporary API)[/]" if temp_config else ""
        console.print(f"[dim]Environment: {current_platform} - {current_model}{temp_suffix}[/dim]")
        console.print(f"[dim]{self.i18n.get('label_error_content')}: {error_msg}[/dim]\n")

        if self.host.operation_logger.is_enabled():
            records = self.host.operation_logger.get_records()
            if records:
                op_flow = " -> ".join(record["action"] for record in records[-10:])
                console.print(f"[dim]{self.i18n.get('label_operation_flow') or '操作流程'}: {op_flow}[/dim]\n")

        table = Table(show_header=False, box=None)
        table.add_row("[cyan]1.[/]", self.i18n.get("error_menu_analyze_llm"))
        table.add_row("[cyan]2.[/]", self.i18n.get("error_menu_analyze_github"))
        table.add_row("[cyan]3.[/]", self.i18n.get("error_menu_update"))
        table.add_row("[cyan]4.[/]", self.i18n.get("error_menu_save_log"))
        table.add_row("[cyan]5.[/]", self.i18n.get("menu_error_temp_api"))
        table.add_row("[red]0.[/]", self.i18n.get("error_menu_exit"))
        console.print(table)

        choice = IntPrompt.ask(
            self.i18n.get("prompt_select"),
            choices=["0", "1", "2", "3", "4", "5"],
            show_choices=False,
        )

        if choice == 1:
            analysis = self.analyze_error_with_llm(error_msg, temp_config)
            if analysis:
                console.print(
                    Panel(
                        analysis,
                        title=f"[bold cyan]{self.i18n.get('msg_llm_analysis_result')}[/bold cyan]",
                    )
                )
                code_issue_keywords = [
                    "此为代码问题",
                    "This is a code issue",
                    "これはコードの問題です",
                ]
                if any(keyword in analysis for keyword in code_issue_keywords):
                    if Confirm.ask(f"\n[bold yellow]{self.i18n.get('msg_ask_submit_issue')}[/bold yellow]"):
                        self.prepare_github_issue(error_msg, analysis)
                else:
                    Prompt.ask(f"\n{self.i18n.get('msg_press_enter_to_continue')}")
            self.handle_crash(error_msg, temp_config)
            return

        if choice == 2:
            analysis = None
            if Confirm.ask(f"{self.i18n.get('msg_confirm_llm_analyze_first')}"):
                analysis = self.analyze_error_with_llm(error_msg, temp_config)
            self.prepare_github_issue(error_msg, analysis)
            self.handle_crash(error_msg, temp_config)
            return

        if choice == 3:
            self.host.update_manager.start_update()
            return

        if choice == 4:
            path = self.save_error_log(error_msg)
            console.print(f"[green]{self.i18n.get('msg_error_saved').format(path=path)}[/green]")
            time.sleep(2)
            self.handle_crash(error_msg, temp_config)
            return

        if choice == 5:
            next_temp_config = self._prompt_temp_api_config()
            if next_temp_config == "__exit__":
                return
            if next_temp_config is None:
                self.handle_crash(error_msg, temp_config)
                return

            if next_temp_config.get("api_key"):
                console.print(f"[green]{self.i18n.get('msg_temp_api_ok')}[/green]")
            self.handle_crash(error_msg, next_temp_config)
            return

        sys.exit(1)

    def analyze_error_with_llm(self, error_msg, temp_config=None):
        """调用 LLM 分析错误原因。"""
        if (
            not temp_config
            and self.host.config.get("target_platform", "None").lower()
            in ["none", "localllm", "sakura", "murasaki"]
        ):
            console.print(f"[yellow]{self.i18n.get('msg_temp_api_prompt')}[/yellow]")
            console.print(f"[red]{self.i18n.get('msg_api_not_configured')}[/red]")
            return None

        from ModuleFolders.Infrastructure.LLMRequester.LLMRequester import LLMRequester
        from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig
        from ModuleFolders.Infrastructure.TaskConfig.TaskType import TaskType
        import copy

        if temp_config:
            preset_path = os.path.join(self.project_root, "Resource", "platforms", "preset.json")
            try:
                with open(preset_path, "r", encoding="utf-8") as file:
                    config_shadow = json.load(file)
            except Exception:
                config_shadow = copy.deepcopy(self.host.config)

            platform_tag = temp_config["target_platform"]
            config_shadow["target_platform"] = platform_tag
            config_shadow["api_settings"] = {"translate": platform_tag, "polish": platform_tag}
            config_shadow.setdefault("platforms", {})
            config_shadow["platforms"].setdefault(platform_tag, {"api_format": "OpenAI"})
            config_shadow["platforms"][platform_tag].update(temp_config)
            config_shadow["base_url"] = temp_config.get("api_url")
            config_shadow["api_key"] = temp_config.get("api_key")
            config_shadow["model"] = temp_config.get("model")
            if temp_config.get("think_switch"):
                config_shadow["think_switch"] = True
                config_shadow["think_depth"] = temp_config.get("think_depth")
                config_shadow["thinking_budget"] = temp_config.get("thinking_budget")
        else:
            config_shadow = copy.deepcopy(self.host.config)

        temp_cfg_path = os.path.join(self.project_root, "Resource", "temp_crash_config.json")
        try:
            with open(temp_cfg_path, "w", encoding="utf-8") as file:
                json.dump(config_shadow, file, indent=4, ensure_ascii=False)

            test_task_config = TaskConfig()
            test_task_config.initialize(config_shadow)

            original_base_print = Base.print
            Base.print = lambda *args, **kwargs: None
            try:
                test_task_config.prepare_for_translation(TaskType.TRANSLATION)
                platform_config = test_task_config.get_platform_configuration("translationReq")
            finally:
                Base.print = original_base_print

            if "model_name" in platform_config and "model" not in platform_config:
                platform_config["model"] = platform_config["model_name"]

            platform_config["temperature"] = 1.0
            platform_config["top_p"] = 1.0

            requester = LLMRequester()
            system_prompt = self._load_error_analysis_prompt()
            user_content = self._build_error_analysis_prompt(error_msg)

            console.print(f"[cyan]{self.i18n.get('msg_llm_analyzing')}[/cyan]")
            skip, _, content, _, _ = requester.sent_request(
                [{"role": "user", "content": user_content}],
                system_prompt,
                platform_config,
            )
            if skip:
                console.print(f"[red]LLM Analysis failed: {content}[/red]")
                return None
            return content
        finally:
            if os.path.exists(temp_cfg_path):
                try:
                    os.remove(temp_cfg_path)
                except Exception:
                    pass

    def prepare_github_issue(self, error_msg, analysis=None):
        """生成 GitHub issue 模板并打开提交页。"""
        env_info = (
            f"- OS: {sys.platform}\n"
            f"- Python: {sys.version.split()[0]}\n"
            f"- App Version: {self.host.update_manager.get_local_version_full()}"
        )
        issue_body = (
            "## Error Description\n\n"
            f"```python\n{error_msg}\n```\n\n"
            f"## Environment\n{env_info}\n"
        )
        if analysis:
            issue_body += f"\n## LLM Analysis Result\n{analysis}\n"

        console.print(Panel(issue_body, title="GitHub Issue Template"))
        console.print(f"\n[bold cyan]{self.i18n.get('msg_github_guide')}[/bold cyan]")
        console.print(f"[bold cyan]{self.i18n.get('msg_github_issue_template')}[/bold cyan]")

        import webbrowser

        webbrowser.open("https://github.com/ShadowLoveElysia/AiNiee-Next/issues/new")
        Prompt.ask(f"\n{self.i18n.get('msg_press_enter_to_continue')}")

    def save_error_log(self, error_msg):
        """保存错误日志。"""
        log_dir = os.path.join(self.project_root, "output", "logs")
        os.makedirs(log_dir, exist_ok=True)

        filename = f"crash_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        path = os.path.join(log_dir, filename)
        with open(path, "w", encoding="utf-8") as file:
            file.write(f"Timestamp: {datetime.now().isoformat()}\n")
            file.write(f"Environment: OS={sys.platform}, Python={sys.version}\n")
            file.write(f"Version: {self.host.update_manager.get_local_version_full()}\n")
            file.write("-" * 40 + "\n")
            file.write(error_msg)
        return path

    def _prompt_temp_api_config(self):
        preset_path = os.path.join(self.project_root, "Resource", "platforms", "preset.json")
        if not os.path.exists(preset_path):
            return "__exit__"

        with open(preset_path, "r", encoding="utf-8") as file:
            preset = json.load(file)

        platforms = preset.get("platforms", {})
        online_platforms = {
            key: value
            for key, value in platforms.items()
            if value.get("group") in ["online", "custom"]
        }
        sorted_keys = sorted(online_platforms.keys())

        console.print(Panel(self.i18n.get("prompt_temp_api_platform")))
        table = Table(show_header=False, box=None)
        for index, key in enumerate(sorted_keys):
            table.add_row(f"[cyan]{index + 1}.[/]", online_platforms[key].get("name", key))
        console.print(table)

        platform_index = IntPrompt.ask(
            self.i18n.get("prompt_select"),
            choices=[str(i) for i in range(len(sorted_keys) + 1)],
            show_choices=False,
        )
        if platform_index == 0:
            return None

        selected_tag = sorted_keys[platform_index - 1]
        selected_config = online_platforms[selected_tag].copy()

        if "api_key" in selected_config.get("key_in_settings", []) or "api_key" in selected_config:
            selected_config["api_key"] = Prompt.ask(
                self.i18n.get("prompt_temp_api_key"),
                password=True,
            ).strip()

        if "api_url" in selected_config.get("key_in_settings", []) or selected_tag == "custom":
            selected_config["api_url"] = Prompt.ask(
                self.i18n.get("prompt_temp_api_url"),
                default=selected_config.get("api_url", ""),
            ).strip()

        if "model" in selected_config.get("key_in_settings", []):
            model_options = selected_config.get("model_datas", [])
            if model_options:
                console.print(f"\n[cyan]Suggested Models for {selected_tag}:[/] {', '.join(model_options)}")
            selected_config["model"] = Prompt.ask(
                self.i18n.get("prompt_temp_model"),
                default=selected_config.get("model", ""),
            ).strip()

        if Confirm.ask(self.i18n.get("prompt_temp_think_switch"), default=False):
            selected_config["think_switch"] = True
            if selected_config.get("api_format") == "Anthropic":
                selected_config["think_depth"] = Prompt.ask(
                    self.i18n.get("prompt_temp_think_depth"),
                    choices=["low", "medium", "high"],
                    default="low",
                )
            else:
                selected_config["think_depth"] = Prompt.ask(
                    self.i18n.get("prompt_temp_think_depth"),
                    choices=["minimal", "low", "medium", "high"],
                    default="low",
                )
            console.print(f"[dim]{self.i18n.get('hint_think_budget') or '提示: 0=关闭, -1=无上限'}[/dim]")
            budget_str = Prompt.ask(self.i18n.get("prompt_temp_think_budget"), default="4096")
            try:
                selected_config["thinking_budget"] = int(budget_str)
            except ValueError:
                selected_config["thinking_budget"] = 4096
        else:
            selected_config["think_switch"] = False

        selected_config["target_platform"] = selected_tag
        return selected_config

    def _load_error_analysis_prompt(self):
        prompt_path = os.path.join(self.project_root, "Resource", "Prompt", "System", "error_analysis.json")
        system_prompt = "You are a Python expert helping a user with a crash."
        try:
            if os.path.exists(prompt_path):
                with open(prompt_path, "r", encoding="utf-8") as file:
                    prompts = json.load(file)
                lang = self._get_language_code()
                system_prompt = prompts.get("system_prompt", {}).get(
                    lang,
                    prompts.get("system_prompt", {}).get("en", system_prompt),
                )
        except Exception:
            pass
        return system_prompt

    def _build_error_analysis_prompt(self, error_msg):
        lang = self._get_language_code()
        env_info = (
            f"OS={sys.platform}, Python={sys.version.split()[0]}, "
            f"App Version={self.host.update_manager.get_local_version_full()}"
        )

        if lang == "zh_CN":
            user_content = (
                "程序发生崩溃。\n"
                f"环境信息: {env_info}\n\n"
                "项目文件结构:\n"
                "- 核心逻辑: ainiee_cli.py, ModuleFolders/*\n"
                "- 用户扩展: PluginScripts/*\n"
                "- 资源文件: Resource/*\n\n"
            )
        elif lang == "ja":
            user_content = (
                "プログラムがクラッシュしました。\n"
                f"環境情報: {env_info}\n\n"
                "プロジェクトファイル構造:\n"
                "- コアロジック: ainiee_cli.py, ModuleFolders/*\n"
                "- ユーザー拡張: PluginScripts/*\n"
                "- リソース: Resource/*\n\n"
            )
        else:
            user_content = (
                "The program crashed.\n"
                f"Environment: {env_info}\n\n"
                "Project File Structure:\n"
                "- Core Logic: ainiee_cli.py, ModuleFolders/*\n"
                "- User Extensions: PluginScripts/*\n"
                "- Resources: Resource/*\n\n"
            )

        if self.host.operation_logger.is_enabled():
            user_content += f"{self.host.operation_logger.get_formatted_log()}\n\n"

        if lang == "zh_CN":
            user_content += (
                f"错误堆栈:\n{error_msg}\n\n"
                "分析要求:\n"
                "请分析此崩溃是由外部因素（网络、API Key、环境、SSL）还是内部软件缺陷（AiNiee-Next代码Bug）导致的。\n"
                "注意: 网络/SSL/429/401错误通常不是代码Bug，除非代码从根本上误用了库。\n"
                "如果错误发生在第三方库（如requests、urllib3、ssl）中且由网络条件引起，则不是代码Bug。\n\n"
                "【重要】如果你确定这是AiNiee-Next的代码Bug，必须在回复中包含这句话：「此为代码问题」"
            )
        elif lang == "ja":
            user_content += (
                f"トレースバック:\n{error_msg}\n\n"
                "分析要求:\n"
                "このクラッシュが外部要因（ネットワーク、APIキー、環境、SSL）によるものか、内部ソフトウェアの欠陥（AiNiee-Nextコードのバグ）によるものかを分析してください。\n"
                "注意: ネットワーク/SSL/429/401エラーは、コードがライブラリを根本的に誤用していない限り、コードのバグではありません。\n"
                "サードパーティライブラリ（requests、urllib3、sslなど）でネットワーク条件によりエラーが発生した場合、コードのバグではありません。\n\n"
                "【重要】これがAiNiee-Nextのコードバグであると確信した場合、回答に必ずこの文を含めてください：「これはコードの問題です」"
            )
        else:
            user_content += (
                f"Traceback:\n{error_msg}\n\n"
                "Strict Analysis Request:\n"
                "Analyze if the crash is due to external factors (Network, API Key, Environment, SSL) or internal software defects (Bugs in AiNiee-Next code).\n"
                "Note: Network/SSL/429/401 errors are NEVER code bugs unless the code is fundamentally misusing the library.\n"
                "If the error occurs in a third-party library (like requests, urllib3, ssl) due to network conditions, it is NOT a code bug.\n\n"
                '[IMPORTANT] If you are certain this is a code bug in AiNiee-Next, you MUST include this exact phrase in your response: "This is a code issue"'
            )

        return user_content

    def _get_language_code(self):
        return getattr(self.i18n, "lang", "en")
