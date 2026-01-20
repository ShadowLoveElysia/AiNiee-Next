"""
TUI Editor输入处理模块
负责编辑模式下的文本输入、光标控制等功能
"""
from typing import Optional


class EditorInput:
    """编辑器输入处理类"""

    def __init__(self, editor):
        self.editor = editor
        self.editing = False
        self.edit_buffer = ""
        self.cursor_pos = 0
        self.original_text = ""

    def start_editing(self, initial_text: str):
        """开始编辑模式"""
        self.editing = True
        self.edit_buffer = initial_text or ""
        self.cursor_pos = len(self.edit_buffer)  # 光标放在末尾
        self.original_text = initial_text or ""

    def stop_editing(self):
        """停止编辑模式"""
        self.editing = False
        self.edit_buffer = ""
        self.cursor_pos = 0
        self.original_text = ""

    def handle_edit_input(self, key: str):
        """处理编辑模式的输入"""
        if not self.editing:
            return

        # 特殊键处理
        if key == '\b' or ord(key) == 127:  # Backspace
            self._handle_backspace()
        elif key == '\x7f':  # Delete
            self._handle_delete()
        elif key == '\x01':  # Ctrl+A (Home)
            self._move_cursor_home()
        elif key == '\x05':  # Ctrl+E (End)
            self._move_cursor_end()
        elif key == '\x02':  # Ctrl+B (Left)
            self._move_cursor_left()
        elif key == '\x06':  # Ctrl+F (Right)
            self._move_cursor_right()
        elif key == '\x0e':  # Ctrl+N (Down) - 可以扩展为换行
            self._insert_newline()
        elif key == '\x15':  # Ctrl+U (清空行)
            self._clear_line()
        elif key == '\x17':  # Ctrl+W (删除单词)
            self._delete_word()
        elif key == '\t':  # Tab键处理
            self._handle_tab()
        elif key in ['\r', '\n']:  # Enter键在编辑模式下插入换行
            self._insert_newline()
        elif len(key) == 1 and ord(key) >= 32:  # 可打印字符
            self._insert_char(key)

    def _insert_char(self, char: str):
        """插入字符"""
        self.edit_buffer = (
            self.edit_buffer[:self.cursor_pos] +
            char +
            self.edit_buffer[self.cursor_pos:]
        )
        self.cursor_pos += 1

    def _handle_backspace(self):
        """处理退格键"""
        if self.cursor_pos > 0:
            self.edit_buffer = (
                self.edit_buffer[:self.cursor_pos - 1] +
                self.edit_buffer[self.cursor_pos:]
            )
            self.cursor_pos -= 1

    def _handle_delete(self):
        """处理删除键"""
        if self.cursor_pos < len(self.edit_buffer):
            self.edit_buffer = (
                self.edit_buffer[:self.cursor_pos] +
                self.edit_buffer[self.cursor_pos + 1:]
            )

    def _move_cursor_left(self):
        """光标左移"""
        if self.cursor_pos > 0:
            self.cursor_pos -= 1

    def _move_cursor_right(self):
        """光标右移"""
        if self.cursor_pos < len(self.edit_buffer):
            self.cursor_pos += 1

    def _move_cursor_home(self):
        """光标移至行首"""
        # 找到当前行的开始位置
        current_line_start = self.edit_buffer.rfind('\n', 0, self.cursor_pos)
        if current_line_start == -1:
            self.cursor_pos = 0
        else:
            self.cursor_pos = current_line_start + 1

    def _move_cursor_end(self):
        """光标移至行尾"""
        # 找到当前行的结束位置
        current_line_end = self.edit_buffer.find('\n', self.cursor_pos)
        if current_line_end == -1:
            self.cursor_pos = len(self.edit_buffer)
        else:
            self.cursor_pos = current_line_end

    def _insert_newline(self):
        """插入换行"""
        self._insert_char('\n')

    def _clear_line(self):
        """清空当前行"""
        # 找到当前行的范围
        line_start = self.edit_buffer.rfind('\n', 0, self.cursor_pos)
        if line_start == -1:
            line_start = 0
        else:
            line_start += 1

        line_end = self.edit_buffer.find('\n', self.cursor_pos)
        if line_end == -1:
            line_end = len(self.edit_buffer)

        # 删除当前行内容
        self.edit_buffer = (
            self.edit_buffer[:line_start] +
            self.edit_buffer[line_end:]
        )
        self.cursor_pos = line_start

    def _delete_word(self):
        """删除光标前的单词"""
        if self.cursor_pos == 0:
            return

        # 找到单词边界
        word_start = self.cursor_pos - 1
        while word_start > 0 and self.edit_buffer[word_start].isalnum():
            word_start -= 1

        if not self.edit_buffer[word_start].isalnum():
            word_start += 1

        # 删除单词
        self.edit_buffer = (
            self.edit_buffer[:word_start] +
            self.edit_buffer[self.cursor_pos:]
        )
        self.cursor_pos = word_start

    def _handle_tab(self):
        """处理Tab键 - 可扩展为术语自动补全"""
        # 基本实现：插入4个空格
        self._insert_char('    ')

        # TODO: 实现术语自动补全逻辑
        # if self.editor.glossary_highlighter:
        #     suggestions = self._get_term_suggestions()
        #     if suggestions:
        #         # 显示补全菜单
        #         pass

    def _get_term_suggestions(self) -> list:
        """获取术语建议"""
        if not self.editor.glossary_highlighter:
            return []

        # 获取光标前的文本作为前缀
        prefix_start = max(0, self.cursor_pos - 20)
        prefix = self.edit_buffer[prefix_start:self.cursor_pos]

        # 在术语表中查找匹配项
        suggestions = []
        # TODO: 实现术语匹配逻辑

        return suggestions

    def get_current_text(self) -> str:
        """获取当前编辑的文本"""
        return self.edit_buffer

    def get_cursor_position(self) -> int:
        """获取光标位置"""
        return self.cursor_pos

    def set_text(self, text: str):
        """设置编辑文本"""
        self.edit_buffer = text
        self.cursor_pos = len(text)

    def reset_to_original(self):
        """重置为原始文本"""
        self.edit_buffer = self.original_text
        self.cursor_pos = len(self.edit_buffer)

    def has_changes(self) -> bool:
        """检查是否有修改"""
        return self.edit_buffer != self.original_text

    def get_display_text(self) -> tuple:
        """获取用于显示的文本和光标位置"""
        return self.edit_buffer, self.cursor_pos

    def insert_text_at_cursor(self, text: str):
        """在光标位置插入文本"""
        self.edit_buffer = (
            self.edit_buffer[:self.cursor_pos] +
            text +
            self.edit_buffer[self.cursor_pos:]
        )
        self.cursor_pos += len(text)

    def get_current_line(self) -> str:
        """获取光标所在的当前行"""
        # 找到当前行的范围
        line_start = self.edit_buffer.rfind('\n', 0, self.cursor_pos)
        if line_start == -1:
            line_start = 0
        else:
            line_start += 1

        line_end = self.edit_buffer.find('\n', self.cursor_pos)
        if line_end == -1:
            line_end = len(self.edit_buffer)

        return self.edit_buffer[line_start:line_end]

    def get_cursor_line_position(self) -> tuple:
        """获取光标在当前行中的位置"""
        line_start = self.edit_buffer.rfind('\n', 0, self.cursor_pos)
        if line_start == -1:
            line_start = 0
        else:
            line_start += 1

        line_pos = self.cursor_pos - line_start
        return line_pos, self.get_current_line()