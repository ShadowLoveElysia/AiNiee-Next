"""
校对任务 - 复用翻译任务的执行逻辑，只换提示词和响应解析
"""

import os
import json
import re
from typing import List, Dict, Any

from ModuleFolders.Base.Base import Base
from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig
from ModuleFolders.Infrastructure.LLMRequester.LLMRequester import LLMRequester
from ModuleFolders.Infrastructure.RequestLimiter.RequestLimiter import RequestLimiter


class ProofreaderTask(Base):
    """校对任务，复用翻译任务的执行逻辑"""

    def __init__(self, config: TaskConfig, request_limiter: RequestLimiter) -> None:
        super().__init__()
        self.config = config
        self.request_limiter = request_limiter
        self.system_prompt = self._load_prompt()
        self.task_id = ""
        self.extra_info = {}
        self.items = []
        self.previous_items = []

    def _load_prompt(self) -> str:
        """加载校对提示词"""
        lang_map = {
            "zh": "zh", "zh_CN": "zh", "zh_TW": "zh", "chinese": "zh",
            "en": "en", "english": "en",
            "ja": "ja", "jp": "ja", "japanese": "ja",
        }
        target_lang = getattr(self.config, 'target_language', '')
        lang_key = target_lang.lower() if target_lang else "zh"
        prompt_lang = lang_map.get(lang_key, "zh")

        prompt_file = f"proofread_{prompt_lang}.txt"
        prompt_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "..",
            "Resource", "Prompt", "System",
            prompt_file
        )

        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()

        default_path = prompt_path.replace(prompt_file, "proofread_zh.txt")
        if os.path.exists(default_path):
            with open(default_path, "r", encoding="utf-8") as f:
                return f.read()

        return ""

    def set_items(self, items: List[Dict[str, Any]]) -> None:
        """设置待校对的数据 (dict格式: index, source, translation)"""
        self.items = items

    def set_previous_items(self, previous_items: List[Dict[str, Any]]) -> None:
        """设置上文数据"""
        self.previous_items = previous_items

    def prepare(self) -> None:
        """构建校对消息 - 使用JSON格式，包含实际行ID"""
        # 构建待校对内容 (使用实际行ID)
        content_list = []
        for item in self.items:
            content_list.append({
                "id": item.get("index"),  # 实际行ID
                "source": item.get("source", ""),
                "translation": item.get("translation", "")
            })

        # 构建用户消息
        message_parts = []

        # 上下文 (简化格式)
        if self.previous_items:
            context_list = []
            for item in self.previous_items:
                context_list.append({
                    "source": item.get("source", "")[:100],
                    "translation": item.get("translation", "")[:100]
                })
            message_parts.append("## 上下文\n" + json.dumps(context_list, ensure_ascii=False, indent=2))

        # 待校对内容 (JSON格式)
        message_parts.append("## 待校对内容\n" + json.dumps(content_list, ensure_ascii=False, indent=2))

        # 术语表
        glossary = getattr(self.config, 'prompt_dictionary_data', [])
        if glossary:
            glossary_str = "\n".join([
                f"- {item.get('src', '')} → {item.get('dst', '')}"
                for item in glossary[:50]
            ])
            message_parts.append(f"## 术语表\n{glossary_str}")

        self.messages = [{"role": "user", "content": "\n\n".join(message_parts)}]

    def run(self) -> Dict[int, Any]:
        """执行校对任务"""
        import time
        from ModuleFolders.Infrastructure.Tokener.Tokener import Tokener

        # 预估 Token 消费
        request_tokens_consume = Tokener.calculate_tokens(self, self.messages, self.system_prompt)

        # 等待限流 (复用翻译任务的限流逻辑)
        wait_start_time = time.time()
        while True:
            if Base.work_status == Base.STATUS.STOPING:
                return {}

            if self.request_limiter.check_limiter(request_tokens_consume):
                break

            if time.time() - wait_start_time > 600:
                return {"skip": True, "prompt_tokens": 0, "completion_tokens": 0, "issues": {}}

            time.sleep(0.1)

        # 获取平台配置
        platform_config = self.config.get_platform_configuration("translationReq")

        # 发送请求
        try:
            requester = LLMRequester()
            skip, response_think, response_content, prompt_tokens, completion_tokens = requester.sent_request(
                messages=self.messages,
                system_prompt=self.system_prompt,
                platform_config=platform_config
            )

            if skip:
                return {"skip": True, "prompt_tokens": 0, "completion_tokens": 0, "issues": {}}

            # 解析响应
            parsed = self._parse_response(response_content)

            return {
                "skip": False,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "issues": parsed.get("issues", {}),
                "corrections": parsed.get("corrections", {})
            }

        except Exception as e:
            self.print(f"[AI校对错误] {e}")
            return {"skip": True, "prompt_tokens": 0, "completion_tokens": 0, "issues": {}, "corrections": {}}

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """解析AI响应，返回issues和corrections"""
        result = {"issues": {}, "corrections": {}}
        confidence_threshold = getattr(self.config, 'proofread_confidence_threshold', 0.7)

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

            # 解析问题列表 (新格式使用id字段)
            for issue_data in data.get("issues", []):
                confidence = issue_data.get("confidence", 0.0)
                if confidence < confidence_threshold:
                    continue

                line_id = issue_data.get("id")
                if line_id is not None:
                    if line_id not in result["issues"]:
                        result["issues"][line_id] = []
                    result["issues"][line_id].append({
                        "type": issue_data.get("type", "unknown"),
                        "severity": issue_data.get("severity", "low"),
                        "description": issue_data.get("description", ""),
                        "confidence": confidence,
                        "check_type": "ai"  # 标记为AI检查
                    })

            # 解析修正译文
            for correction in data.get("corrections", []):
                line_id = correction.get("id")
                text = correction.get("text", "")
                if line_id is not None and text:
                    result["corrections"][line_id] = text

        except (json.JSONDecodeError, KeyError, TypeError):
            pass

        return result
