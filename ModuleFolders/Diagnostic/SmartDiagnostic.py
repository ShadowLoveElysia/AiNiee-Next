"""
智能诊断模块 - DeepWiki 风格

分层诊断策略 (成本从低到高):
1. 规则匹配 - 0 token
2. FAQ缓存 - 0 token
3. 知识库检索 - 0 token
4. LLM分析 - 严格控制token (最后手段)
"""

import os
import sys
import traceback
from typing import Optional, Tuple
from dataclasses import dataclass, field

from ModuleFolders.Diagnostic.RuleMatcher import RuleMatcher, DiagnosticResult
from ModuleFolders.Diagnostic.KnowledgeBase import KnowledgeBase
from ModuleFolders.Diagnostic.i18n import get_text


@dataclass
class DiagnosticConfig:
    """诊断配置"""
    enable_llm: bool = True              # 是否启用LLM分析
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
        if self.config.enable_llm:
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
            from ModuleFolders.Infrastructure.LLMRequester.LLMRequester import LLMRequester
            from ModuleFolders.Base.Base import Base

            config = Base().load_config()
            if not config:
                return DiagnosticResult()

            platform_config = self._build_minimal_platform_config(config)
            if not platform_config:
                return DiagnosticResult()

            system_prompt = self._build_compact_system_prompt()
            user_content = self._build_compact_user_content(error_text, context)
            messages = [{"role": "user", "content": user_content}]

            requester = LLMRequester()
            skip, _, response, prompt_tokens, completion_tokens = requester.sent_request(
                messages, system_prompt, platform_config
            )

            if skip or not response:
                return DiagnosticResult()

            return self._parse_llm_response(response, prompt_tokens + completion_tokens)

        except Exception:
            return DiagnosticResult()

    def _build_minimal_platform_config(self, config: dict) -> Optional[dict]:
        """构建最小化的平台配置"""
        platform = config.get("translation_platform", "")
        if not platform:
            return None

        platform_config = config.get(platform, {})
        if not platform_config.get("api_key"):
            return None

        return {
            "target_platform": platform,
            "api_key": platform_config.get("api_key"),
            "base_url": platform_config.get("api_url", platform_config.get("base_url")),
            "model": platform_config.get("model"),
            "temperature": self.config.llm_temperature,
            "max_tokens": self.config.max_llm_tokens,
        }

    def _build_compact_system_prompt(self) -> str:
        """构建精简的system prompt"""
        return """你是AiNiee错误诊断助手。分析错误并简洁回复。
格式要求(严格遵守):
[类型] 环境问题/配置问题/代码Bug
[原因] 一句话说明
[方案] 2-3个步骤
[是否代码Bug] 是/否"""

    def _build_compact_user_content(self, error_text: str, context: dict) -> str:
        """构建精简的用户内容，控制token"""
        # 截断过长的错误信息
        max_error_len = 1500
        if len(error_text) > max_error_len:
            error_text = error_text[:max_error_len] + "\n...(已截断)"

        parts = [f"错误信息:\n{error_text}"]

        # 添加知识库上下文
        kb_context = self.knowledge_base.get_context_for_llm(error_text, max_items=1)
        if kb_context:
            parts.append(kb_context)

        # 添加环境信息
        env_info = f"环境: Python {sys.version.split()[0]}, OS: {sys.platform}"
        parts.append(env_info)

        return "\n\n".join(parts)

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
