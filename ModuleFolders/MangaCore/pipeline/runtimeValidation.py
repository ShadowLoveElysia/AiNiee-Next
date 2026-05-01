from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Callable
from urllib.parse import quote

from ModuleFolders.MangaCore.io.persistence import MangaProjectPersistence
from ModuleFolders.MangaCore.pipeline.engines.detect import DetectEngine, DetectRegion
from ModuleFolders.MangaCore.pipeline.engines.inpaint import InpaintEngine
from ModuleFolders.MangaCore.pipeline.engines.ocr import OcrEngine
from ModuleFolders.MangaCore.project.page import MangaPage
from ModuleFolders.MangaCore.project.session import MangaProjectSession
from ModuleFolders.MangaCore.render.bubbleAssign import assign_bubbles


@dataclass(slots=True)
class RuntimeValidationStage:
    stage: str
    ok: bool
    configured_engine_id: str = ""
    runtime_engine_id: str = ""
    used_runtime: bool = False
    execution_mode: str = "heuristic_fallback"
    elapsed_ms: int = 0
    warning_message: str = ""
    error_message: str = ""
    fallback_reason: str = ""
    metrics: dict[str, object] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)
    artifact_urls: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class RuntimeValidationResult:
    ok: bool
    project_id: str
    page_id: str
    page_index: int
    source_path: str
    output_dir: str
    created_at: str
    stages: list[RuntimeValidationStage] = field(default_factory=list)
    summary: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["stages"] = [stage.to_dict() for stage in self.stages]
        return payload


def _now_token() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _relative_to_project(session: MangaProjectSession, path: Path) -> str:
    return path.relative_to(session.project_path).as_posix()


def _asset_url(session: MangaProjectSession, relative_path: str) -> str:
    if not relative_path:
        return ""
    target = session.project_path / relative_path
    version = int(target.stat().st_mtime_ns) if target.exists() else 0
    return f"/api/manga/projects/{session.manifest.project_id}/assets/{quote(relative_path, safe='/')}?v={version}"


def _attach_artifact_urls(session: MangaProjectSession, stage: RuntimeValidationStage) -> RuntimeValidationStage:
    stage.artifact_urls = {
        key: _asset_url(session, relative_path)
        for key, relative_path in stage.artifacts.items()
        if relative_path
    }
    return stage


def _elapsed_ms(started_at: float) -> int:
    return int((perf_counter() - started_at) * 1000)


def _is_inpaint_runtime(runtime_engine_id: str) -> bool:
    return not (
        runtime_engine_id.startswith("opencv-")
        or runtime_engine_id.startswith("pil-")
        or runtime_engine_id == "copy-source"
    )


