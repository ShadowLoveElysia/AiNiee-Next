"""
AiNiee 智能诊断模块 (DeepWiki 风格)

分层诊断策略:
1. 规则匹配 (零成本) - 匹配已知错误模式
2. FAQ缓存 (零成本) - 查找历史相似问题
3. 知识库检索 (低成本) - 本地向量检索
4. LLM分析 (高成本) - 最后手段，严格控制token
"""

from ModuleFolders.Diagnostic.SmartDiagnostic import SmartDiagnostic, DiagnosticConfig
from ModuleFolders.Diagnostic.RuleMatcher import RuleMatcher, DiagnosticResult
from ModuleFolders.Diagnostic.KnowledgeBase import KnowledgeBase
from ModuleFolders.Diagnostic.DiagnosticFormatter import DiagnosticFormatter

__all__ = [
    'SmartDiagnostic',
    'DiagnosticConfig',
    'RuleMatcher',
    'DiagnosticResult',
    'KnowledgeBase',
    'DiagnosticFormatter'
]
