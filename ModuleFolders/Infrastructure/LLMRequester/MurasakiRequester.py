from ModuleFolders.Base.Base import Base
from ModuleFolders.Infrastructure.LLMRequester.LLMClientFactory import LLMClientFactory


class MurasakiRequester(Base):
    def __init__(self):
        pass

    def request_murasaki(self, messages, system_prompt, platform_config) -> tuple[bool, str, str, int, int]:
        if Base.work_status == Base.STATUS.STOPING or not Base.is_task_session_active():
            return True, "STOPPED", "Task stopped by user", 0, 0

        try:
            model_name = platform_config.get("model_name")
            request_timeout = platform_config.get("request_timeout", 120)
            temperature = platform_config.get("temperature", 0.6)
            top_p = platform_config.get("top_p", 0.9)
            frequency_penalty = platform_config.get("frequency_penalty", 0)

            if system_prompt:
                messages.insert(0, {"role": "system", "content": system_prompt})

            client = LLMClientFactory().get_openai_client_local(platform_config)

            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                top_p=top_p,
                temperature=temperature,
                frequency_penalty=frequency_penalty,
                timeout=request_timeout,
                **({"max_tokens": platform_config["max_output_tokens"]} if platform_config.get("max_output_tokens") is not None else {}),
            )

            if not Base.is_task_session_active():
                return True, "STOPPED", "Task stopped by user", 0, 0

            response_content = response.choices[0].message.content
        except Exception as e:
            if Base.work_status == Base.STATUS.STOPING or not Base.is_task_session_active():
                return True, "STOPPED", "Task stopped by user", 0, 0
            else:
                self.error(f"请求任务错误 ... {e}", e if self.is_debug() else None)
            return True, None, None, None, None

        # 获取token消耗
        try:
            prompt_tokens = int(response.usage.prompt_tokens)
        except Exception:
            prompt_tokens = 0
        try:
            completion_tokens = int(response.usage.completion_tokens)
        except Exception:
            completion_tokens = 0

        # 提取think内容
        response_think = ""
        if response_content and "</think>" in response_content:
            parts = response_content.split("</think>")
            response_think = parts[0].removeprefix("<think>").replace("\n\n", "\n")
            response_content = parts[-1]

        # 同Sakura，包裹textarea标签方便提取
        response_content = "<textarea>\n" + response_content + "\n</textarea>"

        return False, response_think, response_content, prompt_tokens, completion_tokens