def _count_execution_modes(stages: list[RuntimeValidationStage]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for stage in stages:
        key = stage.execution_mode or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return counts


class RuntimeValidationCancelled(RuntimeError):
    """Raised when a runtime validation job is cancelled between stages."""


def _check_cancelled(should_cancel: Callable[[], bool] | None) -> None:
    if should_cancel and should_cancel():
        raise RuntimeValidationCancelled("Runtime validation cancelled.")


def _stage_from_payload(payload: dict[str, object]) -> RuntimeValidationStage:
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    artifact_urls = payload.get("artifact_urls") if isinstance(payload.get("artifact_urls"), dict) else {}
    return RuntimeValidationStage(
        stage=str(payload.get("stage") or ""),
        ok=bool(payload.get("ok")),
        configured_engine_id=str(payload.get("configured_engine_id") or ""),
        runtime_engine_id=str(payload.get("runtime_engine_id") or ""),
        used_runtime=bool(payload.get("used_runtime")),
        execution_mode=str(payload.get("execution_mode") or "heuristic_fallback"),
        elapsed_ms=int(payload.get("elapsed_ms") or 0),
        warning_message=str(payload.get("warning_message") or ""),
        error_message=str(payload.get("error_message") or ""),
        fallback_reason=str(payload.get("fallback_reason") or ""),
        metrics=dict(metrics),
        artifacts={str(key): str(value) for key, value in artifacts.items()},
        artifact_urls={str(key): str(value) for key, value in artifact_urls.items()},
    )


def _detect_region_from_payload(payload: dict[str, object], index: int) -> DetectRegion | None:
    bbox = payload.get("bbox")
    if not isinstance(bbox, list) or len(bbox) < 4:
        return None
    bbox_values = [int(float(value)) for value in bbox[:4]]
    polygon = payload.get("polygon")
    if isinstance(polygon, list) and len(polygon) >= 4:
        polygon_values = [
            [float(point[0]), float(point[1])]
            for point in polygon[:4]
            if isinstance(point, list) and len(point) >= 2
        ]
    else:
        x1, y1, x2, y2 = bbox_values
        polygon_values = [
            [float(x1), float(y1)],
            [float(x2), float(y1)],
            [float(x2), float(y2)],
            [float(x1), float(y2)],
        ]
    if len(polygon_values) < 4:
        return None
    return DetectRegion(
        region_id=str(payload.get("region_id") or payload.get("id") or f"region_{index:04d}"),
        kind=str(payload.get("kind") or payload.get("type") or "text"),
        bbox=bbox_values,
        polygon=polygon_values,
        score=float(payload.get("score") or 0.0),
    )


class MangaRuntimeValidator:
    def __init__(
        self,
        *,
        ocr_engine: OcrEngine | None = None,
        detect_engine: DetectEngine | None = None,
        inpaint_engine: InpaintEngine | None = None,
    ) -> None:
        self.ocr_engine = ocr_engine or OcrEngine()
        self.detect_engine = detect_engine or DetectEngine()
        self.inpaint_engine = inpaint_engine or InpaintEngine()

    def run_page_validation(
        self,
        session: MangaProjectSession,
        page: MangaPage,
        *,
        should_cancel: Callable[[], bool] | None = None,
    ) -> RuntimeValidationResult:
        self._configure_engines(session)
        page_key = f"{page.index:04d}"
        output_dir = session.project_path / "pages" / page_key / "runtimeValidation" / _now_token()
        output_dir.mkdir(parents=True, exist_ok=True)
        source_path = session.project_path / page.layers.source
        stages: list[RuntimeValidationStage] = []

        _check_cancelled(should_cancel)
        detect_stage, detect_regions, detect_regions_path, segment_path, bubble_path = self._run_detect(
            session=session,
            page=page,
            source_path=source_path,
            output_dir=output_dir,
        )
        stages.append(_attach_artifact_urls(session, detect_stage))

        _check_cancelled(should_cancel)
        ocr_stage, seeds_path, seed_count = self._run_ocr(
            session=session,
            page=page,
            source_path=source_path,
            regions=detect_regions,
            output_dir=output_dir,
        )
        stages.append(_attach_artifact_urls(session, ocr_stage))

        _check_cancelled(should_cancel)
        inpaint_stage = self._run_inpaint(
            session=session,
            page=page,
            source_path=source_path,
            segment_path=segment_path,
            output_dir=output_dir,
        )
        stages.append(_attach_artifact_urls(session, inpaint_stage))

        _check_cancelled(should_cancel)
        result = self._build_result(
            session=session,
            page=page,
            source_path=source_path,
            output_dir=output_dir,
            stages=stages,
            summary_overrides={
                "seed_count": seed_count,
                "detect_regions_path": detect_regions_path,
                "ocr_seeds_path": seeds_path,
                "segment_mask_path": _relative_to_project(session, segment_path),
                "bubble_mask_path": _relative_to_project(session, bubble_path),
            },
        )
        self._write_report(session, page, output_dir, result)
        return result

    def retry_stage(
        self,
        session: MangaProjectSession,
        page: MangaPage,
        stage: str,
        *,
        should_cancel: Callable[[], bool] | None = None,
    ) -> RuntimeValidationResult:
        stage = str(stage).strip().lower()
        if stage not in {"detect", "ocr", "inpaint"}:
            raise ValueError(f"Unsupported runtime validation stage retry: {stage}")

        self._configure_engines(session)
        page_key = f"{page.index:04d}"
        output_dir = session.project_path / "pages" / page_key / "runtimeValidation" / f"{_now_token()}_retry_{stage}"
        output_dir.mkdir(parents=True, exist_ok=True)
        source_path = session.project_path / page.layers.source
        latest = self._load_latest_report(session, page)
        latest_summary = latest.get("summary") if isinstance(latest.get("summary"), dict) else {}
        existing_stages = self._stages_from_report(latest)
        stages_by_id = {item.stage: item for item in existing_stages if item.stage}
        summary_overrides = dict(latest_summary)
        summary_overrides["retry_stage"] = stage

        _check_cancelled(should_cancel)
        if stage == "detect":
            detect_stage, _detect_regions, detect_regions_path, segment_path, bubble_path = self._run_detect(
                session=session,
                page=page,
                source_path=source_path,
                output_dir=output_dir,
            )
            stages_by_id[stage] = _attach_artifact_urls(session, detect_stage)
            summary_overrides.update(
                {
                    "detect_regions_path": detect_regions_path,
                    "segment_mask_path": _relative_to_project(session, segment_path),
                    "bubble_mask_path": _relative_to_project(session, bubble_path),
                }
            )
        elif stage == "ocr":
            regions = self._detect_regions_from_latest_report(latest)
            ocr_stage, seeds_path, seed_count = self._run_ocr(
                session=session,
                page=page,
                source_path=source_path,
                regions=regions,
                output_dir=output_dir,
            )
            stages_by_id[stage] = _attach_artifact_urls(session, ocr_stage)
            summary_overrides.update({"seed_count": seed_count, "ocr_seeds_path": seeds_path})
        else:
            segment_path = self._resolve_latest_segment_mask(session, page, latest_summary)
            inpaint_stage = self._run_inpaint(
                session=session,
                page=page,
                source_path=source_path,
                segment_path=segment_path,
                output_dir=output_dir,
            )
            stages_by_id[stage] = _attach_artifact_urls(session, inpaint_stage)

        _check_cancelled(should_cancel)
        stages = [stages_by_id[item] for item in ("detect", "ocr", "inpaint") if item in stages_by_id]
        result = self._build_result(
            session=session,
            page=page,
            source_path=source_path,
            output_dir=output_dir,
            stages=stages,
            summary_overrides=summary_overrides,
        )
        self._write_report(session, page, output_dir, result)
        return result

    def _build_result(
        self,
        *,
        session: MangaProjectSession,
        page: MangaPage,
        source_path: Path,
        output_dir: Path,
        stages: list[RuntimeValidationStage],
        summary_overrides: dict[str, object],
    ) -> RuntimeValidationResult:
        runtime_stage_count = sum(1 for stage in stages if stage.used_runtime)
        fallback_stage_count = len(stages) - runtime_stage_count
        execution_mode_counts = _count_execution_modes(stages)
        summary = {
            "runtime_stage_count": runtime_stage_count,
            "fallback_stage_count": fallback_stage_count,
            "configured_runtime_stage_count": execution_mode_counts.get("configured_runtime", 0),
            "fallback_runtime_stage_count": execution_mode_counts.get("fallback_runtime", 0),
            "heuristic_fallback_stage_count": execution_mode_counts.get("heuristic_fallback", 0),
            "failed_stage_count": execution_mode_counts.get("failed", 0),
            "execution_mode_counts": execution_mode_counts,
        }
        summary.update(summary_overrides)
        return RuntimeValidationResult(
            ok=all(stage.ok for stage in stages),
            project_id=session.manifest.project_id,
            page_id=page.page_id,
            page_index=page.index,
            source_path=_relative_to_project(session, source_path),
            output_dir=_relative_to_project(session, output_dir),
            created_at=_now_iso(),
            stages=stages,
            summary=summary,
        )

    def _write_report(
        self,
        session: MangaProjectSession,
        page: MangaPage,
        output_dir: Path,
        result: RuntimeValidationResult,
    ) -> None:
        payload = result.to_dict()
        MangaProjectPersistence.write_page_artifact(session, page, "runtimeValidationLatest.json", payload)
        MangaProjectPersistence.write_page_artifact(
            session,
            page,
            f"runtimeValidation/{output_dir.name}/report.json",
            payload,
        )

    def _load_latest_report(self, session: MangaProjectSession, page: MangaPage) -> dict[str, object]:
        latest_path = session.project_path / "pages" / f"{page.index:04d}" / "runtimeValidationLatest.json"
        if not latest_path.exists():
            raise FileNotFoundError("No latest runtime validation report is available for stage retry.")
        with open(latest_path, encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("Latest runtime validation report is invalid.")
        return payload

    def _stages_from_report(self, report: dict[str, object]) -> list[RuntimeValidationStage]:
        stages = report.get("stages")
        if not isinstance(stages, list):
            return []
        return [_stage_from_payload(stage) for stage in stages if isinstance(stage, dict)]

    def _detect_regions_from_latest_report(self, report: dict[str, object]) -> list[DetectRegion]:
        stage_lookup = {stage.stage: stage for stage in self._stages_from_report(report)}
        detect_stage = stage_lookup.get("detect")
        if detect_stage is None:
            return []
        records = detect_stage.metrics.get("text_regions")
        if not isinstance(records, list):
            return []
        return [
            region
            for index, record in enumerate(records, start=1)
            if isinstance(record, dict)
            for region in [_detect_region_from_payload(record, index)]
            if region is not None
        ]

    def _resolve_latest_segment_mask(
        self,
        session: MangaProjectSession,
        page: MangaPage,
        latest_summary: dict[str, object],
    ) -> Path:
        candidates = [
            str(latest_summary.get("segment_mask_path") or ""),
            page.masks.segment,
        ]
        for candidate in candidates:
            if not candidate:
                continue
            path = session.project_path / candidate
            if path.exists():
                return path
        return session.project_path / page.masks.segment

    def _configure_engines(self, session: MangaProjectSession) -> None:
        snapshot = session.config_snapshot if isinstance(getattr(session, "config_snapshot", None), dict) else {}
        if hasattr(self.ocr_engine, "configure"):
            self.ocr_engine.configure(snapshot.get("manga_ocr_engine"))
        if hasattr(self.detect_engine, "configure"):
            self.detect_engine.configure(
                detector_id=snapshot.get("manga_detect_engine"),
                segmenter_id=snapshot.get("manga_segment_engine"),
            )
        if hasattr(self.inpaint_engine, "configure"):
            self.inpaint_engine.configure(snapshot.get("manga_inpaint_engine"))

    def _run_detect(
        self,
        *,
        session: MangaProjectSession,
        page: MangaPage,
        source_path: Path,
        output_dir: Path,
    ) -> tuple[RuntimeValidationStage, list[object], str, Path, Path]:
        started_at = perf_counter()
        segment_path = output_dir / "segmentMask.png"
        bubble_path = output_dir / "bubbleMask.png"
        regions_path = output_dir / "detectResults.json"
        try:
            result = self.detect_engine.run(source_path, page.width, page.height)
            self.detect_engine.write_masks(
                result,
                size=(page.width, page.height),
                segment_path=segment_path,
                bubble_path=bubble_path,
            )
            regions_payload = result.to_dict()
            MangaProjectPersistence.write_page_artifact(
                session,
                page,
                f"runtimeValidation/{output_dir.name}/detectResults.json",
                regions_payload,
            )
            used_runtime = result.runtime_detector_id != "heuristic-grouping"
            return (
                RuntimeValidationStage(
                    stage="detect",
                    ok=True,
                    configured_engine_id=f"{result.configured_detector_id} / {result.configured_segmenter_id}",
                    runtime_engine_id=f"{result.runtime_detector_id} / {result.runtime_segmenter_id}",
                    used_runtime=used_runtime,
                    execution_mode=(
                        "configured_runtime"
                        if used_runtime
                        else "heuristic_fallback"
                    ),
                    elapsed_ms=_elapsed_ms(started_at),
                    warning_message=result.warning_message,
                    fallback_reason="" if used_runtime else "Detector runtime assets are unavailable; heuristic text-region grouping was used.",
                    metrics={
                        "text_region_count": len(result.text_regions),
                        "bubble_region_count": len(result.bubble_regions),
                        "detector_ok": result.ok,
                        "text_regions": [region.to_dict() for region in result.text_regions],
                    },
                    artifacts={
                        "detect_results": _relative_to_project(session, regions_path),
                        "segment_mask": _relative_to_project(session, segment_path),
                        "bubble_mask": _relative_to_project(session, bubble_path),
                    },
                ),
                list(result.text_regions),
                _relative_to_project(session, regions_path),
                segment_path,
                bubble_path,
            )
        except Exception as exc:
            return (
                RuntimeValidationStage(
                    stage="detect",
                    ok=False,
                    configured_engine_id=str(getattr(self.detect_engine, "detector_id", "detect")),
                    runtime_engine_id="unavailable",
                    execution_mode="failed",
                    elapsed_ms=_elapsed_ms(started_at),
                    error_message=str(exc),
                    fallback_reason=str(exc),
                ),
                [],
                "",
                segment_path,
                bubble_path,
            )

    def _run_ocr(
        self,
        *,
        session: MangaProjectSession,
        page: MangaPage,
        source_path: Path,
        regions: object,
        output_dir: Path,
    ) -> tuple[RuntimeValidationStage, str, int]:
        started_at = perf_counter()
        seeds_path = output_dir / "ocrSeeds.json"
        try:
            region_list = regions if isinstance(regions, list) else []
            try:
                seeds = self.ocr_engine.run(source_path, regions=region_list)
            except TypeError:
                seeds = self.ocr_engine.run(source_path)
            assignments = assign_bubbles(seeds, page.width, page.height, source_path=source_path)
            seed_payload = [seed.to_dict() for seed in seeds]
            MangaProjectPersistence.write_page_artifact(
                session,
                page,
                f"runtimeValidation/{output_dir.name}/ocrSeeds.json",
                seed_payload,
            )
            MangaProjectPersistence.write_page_artifact(
                session,
                page,
                f"runtimeValidation/{output_dir.name}/bubbleAssignments.json",
                [assignment.to_dict() for assignment in assignments],
            )
            if hasattr(self.ocr_engine, "describe_last_run"):
                last_run = self.ocr_engine.describe_last_run()
            else:
                last_run = {
                    "configured_engine_id": getattr(self.ocr_engine, "engine_id", self.ocr_engine.__class__.__name__),
                    "runtime_engine_id": self.ocr_engine.__class__.__name__,
                    "used_runtime": False,
                    "warning_message": "",
                }
            used_runtime = bool(last_run.get("used_runtime", False))
            runtime_engine_id = str(last_run.get("runtime_engine_id", ""))
            seed_payload = [seed.to_dict() for seed in seeds]
            assignment_payload = [assignment.to_dict() for assignment in assignments]
            return (
                RuntimeValidationStage(
                    stage="ocr",
                    ok=True,
                    configured_engine_id=str(last_run.get("configured_engine_id", getattr(self.ocr_engine, "engine_id", "ocr"))),
                    runtime_engine_id=runtime_engine_id,
                    used_runtime=used_runtime,
                    execution_mode="configured_runtime" if used_runtime else "fallback_runtime",
                    elapsed_ms=_elapsed_ms(started_at),
                    warning_message=str(last_run.get("warning_message", "")),
                    fallback_reason="" if used_runtime else "OCR runtime bridge did not use a prepared runtime package; fallback OCR adapter was used.",
                    metrics={
                        "seed_count": len(seeds),
                        "assignment_count": len(assignments),
                        "seeds": seed_payload,
                        "assignments": assignment_payload,
                    },
                    artifacts={
                        "ocr_seeds": _relative_to_project(session, seeds_path),
                        "bubble_assignments": _relative_to_project(
                            session,
                            output_dir / "bubbleAssignments.json",
                        ),
                    },
                ),
                _relative_to_project(session, seeds_path),
                len(seeds),
            )
        except Exception as exc:
            return (
                RuntimeValidationStage(
                    stage="ocr",
                    ok=False,
                    configured_engine_id=str(getattr(self.ocr_engine, "engine_id", "ocr")),
                    runtime_engine_id="unavailable",
                    execution_mode="failed",
                    elapsed_ms=_elapsed_ms(started_at),
                    error_message=str(exc),
                    fallback_reason=str(exc),
                ),
                "",
                0,
            )

    def _run_inpaint(
        self,
        *,
        session: MangaProjectSession,
        page: MangaPage,
        source_path: Path,
        segment_path: Path,
        output_dir: Path,
    ) -> RuntimeValidationStage:
        started_at = perf_counter()
        output_path = output_dir / "inpainted.png"
        try:
            result = self.inpaint_engine.run(
                source_path=source_path,
                segment_mask_path=segment_path,
                brush_mask_path=session.project_path / page.masks.brush,
                output_path=output_path,
            )
            MangaProjectPersistence.write_page_artifact(
                session,
                page,
                f"runtimeValidation/{output_dir.name}/inpaintResults.json",
                result.to_dict(),
            )
            used_runtime = _is_inpaint_runtime(result.runtime_engine_id)
            return RuntimeValidationStage(
                stage="inpaint",
                ok=result.ok,
                configured_engine_id=result.configured_engine_id,
                runtime_engine_id=result.runtime_engine_id,
                used_runtime=used_runtime,
                execution_mode=(
                    "configured_runtime"
                    if used_runtime
                    else "heuristic_fallback"
                    if result.runtime_engine_id == "copy-source"
                    else "fallback_runtime"
                ),
                elapsed_ms=_elapsed_ms(started_at),
                error_message=result.error_message,
                fallback_reason="" if used_runtime else "Inpaint runtime assets are unavailable; fallback inpaint mode was used.",
                metrics={"mask_pixels": result.mask_pixels},
                artifacts={
                    "inpaint_results": _relative_to_project(session, output_dir / "inpaintResults.json"),
                    "inpainted": _relative_to_project(session, output_path),
                },
            )
        except Exception as exc:
            return RuntimeValidationStage(
                stage="inpaint",
                ok=False,
                configured_engine_id=str(getattr(self.inpaint_engine, "engine_id", "inpaint")),
                runtime_engine_id="unavailable",
                execution_mode="failed",
                elapsed_ms=_elapsed_ms(started_at),
                error_message=str(exc),
                fallback_reason=str(exc),
            )
