import os
import subprocess
import sys
import time

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table


console = Console()


class TerminalCompatibilityHelper:
    def __init__(self, cli_menu):
        self.cli = cli_menu

    @property
    def i18n(self):
        return self.cli.i18n

    def detect_terminal_capability(self):
        result = {
            "capable": False,
            "is_windows": sys.platform == "win32",
            "is_ssh": bool(os.environ.get("SSH_CLIENT") or os.environ.get("SSH_TTY") or os.environ.get("SSH_CONNECTION")),
            "is_windows_terminal": bool(os.environ.get("WT_SESSION")),
            "is_windows_cmd": False,
            "supports_default_terminal": False,
            "windows_build": 0,
            "colorterm": os.environ.get("COLORTERM", ""),
            "term": os.environ.get("TERM", ""),
            "term_program": os.environ.get("TERM_PROGRAM", ""),
        }

        if result["is_windows_terminal"]:
            result["capable"] = True
            return result

        term_program = result["term_program"].lower()
        high_quality_terminals = ("iterm.app", "vscode", "hyper", "tabby", "wezterm", "kitty", "alacritty")
        if term_program in high_quality_terminals:
            result["capable"] = True
            return result

        if result["is_ssh"]:
            if result["colorterm"].lower() in ("truecolor", "24bit"):
                result["capable"] = True
                return result
            return result

        if result["colorterm"].lower() in ("truecolor", "24bit"):
            result["capable"] = True
            return result

        term = result["term"].lower()
        if any(item in term for item in ["256color", "kitty", "alacritty"]):
            result["capable"] = True
            return result

        if any(item in term for item in ["xterm", "screen", "tmux", "rxvt"]):
            result["capable"] = True
            return result

        if term_program == "apple_terminal":
            result["capable"] = True
            return result

        if result["is_windows"]:
            try:
                import platform

                version = platform.version()
                build = int(version.split(".")[-1])
                result["windows_build"] = build

                if build >= 22000:
                    result["capable"] = True
                    return result

                if build >= 14393:
                    if build >= 19045:
                        result["supports_default_terminal"] = True
                    result["is_windows_cmd"] = True
                    return result
            except (ValueError, IndexError):
                pass

            if not result["term"] and not result["colorterm"]:
                result["is_windows_cmd"] = True

        return result

    def check_terminal_compatibility(self):
        if self.cli.root_config.get("terminal_check_skipped"):
            return True

        term_info = self.detect_terminal_capability()
        if term_info["capable"]:
            return True

        if term_info["is_windows_cmd"]:
            detected_msg = self.i18n.get("terminal_compat_detected_cmd")
            hint_msg = self.i18n.get("terminal_compat_wt_better")
        elif term_info["is_ssh"]:
            detected_msg = self.i18n.get("terminal_compat_detected_ssh")
            hint_msg = self.i18n.get("terminal_compat_ssh_better")
        else:
            detected_msg = self.i18n.get("terminal_compat_detected_limited")
            hint_msg = self.i18n.get("terminal_compat_general_better")

        console.print("\n")
        console.print(
            Panel(
                f"[yellow]{detected_msg}[/yellow]\n[dim]{hint_msg}[/dim]",
                title=f"[bold]{self.i18n.get('terminal_compat_title')}[/bold]",
                border_style="yellow",
            )
        )

        table = Table(show_header=False, box=None)
        table.add_row("[cyan]1.[/]", self.i18n.get("terminal_compat_opt_manual"))

        if term_info["is_windows_cmd"]:
            table.add_row(
                "[green]2.[/]",
                f"{self.i18n.get('terminal_compat_opt_auto')} [green]{self.i18n.get('terminal_compat_opt_auto_recommended')}[/green]",
            )
            if term_info.get("supports_default_terminal"):
                table.add_row("[cyan]3.[/]", self.i18n.get("terminal_compat_opt_auto_default"))
                table.add_row("[dim]4.[/]", self.i18n.get("terminal_compat_opt_skip"))
                choices = ["1", "2", "3", "4"]
            else:
                table.add_row("[dim]3.[/]", self.i18n.get("terminal_compat_opt_skip"))
                choices = ["1", "2", "3"]
            default = "2"
        else:
            table.add_row("[dim]2.[/]", self.i18n.get("terminal_compat_opt_skip"))
            choices = ["1", "2"]
            default = "2"

        console.print(table)

        choice = Prompt.ask(f"\n{self.i18n.get('prompt_select')}", choices=choices, default=default)

        if choice == "1":
            console.print(f"\n[cyan]{self.i18n.get('terminal_compat_manual_hint')}[/cyan]")
            console.print(f"[dim]{self.i18n.get('terminal_compat_manual_search')}[/dim]")
            console.print(f"[dim]{self.i18n.get('terminal_compat_manual_store')}[/dim]")
            console.print(f"[cyan]{self.i18n.get('terminal_compat_install_url')}[/cyan]")
            input(f"\n{self.i18n.get('terminal_compat_press_enter_exit')}")
            sys.exit(0)
        elif choice == "2" and term_info["is_windows_cmd"]:
            try:
                script_path = os.path.abspath(sys.argv[0])
                args = sys.argv[1:] if len(sys.argv) > 1 else []
                cmd = ["wt", "uv", "run", script_path] + args
                subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
                console.print(f"[green]{self.i18n.get('terminal_compat_auto_restarting')}[/green]")
                time.sleep(1)
                sys.exit(0)
            except FileNotFoundError:
                console.print(f"\n[red]{self.i18n.get('terminal_compat_wt_not_found')}[/red]")
                console.print(f"[dim]{self.i18n.get('terminal_compat_install_from_store')}[/dim]")
                console.print(f"[cyan]{self.i18n.get('terminal_compat_install_url')}[/cyan]")
                console.print(f"[yellow]{self.i18n.get('terminal_compat_continue_anyway')}[/yellow]")
                time.sleep(2)
        elif choice == "3" and term_info["is_windows_cmd"] and term_info.get("supports_default_terminal"):
            try:
                script_path = os.path.abspath(sys.argv[0])
                args = sys.argv[1:] if len(sys.argv) > 1 else []
                cmd = ["wt", "uv", "run", script_path] + args
                subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
                subprocess.Popen(
                    ["cmd", "/c", "start", "ms-settings:developers"],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                console.print(f"[green]{self.i18n.get('terminal_compat_auto_restarting')}[/green]")
                time.sleep(1)
                sys.exit(0)
            except FileNotFoundError:
                console.print(f"\n[red]{self.i18n.get('terminal_compat_wt_not_found')}[/red]")
                console.print(f"[dim]{self.i18n.get('terminal_compat_install_from_store')}[/dim]")
                console.print(f"[cyan]{self.i18n.get('terminal_compat_install_url')}[/cyan]")
                console.print(f"[yellow]{self.i18n.get('terminal_compat_continue_anyway')}[/yellow]")
                time.sleep(2)

        self.cli.root_config["terminal_check_skipped"] = True
        self.cli.save_config(save_root=True)
        return True
