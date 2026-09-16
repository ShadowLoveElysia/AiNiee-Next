"""
设置菜单模块
从 ainiee_cli.py 分离
"""
from rich.console import Console
from rich.panel import Panel
from rich.prompt import IntPrompt
from rich.markup import escape


console = Console()


def _prompt_label(text):
    return str(text).strip().rstrip(":：").strip()


class SettingsMenu:
    """设置菜单。"""

    def __init__(self, host):
        self.host = host

    @property
    def i18n(self):
        return self.host.i18n

    def show(self):
        from ModuleFolders.Infrastructure.TaskConfig.SettingsRenderer import SettingsMenuBuilder

        while True:
            builder = SettingsMenuBuilder(self.host.config, self.i18n)
            self.host.display_banner()
            console.print(Panel(f"[bold]{self.i18n.get('menu_settings')}[/bold]"))

            builder.build_menu_items()
            console.print(builder.render_table())

            console.print(f"\n[dim][yellow]*[/yellow] = {self.i18n.get('label_advanced_setting')}[/dim]")
            console.print(f"[dim]0. {self.i18n.get('menu_exit')}[/dim]")

            max_choice = len(builder.menu_items)
            choice = IntPrompt.ask(
                f"\n{_prompt_label(self.i18n.get('prompt_select'))}",
                choices=[str(i) for i in range(max_choice + 1)],
                show_choices=False,
            )
            if choice == 0:
                break

            key, item = builder.get_item_by_id(choice)
            if not (key and item):
                continue

            if key == "api_pool_management":
                self.host.api_manager.api_pool_menu()
                continue
            if key == "automation_settings":
                self.host.automation_menu.show()
                continue
            if key == "ebook_series_settings":
                self._show_ebook_series_settings()
                continue

            new_value = builder.handle_input(key, item, console)
            if new_value is not None:
                self.host.config[key] = new_value
                self.host.save_config()
                if key == "interface_language":
                    self.host.apply_interface_language(new_value)
                if key == "enable_operation_logging":
                    if new_value:
                        self.host.operation_logger.enable()
                    else:
                        self.host.operation_logger.disable()

    def _show_ebook_series_settings(self):
        from ModuleFolders.Domain.FileOutputer.EbookNaming import EbookIdentity, render_ebook_name
        from ModuleFolders.Infrastructure.TaskConfig.SettingsRenderer import SettingsMenuBuilder

        while True:
            builder = SettingsMenuBuilder(self.host.config, self.i18n)
            builder.build_menu_items(submenu="ebook_series_settings")
            self.host.display_banner()
            console.print(Panel(self.i18n.get("setting_ebook_series_settings")))
            console.print(builder.render_table())
            series = self.host.config.get("ebook_series_name") or self.i18n.get("ebook_example_book_name")
            template = self.host.config.get("ebook_name_template", "X 第N卷")
            try:
                single = render_ebook_name(template, EbookIdentity(series, "1"))
                merged = render_ebook_name(template, EbookIdentity(series, "1-7"))
                console.print(escape(self.i18n.get("ebook_name_preview").format(single, merged)))
            except ValueError:
                console.print(self.i18n.get("ebook_name_template_invalid"))
            console.print(f"[dim]0. {self.i18n.get('menu_exit')}[/dim]")
            choice = IntPrompt.ask(
                _prompt_label(self.i18n.get("prompt_select")),
                choices=[str(i) for i in range(len(builder.menu_items) + 1)], show_choices=False,
            )
            if choice == 0:
                return
            key, item = builder.get_item_by_id(choice)
            value = builder.handle_input(key, item, console)
            if value is None:
                continue
            if key == "ebook_name_template":
                try:
                    render_ebook_name(value, EbookIdentity(series, "1"))
                except ValueError:
                    console.print(self.i18n.get("ebook_name_template_invalid"))
                    continue
            self.host.config[key] = value
            self.host.save_config()
