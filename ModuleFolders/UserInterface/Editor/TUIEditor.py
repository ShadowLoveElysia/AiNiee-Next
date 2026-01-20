"""
AiNiee TUI Editor - 交互式校对编辑器
支持双栏对照、实时编辑、术语高亮等功能
"""
import os
import time
import threading
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich import box
from typing import Dict, List, Optional, Tuple

from ModuleFolders.UserInterface.InputListener import InputListener
from .EditorUI import EditorUI
from .EditorInput import EditorInput
from .GlossaryHighlighter import GlossaryHighlighter
from .EditorUtils import EditorUtils


class EditorMode:
    """编辑器模式枚举"""
    VIEW = "VIEW"
    EDIT = "EDIT"


class TUIEditor:
    """AiNiee TUI编辑器主类"""

    def __init__(self, cache_manager, config, i18n, glossary_data=None):
        self.cache_manager = cache_manager
        self.config = config
        self.i18n = i18n
        self.console = Console()

        # 编辑器状态
        self.mode = EditorMode.VIEW
        self.current_line = 0  # 当前选中的行
        self.page_size = config.get("editor_page_size", 15)  # 初始值，会在_setup_layout中动态调整
        self.current_page = 0

        # 数据相关
        self.cache_data = []  # 从cache加载的原文译文对
        self.total_items = 0
        self.total_pages = 0
        self.modified_items = set()  # 记录修改过的条目
        self.project_path = None  # 项目路径

        # UI组件
        self.ui = EditorUI(self.console)
        self.input_handler = EditorInput(self)
        self.glossary_highlighter = GlossaryHighlighter(glossary_data) if glossary_data else None
        self.utils = EditorUtils()

        # 输入监听器
        self.input_listener = InputListener()
        self.running = False
        self._setup_layout()

    def _setup_layout(self):
        """设置界面布局"""
        self.layout = Layout()

        # 获取终端尺寸并动态调整布局
        terminal_width, terminal_height = self._get_terminal_size()

        # 动态计算页面大小（减去header和footer占用的行数）
        reserved_lines = 8  # header(3) + footer(4) + 边框等(1)
        available_lines = max(terminal_height - reserved_lines, 10)

        # 更新页面大小配置
        if available_lines > 30:  # 大屏幕
            self.page_size = min(available_lines - 5, 50)
        elif available_lines > 20:  # 中等屏幕
            self.page_size = min(available_lines - 3, 30)
        else:  # 小屏幕
            self.page_size = max(available_lines - 2, 10)

        # 重新计算总页数
        if self.total_items > 0:
            self.total_pages = (self.total_items + self.page_size - 1) // self.page_size

        # 定义布局结构 - 给footer更多空间
        self.layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=4)  # 增加到4行，确保状态栏显示完整
        )

        # 将body分为左右两栏
        self.layout["body"].split_row(
            Layout(name="source_pane"),
            Layout(name="target_pane")
        )

    def load_cache_data(self, project_path: str) -> bool:
        """从缓存文件加载数据"""
        try:
            cache_file = os.path.join(project_path, "cache", "AinieeCacheData.json")
            if not os.path.exists(cache_file):
                self.console.print(f"[red]{self.i18n.get('editor_no_cache')}: {cache_file}[/red]")
                return False

            # 检查cache_manager是否已经有数据
            if hasattr(self.cache_manager, 'project') and self.cache_manager.project.files:
                # 缓存管理器已经有数据，直接使用
                self.console.print(f"[green]{self.i18n.get('editor_using_existing')}[/green]")
                file_count = len(self.cache_manager.project.files)
                self.console.print(f"[dim]{self.i18n.get('editor_found_files').format(file_count)}[/dim]")
            else:
                # 需要从文件加载缓存数据
                self.console.print(f"[yellow]{self.i18n.get('editor_loading_cache')}: {cache_file}[/yellow]")

                # 使用cache_manager的load_from_file方法
                self.cache_manager.load_from_file(project_path)

                if not hasattr(self.cache_manager, 'project') or not self.cache_manager.project.files:
                    self.console.print(f"[red]{self.i18n.get('editor_error_loading')}[/red]")
                    return False

                file_count = len(self.cache_manager.project.files)
                self.console.print(f"[green]{self.i18n.get('editor_loaded_cache').format(file_count)}[/green]")

            # 提取所有缓存项用于编辑器
            self.cache_data = self._extract_cache_items()

            # 过滤掉没有翻译内容的项目
            self.cache_data = [item for item in self.cache_data if item.get('translation', '').strip()]

            self.total_items = len(self.cache_data)

            if self.total_items == 0:
                self.console.print(f"[yellow]{self.i18n.get('editor_no_data')}[/yellow]")
                return False

            # 重新设置布局以动态调整页面大小
            self._setup_layout()

            self.console.print(f"[green]{self.i18n.get('editor_loaded_pairs').format(self.total_items)}[/green]")

            # 保存项目路径用于后续保存操作
            self.project_path = project_path
            return True

        except Exception as e:
            self.console.print(f"[red]Error loading cache data: {e}[/red]")
            import traceback
            self.console.print(f"[dim]Traceback: {traceback.format_exc()}[/dim]")
            return False

    def _extract_cache_items(self) -> List[Dict]:
        """从缓存管理器中提取数据项"""
        items = []

        try:
            # 获取所有缓存项
            with self.cache_manager.file_lock:
                for file_path, cache_file in self.cache_manager.project.files.items():
                    for idx, item in enumerate(cache_file.items):
                        # 确保有源文本
                        if item.source_text and item.source_text.strip():
                            # 获取翻译文本
                            translation = ""
                            if item.translated_text:
                                translation = item.translated_text
                            elif item.polished_text:
                                translation = item.polished_text

                            items.append({
                                'id': len(items),
                                'file_path': file_path,
                                'text_index': item.text_index,
                                'source': item.source_text,
                                'translation': translation,
                                'original_translation': translation,  # 用于撤销
                                'translation_status': item.translation_status,
                                'cache_item': item,  # 保留原始cache_item的引用
                                'modified': False
                            })
        except Exception as e:
            self.console.print(f"[red]Error extracting cache items: {e}[/red]")

        return items

    def _get_terminal_size(self) -> Tuple[int, int]:
        """获取终端尺寸"""
        try:
            import shutil
            size = shutil.get_terminal_size()
            return size.columns, size.lines
        except:
            return 80, 24  # 默认尺寸

    def start_editor(self, project_path: str):
        """启动编辑器主循环"""
        if not self.load_cache_data(project_path):
            return False

        self.running = True
        self.input_listener.start()

        try:
            with Live(self.layout, console=self.console, refresh_per_second=10) as live:
                self._update_display()

                while self.running:
                    key = self.input_listener.get_key()
                    if key:
                        self._handle_input(key)
                        self._update_display()

                    time.sleep(0.05)  # 减少CPU占用

        finally:
            self.input_listener.stop()

        return True

    def _handle_input(self, key: str):
        """处理输入事件"""
        if self.mode == EditorMode.VIEW:
            self._handle_view_mode_input(key)
        elif self.mode == EditorMode.EDIT:
            self._handle_edit_mode_input(key)

    def _handle_view_mode_input(self, key: str):
        """处理浏览模式输入"""
        if key == 'w':
            self._move_up()
        elif key == 's':
            self._move_down()
        elif key == 'a':
            self._prev_page()
        elif key == 'd':
            self._next_page()
        elif key == '\r' or key == '\n':  # Enter
            self._enter_edit_mode()
        elif key == 'q':
            self._quit_editor()

    def _handle_edit_mode_input(self, key: str):
        """处理编辑模式输入"""
        if key == '\x1b':  # Esc
            self._exit_edit_mode()
        elif key == 'r':  # 保存当前修改
            self._save_current_edit()
        elif key == 'left':  # 左箭头键
            self.input_handler._move_cursor_left()
        elif key == 'right':  # 右箭头键
            self.input_handler._move_cursor_right()
        elif key == 'up':  # 上箭头键 - 移动到上一行的相同位置
            self._move_cursor_up_in_text()
        elif key == 'down':  # 下箭头键 - 移动到下一行的相同位置
            self._move_cursor_down_in_text()
        elif key == 'home':  # Home键 - 移动到行首
            self.input_handler._move_cursor_home()
        elif key == 'end':  # End键 - 移动到行尾
            self.input_handler._move_cursor_end()
        elif key == 'del':  # Delete键
            self.input_handler._handle_delete()
        else:
            # 将字符添加到编辑缓冲区
            self.input_handler.handle_edit_input(key)

    def _move_up(self):
        """向上移动"""
        if self.current_line > 0:
            self.current_line -= 1
            # 如果移动到页面顶部，自动翻页
            if self.current_line < self.current_page * self.page_size:
                self._prev_page()

    def _move_down(self):
        """向下移动"""
        if self.current_line < self.total_items - 1:
            self.current_line += 1
            # 如果移动到页面底部，自动翻页
            if self.current_line >= (self.current_page + 1) * self.page_size:
                self._next_page()

    def _prev_page(self):
        """上一页"""
        if self.current_page > 0:
            self.current_page -= 1
            self.current_line = min(self.current_line, (self.current_page + 1) * self.page_size - 1)

    def _next_page(self):
        """下一页"""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.current_line = max(self.current_line, self.current_page * self.page_size)

    def _enter_edit_mode(self):
        """进入编辑模式"""
        if self.current_line < len(self.cache_data):
            self.mode = EditorMode.EDIT
            self.input_handler.start_editing(self.cache_data[self.current_line]['translation'])

    def _exit_edit_mode(self):
        """退出编辑模式"""
        self.mode = EditorMode.VIEW
        self.input_handler.stop_editing()

    def _save_current_edit(self):
        """保存当前编辑"""
        if self.mode == EditorMode.EDIT and self.current_line < len(self.cache_data):
            new_translation = self.input_handler.get_current_text()

            # 更新数据
            self.cache_data[self.current_line]['translation'] = new_translation
            self.cache_data[self.current_line]['modified'] = True
            self.modified_items.add(self.current_line)

            # 保存到缓存管理器
            self._save_to_cache()

            # 退出编辑模式
            self._exit_edit_mode()

    def _save_to_cache(self):
        """保存修改到缓存"""
        try:
            if self.current_line < len(self.cache_data):
                item_data = self.cache_data[self.current_line]
                cache_item = item_data.get('cache_item')

                if cache_item:
                    # 更新缓存项的翻译文本
                    new_translation = item_data['translation']

                    # 根据当前状态决定保存到哪个字段
                    if cache_item.translation_status == 2:  # POLISHED
                        cache_item.polished_text = new_translation
                    else:
                        cache_item.translated_text = new_translation
                        # 如果之前没有翻译，更新状态为已翻译
                        if cache_item.translation_status == 0:
                            cache_item.translation_status = 1

                    # 立即保存到文件系统
                    if hasattr(self, 'project_path'):
                        self.cache_manager.require_save_to_file(self.project_path)
                        self.console.print(f"[green]{self.i18n.get('editor_saved_line').format(self.current_line + 1)}[/green]")
                    else:
                        self.console.print(f"[yellow]{self.i18n.get('editor_saved_memory')}[/yellow]")

        except Exception as e:
            self.console.print(f"[red]Error saving to cache: {e}[/red]")
            import traceback
            self.console.print(f"[dim]Traceback: {traceback.format_exc()}[/dim]")

    def _save_all_changes(self):
        """保存所有待保存的修改到文件"""
        try:
            if hasattr(self, 'project_path') and self.modified_items:
                self.console.print(f"[yellow]{self.i18n.get('editor_saving_all')}[/yellow]")
                self.cache_manager.require_save_to_file(self.project_path)

                # 等待保存完成
                import time
                time.sleep(0.5)  # 给cache_manager时间处理保存请求

                self.console.print(f"[green]✓ {self.i18n.get('editor_all_saved')} ({len(self.modified_items)} modified items)[/green]")
                return True
            return False

        except Exception as e:
            self.console.print(f"[red]Error saving all changes: {e}[/red]")
            return False

    def _auto_save(self):
        """自动保存机制"""
        if hasattr(self, 'project_path') and self.modified_items:
            # 每5个修改项或每30秒自动保存一次
            if len(self.modified_items) >= 5:
                self._save_all_changes()

    def _goto_line(self):
        """跳转到指定行"""
        try:
            # 暂停当前显示，切换到输入模式
            self.console.print(f"\n[cyan]{self.i18n.get('editor_goto_prompt') or 'Go to line:'}[/cyan]")
            line_input = input(f"{self.i18n.get('editor_goto_line_number') or 'Line number'} (1-{self.total_items}): ").strip()

            if not line_input:
                return

            try:
                target_line = int(line_input) - 1  # 转换为0索引
                if 0 <= target_line < self.total_items:
                    self.current_line = target_line
                    # 计算应该在哪一页
                    self.current_page = target_line // self.page_size
                    self.console.print(f"[green]{self.i18n.get('editor_jumped_to_line') or 'Jumped to line'} {target_line + 1}[/green]")
                    import time
                    time.sleep(0.5)  # 短暂显示确认消息
                else:
                    self.console.print(f"[red]{self.i18n.get('editor_invalid_line_number') or 'Invalid line number'}[/red]")
                    import time
                    time.sleep(1)
            except ValueError:
                self.console.print(f"[red]{self.i18n.get('editor_invalid_input') or 'Invalid input'}[/red]")
                import time
                time.sleep(1)

        except KeyboardInterrupt:
            pass  # 用户取消输入

    def _search(self):
        """搜索功能"""
        try:
            # 暂停当前显示，切换到输入模式
            self.console.print(f"\n[cyan]{self.i18n.get('editor_search_prompt') or 'Search in text:'}[/cyan]")
            search_term = input(f"{self.i18n.get('editor_search_term') or 'Search term'}: ").strip()

            if not search_term:
                return

            # 从当前位置开始搜索
            found_indices = []
            search_term_lower = search_term.lower()

            for i, item in enumerate(self.cache_data):
                # 在原文和翻译中搜索
                source_text = item.get('source_text', '').lower()
                translation = item.get('translation', '').lower()

                if search_term_lower in source_text or search_term_lower in translation:
                    found_indices.append(i)

            if found_indices:
                # 找到下一个匹配项（从当前行之后开始）
                next_match = None
                for idx in found_indices:
                    if idx > self.current_line:
                        next_match = idx
                        break

                # 如果没有找到后续匹配项，使用第一个匹配项（循环搜索）
                if next_match is None:
                    next_match = found_indices[0]

                # 跳转到匹配项
                self.current_line = next_match
                self.current_page = next_match // self.page_size

                self.console.print(f"[green]{self.i18n.get('editor_found_at_line') or 'Found at line'} {next_match + 1} ({len(found_indices)} {self.i18n.get('editor_total_matches') or 'total matches'})[/green]")
                import time
                time.sleep(1)
            else:
                self.console.print(f"[yellow]{self.i18n.get('editor_not_found') or 'Not found'}[/yellow]")
                import time
                time.sleep(1)

        except KeyboardInterrupt:
            pass  # 用户取消输入

    def _move_cursor_up_in_text(self):
        """在多行文本中向上移动光标"""
        if not self.input_handler.editing:
            return

        text = self.input_handler.edit_buffer
        cursor_pos = self.input_handler.cursor_pos

        # 找到当前行的开始位置
        current_line_start = text.rfind('\n', 0, cursor_pos)
        if current_line_start == -1:
            current_line_start = 0
        else:
            current_line_start += 1

        # 计算在当前行中的位置
        pos_in_line = cursor_pos - current_line_start

        # 找到上一行的开始位置
        if current_line_start > 0:
            prev_line_end = current_line_start - 1  # '\n' 的位置
            prev_line_start = text.rfind('\n', 0, prev_line_end)
            if prev_line_start == -1:
                prev_line_start = 0
            else:
                prev_line_start += 1

            # 计算上一行的长度
            prev_line_length = prev_line_end - prev_line_start

            # 将光标移动到上一行的相应位置
            new_pos_in_line = min(pos_in_line, prev_line_length)
            self.input_handler.cursor_pos = prev_line_start + new_pos_in_line

    def _move_cursor_down_in_text(self):
        """在多行文本中向下移动光标"""
        if not self.input_handler.editing:
            return

        text = self.input_handler.edit_buffer
        cursor_pos = self.input_handler.cursor_pos

        # 找到当前行的开始位置和结束位置
        current_line_start = text.rfind('\n', 0, cursor_pos)
        if current_line_start == -1:
            current_line_start = 0
        else:
            current_line_start += 1

        # 计算在当前行中的位置
        pos_in_line = cursor_pos - current_line_start

        # 找到当前行的结束位置
        current_line_end = text.find('\n', cursor_pos)
        if current_line_end == -1:
            # 当前已经在最后一行
            return

        # 找到下一行的开始位置
        next_line_start = current_line_end + 1
        if next_line_start >= len(text):
            # 没有下一行
            return

        # 找到下一行的结束位置
        next_line_end = text.find('\n', next_line_start)
        if next_line_end == -1:
            next_line_end = len(text)

        # 计算下一行的长度
        next_line_length = next_line_end - next_line_start

        # 将光标移动到下一行的相应位置
        new_pos_in_line = min(pos_in_line, next_line_length)
        self.input_handler.cursor_pos = next_line_start + new_pos_in_line

    def _quit_editor(self):
        """退出编辑器"""
        # 如果有未保存的修改，询问用户是否保存
        if self.modified_items:
            # 在TUI环境下，我们自动保存所有更改
            self.console.print(f"\n[yellow]{self.i18n.get('editor_auto_saving').format(len(self.modified_items))}[/yellow]")
            if self._save_all_changes():
                self.console.print(f"[green]{self.i18n.get('editor_all_saved')}[/green]")
            else:
                self.console.print(f"[red]{self.i18n.get('editor_save_warning')}[/red]")

            import time
            time.sleep(1)  # 给用户时间看到保存消息

        self.running = False

    def _update_display(self):
        """更新显示内容"""
        # 更新header
        self._update_header()

        # 更新body
        self._update_body()

        # 更新footer
        self._update_footer()

    def _update_header(self):
        """更新顶部信息"""
        project_name = getattr(self.cache_manager, 'project', 'Unknown Project')
        page_info = f"Block {self.current_line + 1}/{self.total_items} | Page {self.current_page + 1}/{self.total_pages}"
        mode_info = f"[{self.mode} MODE]"

        if self.modified_items:
            mode_info += f" ({len(self.modified_items)} modified)"

        header_text = f"📝 {project_name} | {page_info} | {mode_info}"
        self.layout["header"].update(Panel(header_text, box=box.ROUNDED))

    def _update_body(self):
        """更新主体内容"""
        self.ui.render_dual_pane(
            self.layout,
            self._get_current_page_data(),
            self.current_line % self.page_size,
            self.glossary_highlighter,
            editor=self  # 传递编辑器实例以支持编辑模式渲染
        )

    def _update_footer(self):
        """更新底部操作提示"""
        # 快捷键提示
        if self.mode == EditorMode.VIEW:
            shortcuts = self.i18n.get('editor_shortcuts_view')
        else:
            shortcuts = self.i18n.get('editor_shortcuts_edit')

        # 位置信息
        current_overall_line = self.current_line + 1
        position_info = f"{self.i18n.get('editor_footer_line')} {current_overall_line}/{self.total_items}"

        # 页面信息
        page_info = f"{self.i18n.get('editor_footer_page')} {self.current_page + 1}/{self.total_pages}"

        # 页面大小设置
        page_size_info = f"{self.i18n.get('editor_page_size')}: {self.page_size}"

        # 修改计数
        modified_info = ""
        if self.modified_items:
            modified_info = f" | {self.i18n.get('editor_footer_modified')}: {len(self.modified_items)}"

        # 组合底部信息
        footer_text = f"{shortcuts}\n{position_info} | {page_info} | {page_size_info}{modified_info}"

        self.layout["footer"].update(Panel(footer_text, box=box.ROUNDED))

    def _get_current_page_data(self) -> List[Dict]:
        """获取当前页面的数据"""
        start_idx = self.current_page * self.page_size
        end_idx = min(start_idx + self.page_size, self.total_items)
        return self.cache_data[start_idx:end_idx]

    def get_statistics(self) -> Dict:
        """获取编辑器统计信息"""
        return {
            'total_items': self.total_items,
            'modified_items': len(self.modified_items),
            'current_line': self.current_line,
            'current_page': self.current_page,
            'total_pages': self.total_pages
        }