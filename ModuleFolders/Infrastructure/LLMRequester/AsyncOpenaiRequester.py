"""
异步 OpenAI 请求器 - 基于 aiohttp 的高并发优化方案

解决痛点：
- 100+ 并发时线程切换开销大
- 同步请求阻塞线程资源
- 连接池管理不够高效

优势：
- 单线程处理大量并发请求
- 复用 TCP 连接，减少握手开销
- 更低的内存占用
"""

import asyncio
import hashlib
import json
from typing import Optional, Dict, Any, Tuple

import aiohttp

from ModuleFolders.Base.Base import Base
from ModuleFolders.Infrastructure.LLMRequester.ErrorClassifier import ErrorClassifier, ErrorType
from ModuleFolders.Infrastructure.LLMRequester.ProviderFingerprint import ProviderFingerprint, FeatureSupport
from ModuleFolders.Infrastructure.LLMRequester.AsyncSignalHub import get_signal_hub


class AsyncOpenaiRequester(Base):
    """异步 OpenAI 请求器"""

    # 类级别的连接池（全局复用）
    _session: Optional[aiohttp.ClientSession] = None
    _session_lock = asyncio.Lock()

    def __init__(self) -> None:
        super().__init__()

    @classmethod
    async def get_session(cls) -> aiohttp.ClientSession:
        """获取或创建全局 aiohttp 会话（连接池）"""
        if cls._session is None or cls._session.closed:
            async with cls._session_lock:
                if cls._session is None or cls._session.closed:
                    # 配置连接池参数
                    connector = aiohttp.TCPConnector(
                        limit=200,  # 最大连接数
                        limit_per_host=50,  # 每个主机最大连接数
                        ttl_dns_cache=300,  # DNS 缓存时间
                        enable_cleanup_closed=True,
                    )
                    timeout = aiohttp.ClientTimeout(
                        total=300,  # 总超时
                        connect=30,  # 连接超时
                        sock_read=120,  # 读取超时
                    )
                    cls._session = aiohttp.ClientSession(
                        connector=connector,
                        timeout=timeout,
                    )
        return cls._session

    @classmethod
    async def close_session(cls) -> None:
        """关闭全局会话"""
        if cls._session and not cls._session.closed:
            await cls._session.close()
            cls._session = None

    def _get_api_cache_key(self, api_url: str, model_name: str) -> str:
        """生成API缓存键"""
        key_str = f"{api_url}:{model_name}"
        return hashlib.md5(key_str.encode()).hexdigest()[:16]

    def _get_stream_support_status(self, api_url: str, model_name: str) -> Optional[bool]:
        """获取API的流式支持状态"""
        config = self.load_config()
        cache = config.get("stream_api_cache", {})
        cache_key = self._get_api_cache_key(api_url, model_name)
        return cache.get(cache_key)

    def _set_stream_support_status(self, api_url: str, model_name: str, supports_stream: bool) -> None:
        """设置API的流式支持状态"""
        config = self.load_config()
        cache = config.get("stream_api_cache", {})
        cache_key = self._get_api_cache_key(api_url, model_name)
        cache[cache_key] = supports_stream
        config["stream_api_cache"] = cache
        self.save_config(config)

    def _parse_sse_response(self, raw_text: str) -> Tuple[str, str, int, int]:
        """解析SSE格式响应"""
        full_content = ""
        full_think = ""
        usage = {"prompt_tokens": 0, "completion_tokens": 0}

        for line in raw_text.split("\n"):
            if line.startswith("data:"):
                json_str = line[5:].strip()
                if json_str == "[DONE]":
                    break
                try:
                    res_json = json.loads(json_str)
                    if isinstance(res_json, dict) and "choices" in res_json:
                        choice = res_json["choices"][0]
                        delta = choice.get("delta", {})
                        if c := delta.get("content", ""):
                            full_content += c
                        if t := delta.get("reasoning_content", ""):
                            full_think += t
                    if isinstance(res_json, dict) and res_json.get("usage"):
                        usage["prompt_tokens"] = res_json["usage"].get("prompt_tokens", 0)
                        usage["completion_tokens"] = res_json["usage"].get("completion_tokens", 0)
                except json.JSONDecodeError:
                    continue

        return full_think, full_content, usage["prompt_tokens"], usage["completion_tokens"]

    def _parse_json_response(self, response_json: dict) -> Tuple[str, str, int, int]:
        """解析JSON格式响应"""
        message = response_json["choices"][0]["message"]
        content = message.get("content", "")

        response_think = ""
        response_content = content

        if content and "</think>" in content:
            splited = content.split("</think>")
            response_think = splited[0].removeprefix("<think>").replace("\n\n", "\n")
            response_content = splited[-1]
        else:
            response_think = message.get("reasoning_content", "")

        prompt_tokens = response_json.get("usage", {}).get("prompt_tokens", 0)
        completion_tokens = response_json.get("usage", {}).get("completion_tokens", 0)

        return response_think, response_content, prompt_tokens, completion_tokens

    async def _do_request_async(
        self,
        api_url: str,
        api_key: str,
        request_body: dict,
        request_timeout: int,
        use_stream: bool
    ) -> Tuple[bool, str, str, int, int]:
        """执行异步HTTP请求"""
        request_body["stream"] = use_stream
        if use_stream:
            request_body["stream_options"] = {"include_usage": True}

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        session = await self.get_session()

        # 创建请求特定的超时
        timeout = aiohttp.ClientTimeout(total=request_timeout)

        async with session.post(
            api_url,
            json=request_body,
            headers=headers,
            timeout=timeout
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise Exception(f"HTTP {resp.status}: {error_text}")

            raw_text = await resp.text()
            raw_text = raw_text.strip()

            if raw_text.startswith("data:"):
                think, content, pt, ct = self._parse_sse_response(raw_text)
                return False, think, content, pt, ct
            else:
                response_json = json.loads(raw_text)
                think, content, pt, ct = self._parse_json_response(response_json)
                return False, think, content, pt, ct

    async def request_openai_async(
        self,
        messages: list,
        system_prompt: str,
        platform_config: dict
    ) -> Tuple[bool, str, str, int, int]:
        """异步发起 OpenAI 请求"""
        try:
            # 获取配置
            model_name = platform_config.get("model_name")
            request_timeout = platform_config.get("request_timeout", 60)
            temperature = platform_config.get("temperature", 1.0)
            top_p = platform_config.get("top_p", 1.0)
            presence_penalty = platform_config.get("presence_penalty", 0)
            frequency_penalty = platform_config.get("frequency_penalty", 0)
            extra_body = platform_config.get("extra_body", {})
            think_switch = platform_config.get("think_switch")
            think_depth = platform_config.get("think_depth")
            enable_stream = platform_config.get("enable_stream_api", True)

            # 插入系统消息
            if system_prompt:
                messages = [{"role": "system", "content": system_prompt}] + messages

            # 针对 deepseek 模型的特殊处理
            if model_name and 'deepseek' in model_name.lower():
                if messages and isinstance(messages[-1], dict) and messages[-1].get('role') != 'user':
                    messages = messages[:-1]

            # 构建请求体
            request_body = {
                "model": model_name,
                "messages": messages,
            }

            if extra_body and isinstance(extra_body, dict):
                request_body.update(extra_body)

            if temperature != 1:
                request_body["temperature"] = temperature
            if top_p != 1:
                request_body["top_p"] = top_p
            if presence_penalty != 0:
                request_body["presence_penalty"] = presence_penalty
            if frequency_penalty != 0:
                request_body["frequency_penalty"] = frequency_penalty
            if think_switch:
                request_body["reasoning_effort"] = think_depth

            # 处理 API URL
            api_url = platform_config.get("api_url").rstrip('/')
            if platform_config.get("auto_complete", False) and not api_url.endswith('/chat/completions'):
                api_url = f"{api_url}/chat/completions"
            api_key = platform_config.get("api_key")

            # 智能流式判断
            if enable_stream:
                stream_status = self._get_stream_support_status(api_url, model_name)

                if stream_status is True:
                    return await self._do_request_async(api_url, api_key, request_body, request_timeout, True)
                elif stream_status is False:
                    return await self._do_request_async(api_url, api_key, request_body, request_timeout, False)
                else:
                    # 未知状态，尝试流式
                    try:
                        result = await self._do_request_async(
                            api_url, api_key, request_body.copy(), request_timeout, True
                        )
                        self._set_stream_support_status(api_url, model_name, True)
                        return result
                    except Exception as stream_error:
                        error_str = str(stream_error).lower()
                        stream_error_keywords = ["stream", "unsupported", "not supported", "invalid"]
                        if any(k in error_str for k in stream_error_keywords):
                            try:
                                result = await self._do_request_async(
                                    api_url, api_key, request_body.copy(), request_timeout, False
                                )
                                self._set_stream_support_status(api_url, model_name, False)
                                return result
                            except Exception as non_stream_error:
                                raise non_stream_error
                        else:
                            raise stream_error
            else:
                return await self._do_request_async(api_url, api_key, request_body, request_timeout, False)

        except Exception as e:
            error_str = str(e)
            error_type_enum, reason = ErrorClassifier.classify(error_str)

            # 根据错误分类决定处理策略
            if error_type_enum == ErrorType.HARD_ERROR:
                error_type = "HARD_ERROR"
                # 检查是否为缓存相关错误，更新 Provider 指纹
                api_url = platform_config.get("api_url", "")
                if ErrorClassifier.is_cache_related_error(error_str):
                    fingerprint = ProviderFingerprint()
                    fingerprint.mark_cache_unsupported(api_url, error_str)
            elif error_type_enum == ErrorType.SOFT_ERROR:
                error_type = "SOFT_ERROR"
                # 软伤错误：广播限流信号
                if ErrorClassifier.should_reduce_concurrency(error_str):
                    signal_hub = get_signal_hub()
                    api_url = platform_config.get("api_url", "")
                    signal_hub.broadcast_rate_limit(api_url)
            else:
                error_type = "UNKNOWN_ERROR"

            if Base.work_status != Base.STATUS.STOPING:
                api_url = platform_config.get("api_url", "Unknown URL")
                model_name = platform_config.get("model_name", "Unknown Model")
                self.error(f"Async request error ({error_type}) [URL: {api_url}, Model: {model_name}] ... {e}")

            return True, error_type, str(e), 0, 0
