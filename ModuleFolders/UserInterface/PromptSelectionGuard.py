import time

from rich.console import Console
from rich.panel import Panel
from rich.prompt import IntPrompt

from ModuleFolders.Domain.PromptBuilder.PromptBuilderEnum import PromptBuilderEnum
from ModuleFolders.Infrastructure.TaskConfig.TaskType import TaskType


console = Console()


class PromptSelectionGuard:
    def __init__(self, cli_menu):
        self.cli = cli_menu

    @property
    def i18n(self):
        return self.cli.i18n

    def _is_selection_valid(self, selection, builtin_ids):
        if not isinstance(selection, dict):
            return False

        selected_id = selection.get("last_selected_id")
        if selected_id in (None, ""):
            return False

        if selected_id in builtin_ids:
            return True

        prompt_content = selection.get("prompt_content")
        return isinstance(prompt_content, str) and bool(prompt_content.strip())

    def _get_missing_prompts(self, task_mode):
        missing = []

        if task_mode in (TaskType.TRANSLATION, TaskType.TRANSLATE_AND_POLISH):
            translate_selection = self.cli.config.get("translation_prompt_selection", {})
            if not self._is_selection_valid(
                translate_selection,
                {PromptBuilderEnum.COMMON, PromptBuilderEnum.COT, PromptBuilderEnum.THINK},
            ):
                missing.append(
                    {
                        "name": "translation",
                        "label": self.i18n.get("menu_select_trans_prompt"),
                        "message": self.i18n.get("msg_prompt_guard_translation_missing"),
                        "folder": "Translate",
                        "config_key": "translation_prompt_selection",
                    }
                )

        if task_mode in (TaskType.POLISH, TaskType.TRANSLATE_AND_POLISH):
            polish_selection = self.cli.config.get("polishing_prompt_selection", {})
            if not self._is_selection_valid(
                polish_selection,
                {PromptBuilderEnum.POLISH_COMMON},
            ):
                missing.append(
                    {
                        "name": "polishing",
                        "label": self.i18n.get("menu_select_polish_prompt"),
                        "message": self.i18n.get("msg_prompt_guard_polishing_missing"),
                        "folder": "Polishing",
                        "config_key": "polishing_prompt_selection",
                    }
                )

        return missing

    def _render_missing_panel(self, missing, blocked=False):
        lines = []
        if blocked:
            lines.append(f"[red]{self.i18n.get('msg_prompt_guard_blocked')}[/red]")
            lines.append("")

        lines.append(self.i18n.get("msg_prompt_guard_intro"))
        lines.append("")
        for item in missing:
            lines.append(f"- {item['message']}")
        lines.append("")
        lines.append(self.i18n.get("msg_prompt_guard_hint"))

        console.print(
            Panel(
                "\n".join(lines),
                title=self.i18n.get("title_prompt_guard"),
                border_style="red",
            )
        )

    def ensure_prompts_selected(self, task_mode, interactive=True):
        missing = self._get_missing_prompts(task_mode)
        if not missing:
            return True

        self._render_missing_panel(missing, blocked=not interactive)
        if not interactive:
            return False

        console.print(f"[cyan]1.[/] {self.i18n.get('option_prompt_guard_open_now')}")
        console.print(f"[dim]0. {self.i18n.get('menu_cancel')}[/dim]")
        choice = IntPrompt.ask(
            self.i18n.get("prompt_prompt_guard_open_selector"),
            choices=["0", "1"],
            default=1,
            show_choices=False,
        )
        if choice != 1:
            return False

        self.cli.display_banner()
        console.print(
            Panel(
                self.i18n.get("msg_prompt_guard_menu_redirect"),
                title=self.i18n.get("title_prompt_guard"),
                border_style="red",
            )
        )
        time.sleep(3)
        self.cli.glossary_menu.prompt_menu()

        remaining = self._get_missing_prompts(task_mode)
        if remaining:
            self._render_missing_panel(remaining, blocked=True)
        else:
            console.print(
                Panel(
                    self.i18n.get("msg_prompt_guard_restart_required"),
                    title=self.i18n.get("title_prompt_guard"),
                    border_style="red",
                )
            )

        return False
