"""
插件设置菜单模块
从 ainiee_cli.py 分离
"""
import time

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt
from rich.table import Table


console = Console()


class PluginSettingsMenu:
    """插件设置菜单。"""

    def __init__(self, host):
        self.host = host

    @property
    def i18n(self):
        return self.host.i18n

    def show(self):
        while True:
            self.host.display_banner()
            console.print(Panel(f"[bold]{self.i18n.get('menu_plugin_settings')}[/bold]"))

            plugins = self.host.plugin_manager.get_plugins()
            if not plugins:
                console.print(f"[dim]{self.i18n.get('msg_no_plugins_found')}[/dim]")
                Prompt.ask(f"\n{self.i18n.get('msg_press_enter')}")
                break

            plugin_enables = self.host.root_config.get("plugin_enables", {})
            table = Table(show_header=True, show_lines=True)
            table.add_column("ID", style="dim")
            table.add_column(self.i18n.get("label_plugin_name"))
            table.add_column(self.i18n.get("label_status"), style="cyan")
            table.add_column(self.i18n.get("label_description"), ratio=1)

            sorted_plugin_names = sorted(plugins.keys())
            for index, name in enumerate(sorted_plugin_names, 1):
                plugin = plugins[name]
                is_enabled = plugin_enables.get(name, plugin.default_enable)
                status = "[green]ON[/]" if is_enabled else "[red]OFF[/]"
                table.add_row(str(index), name, status, plugin.description)

            console.print(table)
            console.print(f"\n[dim]0. {self.i18n.get('menu_back')}[/dim]")

            choice = IntPrompt.ask(
                f"\n{self.i18n.get('prompt_toggle_plugin')}",
                choices=[str(i) for i in range(len(sorted_plugin_names) + 1)],
                show_choices=False,
            )
            if choice == 0:
                break

            name = sorted_plugin_names[choice - 1]
            plugin = plugins[name]
            current_state = plugin_enables.get(name, plugin.default_enable)
            plugin_enables[name] = not current_state

            self.host.root_config["plugin_enables"] = plugin_enables
            self.host.save_config(save_root=True)
            self.host.plugin_manager.update_plugins_enable(plugin_enables)

            state_text = "enabled" if not current_state else "disabled"
            console.print(f"[green]Plugin '{name}' {state_text}.[/green]")
            time.sleep(0.5)
