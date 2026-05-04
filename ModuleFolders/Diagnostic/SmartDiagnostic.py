"""
智能诊断模块 - DeepWiki 风格

分层诊断策略 (成本从低到高):
1. 规则匹配 - 0 token
2. FAQ缓存 - 0 token
3. 知识库检索 - 0 token
4. LLM分析 - 严格控制token (最后手段)
"""

from dataclasses import dataclass

from ModuleFolders.Diagnostic.RuleMatcher import RuleMatcher, DiagnosticResult
from ModuleFolders.Diagnostic.KnowledgeBase import KnowledgeBase
from ModuleFolders.Diagnostic.LLMErrorAnalyzer import LLMErrorAnalyzer
from ModuleFolders.Diagnostic.i18n import get_text


@dataclass
class DiagnosticConfig:
    """诊断配置"""
    enable_llm: bool = False             # 是否启用自动LLM分析
    max_llm_tokens: int = 1000           # LLM最大输出token
    max_context_tokens: int = 2000       # 最大上下文token
    llm_temperature: float = 0.3         # LLM温度 (低温度更确定性)
    cache_llm_results: bool = True       # 是否缓存LLM结果


class SmartDiagnostic:
    """
    智能诊断器

    使用分层策略最小化API调用成本
    """

    def __init__(self, config: DiagnosticConfig = None, lang: str = "zh_CN"):
        self.config = config or DiagnosticConfig()
        self.lang = lang
        self.rule_matcher = RuleMatcher(lang=lang)
        self.knowledge_base = KnowledgeBase(lang=lang)

        # 统计信息
        self.stats = {
            "rule_hits": 0,
            "cache_hits": 0,
            "kb_hits": 0,
            "llm_calls": 0,
            "total_tokens": 0
        }

    def diagnose(self, error_text: str, context: dict = None) -> DiagnosticResult:
        """
        执行诊断

        Args:
            error_text: 错误信息/Traceback
            context: 额外上下文 (配置信息、环境信息等)

        Returns:
            DiagnosticResult: 诊断结果
        """
        context = context or {}

        # 第1层: 规则匹配 (0 token)
        result = self._try_rule_match(error_text)
        if result.is_matched:
            self.stats["rule_hits"] += 1
            return result

        # 第2层: FAQ缓存 (0 token)
        result = self._try_faq_cache(error_text)
        if result.is_matched:
            self.stats["cache_hits"] += 1
            return result

        # 第3层: 知识库检索 (0 token)
        result = self._try_knowledge_base(error_text)
        if result.is_matched and result.confidence >= 0.7:
            self.stats["kb_hits"] += 1
            return result

        # 第4层: LLM分析 (消耗token，最后手段)
        if self.config.enable_llm or context.get("allow_llm"):
            result = self._try_llm_analysis(error_text, context)
            if result.is_matched:
                self.stats["llm_calls"] += 1
                self.stats["total_tokens"] += result.token_cost
                # 缓存结果
                if self.config.cache_llm_results:
                    self._cache_result(error_text, result)
                return result

        # 无法诊断，返回默认结果
        return self._create_fallback_result(error_text)

    def _try_rule_match(self, error_text: str) -> DiagnosticResult:
        """尝试规则匹配"""
        return self.rule_matcher.match(error_text)

    def _try_faq_cache(self, error_text: str) -> DiagnosticResult:
        """尝试FAQ缓存匹配"""
        cached = self.knowledge_base.search_faq_cache(error_text)
        if cached:
            answer = cached.get("answer", {})
            return DiagnosticResult(
                is_matched=True,
                is_code_bug=answer.get("is_code_bug", False),
                error_type=answer.get("error_type", ""),
                root_cause=answer.get("root_cause", ""),
                solution=answer.get("solution", ""),
                confidence=0.9,
                matched_rule="faq_cache",
                token_cost=0
            )
        return DiagnosticResult()

    def _try_knowledge_base(self, error_text: str) -> DiagnosticResult:
        """尝试知识库检索"""
        results = self.knowledge_base.search_by_keywords(error_text, top_k=1)
        if results:
            item, score = results[0]
            if score >= 0.3:  # 最低相关度阈值
                return DiagnosticResult(
                    is_matched=True,
                    is_code_bug=False,
                    error_type=item.category,
                    root_cause=item.question,
                    solution=item.answer,
                    confidence=min(score, 0.85),
                    matched_rule=f"kb_{item.id}",
                    token_cost=0
                )
        return DiagnosticResult()

    def _try_llm_analysis(self, error_text: str, context: dict) -> DiagnosticResult:
        """
        LLM分析 (最后手段)
        严格控制token消耗
        """
        try:
            from ModuleFolders.Base.Base import Base

            base_config = context.get("config") if isinstance(context.get("config"), dict) else Base().load_config()
            analyzer = LLMErrorAnalyzer(lang=self.lang)
            kb_context = self.knowledge_base.get_context_for_llm(error_text, max_items=1)
            success, response, token_cost = analyzer.analyze(
                error_text,
                base_config,
                operation_log=context.get("operation_log", ""),
                requester=context.get("requester"),
                temperature=self.config.llm_temperature,
                max_tokens=self.config.max_llm_tokens,
                compact=True,
                knowledge_context=kb_context,
                extra_context=context,
            )

            if not success:
                return DiagnosticResult()

            return self._parse_llm_response(response, token_cost)

        except Exception:
            return DiagnosticResult()

    def _parse_llm_response(self, response: str, token_cost: int) -> DiagnosticResult:
        """解析LLM响应"""
        import re

        result = DiagnosticResult(
            is_matched=True,
            matched_rule="llm_analysis",
            token_cost=token_cost
        )

        # 解析类型
        type_match = re.search(r'\[类型\]\s*(.+)', response)
        if type_match:
            result.error_type = type_match.group(1).strip()

        # 解析原因
        cause_match = re.search(r'\[原因\]\s*(.+)', response)
        if cause_match:
            result.root_cause = cause_match.group(1).strip()

        # 解析方案
        solution_match = re.search(r'\[方案\]\s*([\s\S]+?)(?=\[是否|$)', response)
        if solution_match:
            result.solution = solution_match.group(1).strip()

        # 解析是否代码Bug
        bug_match = re.search(r'\[是否代码Bug\]\s*(是|否)', response)
        if bug_match:
            result.is_code_bug = bug_match.group(1) == "是"

        result.confidence = 0.75
        return result

    def _cache_result(self, error_text: str, result: DiagnosticResult):
        """缓存诊断结果"""
        self.knowledge_base.add_to_faq_cache(error_text, {
            "is_code_bug": result.is_code_bug,
            "error_type": result.error_type,
            "root_cause": result.root_cause,
            "solution": result.solution
        })

    def _create_fallback_result(self, error_text: str) -> DiagnosticResult:
        """创建回退结果"""
        return DiagnosticResult(
            is_matched=False,
            error_type=get_text("error_type_unknown", self.lang),
            root_cause=get_text("cause_unknown", self.lang),
            solution=get_text("solution_unknown", self.lang),
            self_check=[
                get_text("fallback_self_check_1", self.lang),
                get_text("fallback_self_check_2", self.lang),
                get_text("fallback_self_check_3", self.lang)
            ],
            confidence=0.0
        )

    def get_stats(self) -> dict:
        """获取统计信息"""
        return self.stats.copy()
