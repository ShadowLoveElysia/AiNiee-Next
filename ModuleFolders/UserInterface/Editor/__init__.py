"""
AiNiee TUI Editor Module
交互式校对编辑器模块

主要组件:
- TUIEditor: 主编辑器类
- EditorUI: UI渲染模块
- EditorInput: 输入处理模块
- GlossaryHighlighter: 术语高亮模块
- EditorUtils: 工具函数模块
"""

from .TUIEditor import TUIEditor, EditorMode
from .EditorUI import EditorUI
from .EditorInput import EditorInput
from .GlossaryHighlighter import GlossaryHighlighter
from .EditorUtils import EditorUtils

__all__ = [
    'TUIEditor',
    'EditorMode',
    'EditorUI',
    'EditorInput',
    'GlossaryHighlighter',
    'EditorUtils'
]

__version__ = "1.0.0"
__author__ = "ShadowLoveElysia"