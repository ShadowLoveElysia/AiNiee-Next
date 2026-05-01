from __future__ import annotations


def _arg_or_config(host_config: dict[str, object], args, key: str, default: str) -> str:
    value = getattr(args, key, None) or host_config.get(key) or default
    return str(value).strip()


def build_cli_config_snapshot(host, args) -> dict[str, object]:
    config = getattr(host, "config", {}) or {}
    root_config = getattr(host, "root_config", {}) or {}
    return {
        "task": getattr(args, "task", ""),
        "input_path": getattr(args, "input_path", ""),
        "output_path": config.get("label_output_path", ""),
        "source_lang": getattr(args, "source_lang", None) or config.get("source_language", "ja"),
        "target_lang": getattr(args, "target_lang", None) or config.get("target_language", "zh_cn"),
        "profile_name": getattr(args, "profile", None) or root_config.get("active_profile", "default"),
        "rules_profile_name": getattr(args, "rules_profile", None) or root_config.get("active_rules_profile", "default"),
        "platform": getattr(args, "platform", None) or config.get("target_platform", ""),
        "model": getattr(args, "model", None) or config.get("model", ""),
        "api_url": getattr(args, "api_url", None) or config.get("base_url", ""),
        "manga_ocr_engine": _arg_or_config(config, args, "manga_ocr_engine", "paddleocr-vl-1.5"),
        "manga_detect_engine": _arg_or_config(config, args, "manga_detect_engine", "comic-text-bubble-detector"),
        "manga_segment_engine": _arg_or_config(config, args, "manga_segment_engine", "comic-text-detector"),
        "manga_inpaint_engine": _arg_or_config(config, args, "manga_inpaint_engine", "aot-inpainting"),
        "web_mode": bool(getattr(args, "web_mode", False)),
        "manga": bool(getattr(args, "manga", False)),
    }
