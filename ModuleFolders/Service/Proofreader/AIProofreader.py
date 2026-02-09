"""
AI校对器 - 调用LLM进行翻译校对
"""

import json
import os
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class AICheckIssue:
    """AI检查发现的问题"""
    type: str  # terminology|omission|hallucination|logic_error
    severity: str  # high|medium|low
    location: str
    description: str
    suggestion: str = ""
    confidence: float = 0.0


@dataclass
class AICheckResult:
    """AI检查结果"""
    has_issues: bool
    issues: List[AICheckIssue] = field(default_factory=list)
    corrected_translation: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0


class AIProofreader:
    """AI校对器"""

    def __init__(self, config: dict):
        self.config = config
        self.prompt_template = self._load_prompt()
        self.confidence_threshold = config.get("proofread_confidence_threshold", 0.7)

    def _load_prompt(self) -> str:
        """加载校对提示词，根据用户配置自动选择语言"""
        # Mapping from language code to prompt suffix
        lang_map = {
            "zh": "zh", "zh_cn": "zh", "zh_tw": "zh", "chinese": "zh", "chs": "zh", "cht": "zh",
            "en": "en", "english": "en", "us": "en",
            "ja": "ja", "jp": "ja", "japanese": "ja", "jpn": "ja"
        }

        # Try to determine target language from config
        target_lang = self.config.get("target_language", "")
        # Fallback to interface language
        interface_lang = self.config.get("interface_language", "zh")
        
        # Determine the key to use for lookup
        lang_key = target_lang.lower().replace("-", "_") if target_lang else interface_lang.lower()
        
        # Get the suffix, defaulting to 'zh'
        prompt_lang = "zh" # Default
        for key, value in lang_map.items():
            if key in lang_key:
                prompt_lang = value
                break

        # Construct file name: proofread_zh.txt, proofread_ja.txt, or proofread_en.txt
        prompt_file = f"proofread_{prompt_lang}.txt"
        
        # Construct full path
        prompt_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "..",
            "Resource", "Prompt", "System",
            prompt_file
        )

        # Try to load the specific language prompt
        if os.path.exists(prompt_path):
            try:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                print(f"[AIProofreader] Failed to load prompt {prompt_file}: {e}")

        # Fallback to zh if specific one not found
        if prompt_lang != "zh":
            default_path = prompt_path.replace(prompt_file, "proofread_zh.txt")
            if os.path.exists(default_path):
                try:
                    with open(default_path, "r", encoding="utf-8") as f:
                        return f.read()
                except: pass

        return ""

    def _build_user_message(
        self,
        source: str,
        translation: str,
        glossary: List[dict] = None,
        context: str = ""
    ) -> str:
        """构建用户消息"""
        message_parts = []

        if context:
            message_parts.append(f"## 上下文\n{context}")

        message_parts.append(f"## 原文\n{source}")
        message_parts.append(f"## 译文\n{translation}")

        if glossary:
            glossary_str = "\n".join([
                f"- {item.get('src', '')} → {item.get('dst', '')}"
                for item in glossary
            ])
            message_parts.append(f"## 术语表\n{glossary_str}")

        return "\n\n".join(message_parts)

    def _parse_response(self, response: str) -> AICheckResult:
        """解析AI响应"""
        try:
            json_match = response
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                json_match = response[start:end].strip()
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                json_match = response[start:end].strip()

            data = json.loads(json_match)

            issues = []
            for issue_data in data.get("issues", []):
                issue = AICheckIssue(
                    type=issue_data.get("type", "unknown"),
                    severity=issue_data.get("severity", "low"),
                    location=issue_data.get("location", ""),
                    description=issue_data.get("description", ""),
                    suggestion=issue_data.get("suggestion", ""),
                    confidence=issue_data.get("confidence", 0.0)
                )
                if issue.confidence >= self.confidence_threshold:
                    issues.append(issue)

            return AICheckResult(
                has_issues=len(issues) > 0,
                issues=issues,
                corrected_translation=data.get("corrected_translation", "")
            )

        except (json.JSONDecodeError, KeyError, TypeError):
            return AICheckResult(has_issues=False, issues=[])

    def _build_user_message(
        self,
        source: str,
        translation: str,
        glossary: List[dict] = None,
        context: str = "",
        world_building: str = "",
        writing_style: str = "",
        characterization: List[dict] = None
    ) -> str:
        """构建用户消息，包含所有规则设定"""
        message_parts = []

        if world_building:
            message_parts.append(f"## 世界观设定\n{world_building}")
        
        if characterization:
            char_str = "\n".join([f"- {c.get('original_name')} -> {c.get('translated_name')} ({c.get('additional_info', '')})" for c in characterization])
            message_parts.append(f"## 角色设定\n{char_str}")

        if writing_style:
            message_parts.append(f"## 写作风格指南\n{writing_style}")

        if context:
            message_parts.append(f"## 上下文参考\n{context}")

        message_parts.append(f"## 待校对原文\n{source}")
        message_parts.append(f"## 当前译文\n{translation}")

        if glossary:
            glossary_str = "\n".join([
                f"- {item.get('src', '')} → {item.get('dst', '')}"
                for item in glossary
            ])
            message_parts.append(f"## 术语对照表\n{glossary_str}")

        return "\n\n".join(message_parts)

    def proofread_single(
        self,
        source: str,
        translation: str,
        glossary: List[dict] = None,
        context: str = "",
        world_building: str = "",
        writing_style: str = "",
        characterization: List[dict] = None
    ) -> AICheckResult:
        """校对单条翻译（同步方法）"""
        from ModuleFolders.Infrastructure.LLMRequester.LLMRequester import LLMRequester
        from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig

        user_message = self._build_user_message(
            source, translation, glossary, context, 
            world_building, writing_style, characterization
        )

        messages = [{"role": "user", "content": user_message}]

        try:
            from ModuleFolders.Infrastructure.TaskConfig.TaskType import TaskType
            task_config = TaskConfig()
            task_config.load_config_from_dict(self.config)
            task_config.prepare_for_translation(TaskType.TRANSLATION)
            platform_config = task_config.get_platform_configuration("translationReq")

            requester = LLMRequester()
            skip, response_think, response_content, prompt_tokens, completion_tokens = requester.sent_request(
                messages=messages,
                system_prompt=self.prompt_template,
                platform_config=platform_config
            )

            if skip:
                return AICheckResult(has_issues=False, issues=[])

            result = self._parse_response(response_content)
            result.prompt_tokens = prompt_tokens
            result.completion_tokens = completion_tokens
            return result

        except Exception as e:
            print(f"[AI校对错误] {e}")
            return AICheckResult(has_issues=False, issues=[])

    def proofread_lines_block(
        self,
        items: List[Dict[str, Any]],
        glossary: List[dict] = None,
        world_building: str = "",
        writing_style: str = "",
        characterization: List[dict] = None
    ) -> Dict[int, AICheckResult]:
        """
        批量打包校对：将多行内容打包进一次 API 请求
        """
        if not items:
            return {}

        # 构建规则前缀
        rule_parts = []
        if world_building: rule_parts.append(f"世界观: {world_building}")
        if writing_style: rule_parts.append(f"风格: {writing_style}")
        rules_text = "\n".join(rule_parts)

        lines_text = []
        for item in items:
            idx = item.get('index', 0)
            src = item.get('source', '').replace('\n', '\\n')
            trans = item.get('translation', '').replace('\n', '\\n')
            lines_text.append(f"Line {idx}:\n原文: {src}\n译文: {trans}")
        
        block_content = "\n\n".join(lines_text)
        
        user_message = f"""
请根据以下规则和术语表，批量校对这 {len(items)} 行翻译。
请以 JSON 列表格式返回结果，仅返回有问题的行。

{rules_text}

## 待校对列表
{block_content}
"""
        if glossary:
            glossary_str = "\n".join([f"- {i.get('src')} -> {i.get('dst')}" for i in glossary])
            user_message += f"\n\n## 术语表\n{glossary_str}"

        # 发送请求 (复用 platform 配置逻辑)
        from ModuleFolders.Infrastructure.LLMRequester.LLMRequester import LLMRequester
        from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig
        from ModuleFolders.Infrastructure.TaskConfig.TaskType import TaskType

        messages = [{"role": "user", "content": user_message}]
        results = {}

        try:
            task_config = TaskConfig()
            task_config.load_config_from_dict(self.config)
            task_config.prepare_for_translation(TaskType.TRANSLATION)
            platform_config = task_config.get_platform_configuration("translationReq")

            requester = LLMRequester()
            skip, _, response_content, p_tok, c_tok = requester.sent_request(
                messages=messages,
                system_prompt=self.prompt_template,
                platform_config=platform_config
            )

            if skip or not response_content:
                return {}

            import json
            import re
            json_match = response_content
            if "```json" in response_content:
                start = response_content.find("```json") + 7
                end = response_content.find("```", start)
                json_match = response_content[start:end].strip()
            
            try:
                data_list = json.loads(json_match)
                if isinstance(data_list, list):
                    for entry in data_list:
                        line_id = entry.get("line_id")
                        if line_id is not None:
                            issues = []
                            for iss in entry.get("issues", []):
                                issues.append(AICheckIssue(
                                    type=iss.get("type", "unknown"),
                                    severity=iss.get("severity", "medium"),
                                    location="",
                                    description=iss.get("description", ""),
                                    suggestion=iss.get("suggestion", ""),
                                    confidence=iss.get("confidence", 0.8)
                                ))
                            if issues:
                                results[line_id] = AICheckResult(
                                    has_issues=True,
                                    issues=issues,
                                    corrected_translation=entry.get("corrected_translation", ""),
                                    prompt_tokens=p_tok // len(items),
                                    completion_tokens=c_tok // len(items)
                                )
            except: pass
        except Exception as e:
            print(f"[AI批量校对错误] {e}")

        return results

    def proofread_batch(
        self,
        items: List[Dict[str, Any]],
        glossary: List[dict] = None,
        context_lines: int = 5,
        progress_callback=None
    ) -> Dict[int, AICheckResult]:
        """批量校对"""
        results = {}
        total_prompt_tokens = 0
        total_completion_tokens = 0

        for i, item in enumerate(items):
            # 构建上下文
            context_parts = []
            start = max(0, i - context_lines)
            end = min(len(items), i + context_lines + 1)

            for j in range(start, end):
                if j != i:
                    ctx_item = items[j]
                    context_parts.append(
                        f"[{j}] {ctx_item.get('source', '')[:50]}"
                    )

            context = "\n".join(context_parts)

            result = self.proofread_single(
                source=item.get("source", ""),
                translation=item.get("translation", ""),
                glossary=glossary,
                context=context
            )

            total_prompt_tokens += result.prompt_tokens
            total_completion_tokens += result.completion_tokens

            if result.has_issues:
                results[item.get("index", i)] = result

            if progress_callback:
                progress_callback(i + 1, len(items), total_prompt_tokens, total_completion_tokens)

        return results
