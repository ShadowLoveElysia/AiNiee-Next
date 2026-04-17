"""
配置档菜单模块
从 ainiee_cli.py 分离
"""
import os
import shutil
import time

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.table import Table


console = Console()


class ProfileMenu:
    """配置档管理菜单。"""

    def __init__(self, host):
        self.host = host

    @property
    def i18n(self):
        return self.host.i18n

    def show(self):
        while True:
            self.host.display_banner()
            console.print(Panel(f"[bold]{self.i18n.get('menu_profiles')}[/bold]"))

            profiles = self.host._get_profiles_list(self.host.profiles_dir)

            table = Table(show_header=False, box=None)
            table.add_row("[cyan]1.[/]", self.i18n.get("menu_profile_select"))
            table.add_row("[cyan]2.[/]", self.i18n.get("menu_profile_create"))
            table.add_row("[cyan]3.[/]", self.i18n.get("menu_profile_rename"))
            table.add_row("[red]4.[/]", self.i18n.get("menu_profile_delete"))
            console.print(table)
            console.print(f"\n[dim]0. {self.i18n.get('menu_exit')}[/dim]")

            choice = IntPrompt.ask(
                f"\n{self.i18n.get('prompt_select')}",
                choices=["0", "1", "2", "3", "4"],
                show_choices=False,
            )

            if choice == 0:
                break
            if choice == 1:
                if self._switch_profile(profiles):
                    break
            elif choice == 2:
                self._create_profile()
            elif choice == 3:
                self._rename_profile()
            elif choice == 4:
                self._delete_profile(profiles)

    def _switch_profile(self, profiles):
        console.print(Panel(self.i18n.get("menu_profile_select")))
        profile_table = Table(show_header=False, box=None)
        for index, profile_name in enumerate(profiles):
            is_active = profile_name == self.host.active_profile_name
            suffix = " [green](Active)[/]" if is_active else ""
            profile_table.add_row(f"[cyan]{index + 1}.[/]", f"{profile_name}{suffix}")
        console.print(profile_table)
        console.print(f"\n[dim]0. {self.i18n.get('menu_back')}[/dim]")

        selected_index = IntPrompt.ask(
            self.i18n.get("prompt_select"),
            choices=[str(i) for i in range(len(profiles) + 1)],
            show_choices=False,
        )
        if selected_index == 0:
            return False

        selected_profile = profiles[selected_index - 1]
        self.host.root_config["active_profile"] = selected_profile
        self.host.save_config(save_root=True)
        self.host.load_config()
        console.print(f"[green]{self.i18n.get('msg_active_platform').format(selected_profile)}[/green]")
        time.sleep(1)
        return True

    def _create_profile(self):
        new_name = Prompt.ask(self.i18n.get("prompt_profile_name")).strip()
        if new_name and not os.path.exists(os.path.join(self.host.profiles_dir, f"{new_name}.json")):
            shutil.copyfile(
                os.path.join(self.host.profiles_dir, f"{self.host.active_profile_name}.json"),
                os.path.join(self.host.profiles_dir, f"{new_name}.json"),
            )
            console.print(f"[green]{self.i18n.get('msg_profile_created').format(new_name)}[/green]")
        else:
            console.print(f"[red]{self.i18n.get('msg_profile_invalid')}[/red]")
        time.sleep(1)

    def _rename_profile(self):
        new_name = Prompt.ask(self.i18n.get("prompt_profile_rename")).strip()
        if new_name and not os.path.exists(os.path.join(self.host.profiles_dir, f"{new_name}.json")):
            os.rename(
                os.path.join(self.host.profiles_dir, f"{self.host.active_profile_name}.json"),
                os.path.join(self.host.profiles_dir, f"{new_name}.json"),
            )
            self.host.active_profile_name = new_name
            self.host.root_config["active_profile"] = new_name
            self.host.save_config(save_root=True)
            console.print(f"[green]{self.i18n.get('msg_profile_renamed').format(new_name)}[/green]")
        else:
            console.print(f"[red]{self.i18n.get('msg_profile_invalid')}[/red]")
        time.sleep(1)

    def _delete_profile(self, profiles):
        if len(profiles) <= 1:
            console.print(f"[red]{self.i18n.get('msg_cannot_delete_last')}[/red]")
            time.sleep(1)
            return

        delete_candidates = [profile for profile in profiles if profile != self.host.active_profile_name]
        console.print(Panel(f"{self.i18n.get('menu_profile_delete')}"))
        profile_table = Table(show_header=False, box=None)
        for index, profile_name in enumerate(delete_candidates):
            profile_table.add_row(f"[cyan]{index + 1}.[/]", profile_name)
        console.print(profile_table)
        console.print(f"\n[dim]0. {self.i18n.get('menu_cancel')}[/dim]")

        selected_index = IntPrompt.ask(
            self.i18n.get("prompt_select"),
            choices=[str(i) for i in range(len(delete_candidates) + 1)],
            show_choices=False,
        )
        if selected_index == 0:
            return

        selected_profile = delete_candidates[selected_index - 1]
        if Confirm.ask(f"[bold red]{self.i18n.get('msg_profile_delete_confirm').format(selected_profile)}[/bold red]"):
            os.remove(os.path.join(self.host.profiles_dir, f"{selected_profile}.json"))
            console.print(f"[green]{self.i18n.get('msg_profile_deleted').format(selected_profile)}[/green]")
        else:
            console.print(f"[yellow]{self.i18n.get('msg_delete_cancel')}[/yellow]")
        time.sleep(1)
