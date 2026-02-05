"""
规则匹配器 - 零成本诊断层

通过预定义规则快速匹配已知错误模式，无需调用LLM
"""

import re
from dataclasses import dataclass
from typing import Optional, List, Dict

from ModuleFolders.Diagnostic.i18n import get_text


@dataclass
class DiagnosticResult:
    """诊断结果"""
    is_matched: bool = False           # 是否匹配到规则
    is_code_bug: bool = False          # 是否为代码Bug
    error_type: str = ""               # 错误类型
    root_cause: str = ""               # 根本原因
    solution: str = ""                 # 解决方案
    self_check: List[str] = None       # 自查清单
    confidence: float = 0.0            # 置信度 (0-1)
    matched_rule: str = ""             # 匹配的规则名称
    token_cost: int = 0                # 消耗的token数


class RuleMatcher:
    """
    规则匹配器

    优先级: 精确匹配 > 正则匹配 > 关键词匹配
    """

    def __init__(self, lang: str = "zh_CN"):
        self.lang = lang
        self._init_rules()

    def _init_rules(self):
        """初始化规则库"""

        # 精确匹配规则 (错误码/状态码) - 使用 i18n key
        self.exact_rules: Dict[str, dict] = {
            "401": {
                "error_type_key": "error_type_auth",
                "root_cause_key": "cause_invalid_key",
                "solution_key": "solution_check_key",
                "is_code_bug": False,
                "confidence": 0.95
            },
            "403": {
                "error_type_key": "error_type_permission",
                "root_cause_key": "cause_no_permission",
                "solution_key": "solution_check_permission",
                "is_code_bug": False,
                "confidence": 0.95
            },
            "429": {
                "error_type_key": "error_type_rate_limit",
                "root_cause_key": "cause_rate_limit",
                "solution_key": "solution_rate_limit",
                "is_code_bug": False,
                "confidence": 0.95
            },
            "500": {
                "error_type_key": "error_type_server",
                "root_cause_key": "cause_server_error",
                "solution_key": "solution_server_error",
                "is_code_bug": False,
                "confidence": 0.90
            },
            "502": {
                "error_type_key": "error_type_gateway",
                "root_cause_key": "cause_gateway_error",
                "solution_key": "solution_gateway",
                "is_code_bug": False,
                "confidence": 0.90
            },
            "503": {
                "error_type_key": "error_type_unavailable",
                "root_cause_key": "cause_service_unavailable",
                "solution_key": "solution_maintenance",
                "is_code_bug": False,
                "confidence": 0.90
            }
        }

        # 正则匹配规则 - 使用 i18n key
        self.regex_rules: List[dict] = [
            {
                "pattern": r"SSLError|SSL: CERTIFICATE_VERIFY_FAILED|ssl\.SSLCertVerificationError",
                "error_type_key": "error_type_ssl",
                "root_cause_key": "cause_ssl",
                "solution_key": "solution_ssl",
                "is_code_bug": False,
                "confidence": 0.95
            },
            {
                "pattern": r"Connection(Error|Refused|Reset)|ConnectionResetError|RemoteDisconnected",
                "error_type_key": "error_type_connection",
                "root_cause_key": "cause_connection",
                "solution_key": "solution_connection",
                "is_code_bug": False,
                "confidence": 0.95
            },
            {
                "pattern": r"TimeoutError|ReadTimeout|ConnectTimeout|timed?\s*out",
                "error_type_key": "error_type_timeout",
                "root_cause_key": "cause_timeout",
                "solution_key": "solution_timeout",
                "is_code_bug": False,
                "confidence": 0.90
            },
            {
                "pattern": r"model.*not\s*found|model_not_found|does not exist|Model .+ does not exist",
                "error_type_key": "error_type_model_not_found",
                "root_cause_key": "cause_model_not_found",
                "solution_key": "solution_model",
                "is_code_bug": False,
                "confidence": 0.95
            },
            {
                "pattern": r"Invalid API Key|invalid.*api.?key|Incorrect API key|API key not valid",
                "error_type_key": "error_type_invalid_key",
                "root_cause_key": "cause_invalid_key_format",
                "solution_key": "solution_key_format",
                "is_code_bug": False,
                "confidence": 0.98
            },
            {
                "pattern": r"insufficient.*(quota|balance|credit)|余额不足|Quota exceeded",
                "error_type_key": "error_type_insufficient_balance",
                "root_cause_key": "cause_insufficient_balance",
                "solution_key": "solution_balance",
                "is_code_bug": False,
                "confidence": 0.98
            },
            {
                "pattern": r"rate.?limit|RateLimitError",
                "error_type_key": "error_type_rate_limit",
                "root_cause_key": "cause_rate_limit",
                "solution_key": "solution_rate_limit",
                "is_code_bug": False,
                "confidence": 0.95
            },
            {
                "pattern": r"context.*(length|window)|too\s*long|maximum.*token|token.*limit|max.*length",
                "error_type_key": "error_type_context_limit",
                "root_cause_key": "cause_context_limit",
                "solution_key": "solution_context",
                "is_code_bug": False,
                "confidence": 0.90
            },
            {
                "pattern": r"FileNotFoundError|No such file|文件.*不存在|路径.*不存在",
                "error_type_key": "error_type_file_not_found",
                "root_cause_key": "cause_file_not_found",
                "solution_key": "solution_file",
                "is_code_bug": False,
                "confidence": 0.90
            },
            {
                "pattern": r"PermissionError|Permission denied|拒绝访问",
                "error_type_key": "error_type_permission_denied",
                "root_cause_key": "cause_permission_denied",
                "solution_key": "solution_permission",
                "is_code_bug": False,
                "confidence": 0.90
            },
            {
                "pattern": r"JSONDecodeError|json\.decoder|Expecting value|Invalid JSON",
                "error_type_key": "error_type_json_error",
                "root_cause_key": "cause_json_error",
                "solution_key": "solution_json",
                "is_code_bug": False,
                "confidence": 0.85
            },
            {
                "pattern": r"UnicodeDecodeError|UnicodeEncodeError|codec can't (decode|encode)",
                "error_type_key": "error_type_encoding",
                "root_cause_key": "cause_encoding",
                "solution_key": "solution_encoding",
                "is_code_bug": False,
                "confidence": 0.90
            },
            {
                "pattern": r"ImportError|ModuleNotFoundError|No module named",
                "error_type_key": "error_type_dependency",
                "root_cause_key": "cause_dependency",
                "solution_key": "solution_dependency",
                "is_code_bug": False,
                "confidence": 0.70,
                "needs_detail_check": True
            }
        ]

        # KeyError 特殊处理规则 - 使用 i18n key
        self.keyerror_rules: List[dict] = [
            {
                "pattern": r"KeyError.*['\"]model['\"]",
                "error_type_key": "error_type_config_missing",
                "root_cause_key": "cause_model_not_selected",
                "solution_key": "solution_select_model",
                "is_code_bug": False,
                "confidence": 0.95
            },
            {
                "pattern": r"KeyError.*['\"]api_key['\"]",
                "error_type_key": "error_type_config_missing",
                "root_cause_key": "cause_api_key_not_set",
                "solution_key": "solution_select_key",
                "is_code_bug": False,
                "confidence": 0.95
            },
            {
                "pattern": r"KeyError.*['\"]prompt['\"]",
                "error_type_key": "error_type_config_missing",
                "root_cause_key": "cause_prompt_not_selected",
                "solution_key": "solution_select_prompt",
                "is_code_bug": False,
                "confidence": 0.95
            }
        ]

        # 默认自查清单 - 使用 i18n key
        self.default_self_check_keys = [
            "self_check_1",
            "self_check_2",
            "self_check_3"
        ]

    @property
    def default_self_check(self) -> List[str]:
        """获取翻译后的默认自查清单"""
        return [get_text(key, self.lang) for key in self.default_self_check_keys]

    def match(self, error_text: str) -> DiagnosticResult:
        """
        匹配错误文本

        Args:
            error_text: 错误信息/Traceback

        Returns:
            DiagnosticResult: 诊断结果
        """
        result = DiagnosticResult(self_check=self.default_self_check)

        # 1. 精确匹配状态码
        for code, rule in self.exact_rules.items():
            if code in error_text:
                return self._create_result(rule, f"status_code_{code}")

        # 2. KeyError 特殊处理
        if "KeyError" in error_text:
            for rule in self.keyerror_rules:
                if re.search(rule["pattern"], error_text, re.IGNORECASE):
                    return self._create_result(rule, f"keyerror_{rule['pattern'][:20]}")

        # 3. ImportError 特殊处理 (区分本地模块和第三方依赖)
        if "ImportError" in error_text or "ModuleNotFoundError" in error_text:
            return self._handle_import_error(error_text)

        # 4. 其他正则匹配
        for rule in self.regex_rules:
            if rule.get("needs_detail_check"):
                continue  # 跳过需要详细检查的规则
            if re.search(rule["pattern"], error_text, re.IGNORECASE):
                return self._create_result(rule, f"regex_{rule['pattern'][:30]}")

        # 未匹配到任何规则
        return result

    def _create_result(self, rule: dict, rule_name: str) -> DiagnosticResult:
        """从规则创建诊断结果，使用 i18n 翻译"""
        # 获取 i18n key 并翻译
        error_type_key = rule.get("error_type_key", "")
        root_cause_key = rule.get("root_cause_key", "")
        solution_key = rule.get("solution_key", "")

        return DiagnosticResult(
            is_matched=True,
            is_code_bug=rule.get("is_code_bug", False),
            error_type=get_text(error_type_key, self.lang) if error_type_key else "",
            root_cause=get_text(root_cause_key, self.lang) if root_cause_key else "",
            solution=get_text(solution_key, self.lang) if solution_key else "",
            self_check=self.default_self_check,
            confidence=rule.get("confidence", 0.8),
            matched_rule=rule_name,
            token_cost=0  # 规则匹配不消耗token
        )

    def _handle_import_error(self, error_text: str) -> DiagnosticResult:
        """
        处理 ImportError/ModuleNotFoundError
        区分本地模块错误(代码Bug)和第三方依赖缺失(用户问题)
        """
        # 本地模块模式 - 这些是项目内部模块
        local_patterns = [
            r"ModuleFolders\.",
            r"PluginScripts\.",
            r"Tools\.",
            r"from ModuleFolders",
            r"from PluginScripts",
            r"import ModuleFolders",
        ]

        is_local_module = any(
            re.search(p, error_text) for p in local_patterns
        )

        if is_local_module:
            # 本地模块导入错误 = 代码Bug
            return DiagnosticResult(
                is_matched=True,
                is_code_bug=True,
                error_type=get_text("error_type_code_import", self.lang),
                root_cause=get_text("cause_local_import", self.lang),
                solution=get_text("solution_code_bug", self.lang),
                self_check=self.default_self_check,
                confidence=0.90,
                matched_rule="import_local_module",
                token_cost=0
            )
        else:
            # 第三方依赖缺失 = 用户问题
            # 尝试提取缺失的模块名
            module_match = re.search(
                r"No module named ['\"]?([a-zA-Z0-9_]+)",
                error_text
            )
            module_name = module_match.group(1) if module_match else "<package>"

            # 获取基础解决方案文本并替换占位符
            base_solution = get_text("solution_dependency", self.lang)
            solution_text = base_solution.replace("<package>", module_name).replace("<包名>", module_name).replace("<パッケージ名>", module_name)

            return DiagnosticResult(
                is_matched=True,
                is_code_bug=False,
                error_type=get_text("error_type_dependency", self.lang),
                root_cause=f"{get_text('cause_third_party', self.lang)}: {module_name}",
                solution=solution_text,
                self_check=self.default_self_check,
                confidence=0.92,
                matched_rule="import_third_party",
                token_cost=0
            )
