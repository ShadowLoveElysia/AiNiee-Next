from ModuleFolders.Base.Base import Base
from ModuleFolders.Infrastructure.LLMRequester.LLMClientFactory import LLMClientFactory
from ModuleFolders.Infrastructure.LLMRequester.ModelConfigHelper import ModelConfigHelper
from ModuleFolders.Infrastructure.LLMRequester.ErrorClassifier import ErrorClassifier, ErrorType
from ModuleFolders.Infrastructure.LLMRequester.ProviderFingerprint import ProviderFingerprint
from ModuleFolders.Infrastructure.LLMRequester.SdkRequestMode import is_anthropic_sdk_mode


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

    def _build_params(self, messages, system_content, platform_config) -> dict:
        model_name = platform_config.get("model_name")
        request_timeout = platform_config.get("request_timeout", 60)
        temperature = platform_config.get("temperature", 1.0)
        top_p = platform_config.get("top_p", 1.0)
        return {
            "model": model_name,
            "system": system_content,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "timeout": request_timeout,
            "max_tokens": ModelConfigHelper.get_claude_max_output_tokens(model_name)
        }

    def _parse_response_json(self, response_json: dict) -> tuple[str, str, int, int]:
        response_think = ""
        response_content = ""
        for block in response_json.get("content", []) or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                response_content += str(block.get("text") or "")
            elif block.get("type") == "thinking":
                response_think += str(block.get("thinking") or "")

        usage = response_json.get("usage", {}) if isinstance(response_json, dict) else {}
        prompt_tokens = int(usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("output_tokens", 0) or usage.get("completion_tokens", 0) or 0)
        return response_think, response_content, prompt_tokens, completion_tokens

    def _parse_sdk_response(self, response) -> tuple[str, str, int, int]:
        response_think = ""
        response_content = ""
        for block in getattr(response, "content", []) or []:
            block_type = getattr(block, "type", "")
            if block_type == "text":
                response_content += str(getattr(block, "text", "") or "")
            elif block_type == "thinking":
                response_think += str(getattr(block, "thinking", "") or "")

        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0) or 0)
        return response_think, response_content, prompt_tokens, completion_tokens

    def _do_request_httpx(self, base_params: dict, platform_config: dict) -> tuple[bool, str, str, int, int]:
        from ModuleFolders.Infrastructure.LLMRequester.LLMClientFactory import create_httpx_client

        api_url = str(platform_config.get("api_url") or "https://api.anthropic.com").rstrip("/")
        if api_url.endswith("/v1"):
            api_url = f"{api_url}/messages"
        elif not api_url.endswith("/messages"):
            api_url = f"{api_url}/v1/messages"
        headers = {
            "x-api-key": str(platform_config.get("api_key") or ""),
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        request_timeout = int(base_params.get("timeout", platform_config.get("request_timeout", 60)) or 60)
        request_body = dict(base_params)
        request_body.pop("timeout", None)

        with create_httpx_client(timeout=request_timeout) as http_client:
            response = http_client.post(api_url, json=request_body, headers=headers)
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
            response_think, response_content, prompt_tokens, completion_tokens = self._parse_response_json(response.json())
            return False, response_think, response_content, prompt_tokens, completion_tokens

    def _do_request_sdk(self, base_params: dict, platform_config: dict) -> tuple[bool, str, str, int, int]:
        client = LLMClientFactory().get_anthropic_client(platform_config)
        response = client.messages.create(**base_params)
        response_think, response_content, prompt_tokens, completion_tokens = self._parse_sdk_response(response)
        return False, response_think, response_content, prompt_tokens, completion_tokens

    # 发起请求
    def request_anthropic(self, messages, system_prompt, platform_config) -> tuple[bool, str, str, int, int]:
        enable_caching = platform_config.get("enable_prompt_caching", False)

        # 检查缓存是否被禁用（之前请求失败过）
        use_cache = enable_caching and self._is_cache_supported(platform_config)

        # 根据是否启用缓存来构建系统提示词
        if use_cache and system_prompt:
            system_content = self._build_system_with_cache(system_prompt)
        else:
            system_content = system_prompt

        # 参数基础配置
        base_params = self._build_params(messages, system_content, platform_config)
        request_func = self._do_request_sdk if is_anthropic_sdk_mode(platform_config) else self._do_request_httpx

        try:
            return request_func(base_params.copy(), platform_config)
        except Exception as e:
            error_str = str(e)
            # 如果启用了缓存且是缓存相关错误，尝试禁用缓存重试
            if use_cache and ErrorClassifier.is_cache_related_error(error_str):
                self._disable_cache_for_api(platform_config, error_str)
                self.warning("Cache not supported by this API, disabled automatically. Retrying...")

                # 使用普通模式重试
                base_params["system"] = system_prompt
                try:
                    return request_func(base_params.copy(), platform_config)
                except Exception as retry_e:
                    error_type, _ = ErrorClassifier.classify(str(retry_e))
                    self.error(f"Request error ({error_type.value}) ... {retry_e}", retry_e if self.is_debug() else None)
                    return True, error_type.value.upper(), str(retry_e), 0, 0
            else:
                error_type, _ = ErrorClassifier.classify(error_str)
                self.error(f"Request error ({error_type.value}) ... {e}", e if self.is_debug() else None)
                return True, error_type.value.upper(), error_str, 0, 0
