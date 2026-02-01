from ModuleFolders.Base.Base import Base
from ModuleFolders.Infrastructure.LLMRequester.LLMClientFactory import LLMClientFactory


# 接口请求器
class OpenaiRequester(Base):
    def __init__(self) -> None:
        pass

    # 发起请求
    def request_openai(self, messages, system_prompt, platform_config) -> tuple[bool, str, str, int, int]:
        try:
            # 获取具体配置
            model_name = platform_config.get("model_name")
            request_timeout = platform_config.get("request_timeout", 60)
            temperature = platform_config.get("temperature", 1.0)
            top_p = platform_config.get("top_p", 1.0)
            presence_penalty = platform_config.get("presence_penalty", 0)
            frequency_penalty = platform_config.get("frequency_penalty", 0)
            extra_body = platform_config.get("extra_body", {})
            think_switch = platform_config.get("think_switch")
            think_depth = platform_config.get("think_depth")

            # 插入系统消息
            if system_prompt:
                messages.insert(
                    0,
                    {
                        "role": "system",
                        "content": system_prompt
                    })

            # 从工厂获取客户端
            client = LLMClientFactory().get_openai_client(platform_config)

            # 针对ds模型的特殊处理，因为该模型不支持模型预输入回复
            if model_name and 'deepseek' in model_name.lower():
                # 检查一下最后的消息是否用户消息，以免误删。(用户使用了推理模型卻不切换为推理模型提示词的情况)
                if messages and isinstance(messages[-1], dict) and messages[-1].get('role') != 'user':
                    messages = messages[:-1]  # 移除最后一个元素


            # 参数基础配置
            base_params = {
                "extra_body": extra_body,
                "model": model_name,
                "messages": messages,
                "timeout": request_timeout,
                "stream": False
            }

            # 按需添加参数
            if temperature != 1:
                base_params.update({
                    "temperature": temperature,
                })

            if top_p != 1:
                base_params.update({
                    "top_p": top_p,
                })

            if presence_penalty != 0:
                base_params.update({
                    "presence_penalty": presence_penalty,
                })

            if frequency_penalty != 0:
                base_params.update({
                    "frequency_penalty": frequency_penalty
                })


            # 开启思考开关时添加参数
            if think_switch:
                base_params.update({
                    "reasoning_effort": think_depth
                })


            # 发起请求
            try:
                response = client.chat.completions.create(**base_params)
                # 提取回复内容
                message = response.choices[0].message

                # 自适应提取推理过程
                if message.content and "</think>" in message.content:
                    splited = message.content.split("</think>")
                    response_think = splited[0].removeprefix("<think>").replace("\n\n", "\n")
                    response_content = splited[-1]
                else:
                    try:
                        response_think = getattr(message, "reasoning_content", "")
                        if not response_think:
                            response_think = ""
                    except Exception:
                        response_think = ""
                    response_content = message.content
                
                # 安全获取消耗
                prompt_tokens = 0
                completion_tokens = 0
                if hasattr(response, "usage") and response.usage:
                    prompt_tokens = getattr(response.usage, "prompt_tokens", 0)
                    completion_tokens = getattr(response.usage, "completion_tokens", 0)

                return False, response_think, response_content, int(prompt_tokens), int(completion_tokens)

            except Exception as sdk_err:
                # 如果 SDK 请求失败，尝试使用 httpx 兼容 SSE 格式 (解决部分中转站强制 SSE 问题)
                if "expecting value" in str(sdk_err).lower() or "data:" in str(sdk_err).lower():
                    import httpx
                    import json
                    api_url = platform_config.get("api_url").rstrip('/') + "/chat/completions"
                    api_key = platform_config.get("api_key")
                    
                    auth_headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                    }
                    
                    with httpx.Client(timeout=request_timeout) as http_client:
                        resp = http_client.post(api_url, json=base_params, headers=auth_headers)
                        if resp.status_code == 200:
                            raw_text = resp.text.strip()
                            if raw_text.startswith("data:"):
                                # SSE 解析逻辑：遍历所有行并聚合内容
                                full_content = ""
                                full_think = ""
                                usage = {"prompt_tokens": 0, "completion_tokens": 0}
                                lines = raw_text.split("\n")
                                for line in lines:
                                    if line.startswith("data:"):
                                        json_str = line.replace("data:", "").strip()
                                        if json_str == "[DONE]": break
                                        try:
                                            res_json = json.loads(json_str)
                                            if isinstance(res_json, dict) and "choices" in res_json:
                                                choice = res_json["choices"][0]
                                                # 获取内容
                                                delta = choice.get("delta", {})
                                                c = delta.get("content", "")
                                                if c: full_content += c
                                                t = delta.get("reasoning_content", "")
                                                if t: full_think += t
                                            # SSE 模式下尝试在最后一个包获取 usage
                                            if isinstance(res_json, dict) and "usage" in res_json and res_json["usage"]:
                                                usage["prompt_tokens"] = res_json["usage"].get("prompt_tokens", 0)
                                                usage["completion_tokens"] = res_json["usage"].get("completion_tokens", 0)
                                        except: continue
                                return False, full_think, full_content, int(usage["prompt_tokens"]), int(usage["completion_tokens"])
                            else:
                                raise sdk_err
                        else:
                            raise sdk_err
                else:
                    raise sdk_err

        except Exception as e:
            error_str = str(e).lower()
            error_type = "GENERIC_FAIL"
            
            # 简单的关键词匹配来判断是否为 API/网络 错误
            api_error_keywords = [
                "429", "500", "502", "503", "timeout", "connection", 
                "rate limit", "service unavailable", "bad gateway",
                "api_key", "insufficient_quota" # 这些通常不需要重试，但也属于 API 错误，交给上层判断
            ]
            
            if any(k in error_str for k in api_error_keywords):
                error_type = "API_FAIL"
            
            if Base.work_status != Base.STATUS.STOPING:
                api_url = platform_config.get("api_url", "Unknown URL")
                model_name = platform_config.get("model_name", "Unknown Model")
                self.error(f"请求任务错误 ({error_type}) [URL: {api_url}, Model: {model_name}] ... {e}", e if self.is_debug() else None)
            else:
                self.print(f"[dim]Request aborted due to stop signal: {e}[/dim]")

            return True, error_type, str(e), 0, 0
