"""
Shared LLM-backed error analysis helpers.

This module keeps request configuration and prompt construction in one place so
manual crash analysis and optional SmartDiagnostic LLM fallback do not drift.
"""

import copy
import os
import sys
from typing import Optional

try:
    import rapidjson as json
except ImportError:
    import json

from ModuleFolders.Base.Base import Base
from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig
from ModuleFolders.Infrastructure.TaskConfig.TaskType import TaskType


class LLMErrorAnalyzer:
    def __init__(self, project_root: str = ".", lang: str = "en"):
        self.project_root = project_root
        self.lang = lang

    def build_config_shadow(self, base_config: dict, temp_config: Optional[dict] = None) -> dict:
        """Build an isolated config dict for diagnostics without mutating app config."""
        if temp_config:
            config_shadow = self._load_preset_config() or copy.deepcopy(base_config or {})
            platform_tag = temp_config["target_platform"]
            config_shadow["target_platform"] = platform_tag
            config_shadow["api_settings"] = {"translate": platform_tag, "polish": platform_tag}
            config_shadow.setdefault("platforms", {})
            config_shadow["platforms"].setdefault(platform_tag, {"api_format": "OpenAI"})
            config_shadow["platforms"][platform_tag].update(temp_config)
            config_shadow["base_url"] = temp_config.get("api_url")
            config_shadow["api_key"] = temp_config.get("api_key")
            config_shadow["model"] = temp_config.get("model")
            if temp_config.get("think_switch"):
                config_shadow["think_switch"] = True
                config_shadow["think_depth"] = temp_config.get("think_depth")
                config_shadow["thinking_budget"] = temp_config.get("thinking_budget")
            return config_shadow

        return copy.deepcopy(base_config or {})

    def build_platform_config(
        self,
        base_config: dict,
        temp_config: Optional[dict] = None,
        temperature: float = 1.0,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Optional[dict]:
        """Resolve the current diagnostic LLM platform using TaskConfig."""
        config_shadow = self.build_config_shadow(base_config, temp_config)
        if not config_shadow:
            return None

        task_config = TaskConfig()
        task_config.initialize(config_shadow)
        task_config.save_config = lambda new_config: new_config

        original_base_print = Base.print
        Base.print = lambda *args, **kwargs: None
        try:
            task_config.prepare_for_translation(TaskType.TRANSLATION)
            platform_config = task_config.get_platform_configuration("translationReq")
        finally:
            Base.print = original_base_print

        if "model_name" in platform_config and "model" not in platform_config:
            platform_config["model"] = platform_config["model_name"]

        platform_config["temperature"] = temperature
        if top_p is not None:
            platform_config["top_p"] = top_p
        if max_tokens is not None:
            platform_config["max_tokens"] = max_tokens

        return platform_config

    def analyze(
        self,
        error_msg: str,
        base_config: dict,
        temp_config: Optional[dict] = None,
        operation_log: str = "",
        update_version: str = "",
        requester=None,
        temperature: float = 1.0,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
        compact: bool = False,
        knowledge_context: str = "",
        extra_context: Optional[dict] = None,
    ) -> tuple[bool, str, int]:
        """Run LLM error analysis. Returns (success, content, token_cost)."""
        from ModuleFolders.Infrastructure.LLMRequester.LLMRequester import LLMRequester

        platform_config = self.build_platform_config(
            base_config,
            temp_config=temp_config,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
        )
        if not platform_config:
            return False, "", 0

        requester = requester or LLMRequester()
        system_prompt = (
            self.build_compact_system_prompt()
            if compact
            else self.load_error_analysis_prompt()
        )
        user_content = (
            self.build_compact_user_content(
                error_msg,
                knowledge_context=knowledge_context,
                extra_context=extra_context,
            )
            if compact
            else self.build_error_analysis_prompt(
                error_msg,
                operation_log=operation_log,
                update_version=update_version,
            )
        )

        skip, _, content, prompt_tokens, completion_tokens = requester.sent_request(
            [{"role": "user", "content": user_content}],
            system_prompt,
            platform_config,
        )
        if skip or not content:
            return False, content or "", prompt_tokens + completion_tokens
        return True, content, prompt_tokens + completion_tokens

    def load_error_analysis_prompt(self) -> str:
        prompt_path = os.path.join(self.project_root, "Resource", "Prompt", "System", "error_analysis.json")
        system_prompt = "You are a Python expert helping a user with a crash."
        try:
            if os.path.exists(prompt_path):
                with open(prompt_path, "r", encoding="utf-8") as file:
                    prompts = json.load(file)
                system_prompt = prompts.get("system_prompt", {}).get(
                    self.lang,
                    prompts.get("system_prompt", {}).get("en", system_prompt),
                )
        except Exception:
            pass
        return system_prompt

    def build_compact_system_prompt(self) -> str:
        return """你是AiNiee错误诊断助手。分析错误并简洁回复。
格式要求(严格遵守):
[类型] 环境问题/配置问题/代码Bug
[原因] 一句话说明
[方案] 2-3个步骤
[是否代码Bug] 是/否"""

    def build_compact_user_content(
        self,
        error_msg: str,
        knowledge_context: str = "",
        extra_context: Optional[dict] = None,
    ) -> str:
        max_error_len = 1500
        if len(error_msg) > max_error_len:
            error_msg = error_msg[:max_error_len] + "\n...(已截断)"

        parts = [f"错误信息:\n{error_msg}"]
        if knowledge_context:
            parts.append(knowledge_context)

        context_lines = self._format_extra_context(extra_context or {})
        if context_lines:
            parts.append("诊断上下文:\n" + "\n".join(context_lines))

        parts.append(f"环境: Python {sys.version.split()[0]}, OS: {sys.platform}")
        return "\n\n".join(parts)

    def build_error_analysis_prompt(
        self,
        error_msg: str,
        operation_log: str = "",
        update_version: str = "",
    ) -> str:
        env_info = (
            f"OS={sys.platform}, Python={sys.version.split()[0]}, "
            f"App Version={update_version or 'unknown'}"
        )

        if self.lang == "zh_CN":
            user_content = (
                "程序发生崩溃。\n"
                f"环境信息: {env_info}\n\n"
                "项目文件结构:\n"
                "- 核心逻辑: ainiee_cli.py, ModuleFolders/*\n"
                "- 用户扩展: PluginScripts/*\n"
                "- 资源文件: Resource/*\n\n"
            )
        elif self.lang == "ja":
            user_content = (
                "プログラムがクラッシュしました。\n"
                f"環境情報: {env_info}\n\n"
                "プロジェクトファイル構造:\n"
                "- コアロジック: ainiee_cli.py, ModuleFolders/*\n"
                "- ユーザー拡張: PluginScripts/*\n"
                "- リソース: Resource/*\n\n"
            )
        else:
            user_content = (
                "The program crashed.\n"
                f"Environment: {env_info}\n\n"
                "Project File Structure:\n"
                "- Core Logic: ainiee_cli.py, ModuleFolders/*\n"
                "- User Extensions: PluginScripts/*\n"
                "- Resources: Resource/*\n\n"
            )

        if operation_log:
            user_content += f"{operation_log}\n\n"

        if self.lang == "zh_CN":
            user_content += (
                f"错误堆栈:\n{error_msg}\n\n"
                "分析要求:\n"
                "请分析此崩溃是由外部因素（网络、API Key、环境、SSL）还是内部软件缺陷（AiNiee-Next代码Bug）导致的。\n"
                "注意: 网络/SSL/429/401错误通常不是代码Bug，除非代码从根本上误用了库。\n"
                "如果错误发生在第三方库（如requests、urllib3、ssl）中且由网络条件引起，则不是代码Bug。\n\n"
                "【重要】如果你确定这是AiNiee-Next的代码Bug，必须在回复中包含这句话：「此为代码问题」"
            )
        elif self.lang == "ja":
            user_content += (
                f"トレースバック:\n{error_msg}\n\n"
                "分析要求:\n"
                "このクラッシュが外部要因（ネットワーク、APIキー、環境、SSL）によるものか、内部ソフトウェアの欠陥（AiNiee-Nextコードのバグ）によるものかを分析してください。\n"
                "注意: ネットワーク/SSL/429/401エラーは、コードがライブラリを根本的に誤用していない限り、コードのバグではありません。\n"
                "サードパーティライブラリ（requests、urllib3、sslなど）でネットワーク条件によりエラーが発生した場合、コードのバグではありません。\n\n"
                "【重要】これがAiNiee-Nextのコードバグであると確信した場合、回答に必ずこの文を含めてください：「これはコードの問題です」"
            )
        else:
            user_content += (
                f"Traceback:\n{error_msg}\n\n"
                "Strict Analysis Request:\n"
                "Analyze if the crash is due to external factors (Network, API Key, Environment, SSL) or internal software defects (Bugs in AiNiee-Next code).\n"
                "Note: Network/SSL/429/401 errors are NEVER code bugs unless the code is fundamentally misusing the library.\n"
                "If the error occurs in a third-party library (like requests, urllib3, ssl) due to network conditions, it is NOT a code bug.\n\n"
                '[IMPORTANT] If you are certain this is a code bug in AiNiee-Next, you MUST include this exact phrase in your response: "This is a code issue"'
            )

        return user_content

    def _load_preset_config(self) -> Optional[dict]:
        preset_path = os.path.join(self.project_root, "Resource", "platforms", "preset.json")
        try:
            with open(preset_path, "r", encoding="utf-8") as file:
                return json.load(file)
        except Exception:
            return None

    def _format_extra_context(self, context: dict) -> list[str]:
        lines = []
        config = context.get("config") if isinstance(context, dict) else None
        if isinstance(config, dict):
            platform = config.get("target_platform") or config.get("api_settings", {}).get("translate")
            model = config.get("model")
            if platform:
                lines.append(f"- platform: {platform}")
            if model:
                lines.append(f"- model: {model}")

        operation_log = context.get("operation_log") if isinstance(context, dict) else None
        if operation_log:
            lines.append("- recent operations:")
            lines.extend(f"  {line}" for line in str(operation_log).splitlines()[:12])

        for key in ("input_path", "output_path", "task_type"):
            value = context.get(key) if isinstance(context, dict) else None
            if value:
                lines.append(f"- {key}: {value}")
        return lines
