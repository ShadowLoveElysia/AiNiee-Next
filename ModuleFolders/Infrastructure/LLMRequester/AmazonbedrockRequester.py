from ModuleFolders.Base.Base import Base
from ModuleFolders.Infrastructure.LLMRequester.ModelConfigHelper import ModelConfigHelper
from ModuleFolders.Infrastructure.LLMRequester.LLMClientFactory import LLMClientFactory


# 接口请求器
class AmazonbedrockRequester(Base):
    # 类级别的缓存支持状态标记
    _cache_disabled_apis: set = set()

    def __init__(self) -> None:
        pass

    def _get_api_key(self, platform_config: dict) -> str:
        """获取API标识用于缓存状态跟踪"""
        return f"{platform_config.get('region', '')}:{platform_config.get('model_name', '')}"

    def _is_cache_supported(self, platform_config: dict) -> bool:
        """检查当前API是否支持缓存"""
        return self._get_api_key(platform_config) not in self._cache_disabled_apis

    def _disable_cache_for_api(self, platform_config: dict) -> None:
        """禁用当前API的缓存功能"""
        self._cache_disabled_apis.add(self._get_api_key(platform_config))

    def _is_cache_error(self, error: Exception) -> bool:
        """检测是否是缓存相关错误"""
        error_str = str(error).lower()
        cache_error_keywords = ["cache", "cache_control", "ephemeral", "unsupported", "not supported"]
        return any(keyword in error_str for keyword in cache_error_keywords)

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
    def request_amazonbedrock(self, messages, system_prompt, platform_config) -> tuple[bool, str, str, int, int]:
        model_name = platform_config.get("model_name")
        if "anthropic" in model_name:
            return self.request_amazonbedrock_anthropic(messages, system_prompt, platform_config)
        else:
            return self.request_amazonbedrock_boto3(messages, system_prompt, platform_config)

    # 发起请求
    def request_amazonbedrock_anthropic(self, messages, system_prompt, platform_config) -> tuple[bool, str, str, int, int]:
        model_name: str = platform_config.get("model_name")
        request_timeout = platform_config.get("request_timeout", 60)
        temperature = platform_config.get("temperature", 1.0)
        top_p = platform_config.get("top_p", 1.0)
        enable_caching = platform_config.get("enable_prompt_caching", False)

        # 检查缓存是否被禁用
        use_cache = enable_caching and self._is_cache_supported(platform_config)

        # 根据是否启用缓存来构建系统提示词
        if use_cache and system_prompt:
            system_content = self._build_system_with_cache(system_prompt)
        else:
            system_content = system_prompt

        # 从工厂获取客户端
        client = LLMClientFactory().get_anthropic_bedrock(platform_config)

        try:
            response = client.messages.create(
                model=model_name,
                system=system_content,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                timeout=request_timeout,
                max_tokens=ModelConfigHelper.get_claude_max_output_tokens(model_name),
            )
            response_content = response.content[0].text
        except Exception as e:
            # 如果启用了缓存且是缓存相关错误，尝试禁用缓存重试
            if use_cache and self._is_cache_error(e):
                self._disable_cache_for_api(platform_config)
                self.warning("检测到API不支持上下文缓存功能，已自动关闭，将使用普通模式重试...")

                try:
                    response = client.messages.create(
                        model=model_name,
                        system=system_prompt,
                        messages=messages,
                        temperature=temperature,
                        top_p=top_p,
                        timeout=request_timeout,
                        max_tokens=ModelConfigHelper.get_claude_max_output_tokens(model_name),
                    )
                    response_content = response.content[0].text
                except Exception as retry_e:
                    self.error(f"请求任务错误 ... {retry_e}", retry_e if self.is_debug() else None)
                    return True, None, None, None, None
            else:
                self.error(f"请求任务错误 ... {e}", e if self.is_debug() else None)
                return True, None, None, None, None

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

        return False, "", response_content, prompt_tokens, completion_tokens

    # 发起请求
    def request_amazonbedrock_boto3(self, messages, system_prompt, platform_config) -> tuple[bool, str, str, int, int]:
        try:
            model_name = platform_config.get("model_name")
            _request_timeout = platform_config.get("request_timeout")
            temperature = platform_config.get("temperature")
            top_p = platform_config.get("top_p")

            # 从工厂获取客户端
            client = LLMClientFactory().get_boto3_bedrock(platform_config)

            # 使用boto3 converse api 调用,
            # 需要把"context":{"text":"message"} 转换为 "content":["text":"message"]
            # 如果messages最后一个元素是assistant，则需要添加{"role":"user","content":[{"text":"continue"}]}
            new_messages = []
            for message in messages:
                new_messages.append({"role": message["role"], "content": [{"text": message["content"]}]})
            if messages[-1]["role"] == "assistant":
                new_messages.append({"role": "user", "content": [{"text": "continue"}]})
            response = client.converse(
                modelId=model_name,
                system=[{"text": system_prompt}],
                messages=new_messages,
                inferenceConfig={"maxTokens": 4096, "temperature": temperature, "topP": top_p},
            )

            # 提取回复的文本内容
            response_content = response["output"]["message"]["content"][0]["text"]
        except Exception as e:
            self.error(f"请求任务错误 ... {e}", e if self.is_debug() else None)
            return True, None, None, None, None

        # 获取指令消耗
        try:
            prompt_tokens = int(response["usage"]["inputTokens"])
        except Exception:
            prompt_tokens = 0

        # 获取回复消耗
        try:
            completion_tokens = int(response["usage"]["outputTokens"])
        except Exception:
            completion_tokens = 0

        return False, "", response_content, prompt_tokens, completion_tokens
