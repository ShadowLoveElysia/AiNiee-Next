"""
TUI Editor工具函数模块
包含各种辅助功能和工具方法
"""
import os
import time
import json
from typing import Dict, List, Optional, Tuple, Any


class EditorUtils:
    """编辑器工具类"""

    @staticmethod
    def calculate_text_metrics(text: str) -> Dict:
        """计算文本指标"""
        if not text:
            return {
                'chars': 0,
                'chars_no_space': 0,
                'words': 0,
                'lines': 0,
                'paragraphs': 0
            }

        lines = text.split('\n')
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        words = text.split()

        return {
            'chars': len(text),
            'chars_no_space': len(text.replace(' ', '')),
            'words': len(words),
            'lines': len(lines),
            'paragraphs': len(paragraphs)
        }

    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """格式化文件大小显示"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    @staticmethod
    def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
        """截断文本并添加省略号"""
        if len(text) <= max_length:
            return text
        return text[:max_length - len(suffix)] + suffix

    @staticmethod
    def find_text_differences(original: str, modified: str) -> List[Dict]:
        """查找两个文本之间的差异"""
        differences = []

        # 简单的行级差异比较
        original_lines = original.split('\n')
        modified_lines = modified.split('\n')

        max_lines = max(len(original_lines), len(modified_lines))

        for i in range(max_lines):
            original_line = original_lines[i] if i < len(original_lines) else ""
            modified_line = modified_lines[i] if i < len(modified_lines) else ""

            if original_line != modified_line:
                differences.append({
                    'line_number': i + 1,
                    'type': 'modified' if original_line and modified_line else
                            'added' if not original_line else 'deleted',
                    'original': original_line,
                    'modified': modified_line
                })

        return differences

    @staticmethod
    def search_text(text: str, query: str, case_sensitive: bool = False) -> List[Dict]:
        """在文本中搜索指定内容"""
        if not query:
            return []

        search_text = text if case_sensitive else text.lower()
        search_query = query if case_sensitive else query.lower()

        results = []
        lines = text.split('\n')

        for line_num, line in enumerate(lines):
            search_line = line if case_sensitive else line.lower()
            start = 0

            while True:
                pos = search_line.find(search_query, start)
                if pos == -1:
                    break

                results.append({
                    'line': line_num + 1,
                    'column': pos + 1,
                    'text': line,
                    'match_start': pos,
                    'match_end': pos + len(query),
                    'context': EditorUtils.get_text_context(lines, line_num, pos, len(query))
                })

                start = pos + 1

        return results

    @staticmethod
    def get_text_context(lines: List[str], line_num: int, pos: int, match_length: int, context_size: int = 2) -> Dict:
        """获取匹配文本的上下文"""
        context = {
            'before_lines': [],
            'current_line': lines[line_num] if line_num < len(lines) else "",
            'after_lines': [],
            'match_highlight': (pos, pos + match_length)
        }

        # 获取前面的行
        for i in range(max(0, line_num - context_size), line_num):
            context['before_lines'].append(lines[i])

        # 获取后面的行
        for i in range(line_num + 1, min(len(lines), line_num + context_size + 1)):
            context['after_lines'].append(lines[i])

        return context

    @staticmethod
    def create_backup_filename(original_path: str) -> str:
        """创建备份文件名"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        base_path, ext = os.path.splitext(original_path)
        return f"{base_path}_backup_{timestamp}{ext}"

    @staticmethod
    def validate_json_data(data: Any) -> Tuple[bool, str]:
        """验证JSON数据的有效性"""
        try:
            if isinstance(data, str):
                json.loads(data)
            else:
                json.dumps(data)
            return True, "Valid JSON"
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON: {e}"
        except Exception as e:
            return False, f"Error: {e}"

    @staticmethod
    def split_text_by_sentences(text: str) -> List[str]:
        """按句子分割文本"""
        import re
        # 简单的句子分割规则
        sentence_endings = r'[.!?。！？]'
        sentences = re.split(sentence_endings, text)

        # 清理并过滤空句子
        clean_sentences = []
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence:
                clean_sentences.append(sentence)

        return clean_sentences

    @staticmethod
    def calculate_edit_distance(str1: str, str2: str) -> int:
        """计算两个字符串的编辑距离"""
        if not str1:
            return len(str2)
        if not str2:
            return len(str1)

        # 动态规划计算Levenshtein距离
        m, n = len(str1), len(str2)
        dp = [[0] * (n + 1) for _ in range(m + 1)]

        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j

        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if str1[i - 1] == str2[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1]
                else:
                    dp[i][j] = min(
                        dp[i - 1][j] + 1,    # 删除
                        dp[i][j - 1] + 1,    # 插入
                        dp[i - 1][j - 1] + 1 # 替换
                    )

        return dp[m][n]

    @staticmethod
    def extract_numbers_from_text(text: str) -> List[Dict]:
        """从文本中提取数字"""
        import re
        number_pattern = r'-?\d+(?:\.\d+)?'
        matches = []

        for match in re.finditer(number_pattern, text):
            try:
                value = float(match.group()) if '.' in match.group() else int(match.group())
                matches.append({
                    'value': value,
                    'start': match.start(),
                    'end': match.end(),
                    'text': match.group()
                })
            except ValueError:
                continue

        return matches

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """清理文件名，移除不合法字符"""
        import re
        # 移除Windows文件名中的非法字符
        illegal_chars = r'[<>:"/\\|?*]'
        sanitized = re.sub(illegal_chars, '_', filename)

        # 移除开头和结尾的空格和点
        sanitized = sanitized.strip(' .')

        # 确保不是Windows保留名称
        reserved_names = [
            'CON', 'PRN', 'AUX', 'NUL',
            'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
            'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
        ]

        if sanitized.upper() in reserved_names:
            sanitized = f"_{sanitized}"

        return sanitized

    @staticmethod
    def format_duration(seconds: float) -> str:
        """格式化时间持续时长"""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            remaining_seconds = int(seconds % 60)
            return f"{minutes}m {remaining_seconds}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"

    @staticmethod
    def get_terminal_size() -> Tuple[int, int]:
        """获取终端尺寸"""
        try:
            import shutil
            size = shutil.get_terminal_size()
            return size.columns, size.lines
        except:
            return 80, 24  # 默认尺寸

    @staticmethod
    def wrap_text(text: str, width: int) -> List[str]:
        """文本换行处理"""
        if not text:
            return [""]

        import textwrap
        wrapped_lines = []

        for line in text.split('\n'):
            if len(line) <= width:
                wrapped_lines.append(line)
            else:
                wrapped_lines.extend(textwrap.wrap(line, width=width))

        return wrapped_lines

    @staticmethod
    def is_chinese_text(text: str) -> bool:
        """检查文本是否包含中文字符"""
        import re
        chinese_pattern = r'[\u4e00-\u9fff]'
        return bool(re.search(chinese_pattern, text))

    @staticmethod
    def count_asian_characters(text: str) -> int:
        """计算亚洲字符数量"""
        import re
        # 包括中文、日文、韩文字符
        asian_pattern = r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]'
        return len(re.findall(asian_pattern, text))