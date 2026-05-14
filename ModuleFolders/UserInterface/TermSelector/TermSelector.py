"""
术语多翻译选择器 - TUI交互界面
使用即时键盘响应
"""
import sys
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt
from ModuleFolders.Base.Base import Base

console = Console()


def getch():
    """跨平台读取单个按键"""
    if sys.platform == 'win32':
        import msvcrt
        ch = msvcrt.getch()
        if ch in (b'\x00', b'\xe0'):
            ch2 = msvcrt.getch()
            if ch2 == b'H':
                return 'up'
            elif ch2 == b'P':
                return 'down'
            return None
        return ch.decode('utf-8', errors='ignore').lower()
    else:
        import tty
        import termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == '\x1b':
                ch2 = sys.stdin.read(1)
                if ch2 == '[':
                    ch3 = sys.stdin.read(1)
                    if ch3 == 'A':
                        return 'up'
                    elif ch3 == 'B':
                        return 'down'
                return None
            return ch.lower()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


class TermSelector:
    """术语多翻译选择器"""

    def __init__(self, results: list, request_callback=None, save_callback=None):
        self.results = results
        self.current_row = 0
        self.request_callback = request_callback
        self.save_callback = save_callback  # 单条保存回调

    def show_selector(self) -> list:
        """显示选择界面，返回用户选择结果"""
        if not self.results:
            return []

        while True:
            console.clear()
            self._display_table()
            self._display_current_term()
            self._display_help()

            key = getch()
            if key is None:
                continue

            if key in ('w', 'up'):
                self._move_up()
            elif key in ('s', 'down'):
                self._move_down()
            elif key in ('1', '2', '3', '4', '5'):
                self._select_option(int(key) - 1)
            elif key == 'e':
                self._edit_translation()
            elif key == 'r':
                self._retry_current_term()
            elif key == 'o':
                self._save_current_term()
            elif key == 'f':
                return self._get_selected_results()
            elif key == 'q':
                return []

    def _display_table(self):
        """显示术语表格"""
        i18n = Base.i18n
        table = Table(title=i18n.get("term_selector_title"), show_header=True, header_style="bold cyan")
        table.add_column("#", width=4)
        table.add_column(i18n.get("label_term"), width=15)
        table.add_column(i18n.get("label_type"), width=10)
        table.add_column(i18n.get("label_info"), width=24)

        max_opts = max(len(r.get("options", [])) for r in self.results) if self.results else 3
        for i in range(max_opts):
            table.add_column(f"{i18n.get('option')} {i+1}", width=12)
        table.add_column(i18n.get("selected"), width=8)

        for idx, item in enumerate(self.results):
            is_current = idx == self.current_row
            is_saved = item.get("saved", False)
            prefix = ">" if is_current else " "

            # 已保存用绿色，当前行用黄底蓝字
            if is_current:
                style = "bold yellow on blue"
            elif is_saved:
                style = "green"
            else:
                style = None

            row = [
                f"{prefix}{idx+1}",
                item["src"],
                item.get("type", ""),
                str(item.get("analysis_info") or "null")[:24],
            ]
            options = item.get("options", [])
            selected_idx = item.get("selected_index", 0)

            for i in range(max_opts):
                if i < len(options):
                    opt = options[i]
                    dst = opt["dst"] if isinstance(opt, dict) else opt
                    row.append(dst[:10])
                else:
                    row.append("-")

            row.append(f"[{selected_idx + 1}]")
            table.add_row(*row, style=style)

        console.print(table)

    def _display_current_term(self):
        """显示当前术语详情"""
        i18n = Base.i18n
        item = self.results[self.current_row]
        options = item.get("options", [])
        selected_idx = item.get("selected_index", 0)

        text = Text()
        text.append(f"\n{i18n.get('current')}: ", style="cyan")
        text.append(f"#{self.current_row + 1} ", style="yellow")
        text.append(item["src"], style="white")
        if item.get("analysis_info"):
            text.append(f"\n{i18n.get('label_info')}: ", style="cyan")
            text.append(item.get("analysis_info", "null"), style="dim")

        if options and selected_idx < len(options):
            opt = options[selected_idx]
            dst = opt["dst"] if isinstance(opt, dict) else opt
            info = opt.get("info", "") if isinstance(opt, dict) else ""

            text.append(" -> ", style="dim")
            text.append(dst, style="green bold")
            if info:
                text.append(f" ({info})", style="dim")
        console.print(text)

    def _display_help(self):
        """显示操作提示"""
        i18n = Base.i18n
        help_text = (
            f"\n[bold cyan][1-5][/bold cyan]{i18n.get('select_option')} | "
            f"[bold cyan][w/s][/bold cyan]{i18n.get('switch_row')} | "
            f"[bold cyan][e][/bold cyan]{i18n.get('edit')} | "
            f"[bold cyan][r][/bold cyan]{i18n.get('retry')} | "
            f"[bold cyan][o][/bold cyan]{i18n.get('save_current')} | "
            f"[bold cyan][f][/bold cyan]{i18n.get('save_all')} | "
            f"[bold cyan][q][/bold cyan]{i18n.get('quit')}"
        )
        console.print(help_text)
        console.print(f"[bold yellow]{i18n.get('term_selector_hint')}[/bold yellow]")

    def _move_up(self):
        if self.current_row > 0:
            self.current_row -= 1

    def _move_down(self):
        if self.current_row < len(self.results) - 1:
            self.current_row += 1

    def _select_option(self, opt_idx: int):
        item = self.results[self.current_row]
        options = item.get("options", [])
        if opt_idx < len(options):
            item["selected_index"] = opt_idx

    def _edit_translation(self):
        """手动编辑翻译"""
        i18n = Base.i18n
        console.print(f"\n[cyan]{i18n.get('prompt_enter_content')}:[/cyan]")
        new_dst = Prompt.ask("")
        if new_dst:
            item = self.results[self.current_row]
            item["options"] = [{"dst": new_dst, "info": ""}]
            item["selected_index"] = 0

    def _retry_current_term(self):
        """调用LLM重新翻译当前术语，避开已有翻译"""
        i18n = Base.i18n
        if not self.request_callback:
            console.print(f"[red]{i18n.get('msg_no_callback')}[/red]")
            import time
            time.sleep(1)
            return

        item = self.results[self.current_row]
        options = item.get("options", [])

        # 收集所有已有翻译作为避开列表
        avoid_set = set()
        for opt in options:
            dst = opt["dst"] if isinstance(opt, dict) else opt
            if dst:
                avoid_set.add(dst)

        console.print(f"\n[cyan]{i18n.get('msg_retrying')} {item['src']}...[/cyan]")
        if avoid_set:
            console.print(f"[dim]{i18n.get('msg_avoiding')}: {', '.join(avoid_set)}[/dim]")

        # 调用回调获取新翻译，传入避开列表
        new_translation = self.request_callback(item["src"], item.get("type", ""), avoid_set)

        if new_translation:
            new_dst = new_translation.get("dst", "") if isinstance(new_translation, dict) else new_translation

            if new_dst and new_dst not in avoid_set:
                options.append(new_translation)
                item["options"] = options
                # 自动选中新添加的选项
                item["selected_index"] = len(options) - 1
                console.print(f"[green]{i18n.get('msg_new_option_added')}: {new_dst}[/green]")
            else:
                console.print(f"[yellow]{i18n.get('msg_duplicate_translation')}[/yellow]")
        else:
            console.print(f"[red]{i18n.get('msg_retry_failed')}[/red]")

        # 暂停让用户看到结果
        import time
        time.sleep(1)

    def _save_current_term(self):
        """保存当前选中的术语"""
        item = self.results[self.current_row]
        options = item.get("options", [])
        selected_idx = item.get("selected_index", 0)

        if options and selected_idx < len(options):
            opt = options[selected_idx]
            dst = opt["dst"] if isinstance(opt, dict) else opt
            info = opt.get("info", "") if isinstance(opt, dict) else ""

            term_data = {
                "src": item["src"],
                "dst": dst,
                "info": self._build_saved_info(item, info)
            }

            # 调用保存回调
            if self.save_callback:
                self.save_callback(term_data)

            # 标记为已保存
            item["saved"] = True

    def _get_selected_results(self) -> list:
        """获取用户选择的结果"""
        results = []
        for item in self.results:
            options = item.get("options", [])
            selected_idx = item.get("selected_index", 0)
            if options and selected_idx < len(options):
                opt = options[selected_idx]
                dst = opt["dst"] if isinstance(opt, dict) else opt
                info = opt.get("info", "") if isinstance(opt, dict) else ""
                results.append({
                    "src": item["src"],
                    "dst": dst,
                    "info": self._build_saved_info(item, info)
                })
        return results

    def _build_saved_info(self, item: dict, fallback: str = "") -> str:
        analysis_info = item.get("analysis_info")
        if analysis_info is not None and str(analysis_info).strip():
            term_type = item.get("type") or "专有名词"
            return f"{term_type} | {str(analysis_info).strip()}"
        return fallback
