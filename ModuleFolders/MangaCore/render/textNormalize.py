from __future__ import annotations

import re

_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uff00-\uffef]")
_SPACE_RE = re.compile(r"[ \t\r\f\v]+")
_LINEBREAK_RE = re.compile(r"\s*\n+\s*")


def normalize_manga_dialogue_for_translation(text: str) -> str:
    return _normalize_dialogue_text(text, preserve_semantic_breaks=False)


def normalize_manga_dialogue_for_layout(text: str, *, direction: str = "horizontal") -> str:
    preserve_breaks = str(direction or "").lower() != "vertical"
    return _normalize_dialogue_text(text, preserve_semantic_breaks=preserve_breaks)


def _normalize_dialogue_text(text: str, *, preserve_semantic_breaks: bool) -> str:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = _SPACE_RE.sub(" ", normalized)
    normalized = normalized.strip()
    if not normalized:
        return ""

    if preserve_semantic_breaks:
        lines = [_normalize_dialogue_line(line) for line in normalized.splitlines()]
        return "\n".join(line for line in lines if line)

    normalized = _LINEBREAK_RE.sub(_line_joiner(normalized), normalized)
    normalized = _normalize_dialogue_line(normalized)
    normalized = re.sub(r"\.{3,}|。{3,}|…{2,}", "……", normalized)
    normalized = re.sub(r"・{2,}|·{2,}", "……", normalized)
    return normalized


def _normalize_dialogue_line(text: str) -> str:
    text = _SPACE_RE.sub(" ", text).strip()
    text = re.sub(r"\s+([，。！？、；：…])", r"\1", text)
    text = re.sub(r"([（「『《])\s+", r"\1", text)
    text = re.sub(r"\s+([）」』》])", r"\1", text)
    if _CJK_RE.search(text):
        text = re.sub(r"(?<=[\u3040-\u30ff\u3400-\u9fff\uff00-\uffef])\s+(?=[\u3040-\u30ff\u3400-\u9fff\uff00-\uffef])", "", text)
    return text


def _line_joiner(text: str) -> str:
    return "" if _CJK_RE.search(text) else " "
