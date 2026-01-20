"""
TUI Editor UI渲染模块
负责双栏布局渲染、文本高亮等UI相关功能
"""
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich import box
from typing import List, Dict, Optional


class EditorUI:
    """编辑器UI渲染类"""

    def __init__(self, console: Console):
        self.console = console

    def render_dual_pane(self, layout, page_data: List[Dict], current_line_index: int, glossary_highlighter=None, editor=None):
        """渲染双栏显示"""
        source_content = self._render_source_pane(page_data, current_line_index, glossary_highlighter)
        target_content = self._render_target_pane(page_data, current_line_index, glossary_highlighter, editor)

        # 根据编辑器模式设置边框颜色
        target_border_color = "green"
        if editor and hasattr(editor, 'mode'):
            target_border_color = "red" if editor.mode == "EDIT" else "green"

        # 更新左右面板
        layout["source_pane"].update(Panel(
            source_content,
            title="[bold magenta]Source Text[/bold magenta]",
            border_style="magenta",
            box=box.ROUNDED
        ))

        layout["target_pane"].update(Panel(
            target_content,
            title="[bold green]Translation[/bold green]",
            border_style=target_border_color,
            box=box.ROUNDED
        ))

    def _render_source_pane(self, page_data: List[Dict], current_line_index: int, glossary_highlighter=None) -> Text:
        """渲染源文本面板"""
        content = Text()

        for i, item in enumerate(page_data):
            line_number = i + 1
            source_text = item.get('source', '')

            # 创建行内容
            line_content = Text()

            # 添加行号
            if i == current_line_index:
                line_content.append(f"{line_number:3d}► ", style="bold cyan")
            else:
                line_content.append(f"{line_number:3d}  ", style="dim")

            # 处理源文本
            if glossary_highlighter:
                highlighted_text = glossary_highlighter.highlight_source(source_text)
                line_content.append(highlighted_text)
            else:
                line_content.append(source_text)

            # 高亮当前行
            if i == current_line_index:
                line_content.stylize("on blue")

            content.append(line_content)
            content.append("\n")

        return content

    def _render_target_pane(self, page_data: List[Dict], current_line_index: int, glossary_highlighter=None, editor=None) -> Text:
        """渲染译文面板"""
        content = Text()

        for i, item in enumerate(page_data):
            line_number = i + 1
            translation_text = item.get('translation', '')
            is_modified = item.get('modified', False)

            # 创建行内容
            line_content = Text()

            # 添加行号和修改标记
            if i == current_line_index:
                marker = "►"
                if is_modified:
                    line_content.append(f"{line_number:3d}*{marker} ", style="bold yellow")
                else:
                    line_content.append(f"{line_number:3d} {marker} ", style="bold cyan")
            else:
                if is_modified:
                    line_content.append(f"{line_number:3d}* ", style="yellow")
                else:
                    line_content.append(f"{line_number:3d}  ", style="dim")

            # 处理译文和编辑模式的光标
            if i == current_line_index and editor and hasattr(editor, 'mode') and editor.mode == "EDIT":
                # 编辑模式：显示带光标的文本
                if hasattr(editor, 'input_handler') and editor.input_handler.editing:
                    edit_text, cursor_pos = editor.input_handler.get_display_text()
                    cursor_content = self.render_edit_cursor(edit_text, cursor_pos)
                    line_content.append(cursor_content)
                else:
                    # 退回到普通显示
                    if glossary_highlighter:
                        highlighted_text = glossary_highlighter.highlight_translation(translation_text)
                        line_content.append(highlighted_text)
                    else:
                        line_content.append(translation_text)
            else:
                # 普通模式：正常显示译文
                if glossary_highlighter:
                    highlighted_text = glossary_highlighter.highlight_translation(translation_text)
                    line_content.append(highlighted_text)
                else:
                    line_content.append(translation_text)

            # 高亮当前行
            if i == current_line_index:
                if editor and hasattr(editor, 'mode') and editor.mode == "EDIT":
                    line_content.stylize("on red")  # 编辑模式用红色背景
                else:
                    line_content.stylize("on blue")  # 浏览模式用蓝色背景

            content.append(line_content)
            content.append("\n")

        return content

    def render_edit_cursor(self, text: str, cursor_pos: int) -> Text:
        """在编辑模式下渲染带光标的文本"""
        content = Text()

        if cursor_pos > len(text):
            cursor_pos = len(text)

        # 添加光标前的文本
        if cursor_pos > 0:
            content.append(text[:cursor_pos])

        # 添加光标
        if cursor_pos < len(text):
            content.append(text[cursor_pos], style="reverse")
            content.append(text[cursor_pos + 1:])
        else:
            content.append(" ", style="reverse")  # 在末尾显示空格光标

        return content

    def render_search_results(self, results: List[Dict], current_result: int) -> Text:
        """渲染搜索结果"""
        content = Text()
        content.append(f"Search Results ({len(results)} found):\n", style="bold yellow")

        for i, result in enumerate(results[:10]):  # 只显示前10个结果
            line_num = result.get('line', 0)
            text = result.get('text', '')[:50]  # 截断长文本

            if i == current_result:
                content.append(f"► {line_num}: {text}...\n", style="bold cyan")
            else:
                content.append(f"  {line_num}: {text}...\n", style="dim")

        if len(results) > 10:
            content.append(f"... and {len(results) - 10} more results\n", style="dim")

        return content

    def render_glossary_tooltip(self, terms: List[Dict]) -> Text:
        """渲染术语提示面板"""
        content = Text()
        content.append("Glossary Terms:\n", style="bold yellow")

        for term in terms:
            src = term.get('src', '')
            dst = term.get('dst', '')
            info = term.get('info', '')

            content.append(f"• {src} → {dst}", style="cyan")
            if info:
                content.append(f" ({info})", style="dim")
            content.append("\n")

        return content

    def render_status_message(self, message: str, message_type: str = "info") -> Text:
        """渲染状态消息"""
        color_map = {
            "info": "blue",
            "success": "green",
            "warning": "yellow",
            "error": "red"
        }

        color = color_map.get(message_type, "white")
        return Text(message, style=color)

    def render_confirmation_dialog(self, message: str, options: List[str]) -> Text:
        """渲染确认对话框"""
        content = Text()
        content.append(f"{message}\n\n", style="bold")

        for i, option in enumerate(options):
            content.append(f"[{i + 1}] {option}\n", style="cyan")

        return content

    def create_table_view(self, data: List[Dict], headers: List[str], current_row: int = -1) -> Table:
        """创建表格视图"""
        table = Table(show_header=True, header_style="bold magenta")

        # 添加列
        for header in headers:
            table.add_column(header)

        # 添加行
        for i, row_data in enumerate(data):
            row_values = []
            for header in headers:
                value = str(row_data.get(header.lower(), ''))
                if len(value) > 50:
                    value = value[:47] + "..."
                row_values.append(value)

            # 高亮当前行
            if i == current_row:
                row_values = [f"[bold cyan]{val}[/bold cyan]" for val in row_values]

            table.add_row(*row_values)

        return table