from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ModuleFolders.MangaCore.pipeline.engines.detect import DetectResult
from ModuleFolders.MangaCore.pipeline.engines.inpaint import InpaintResult
from ModuleFolders.MangaCore.pipeline.engines.render import RenderResult
from ModuleFolders.MangaCore.pipeline.engines.translate import TranslationBatchResult
from ModuleFolders.MangaCore.project.page import MangaPage
from ModuleFolders.MangaCore.project.session import MangaProjectSession

QUALITY_GATE_ARTIFACT = "qualityGate.json"
BLOCKED_PAGE_STATUS = "needs_review"


@dataclass(slots=True)
class QualityIssue:
    code: str
    stage: str
    message_key: str
    message: str
    message_args: list[object] = field(default_factory=list)
    blocks_final: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class PageQualityGate:
    ok: bool
    final_allowed: bool
    issues: list[QualityIssue] = field(default_factory=list)
    metrics: dict[str, object] = field(default_factory=dict)
    stage_modes: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "final_allowed": self.final_allowed,
            "issues": [issue.to_dict() for issue in self.issues],
            "metrics": dict(self.metrics),
            "stage_modes": dict(self.stage_modes),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "PageQualityGate":
        issues_payload = payload.get("issues") if isinstance(payload.get("issues"), list) else []
        issues = [
            QualityIssue(
                code=str(issue.get("code", "")),
                stage=str(issue.get("stage", "")),
                message_key=str(issue.get("message_key", "")),
                message=str(issue.get("message", "")),
                message_args=list(issue.get("message_args", [])) if isinstance(issue.get("message_args"), list) else [],
                blocks_final=bool(issue.get("blocks_final", True)),
            )
            for issue in issues_payload
            if isinstance(issue, dict)
        ]
        return cls(
            ok=bool(payload.get("ok")),
            final_allowed=bool(payload.get("final_allowed")),
            issues=issues,
            metrics=dict(payload.get("metrics")) if isinstance(payload.get("metrics"), dict) else {},
            stage_modes=dict(payload.get("stage_modes")) if isinstance(payload.get("stage_modes"), dict) else {},
        )


def _issue(
    code: str,
    stage: str,
    message_key: str,
    message: str,
    *message_args: object,
    blocks_final: bool = True,
) -> QualityIssue:
    return QualityIssue(
        code=code,
        stage=stage,
        message_key=message_key,
        message=message,
        message_args=list(message_args),
        blocks_final=blocks_final,
    )


LAYOUT_BLOCKING_WARNING_CODES = {
    "layout_overflow",
    "layout_truncated",
    "font_too_small",
    "font_scaled_too_small",
    "font_scaled_too_large",
}


def _layout_warning_codes(layout_warnings: list[dict[str, object]]) -> set[str]:
    codes: set[str] = set()
    for item in layout_warnings:
        warnings = item.get("warnings") if isinstance(item, dict) else None
        if not isinstance(warnings, list):
            continue
        codes.update(str(warning) for warning in warnings if str(warning or "").strip())
    return codes


def _is_detect_fallback(result: DetectResult) -> bool:
    return result.runtime_detector_id == "heuristic-grouping" or result.runtime_segmenter_id == "pil-mask-rasterizer"


def _is_inpaint_runtime(runtime_engine_id: str) -> bool:
    return not (
        runtime_engine_id == "copy-source"
        or runtime_engine_id.startswith("opencv-")
        or runtime_engine_id.startswith("pil-")
    )


def _cleanup_text_region_count(result: DetectResult) -> int:
    return len(result.cleanup_text_regions)


def _ocr_candidate_region_count(result: DetectResult) -> int:
    return len(result.ocr_candidate_regions)


def describe_ocr_last_run(ocr_engine: object) -> dict[str, object]:
    if hasattr(ocr_engine, "describe_last_run"):
        try:
            payload = ocr_engine.describe_last_run()  # type: ignore[attr-defined]
            if isinstance(payload, dict):
                return payload
        except Exception:
            return {
                "configured_engine_id": ocr_engine.__class__.__name__,
                "runtime_engine_id": "unknown",
                "used_runtime": False,
                "warning_message": "Unable to describe OCR runtime.",
            }
    return {
        "configured_engine_id": ocr_engine.__class__.__name__,
        "runtime_engine_id": ocr_engine.__class__.__name__,
        "used_runtime": True,
        "warning_message": "",
        "custom_engine": True,
    }


