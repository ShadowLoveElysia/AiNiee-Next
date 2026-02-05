"""
诊断结果格式化输出
"""

from ModuleFolders.Diagnostic.RuleMatcher import DiagnosticResult
from ModuleFolders.Diagnostic.i18n import get_text


class DiagnosticFormatter:
    """诊断结果格式化器"""

    @staticmethod
    def format_result(result: DiagnosticResult, lang: str = "zh_CN") -> str:
        """格式化诊断结果为用户友好的文本"""
        if not result.is_matched:
            return get_text("label_unknown_error", lang)

        lines = []

        # 错误类型
        lines.append(f"{get_text('label_error_type', lang)}: {result.error_type}")

        # 根本原因
        lines.append(f"\n{get_text('label_root_cause', lang)}:")
        lines.append(f"  {result.root_cause}")

        # 解决方案
        lines.append(f"\n{get_text('label_solution', lang)}:")
        for line in result.solution.split('\n'):
            lines.append(f"  {line}")

        # 是否代码Bug
        if result.is_code_bug:
            lines.append(f"\n{get_text('label_code_bug_hint', lang)}")

        # 自查清单
        if result.self_check:
            lines.append(f"\n{get_text('label_self_check', lang)}:")
            for i, item in enumerate(result.self_check, 1):
                lines.append(f"  {i}. {item}")

        # 诊断来源和成本
        lines.append(f"\n---")
        lines.append(f"{get_text('label_diagnosis_source', lang)}: {result.matched_rule} | {get_text('label_token_cost', lang)}: {result.token_cost}")

        return '\n'.join(lines)
