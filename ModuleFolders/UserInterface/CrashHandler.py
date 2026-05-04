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

        diagnostic_context = self._build_diagnostic_context(temp_config)
        diag_result = self.host.smart_diagnostic.diagnose(error_msg, diagnostic_context)
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

        from ModuleFolders.Diagnostic.LLMErrorAnalyzer import LLMErrorAnalyzer
        config_shadow = {} if temp_config else self.host.config

        analyzer = LLMErrorAnalyzer(self.project_root, self._get_language_code())
        operation_log = ""
        if self.host.operation_logger.is_enabled():
            operation_log = self.host.operation_logger.get_formatted_log()
        update_version = self.host.update_manager.get_local_version_full()

        console.print(f"[cyan]{self.i18n.get('msg_llm_analyzing')}[/cyan]")
        success, content, _ = analyzer.analyze(
            error_msg,
            config_shadow,
            temp_config=temp_config,
            operation_log=operation_log,
            update_version=update_version,
            temperature=1.0,
            top_p=1.0,
        )
        if not success:
            console.print(f"[red]LLM Analysis failed: {content}[/red]")
            return None
        return content

    def _build_diagnostic_context(self, temp_config=None):
        context = {
            "config": temp_config or self.host.config,
        }
        if self.host.operation_logger.is_enabled():
            context["operation_log"] = self.host.operation_logger.get_formatted_log()
        if self.host.config.get("label_input_path"):
            context["input_path"] = self.host.config.get("label_input_path")
        if self.host.config.get("label_output_path"):
            context["output_path"] = self.host.config.get("label_output_path")
        return context

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
            elif selected_config.get("target_platform") == "deepseek":
                selected_config["think_depth"] = Prompt.ask(
                    self.i18n.get("prompt_temp_think_depth"),
                    choices=["low", "medium", "high", "xhigh", "max"],
                    default="low",
                )
            else:
                selected_config["think_depth"] = Prompt.ask(
                    self.i18n.get("prompt_temp_think_depth"),
                    choices=["minimal", "low", "medium", "high", "xhigh"],
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

    def _get_language_code(self):
        return getattr(self.i18n, "lang", "en")