def evaluate_automatic_pipeline_quality(
    *,
    detect_result: DetectResult,
    ocr_last_run: dict[str, object],
    inpaint_result: InpaintResult | None,
    render_result: RenderResult | None = None,
    block_count: int,
    translated_blocks: int,
    translation_result: TranslationBatchResult | None,
    require_inpaint: bool,
) -> PageQualityGate:
    issues: list[QualityIssue] = []

    if block_count <= 0:
        issues.append(
            _issue(
                "no_text_blocks",
                "planner",
                "manga_quality_issue_no_text_blocks",
                "No editable text blocks were generated.",
            )
        )

    cleanup_text_region_count = _cleanup_text_region_count(detect_result)
    ocr_candidate_region_count = _ocr_candidate_region_count(detect_result)
    if not detect_result.ok or cleanup_text_region_count <= 0:
        issues.append(
            _issue(
                "detect_no_text_regions",
                "detect",
                "manga_quality_issue_detect_no_text_regions",
                "Detect produced no cleanup text regions.",
            )
        )
    if _is_detect_fallback(detect_result):
        issues.append(
            _issue(
                "detect_fallback",
                "detect",
                "manga_quality_issue_detect_fallback",
                "Detect used heuristic fallback instead of a configured runtime.",
            )
        )

    if ocr_last_run and not bool(ocr_last_run.get("used_runtime", False)):
        issues.append(
            _issue(
                "ocr_fallback",
                "ocr",
                "manga_quality_issue_ocr_fallback",
                "OCR used a fallback adapter instead of a configured runtime.",
            )
        )

    if translation_result is not None:
        if not translation_result.ok:
            message = translation_result.error_message or "Translation completed with warnings."
            issues.append(
                _issue(
                    "translation_warning",
                    "translate",
                    "manga_quality_issue_translation_warning",
                    message,
                )
            )
        if block_count > 0 and translated_blocks < block_count:
            issues.append(
                _issue(
                    "translation_incomplete",
                    "translate",
                    "manga_quality_issue_translation_incomplete",
                    f"Only translated {translated_blocks}/{block_count} text block(s).",
                    translated_blocks,
                    block_count,
                )
            )

    if require_inpaint:
        if inpaint_result is None:
            issues.append(
                _issue(
                    "inpaint_not_run",
                    "inpaint",
                    "manga_quality_issue_inpaint_not_run",
                    "Inpaint was required before automatic final render.",
                )
            )
        else:
            if block_count > 0 and inpaint_result.mask_pixels <= 0:
                issues.append(
                    _issue(
                        "inpaint_empty_mask",
                        "inpaint",
                        "manga_quality_issue_inpaint_empty_mask",
                        "Inpaint mask is empty while translated text blocks exist; source text may remain visible.",
                    )
                )
            if not _is_inpaint_runtime(inpaint_result.runtime_engine_id):
                issues.append(
                    _issue(
                        "inpaint_fallback",
                        "inpaint",
                        "manga_quality_issue_inpaint_fallback",
                        f"Inpaint used fallback mode `{inpaint_result.runtime_engine_id}`.",
                        inpaint_result.runtime_engine_id,
                    )
                )

    if render_result is not None:
        if render_result.layout_fit_failed_blocks > 0:
            issues.append(
                _issue(
                    "layout_fit_failed",
                    "render",
                    "manga_quality_issue_layout_fit_failed",
                    f"Layout failed to fit {render_result.layout_fit_failed_blocks} text block(s).",
                    render_result.layout_fit_failed_blocks,
                )
            )
        layout_warnings = render_result.layout_warnings or []
        if layout_warnings:
            warning_count = len(layout_warnings)
            warning_codes = _layout_warning_codes(layout_warnings)
            blocking_warning_codes = sorted(warning_codes & LAYOUT_BLOCKING_WARNING_CODES)
            if blocking_warning_codes:
                issues.append(
                    _issue(
                        "layout_warning_blocking",
                        "render",
                        "manga_quality_issue_layout_warning_blocking",
                        f"Render produced blocking layout warning(s) for {warning_count} text block(s): {', '.join(blocking_warning_codes)}.",
                        warning_count,
                        ", ".join(blocking_warning_codes),
                    )
                )
            issues.append(
                _issue(
                    "layout_warning",
                    "render",
                    "manga_quality_issue_layout_warning",
                    f"Render produced layout warning(s) for {warning_count} text block(s).",
                    warning_count,
                    blocks_final=False,
                )
            )

    blocking_issues = [issue for issue in issues if issue.blocks_final]
    final_allowed = not blocking_issues
    metrics = {
        "block_count": block_count,
        "translated_blocks": translated_blocks,
        "detect_text_region_count": cleanup_text_region_count,
        "detect_ocr_candidate_region_count": ocr_candidate_region_count,
        "detect_region_count": len(detect_result.text_regions),
        "detect_bubble_region_count": len(detect_result.bubble_regions),
        "inpaint_mask_pixels": inpaint_result.mask_pixels if inpaint_result is not None else 0,
        "layout_fit_failed_blocks": render_result.layout_fit_failed_blocks if render_result is not None else 0,
    }
    stage_modes = {
        "detect": {
            "configured_detector_id": detect_result.configured_detector_id,
            "configured_segmenter_id": detect_result.configured_segmenter_id,
            "runtime_detector_id": detect_result.runtime_detector_id,
            "runtime_segmenter_id": detect_result.runtime_segmenter_id,
        },
        "ocr": dict(ocr_last_run),
        "inpaint": inpaint_result.to_dict() if inpaint_result is not None else {},
        "render": render_result.to_dict() if render_result is not None else {},
    }
    return PageQualityGate(
        ok=final_allowed,
        final_allowed=final_allowed,
        issues=issues,
        metrics=metrics,
        stage_modes=stage_modes,
    )


def quality_gate_path(session: MangaProjectSession, page: MangaPage) -> Path:
    return session.project_path / "pages" / f"{page.index:04d}" / QUALITY_GATE_ARTIFACT


def write_quality_gate(session: MangaProjectSession, page: MangaPage, gate: PageQualityGate) -> None:
    path = quality_gate_path(session, page)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(gate.to_dict(), handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def load_quality_gate(session: MangaProjectSession, page: MangaPage) -> PageQualityGate | None:
    path = quality_gate_path(session, page)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload: Any = json.load(handle)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return PageQualityGate.from_dict(payload)


def final_page_path(session: MangaProjectSession, page: MangaPage) -> Path:
    return session.output_root / "final" / "pages" / f"{page.index:04d}.png"


def remove_final_page(session: MangaProjectSession, page: MangaPage) -> None:
    path = final_page_path(session, page)
    if path.exists():
        path.unlink()


def page_blocked_from_final(session: MangaProjectSession, page: MangaPage) -> tuple[bool, list[str]]:
    gate = load_quality_gate(session, page)
    if page.status != BLOCKED_PAGE_STATUS or gate is None or gate.final_allowed:
        return False, []
    return True, [issue.message for issue in gate.issues if issue.blocks_final]
