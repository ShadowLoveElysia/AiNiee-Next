"""
诊断菜单模块
从 ainiee_cli.py 分离
"""
import time

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt
from rich.table import Table


console = Console()


class DiagnosticMenu:
    """智能诊断菜单。"""

    def __init__(self, host):
        self.host = host

    @property
    def i18n(self):
        return self.host.i18n

    def show(self):
        while True:
            self.host.display_banner()
            console.print(Panel(f"[bold]{self.i18n.get('menu_diagnostic_title')}[/bold]"))

            table = Table(show_header=False, box=None)
            table.add_row("[cyan]1.[/]", self.i18n.get("menu_diagnostic_auto"))
            table.add_row("[cyan]2.[/]", self.i18n.get("menu_diagnostic_browse"))
            table.add_row("[cyan]3.[/]", self.i18n.get("menu_diagnostic_search"))
            console.print(table)
            console.print(f"\n[dim]0. {self.i18n.get('menu_back')}[/dim]")

            choice = IntPrompt.ask(
                self.i18n.get("prompt_select"),
                choices=["0", "1", "2", "3"],
                show_choices=False,
            )
            if choice == 0:
                break
            if choice == 1:
                self._auto_menu()
            elif choice == 2:
                self._browse_menu()
            elif choice == 3:
                self._search_menu()

    def _auto_menu(self):
        self.host.display_banner()
        console.print(Panel(f"[bold]{self.i18n.get('menu_diagnostic_auto')}[/bold]"))

        error_text = ""
        if getattr(self.host, "_last_crash_msg", None):
            error_text = self.host._last_crash_msg
        elif getattr(self.host, "_api_error_messages", None):
            error_text = "\n".join(self.host._api_error_messages)

        if not error_text.strip():
            console.print(f"[yellow]{self.i18n.get('msg_no_error_detected')}[/yellow]")
            Prompt.ask(f"\n{self.i18n.get('msg_press_enter_to_continue')}")
            return

        preview = error_text[:500] + ("..." if len(error_text) > 500 else "")
        console.print(
            Panel(
                preview,
                title=f"[bold yellow]{self.i18n.get('label_error_content')}[/bold yellow]",
            )
        )

        result = self.host.smart_diagnostic.diagnose(error_text)
        formatted = self.host._format_diagnostic_result(result)
        console.print(
            Panel(
                formatted,
                title=f"[bold cyan]{self.i18n.get('msg_diagnostic_result')}[/bold cyan]",
            )
        )
        Prompt.ask(f"\n{self.i18n.get('msg_press_enter_to_continue')}")

    def _browse_menu(self):
        knowledge_base = self.host.smart_diagnostic.knowledge_base
        items = list(knowledge_base.knowledge_items.values())
        if not items:
            console.print(f"[yellow]{self.i18n.get('msg_no_match_found')}[/yellow]")
            time.sleep(1)
            return

        categories = {}
        for item in items:
            categories.setdefault(item.category, []).append(item)

        while True:
            self.host.display_banner()
            console.print(Panel(f"[bold]{self.i18n.get('menu_diagnostic_browse')}[/bold]"))

            category_list = list(categories.keys())
            table = Table(show_header=False, box=None)
            for index, category in enumerate(category_list):
                table.add_row(f"[cyan]{index + 1}.[/]", category)
            console.print(table)
            console.print(f"\n[dim]0. {self.i18n.get('menu_back')}[/dim]")

            choice = IntPrompt.ask(
                self.i18n.get("prompt_select"),
                choices=[str(i) for i in range(len(category_list) + 1)],
                show_choices=False,
            )
            if choice == 0:
                break

            selected_category = category_list[choice - 1]
            self._browse_category(selected_category, categories[selected_category])

    def _browse_category(self, category_name, category_items):
        while True:
            self.host.display_banner()
            console.print(Panel(f"[bold]{category_name}[/bold]"))

            for index, item in enumerate(category_items):
                console.print(f"[cyan]{index + 1}.[/] {item.question}")
            console.print(f"\n[dim]0. {self.i18n.get('menu_back')}[/dim]")

            choice = IntPrompt.ask(
                self.i18n.get("prompt_select"),
                choices=[str(i) for i in range(len(category_items) + 1)],
                show_choices=False,
            )
            if choice == 0:
                break

            selected_item = category_items[choice - 1]
            console.print(
                Panel(
                    selected_item.answer,
                    title=f"[bold green]{selected_item.question}[/bold green]",
                )
            )
            Prompt.ask(f"\n{self.i18n.get('msg_press_enter_to_continue')}")

    def _search_menu(self):
        self.host.display_banner()
        console.print(Panel(f"[bold]{self.i18n.get('menu_diagnostic_search')}[/bold]"))

        keyword = Prompt.ask(self.i18n.get("prompt_search_keyword"))
        if not keyword.strip():
            return

        found_any = False
        self.host.display_banner()
        console.print(Panel(f"[bold]{self.i18n.get('msg_diagnostic_result')}[/bold]"))

        rule_result = self.host.smart_diagnostic.rule_matcher.match(keyword)
        if rule_result.is_matched:
            found_any = True
            formatted = self.host._format_diagnostic_result(rule_result)
            console.print(
                Panel(
                    formatted,
                    title=(
                        f"[bold cyan]{self.i18n.get('label_matched_rule')}: "
                        f"{rule_result.matched_rule}[/bold cyan]"
                    ),
                )
            )

        knowledge_base = self.host.smart_diagnostic.knowledge_base
        results = knowledge_base.search_by_keywords(keyword, top_k=5)
        if results:
            found_any = True
            for item, score in results:
                console.print(
                    Panel(
                        item.answer,
                        title=f"[bold green]{item.question}[/bold green] [dim](score: {score:.2f})[/dim]",
                    )
                )

        if not found_any:
            console.print(f"[yellow]{self.i18n.get('msg_no_match_found')}[/yellow]")

        Prompt.ask(f"\n{self.i18n.get('msg_press_enter_to_continue')}")
