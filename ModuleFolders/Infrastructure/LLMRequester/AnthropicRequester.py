from ModuleFolders.Base.Base import Base
from ModuleFolders.Infrastructure.LLMRequester.LLMClientFactory import LLMClientFactory
from ModuleFolders.Infrastructure.LLMRequester.ModelConfigHelper import ModelConfigHelper
from ModuleFolders.Infrastructure.LLMRequester.ErrorClassifier import ErrorClassifier, ErrorType
from ModuleFolders.Infrastructure.LLMRequester.ProviderFingerprint import ProviderFingerprint


# 接口请求器
class AnthropicRequester(Base):

    def __init__(self) -> None:
        pass

    def _is_cache_supported(self, platform_config: dict) -> bool:
        """检查当前API是否支持缓存（使用 ProviderFingerprint）"""
        api_url = platform_config.get('api_url', '')
        fingerprint = ProviderFingerprint()
        return fingerprint.should_use_cache(api_url)

    def _disable_cache_for_api(self, platform_config: dict, error_msg: str) -> None:
        """禁用当前API的缓存功能（使用 ProviderFingerprint）"""
        api_url = platform_config.get('api_url', '')
        fingerprint = ProviderFingerprint()
        fingerprint.mark_cache_unsupported(api_url, error_msg)

    def _build_system_with_cache(self, system_prompt: str) -> list[dict]:
        """构建带缓存控制的系统提示词"""
        return [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"}
            }
        ]

    # 发起请求
    def request_anthropic(self, messages, system_prompt, platform_config) -> tuple[bool, str, str, int, int]:
        model_name = platform_config.get("model_name")
        request_timeout = platform_config.get("request_timeout", 60)
        temperature = platform_config.get("temperature", 1.0)
        top_p = platform_config.get("top_p", 1.0)
        think_switch = platform_config.get("think_switch")
        think_depth = platform_config.get("think_depth")
        enable_caching = platform_config.get("enable_prompt_caching", False)

        # 检查缓存是否被禁用（之前请求失败过）
        use_cache = enable_caching and self._is_cache_supported(platform_config)

        # 根据是否启用缓存来构建系统提示词
        if use_cache and system_prompt:
            system_content = self._build_system_with_cache(system_prompt)
        else:
            system_content = system_prompt

        # 参数基础配置
        base_params = {
            "model": model_name,
            "system": system_content,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "timeout": request_timeout,
            "max_tokens": ModelConfigHelper.get_claude_max_output_tokens(model_name)
        }

        # 从工厂获取客户端
        client = LLMClientFactory().get_anthropic_client(platform_config)

        try:
            response = client.messages.create(**base_params)
            response_think = ""
            response_content = response.content[0].text
        except Exception as e:
            error_str = str(e)
            # 如果启用了缓存且是缓存相关错误，尝试禁用缓存重试
            if use_cache and ErrorClassifier.is_cache_related_error(error_str):
                self._disable_cache_for_api(platform_config, error_str)
                self.warning("Cache not supported by this API, disabled automatically. Retrying...")

                # 使用普通模式重试
                base_params["system"] = system_prompt
                try:
                    response = client.messages.create(**base_params)
                    response_think = ""
                    response_content = response.content[0].text
                except Exception as retry_e:
                    error_type, _ = ErrorClassifier.classify(str(retry_e))
                    self.error(f"Request error ({error_type.value}) ... {retry_e}", retry_e if self.is_debug() else None)
                    return True, error_type.value.upper(), str(retry_e), 0, 0
            else:
                error_type, _ = ErrorClassifier.classify(error_str)
                self.error(f"Request error ({error_type.value}) ... {e}", e if self.is_debug() else None)
                return True, error_type.value.upper(), error_str, 0, 0

        # 获取指令消耗
        try:
            prompt_tokens = int(response.usage.prompt_tokens)
        except Exception:
            prompt_tokens = 0

        # 获取回复消耗
        try:
            completion_tokens = int(response.usage.completion_tokens)
        except Exception:
            completion_tokens = 0

        return False, response_think, response_content, prompt_tokens, completion_tokens
