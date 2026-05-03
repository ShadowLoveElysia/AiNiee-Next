"""
导出流程模块
从 ainiee_cli.py 分离
"""
import glob
import os

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm


console = Console()


class ExportFlow:
    """缓存导出流程。"""

    def __init__(self, host):
        self.host = host

    @property
    def i18n(self):
        return self.host.i18n

    @staticmethod
    def _is_proofread_cache(cache_path):
        return os.path.basename(cache_path) == "AinieeCacheData_proofread.json"

    @staticmethod
    def _normalize_ai_proofread_status_for_export(project):
        """兼容旧版AI校对缓存，避免AI_PROOFREAD状态被部分Writer跳过。"""
        from ModuleFolders.Infrastructure.Cache.CacheItem import TranslationStatus

        for item in project.items_iter():
            if item.translation_status != TranslationStatus.AI_PROOFREAD:
                continue
            if item.translated_text and item.translated_text.strip():
                item.polished_text = ""
                item.translation_status = TranslationStatus.TRANSLATED
            elif item.polished_text and item.polished_text.strip():
                item.translation_status = TranslationStatus.POLISHED

    def run_export_only(self, target_path=None, non_interactive=False):
        from ModuleFolders.Infrastructure.Cache.CacheManager import CacheManager

        if target_path is None:
            target_path = self._select_target_path()
            if not target_path:
                return

        if os.path.isdir(target_path):
            target_path = self._maybe_switch_to_single_file(target_path)

        if not os.path.exists(target_path):
            console.print(f"[red]Error: Input path '{target_path}' not found.[/red]")
            return

        abs_input = os.path.abspath(target_path)
        parent_dir = os.path.dirname(abs_input)
        base_name = os.path.basename(abs_input)
        if os.path.isfile(target_path):
            base_name = os.path.splitext(base_name)[0]
        output_path = os.path.join(parent_dir, f"{base_name}_AiNiee_Output")

        cache_path = os.path.join(output_path, "cache", "AinieeCacheData.json")
        proofread_cache_path = os.path.join(output_path, "cache", "AinieeCacheData_proofread.json")
        cache_path = self._resolve_cache_path(
            cache_path,
            proofread_cache_path,
            non_interactive,
        )
        if not cache_path:
            return

        try:
            with console.status(f"[cyan]{self.i18n.get('msg_export_started')}[/cyan]"):
                if hasattr(self.host.cache_manager, "flush_pending_save"):
                    self.host.cache_manager.flush_pending_save()
                project = CacheManager.read_from_file(cache_path)
                if self._is_proofread_cache(cache_path):
                    self._normalize_ai_proofread_status_for_export(project)
                self.host.task_executor.config.initialize(self.host.config)
                config = self.host.task_executor.config
                output_config = {
                    "translated_suffix": config.output_filename_suffix,
                    "bilingual_suffix": "_bilingual",
                    "bilingual_order": config.bilingual_text_order,
                }
                self.host.file_outputer.output_translated_content(
                    project,
                    output_path,
                    target_path,
                    output_config,
                    config,
                )

            console.print(f"\n[green]✓ {self.i18n.get('msg_export_completed')}[/green]")
            console.print(f"[dim]Output: {output_path}[/dim]")
        except Exception as exc:
            console.print(f"[red]Export Error: {exc}[/red]")

        if not non_interactive:
            Prompt.ask(f"\n{self.i18n.get('msg_press_enter')}")

    def _select_target_path(self):
        last_path = self.host.config.get("label_input_path")
        can_resume = last_path and os.path.exists(last_path)

        console.clear()
        menu_text = f"1. {self.i18n.get('mode_single_file')}\n2. {self.i18n.get('mode_batch_folder')}"
        if can_resume:
            short_path = last_path if len(last_path) < 40 else "..." + last_path[-37:]
            menu_text += f"\n3. {self.i18n.get('mode_resume').format(short_path)}"

        console.print(Panel(menu_text, title=f"[bold]{self.i18n.get('menu_export_only')}[/bold]", expand=False))

        choices = ["0", "1", "2"]
        if can_resume:
            choices.append("3")

        prompt_txt = self.i18n.get("prompt_select").strip().rstrip(":").rstrip("：")
        choice = IntPrompt.ask(f"\n{prompt_txt}", choices=choices, show_choices=False)
        if choice == 0:
            return None
        if choice == 3:
            return last_path

        is_file_mode = choice == 1
        start_path = self.host.config.get("label_input_path", ".")
        if is_file_mode and os.path.isfile(start_path):
            start_path = os.path.dirname(start_path)

        return self.host.file_selector.select_path(
            start_path=start_path,
            select_file=is_file_mode,
            select_dir=not is_file_mode,
        )

    def _maybe_switch_to_single_file(self, target_path):
        candidates = []
        for ext in ("*.txt", "*.epub"):
            candidates.extend(glob.glob(os.path.join(target_path, ext)))

        if len(candidates) != 1:
            return target_path

        file_name = os.path.basename(candidates[0])
        if Confirm.ask(
            f"\n[cyan]Found a single file '{file_name}' in this directory. Search for cache based on this file instead of the folder?[/cyan]",
            default=True,
        ):
            target_path = candidates[0]
            console.print(f"[dim]Switched target to file: {target_path}[/dim]")
        return target_path

    def _resolve_cache_path(self, cache_path, proofread_cache_path, non_interactive):
        while not os.path.exists(cache_path):
            console.print(f"\n[yellow]Cache not found at default path: {cache_path}[/yellow]")
            if non_interactive:
                console.print("[red]Aborting in non-interactive mode.[/red]")
                return None

            output_path = Prompt.ask(self.i18n.get("msg_enter_output_path")).strip().strip('"').strip("'")
            if output_path.lower() == "q":
                return None
            cache_path = os.path.join(output_path, "cache", "AinieeCacheData.json")
            proofread_cache_path = os.path.join(output_path, "cache", "AinieeCacheData_proofread.json")

        if os.path.exists(proofread_cache_path) and not non_interactive:
            console.print("\n[cyan]检测到AI校对版本的cache文件[/cyan]")
            console.print("  [1] 使用原始翻译版本")
            console.print("  [2] 使用AI校对版本 (推荐)")
            cache_choice = IntPrompt.ask("请选择", choices=["1", "2"], default=2, show_choices=False)
            if cache_choice == 2:
                console.print("[green]将使用AI校对版本导出[/green]")
                return proofread_cache_path

        return cache_path
