from google.genai import types
from google.genai.types import Content, HarmCategory, Part
from ModuleFolders.Base.Base import Base
from ModuleFolders.Infrastructure.LLMRequester.LLMClientFactory import LLMClientFactory
from ModuleFolders.Infrastructure.LLMRequester.ModelConfigHelper import ModelConfigHelper


# 接口请求器
class GoogleRequester(Base):
    # 类级别的缓存存储
    _cached_content_store: dict = {}
    # 类级别的缓存支持状态标记
    _cache_disabled_apis: set = set()

    def __init__(self) -> None:
        pass

    def _get_api_key(self, platform_config: dict) -> str:
        """获取API标识用于缓存状态跟踪"""
        return f"{platform_config.get('api_url', '')}:{platform_config.get('model_name', '')}"

    def _is_cache_supported(self, platform_config: dict) -> bool:
        """检查当前API是否支持缓存"""
        return self._get_api_key(platform_config) not in self._cache_disabled_apis

    def _disable_cache_for_api(self, platform_config: dict) -> None:
        """禁用当前API的缓存功能"""
        self._cache_disabled_apis.add(self._get_api_key(platform_config))

    def _get_or_create_cache(self, client, model_name: str, system_prompt: str, platform_config: dict):
        """获取或创建缓存内容"""
        import hashlib
        from google.genai import caching

        # 生成缓存键
        cache_key = hashlib.md5(f"{model_name}:{system_prompt}".encode()).hexdigest()

        # 检查是否已有缓存
        if cache_key in self._cached_content_store:
            cached = self._cached_content_store[cache_key]
            try:
                return cached
            except Exception:
                del self._cached_content_store[cache_key]

        # 创建新缓存
        try:
            cached_content = caching.CachedContent.create(
                model=model_name,
                config=caching.CreateCachedContentConfig(
                    system_instruction=system_prompt,
                    ttl="3600s",
                )
            )
            self._cached_content_store[cache_key] = cached_content
            return cached_content
        except Exception as e:
            # 缓存创建失败，禁用此API的缓存功能
            self._disable_cache_for_api(platform_config)
            self.warning(f"检测到API不支持上下文缓存功能，已自动关闭: {e}")
            return None

    # 发起请求
    def request_google(self, messages, system_prompt, platform_config) -> tuple[bool, str, str, int, int]:
        try:
            model_name = platform_config.get("model_name")
            temperature = platform_config.get("temperature", 1.0)
            top_p = platform_config.get("top_p", 1.0)
            presence_penalty = platform_config.get("presence_penalty", 0.0)
            frequency_penalty = platform_config.get("frequency_penalty", 0.0)
            think_switch = platform_config.get("think_switch")
            thinking_budget = platform_config.get("thinking_budget")
            enable_caching = platform_config.get("enable_prompt_caching", False)

            # 重新处理openai格式的消息为google格式
            processed_messages = [
                Content(
                    role="model" if m["role"] == "assistant" else m["role"],
                    parts=[Part.from_text(text=m["content"])]
                )
                for m in messages if m["role"] != "system"
            ]

            # 创建 Gemini Developer API 客户端（非 Vertex AI API）
            client = LLMClientFactory().get_google_client(platform_config)

            # 定义适用于文本模型的安全类别
            TEXT_HARM_CATEGORIES = [
                HarmCategory.HARM_CATEGORY_HARASSMENT,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            ]

            # 尝试使用缓存（检查是否被禁用）
            cached_content = None
            use_cache = enable_caching and self._is_cache_supported(platform_config)
            if use_cache and system_prompt:
                cached_content = self._get_or_create_cache(client, model_name, system_prompt, platform_config)

            # 构建基础配置
            gen_config = types.GenerateContentConfig(
                max_output_tokens=ModelConfigHelper.get_google_max_output_tokens(model_name),
                temperature=temperature,
                top_p=top_p,
                safety_settings=[
                    types.SafetySetting(category=category, threshold='BLOCK_NONE')
                    for category in TEXT_HARM_CATEGORIES
                ]
            )

            # 如果没有使用缓存，则设置系统指令
            if not cached_content:
                gen_config.system_instruction = system_prompt

            # 如果开启了思考模式，则添加思考配置
            if think_switch:
                gen_config.thinking_config = types.ThinkingConfig(
                    include_thoughts=True,
                    thinking_budget=thinking_budget
                )

            # 生成文本内容
            generate_params = {
                "contents": processed_messages,
                "config": gen_config,
            }

            # 如果有缓存，使用缓存的模型名称
            if cached_content:
                generate_params["model"] = cached_content.name
            else:
                generate_params["model"] = model_name

            response = client.models.generate_content(**generate_params)

            # 初始化思考内容和回复内容
            response_think = ""
            response_content = ""

            # 根据Google API文档，思考内容和回复内容在不同的 "parts" 中
            # 遍历这些 parts 来分别提取它们
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if not part.text:
                        continue
                    # 检查 part 是否包含思考内容 (part.thought is True)
                    # 使用 hasattr 增加代码健壮性
                    if hasattr(part, 'thought') and part.thought:
                        response_think += part.text
                    else:
                        # 否则，这是常规的回复内容
                        response_content += part.text
            else:
                # 作为后备方案，如果 response.candidates[0].content.parts 不存在或为空
                # 尝试直接获取 .text 属性，这通常只包含最终回复
                response_content = response.text

        except Exception as e:
            self.error(f"请求任务错误 ... {e}", e if self.is_debug() else None)
            return True, None, None, None, None

        # 获取指令消耗
        try:
            prompt_tokens = int(response.usage_metadata.prompt_token_count)
        except Exception:
            prompt_tokens = 0

        # 获取回复消耗
        try:
            completion_tokens = int(response.usage_metadata.candidates_token_count)
        except Exception:
            completion_tokens = 0

        return False, response_think, response_content, prompt_tokens, completion_tokens
