from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from ModuleFolders.MangaCore.project.textBlock import MangaTextBlock


TEXT_QA_ARTIFACT = "textQaResults.json"

_HIRAGANA_KATAKANA_RE = re.compile(r"[\u3040-\u30ff]")
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_REPEATED_PUNCTUATION_RE = re.compile(r"([。！？!?…~～])\1{3,}")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(slots=True)
class TextQaIssue:
    code: str
    block_id: str
    severity: str
    message: str
    blocks_final: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class TextQaResult:
    issues: list[TextQaIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(issue.blocks_final for issue in self.issues)

    @property
    def blocking_count(self) -> int:
        return sum(1 for issue in self.issues if issue.blocks_final)

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if not issue.blocks_final)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "issue_count": len(self.issues),
            "blocking_count": self.blocking_count,
            "warning_count": self.warning_count,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _normalize_for_compare(value: str) -> str:
    return _WHITESPACE_RE.sub("", value or "").strip().lower()


def _target_family(target_lang: str) -> str:
    token = str(target_lang or "").strip().lower().replace("-", "_")
    if token in {"zh", "zh_cn", "zh_hans", "chinese", "chinese_simplified"}:
        return "zh_hans"
    if token in {"zh_tw", "zh_hant", "chinese_traditional"}:
        return "zh_hant"
    if token in {"en", "english"}:
        return "latin"
    if token in {"ja", "jp", "japanese"}:
        return "ja"
    return token


def _is_latin_only(text: str) -> bool:
    has_latin = bool(_LATIN_RE.search(text))
    return has_latin and not bool(_CJK_RE.search(text))


def _append_flag(block: MangaTextBlock, flag: str) -> None:
    if flag not in block.flags:
        block.flags.append(flag)


def evaluate_text_qa(
    blocks: list[MangaTextBlock],
    *,
    source_lang: str = "",
    target_lang: str = "",
    mutate_blocks: bool = True,
) -> TextQaResult:
    issues: list[TextQaIssue] = []
    target = _target_family(target_lang)

    for block in blocks:
        source_text = str(block.source_text or "")
        translation = str(block.translation or "")
        normalized_source = _normalize_for_compare(source_text)
        normalized_translation = _normalize_for_compare(translation)
        block_codes: list[str] = []

        if not normalized_translation:
            issues.append(
                TextQaIssue(
                    code="translation_empty",
                    block_id=block.block_id,
                    severity="error",
                    message="Translated text is empty.",
                )
            )
            block_codes.append("translation_empty")
        elif normalized_source and normalized_source == normalized_translation:
            issues.append(
                TextQaIssue(
                    code="translation_same_as_source",
                    block_id=block.block_id,
                    severity="error",
                    message="Translated text is identical to the OCR source text.",
                )
            )
            block_codes.append("translation_same_as_source")

        if target in {"zh_hans", "zh_hant"} and _HIRAGANA_KATAKANA_RE.search(translation):
            issues.append(
                TextQaIssue(
                    code="target_japanese_residue",
                    block_id=block.block_id,
                    severity="error",
                    message="Chinese target text still contains Japanese kana.",
                )
            )
            block_codes.append("target_japanese_residue")

        if _REPEATED_PUNCTUATION_RE.search(translation):
            issues.append(
                TextQaIssue(
                    code="punctuation_repeated",
                    block_id=block.block_id,
                    severity="warning",
                    message="Translated text contains repeated punctuation that should be reviewed.",
                    blocks_final=False,
                )
            )
            block_codes.append("punctuation_repeated")

        if (
            str(block.rendered_direction or "").lower() == "vertical"
            and target == "latin"
            and _is_latin_only(translation)
        ):
            issues.append(
                TextQaIssue(
                    code="latin_vertical_layout",
                    block_id=block.block_id,
                    severity="error",
                    message="Latin target text is set to vertical layout.",
                )
            )
            block_codes.append("latin_vertical_layout")

        if mutate_blocks:
            block.flags = [flag for flag in block.flags if not flag.startswith("text_qa:")]
            for code in sorted(set(block_codes)):
                _append_flag(block, f"text_qa:{code}")

    return TextQaResult(issues=issues)
