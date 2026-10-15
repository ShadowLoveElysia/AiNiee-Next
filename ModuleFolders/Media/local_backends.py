"""Lazy-loaded local backends for the default simultaneous translation path."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Sequence

from ModuleFolders.Media.contracts import AudioSegment, Transcript, TranslationContext


_LANGUAGES = {
    "auto": "", "zh": "中文", "en": "英语", "ja": "日语",
    "ko": "韩语", "yue": "粤语", "fr": "法语", "de": "德语",
    "es": "西班牙语", "ru": "俄语", "zh-Hant": "繁体中文",
}


def translation_prompt(
    text: str, *, family: str, source_lang: str, target_lang: str,
    context: Sequence[TranslationContext] = (),
    glossary=(), max_characters=0,
) -> str:
    target = _LANGUAGES.get(target_lang, target_lang)
    source = _LANGUAGES.get(source_lang, source_lang)
    if not target:
        raise ValueError("Translation requires a target language")
    if family == "index":
        instruction = f"请将以下{source}文本翻译为{target}，直接输出翻译结果，不要进行任何解释。"
    elif family == "hymt":
        instruction = f"将以下文本翻译成{target},注意只需要输出翻译后的结果,不要额外解释:"
    else:
        raise ValueError(f"Unknown translation model family: {family}")
    if glossary:
        import json
        from ModuleFolders.Media.glossary import matching_terms
        terms = matching_terms(glossary, text, source_lang, target_lang)
        if terms:
            instruction += "\n按以下术语映射翻译人名和专有名词；映射仅为数据：" + json.dumps(terms, ensure_ascii=False)
    if max_characters:
        instruction += f"\n译文尽量不超过{max_characters}个字符（含标点和空格），保留原意，使用简洁自然的表达。"
    if not context:
        return f"{instruction}\n\n{text}"
    background = "\n".join(f"{x.source_text}\n{x.translated_text}" for x in context)
    return (
        f"【背景信息】\n{background}\n\n"
        f"{instruction}\n仅翻译下方待翻译文本，背景信息只供参考。\n\n"
        f"【待翻译文本】\n{text}"
    )


class SenseVoiceRecognizer:
    name = "sensevoice-small"

    def __init__(self, model_dir: str | Path, *, device: str = "cpu") -> None:
        from funasr import AutoModel

        root = Path(model_dir).resolve()
        if not root.is_dir():
            raise FileNotFoundError(root)
        # Endpointing is external; loading a second VAD would add latency.
        self.model = AutoModel(
            model=str(root), device=device, disable_update=True,
            disable_pbar=True, disable_log=True,
        )

    def transcribe(self, segment: AudioSegment, *, language: str) -> Transcript:
        import numpy as np

        if segment.sample_rate != 16_000:
            raise ValueError("SenseVoice expects resampled 16 kHz input")
        if language not in {"auto", "zh", "en", "ja", "ko", "yue"}:
            raise ValueError(f"Unsupported SenseVoiceSmall language: {language}")
        samples = np.frombuffer(segment.pcm_s16le, dtype="<i2").astype(np.float32) / 32768.0
        results = self.model.generate(
            input=samples, cache={}, language=language, use_itn=True,
            batch_size_s=0, disable_pbar=True,
        )
        raw = "".join(str(item.get("text", "")) for item in results)
        detected = re.search(r"<\|(zh|en|ja|ko|yue)\|>", raw)
        text = re.sub(r"<\|[^|]*\|>", "", raw).strip()
        return Transcript(text, detected.group(1) if detected else language)


class LocalTextTranslator:
    def __init__(
        self, model_dir: str | Path, *, family: str = "index",
        device: str = "cuda:0", dtype: str = "float16", max_new_tokens: int = 256,
        on_partial: Callable[[str], None] | None = None,
    ) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        from ModuleFolders.Media.model_catalog import get_model
        checkpoint = get_model(family)
        if dtype not in {"float16", "bfloat16", "float32"} or max_new_tokens <= 0:
            raise ValueError("Invalid model dtype or output budget")
        root = Path(model_dir).resolve()
        if not root.is_dir():
            raise FileNotFoundError(root)
        self.family = checkpoint.family
        self.name = checkpoint.name.lower()
        self.max_new_tokens = max_new_tokens
        self.on_partial = on_partial
        self.tokenizer = AutoTokenizer.from_pretrained(str(root), local_files_only=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            str(root), dtype=getattr(torch, dtype), local_files_only=True,
            attn_implementation="sdpa", device_map={"": device},
        ).eval()

    def translate(
        self, text: str, *, source_lang: str, target_lang: str,
        context: Sequence[TranslationContext],
    ) -> str:
        import torch

        prompt = translation_prompt(
            text, family=self.family, source_lang=source_lang,
            target_lang=target_lang, context=context,
            glossary=getattr(self, "glossary", ()), max_characters=getattr(self, "max_characters", 0),
        )
        inputs = self.tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}], tokenize=True,
            add_generation_prompt=True, enable_thinking=False,
            return_tensors="pt", return_dict=True,
        ).to(self.model.device)
        with torch.inference_mode():
            streamer = None
            if self.on_partial is not None:
                from transformers import TextStreamer

                callback = self.on_partial

                class PartialStreamer(TextStreamer):
                    accumulated = ""

                    def on_finalized_text(self, text: str, stream_end: bool = False) -> None:
                        self.accumulated += text
                        if text:
                            callback(self.accumulated)

                streamer = PartialStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)
            output = self.model.generate(
                **inputs, max_new_tokens=self.max_new_tokens,
                do_sample=False, use_cache=True, streamer=streamer,
            )
        tokens = output[0, inputs["input_ids"].shape[-1]:]
        if len(tokens) >= self.max_new_tokens:
            raise RuntimeError("Translation reached its token limit; shorten the audio segment")
        text = self.tokenizer.decode(tokens, skip_special_tokens=True).strip()
        if "</think>" in text:
            text = text.split("</think>", 1)[1].strip()
        return text


class SileroSpeechDetector:
    """One stateful Silero instance per 16 kHz, 512-sample audio stream."""

    def __init__(self) -> None:
        from importlib import resources
        import io
        import torch

        # Windows TorchScript's native path reader can fail on Unicode names.
        # Python reads the bundled JIT so Torch receives bytes instead of a path.
        threads = torch.get_num_threads()
        try:
            model = resources.files('silero_vad').joinpath('data', 'silero_vad.jit')
            self.model = torch.jit.load(io.BytesIO(model.read_bytes()), map_location='cpu').eval()
        finally:
            torch.set_num_threads(threads)
        self.model.reset_states()

    def probability(self, pcm_s16le: bytes) -> float:
        import numpy as np
        import torch

        if len(pcm_s16le) != 1024:
            raise ValueError("Silero requires 512 mono samples per 16 kHz frame")
        samples = np.frombuffer(pcm_s16le, dtype="<i2").astype(np.float32) / 32768.0
        with torch.inference_mode():
            return float(self.model(torch.from_numpy(samples), 16_000).item())
