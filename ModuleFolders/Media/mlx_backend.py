"""Apple MLX text inference using locally installed Index Qwen3.5 weights."""

from pathlib import Path
import json
import time

from ModuleFolders.Media.local_backends import translation_prompt


class MlxTextTranslator:
    def __init__(self, model_dir, *, family="index", max_new_tokens=256, on_partial=None):
        import mlx.core as mx
        from mlx_lm import load
        from ModuleFolders.Media.model_catalog import get_model

        checkpoint = get_model(family)
        if checkpoint.family != "index" or checkpoint.backend != "transformers":
            raise ValueError("MLX currently supports Index Transformers checkpoints")
        if max_new_tokens <= 0:
            raise ValueError("Output budget must be positive")
        root = Path(model_dir).expanduser().resolve()
        if not root.is_dir():
            raise FileNotFoundError(root)
        config = json.loads((root / "config.json").read_text(encoding="utf-8"))
        if config.get("model_type") != "qwen3_5":
            raise ValueError("This Index checkpoint is not a supported MLX Qwen3.5 model; select Metal GGUF or MPS")
        if not mx.metal.is_available():
            raise RuntimeError("MLX Metal GPU is unavailable; use native arm64 Python on Apple Silicon")
        mx.set_default_device(mx.gpu)
        self.model, self.tokenizer = load(str(root), tokenizer_config={"local_files_only": True})
        self.name = checkpoint.name.lower() + "-mlx"
        self.family = checkpoint.family
        self.max_new_tokens = max_new_tokens
        self.on_partial = on_partial

    def translate(self, text, *, source_lang, target_lang, context):
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler

        prompt = translation_prompt(text, family=self.family, source_lang=source_lang,
                                    target_lang=target_lang, context=context)
        tokens = self.tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}], tokenize=True,
            add_generation_prompt=True, enable_thinking=False,
        )
        result = ""
        self.last_metrics = {}
        started = time.perf_counter()
        for response in stream_generate(self.model, self.tokenizer, prompt=tokens,
                                        max_tokens=self.max_new_tokens, sampler=make_sampler(temp=0)):
            if response.finish_reason == "length":
                raise RuntimeError("Translation reached its token limit; shorten the audio segment")
            if response.text:
                self.last_metrics.setdefault("first_text_ms", round((time.perf_counter() - started) * 1000, 2))
                result += response.text
                if self.on_partial:
                    self.on_partial(result)
        self.last_metrics["final_ms"] = round((time.perf_counter() - started) * 1000, 2)
        if "</think>" in result:
            result = result.split("</think>", 1)[1]
        if not result.strip():
            raise RuntimeError("MLX returned an empty translation")
        return result.strip()
