from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ModuleFolders.MangaCore.export.archiveCommon import write_zip_archive
from ModuleFolders.MangaCore.export.photoshopLocator import PhotoshopLocation, find_photoshop_location
from ModuleFolders.MangaCore.io.persistence import MangaProjectPersistence
from ModuleFolders.MangaCore.pipeline.engines.render import RenderEngine
from ModuleFolders.MangaCore.pipeline.qualityGate import page_blocked_from_final
from ModuleFolders.MangaCore.project.page import MangaPage
from ModuleFolders.MangaCore.project.session import MangaProjectSession
from ModuleFolders.MangaCore.project.textBlock import MangaTextBlock
from ModuleFolders.MangaCore.render.font import FontCatalogEntry, list_font_catalog
from ModuleFolders.MangaCore.render.textNormalize import normalize_manga_dialogue_for_layout


PHOTOSHOP_TIMEOUT_SECONDS = 30 * 60
PSD_STABLE_CHECKS = 3


@dataclass(slots=True)
class PsdExportResult:
    output_path: Path | None = None
    psd_paths: list[Path] = field(default_factory=list)
    script_paths: list[Path] = field(default_factory=list)
    manifest_path: Path | None = None
    warnings: list[str] = field(default_factory=list)
    missing_fonts: list[dict[str, object]] = field(default_factory=list)
    skipped_pages: list[str] = field(default_factory=list)
    blocked_pages: list[str] = field(default_factory=list)
    photoshop: dict[str, object] = field(default_factory=dict)
    output_kind: str = "psd"
    output_count: int = 0
    output_target_count: int = 0
    output_failed_count: int = 0
    complete: bool = False


class PsdExportCancelled(Exception):
    """Raised when a PSD export job is cancelled before the next page starts."""


def _append_warning_once(result: PsdExportResult, warning: str) -> None:
    if warning and warning not in result.warnings:
        result.warnings.append(warning)


def _normalize_font_key(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.split(",", 1)[0].strip().strip("\"'")
    return re.sub(r"\s+", " ", text).lower()


def _font_lookup(project_path: Path) -> dict[str, FontCatalogEntry]:
    lookup: dict[str, FontCatalogEntry] = {}
    for entry in list_font_catalog(project_path):
        lookup[entry.font_id] = entry
        for value in (
            entry.display_name,
            entry.css_family,
            entry.family,
            entry.postscript_name,
        ):
            key = _normalize_font_key(value)
            if key and key not in lookup:
                lookup[key] = entry
    return lookup


def _resolve_font_entry(
    block: MangaTextBlock,
    lookup: dict[str, FontCatalogEntry],
) -> FontCatalogEntry | None:
    for query in (
        str(getattr(block.style, "font_id", "") or ""),
        str(getattr(block.style, "font_family", "") or ""),
        str(block.font_prediction or ""),
    ):
        if not query:
            continue
        if query in lookup:
            return lookup[query]
        normalized = _normalize_font_key(query)
        if normalized in lookup:
            return lookup[normalized]
    return None


def _path_for_layer(session: MangaProjectSession, page: MangaPage, layer_name: str) -> Path | None:
    relative = str(getattr(page.layers, layer_name, "") or "")
    if not relative:
        return None
    path = session.project_path / relative
    return path if path.exists() else None


def _path_for_mask(session: MangaProjectSession, page: MangaPage, mask_name: str) -> Path | None:
    relative = str(getattr(page.masks, mask_name, "") or "")
    if not relative:
        return None
    path = session.project_path / relative
    return path if path.exists() else None


def _page_artifact_path(session: MangaProjectSession, page: MangaPage, filename: str) -> Path:
    return session.project_path / "pages" / f"{page.index:04d}" / filename


def _read_json_file(path: Path) -> object | None:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def _layout_plan_map(payload: object) -> dict[str, dict[str, object]]:
    if not isinstance(payload, dict):
        return {}
    plans = payload.get("layout_plans")
    if not isinstance(plans, list):
        return {}
    mapped: dict[str, dict[str, object]] = {}
    for plan in plans:
        if not isinstance(plan, dict):
            continue
        block_id = str(plan.get("block_id") or "")
        if block_id:
            mapped[block_id] = plan
    return mapped


def _load_persisted_layout_plans(session: MangaProjectSession, page: MangaPage) -> dict[str, dict[str, object]]:
    payload = _read_json_file(_page_artifact_path(session, page, "renderResults.json"))
    if not isinstance(payload, dict):
        return {}
    payload_page_id = str(payload.get("page_id") or "")
    if payload_page_id and payload_page_id != page.page_id:
        return {}
    return _layout_plan_map(payload)


def _block_export_text(block: MangaTextBlock) -> str:
    return str(block.translation or block.source_text or "").strip()


def _text_content_key(value: str) -> str:
    return re.sub(r"[\r\n]+", "", str(value or "")).strip()


def _layout_plan_text_key(layout_plan: dict[str, object]) -> str:
    runs = layout_plan.get("runs")
    if not isinstance(runs, list):
        return ""
    return _text_content_key(
        "".join(str(run.get("text", "")) for run in runs if isinstance(run, dict))
    )


def _layout_plan_stale_for_block(block: MangaTextBlock, layout_plan: dict[str, object]) -> bool:
    bbox_raw = layout_plan.get("bbox")
    if not isinstance(bbox_raw, list) or len(bbox_raw) < 4:
        return True
    try:
        plan_bbox = [int(value) for value in bbox_raw[:4]]
    except (TypeError, ValueError):
        return True
    if plan_bbox != [int(value) for value in block.bbox]:
        return True

    direction = str(layout_plan.get("direction") or block.rendered_direction or "horizontal")
    if direction != str(block.rendered_direction or direction):
        return True

    plan_key = _layout_plan_text_key(layout_plan)
    if not plan_key:
        return False
    expected_text = normalize_manga_dialogue_for_layout(_block_export_text(block), direction=direction)
    if plan_key == _text_content_key(expected_text):
        return False

    warnings = {
        str(warning)
        for warning in layout_plan.get("warnings", [])
        if isinstance(warning, str)
    }
    return "layout_truncated" not in warnings


def _missing_or_stale_layout_block_ids(
    page: MangaPage,
    layout_plans: dict[str, dict[str, object]],
) -> list[str]:
    stale_ids: list[str] = []
    for block in page.text_blocks:
        if not _block_export_text(block):
            continue
        layout_plan = layout_plans.get(block.block_id)
        if layout_plan is None or _layout_plan_stale_for_block(block, layout_plan):
            stale_ids.append(block.block_id)
    return stale_ids


def _js(value: object) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _jsx_path(path: Path) -> str:
    return path.resolve().as_posix()


def _parse_hex_color(value: str) -> tuple[int, int, int]:
    text = str(value or "").strip()
    if not text:
        return (17, 17, 17)
    if text.startswith("#"):
        text = text[1:]
    if len(text) == 3:
        text = "".join(character * 2 for character in text)
    if len(text) != 6:
        return (17, 17, 17)
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError:
        return (17, 17, 17)


def _layout_runs(layout_plan: dict[str, object] | None) -> list[dict[str, object]]:
    runs = (layout_plan or {}).get("runs") if layout_plan else None
    if not isinstance(runs, list):
        return []
    return [run for run in runs if isinstance(run, dict) and str(run.get("text", "")).strip()]


def _horizontal_text_from_runs(layout_plan: dict[str, object] | None) -> str:
    return "\r".join(str(run.get("text", "")) for run in _layout_runs(layout_plan))


def _vertical_text_from_runs(layout_plan: dict[str, object] | None) -> str:
    runs = _layout_runs(layout_plan)
    if not runs:
        return ""

    font_size = max(1, int((layout_plan or {}).get("font_size") or 24))
    column_tolerance = max(4, int(font_size * 0.45))
    columns: list[dict[str, object]] = []
    for run in sorted(runs, key=lambda item: (-int(item.get("x", 0)), int(item.get("y", 0)))):
        x = int(run.get("x", 0))
        y = int(run.get("y", 0))
        text = str(run.get("text", ""))
        target_column: dict[str, object] | None = None
        for column in columns:
            if abs(x - int(column.get("x", 0))) <= column_tolerance:
                target_column = column
                break
        if target_column is None:
            target_column = {"x": x, "items": []}
            columns.append(target_column)
        items = target_column.get("items")
        if isinstance(items, list):
            items.append({"text": text, "y": y})

    column_texts: list[str] = []
    for column in sorted(columns, key=lambda item: -int(item.get("x", 0))):
        items = column.get("items")
        if not isinstance(items, list):
            continue
        text = "".join(str(item.get("text", "")) for item in sorted(items, key=lambda item: int(item.get("y", 0))))
        if text.strip():
            column_texts.append(text)
    return "\r".join(column_texts)


def _layer_layout_runs(layer: dict[str, object]) -> list[dict[str, object]]:
    runs = layer.get("layout_runs")
    if not isinstance(runs, list):
        return []
    return [run for run in runs if isinstance(run, dict) and str(run.get("text", "")).strip()]


def _run_int(run: dict[str, object], key: str) -> int:
    try:
        return int(run.get(key, 0))
    except (TypeError, ValueError):
        return 0


def _horizontal_anchor_from_runs(runs: list[dict[str, object]], font_size: int) -> tuple[int, int] | None:
    if not runs:
        return None
    first_run = sorted(runs, key=lambda run: (_run_int(run, "y"), _run_int(run, "x")))[0]
    return _run_int(first_run, "x"), _run_int(first_run, "y") + int(font_size * 0.86)


def _vertical_anchor_from_runs(runs: list[dict[str, object]], font_size: int) -> tuple[int, int] | None:
    if not runs:
        return None
    column_tolerance = max(4, int(font_size * 0.45))
    columns: list[dict[str, object]] = []
    for run in sorted(runs, key=lambda item: -_run_int(item, "x")):
        x = _run_int(run, "x")
        target_column: dict[str, object] | None = None
        for column in columns:
            center = float(column.get("center", 0.0))
            if abs(x - center) <= column_tolerance:
                target_column = column
                break
        if target_column is None:
            target_column = {"xs": [], "ys": [], "center": float(x)}
            columns.append(target_column)
        xs = target_column.get("xs")
        ys = target_column.get("ys")
        if isinstance(xs, list) and isinstance(ys, list):
            xs.append(x)
            ys.append(_run_int(run, "y"))
            target_column["center"] = sum(xs) / max(1, len(xs))
    rightmost_column = sorted(columns, key=lambda column: float(column.get("center", 0.0)), reverse=True)[0]
    xs = rightmost_column.get("xs") if isinstance(rightmost_column.get("xs"), list) else []
    ys = rightmost_column.get("ys") if isinstance(rightmost_column.get("ys"), list) else []
    if not xs or not ys:
        return None
    return int(round(sum(xs) / len(xs) + font_size * 0.5)), min(int(y) for y in ys)


def _text_for_layer(block: MangaTextBlock, layout_plan: dict[str, object] | None) -> tuple[str, bool]:
    text = str(block.translation or "").strip()
    used_source_fallback = False
    if not text:
        text = str(block.source_text or "").strip()
        used_source_fallback = bool(text)
    if not text:
        return "", used_source_fallback

    direction = str((layout_plan or {}).get("direction") or block.rendered_direction or "horizontal")
    if layout_plan:
        planned_text = _vertical_text_from_runs(layout_plan) if direction == "vertical" else _horizontal_text_from_runs(layout_plan)
        if planned_text:
            return planned_text, used_source_fallback
    return normalize_manga_dialogue_for_layout(text, direction=direction), used_source_fallback


def _layer_position(block: MangaTextBlock, layout_plan: dict[str, object] | None) -> tuple[int, int, int, int, str, int, float]:
    bbox_raw = (layout_plan or {}).get("bbox") if layout_plan else None
    bbox_values = bbox_raw if isinstance(bbox_raw, list) and len(bbox_raw) >= 4 else list(block.bbox)
    x1, y1, x2, y2 = [int(value) for value in bbox_values[:4]]
    direction = str((layout_plan or {}).get("direction") or block.rendered_direction or "horizontal")
    font_size = int((layout_plan or {}).get("font_size") or block.style.font_size or 24)
    line_spacing = float((layout_plan or {}).get("line_spacing") or block.style.line_spacing or 1.0)
    return x1, y1, x2, y2, direction, font_size, line_spacing


def _font_manifest(
    block: MangaTextBlock,
    entry: FontCatalogEntry | None,
) -> dict[str, object]:
    requested = str(getattr(block.style, "font_id", "") or getattr(block.style, "font_family", "") or block.font_prediction or "")
    if entry is None:
        return {
            "requested": requested,
            "font_id": str(getattr(block.style, "font_id", "") or ""),
            "display_name": str(getattr(block.style, "font_family", "") or requested),
            "css_family": "",
            "postscript_name": "",
            "available": False,
        }
    return {
        "requested": requested,
        "font_id": entry.font_id,
        "display_name": entry.display_name,
        "css_family": entry.css_family,
        "postscript_name": entry.postscript_name,
        "available": entry.available,
        "path_or_url": entry.path_or_url,
    }


def _run_photoshop_script(
    script_path: Path,
    output_path: Path,
    photoshop_location: PhotoshopLocation,
    should_cancel: Callable[[], bool] | None = None,
    progress_callback: Callable[[dict[str, object]], None] | None = None,
    progress_payload: dict[str, object] | None = None,
) -> tuple[bool, str]:
    executable = photoshop_location.executable_path
    if not executable:
        return False, photoshop_location.message or "Photoshop was not found; generated JSX script only."

    old_mtime = output_path.stat().st_mtime if output_path.exists() else 0.0
    try:
        process = subprocess.Popen(
            [executable, "-r", str(script_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        return False, f"Failed to start Photoshop: {exc}"

    started_at = time.monotonic()
    last_progress_at = 0.0
    stable_state: tuple[int, float] | None = None
    stable_checks = 0
    deadline = time.monotonic() + PHOTOSHOP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if should_cancel and should_cancel():
            try:
                process.terminate()
            except OSError:
                pass
            raise PsdExportCancelled("PSD export cancelled.")
        now = time.monotonic()
        if progress_callback and now - last_progress_at >= 2:
            last_progress_at = now
            payload = dict(progress_payload or {})
            elapsed = max(0.0, now - started_at)
            payload.update(
                {
                    "stage": "psd_export_photoshop",
                    "progress": int(payload.get("progress") or 0),
                    "message": payload.get("message") or "Photoshop is generating the PSD.",
                    "elapsed_seconds": int(elapsed),
                    "psd_detected": stable_state is not None,
                    "stable_check_count": stable_checks,
                    "stable_check_target": PSD_STABLE_CHECKS,
                    "observed_output_size": stable_state[0] if stable_state else 0,
                }
            )
            progress_callback(payload)
        if output_path.exists():
            stat = output_path.stat()
            current_state = (stat.st_size, stat.st_mtime)
            if stat.st_size > 0 and stat.st_mtime > old_mtime:
                if current_state == stable_state:
                    stable_checks += 1
                else:
                    stable_state = current_state
                    stable_checks = 1
                if stable_checks >= PSD_STABLE_CHECKS:
                    return True, ""
            else:
                stable_state = None
                stable_checks = 0
        time.sleep(0.5)
    return False, f"Photoshop PSD export timed out after {PHOTOSHOP_TIMEOUT_SECONDS} seconds."


def _running_output_progress(output_count: int, output_target_count: int) -> int:
    if output_target_count <= 0:
        return 0
    return max(0, min(99, int(output_count * 100 / output_target_count)))


def _output_target_count(result: PsdExportResult, total_pages: int) -> int:
    return max(0, total_pages - len(result.skipped_pages))


def _output_progress_counts(
    result: PsdExportResult,
    total_pages: int,
    *,
    script_only: bool,
    active_page_in_progress: bool = False,
) -> dict[str, object]:
    output_kind = "jsx" if script_only else "psd"
    output_target_count = _output_target_count(result, total_pages)
    output_count = len(result.script_paths) if script_only else len(result.psd_paths)
    attempted_count = len(result.script_paths)
    failed_count = 0
    if not script_only:
        failed_count = max(0, attempted_count - len(result.psd_paths) - (1 if active_page_in_progress else 0))
    return {
        "progress": _running_output_progress(output_count, output_target_count),
        "output_kind": output_kind,
        "output_count": output_count,
        "output_target_count": output_target_count,
        "output_attempted_count": attempted_count,
        "output_failed_count": failed_count,
    }


def _update_result_output_summary(result: PsdExportResult, total_pages: int, *, script_only: bool) -> dict[str, object]:
    summary = _output_progress_counts(result, total_pages, script_only=script_only)
    result.output_kind = str(summary["output_kind"])
    result.output_count = int(summary["output_count"])
    result.output_target_count = int(summary["output_target_count"])
    result.output_failed_count = int(summary["output_failed_count"])
    result.complete = result.output_target_count == 0 or result.output_count >= result.output_target_count
    return summary


class PsdExporter:
    def export(
        self,
        session: MangaProjectSession,
        *,
        page_ids: list[str] | None = None,
        script_only: bool = False,
        include_blocked: bool = True,
        package: bool = False,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> PsdExportResult:
        output_dir = session.project_path / "exports" / "psd"
        output_dir.mkdir(parents=True, exist_ok=True)

        result = PsdExportResult(output_path=output_dir)
        photoshop_location = find_photoshop_location()
        result.photoshop = photoshop_location.to_dict()
        selected_page_ids = set(page_ids or [])
        font_lookup = _font_lookup(session.project_path)
        manifest: dict[str, object] = {
            "project_id": session.manifest.project_id,
            "project_name": session.manifest.name,
            "pages": [],
            "warnings": result.warnings,
            "missing_fonts": result.missing_fonts,
        }

        page_refs = [
            page_ref
            for page_ref in session.scene.pages
            if not selected_page_ids or page_ref.page_id in selected_page_ids
        ]
        total_pages = len(page_refs)
        if progress_callback:
            progress_callback(
                {
                    "stage": "psd_export_running",
                    "message": f"Preparing PSD export for {total_pages} page(s).",
                    "page_count": total_pages,
                    **_output_progress_counts(result, total_pages, script_only=script_only),
                }
            )

        for page_number, page_ref in enumerate(page_refs, start=1):
            if should_cancel and should_cancel():
                raise PsdExportCancelled("PSD export cancelled.")
            page = session.get_page(page_ref.page_id)
            if progress_callback:
                progress_callback(
                    {
                        "stage": "psd_export_page",
                        "message": f"Exporting PSD page {page_number}/{total_pages}: {page.index:04d}.",
                        "page_id": page.page_id,
                        "page_index": page.index,
                        "page_number": page_number,
                        "page_count": total_pages,
                        **_output_progress_counts(result, total_pages, script_only=script_only),
                    }
                )
            blocked, reasons = page_blocked_from_final(session, page)
            if blocked:
                result.blocked_pages.append(page.page_id)
                if not include_blocked:
                    result.skipped_pages.append(page.page_id)
                    _append_warning_once(result, f"Skipped blocked page {page.index:04d}: {'; '.join(reasons)}")
                    continue
                _append_warning_once(result, f"Included quality-gated page {page.index:04d}: {'; '.join(reasons)}")

            layout_plans = _load_persisted_layout_plans(session, page)
            stale_block_ids = _missing_or_stale_layout_block_ids(page, layout_plans)
            if stale_block_ids:
                render_result = RenderEngine().run_page(session, page, write_final=False)
                MangaProjectPersistence.write_page_artifact(session, page, "renderResults.json", render_result.to_dict())
                layout_plans = _layout_plan_map(render_result.to_dict())
                preview_ids = ", ".join(stale_block_ids[:3])
                suffix = "..." if len(stale_block_ids) > 3 else ""
                _append_warning_once(
                    result,
                    f"PSD export refreshed layout for page {page.index:04d} because saved layout was missing or stale: {preview_ids}{suffix}",
                )
            page_manifest = self._export_page(
                session=session,
                page=page,
                output_dir=output_dir,
                layout_plans=layout_plans,
                font_lookup=font_lookup,
                script_only=script_only,
                photoshop_location=photoshop_location,
                result=result,
                page_number=page_number,
                total_pages=total_pages,
                progress_callback=progress_callback,
                should_cancel=should_cancel,
            )
            if page_manifest is not None:
                pages = manifest["pages"]
                if isinstance(pages, list):
                    pages.append(page_manifest)
            if progress_callback:
                progress_callback(
                    {
                        "stage": "psd_export_page_done",
                        "message": f"PSD page {page_number}/{total_pages} exported: {page.index:04d}.",
                        "page_id": page.page_id,
                        "page_index": page.index,
                        "page_number": page_number,
                        "page_count": total_pages,
                        **_output_progress_counts(result, total_pages, script_only=script_only),
                    }
                )

        manifest_path = output_dir / "layer_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)
        result.manifest_path = manifest_path

        if package and (result.script_paths or result.psd_paths):
            zip_path = session.project_path / "exports" / f"{session.manifest.project_id}_psd.zip"
            files: list[tuple[str, Path]] = [
                ("layer_manifest.json", manifest_path),
                *[(path.relative_to(output_dir).as_posix(), path) for path in result.script_paths],
                *[(path.relative_to(output_dir).as_posix(), path) for path in result.psd_paths],
            ]
            result.output_path = write_zip_archive(zip_path, files)
        elif not result.script_paths and not result.psd_paths:
            result.output_path = None
        final_summary = _update_result_output_summary(result, total_pages, script_only=script_only)
        final_stage = "psd_export_completed" if result.complete else "psd_export_incomplete"
        final_message = (
            "PSD export completed."
            if result.complete
            else f"PSD export incomplete: generated {result.output_count}/{result.output_target_count} {result.output_kind.upper()} file(s)."
        )
        if progress_callback:
            progress_callback(
                {
                    "stage": final_stage,
                    "message": final_message,
                    "page_count": total_pages,
                    "psd_count": len(result.psd_paths),
                    "script_count": len(result.script_paths),
                    **final_summary,
                    "complete": result.complete,
                    "progress": 100 if result.complete else final_summary["progress"],
                }
            )
        return result

    def _export_page(
        self,
        *,
        session: MangaProjectSession,
        page: MangaPage,
        output_dir: Path,
        layout_plans: dict[str, dict[str, object]],
        font_lookup: dict[str, FontCatalogEntry],
        script_only: bool,
        photoshop_location: PhotoshopLocation,
        result: PsdExportResult,
        page_number: int = 1,
        total_pages: int = 1,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> dict[str, object] | None:
        source_path = _path_for_layer(session, page, "source")
        if source_path is None:
            source_path = _path_for_layer(session, page, "rendered") or _path_for_layer(session, page, "inpainted")
        if source_path is None:
            _append_warning_once(result, f"Skipped page {page.index:04d}: source layer is missing.")
            return None

        page_token = f"{page.index:04d}_{page.page_id}"
        script_path = output_dir / f"{page_token}.jsx"
        psd_path = output_dir / f"{page_token}.psd"
        page_manifest = self._page_manifest(
            session=session,
            page=page,
            source_path=source_path,
            psd_path=psd_path,
            script_path=script_path,
            layout_plans=layout_plans,
            font_lookup=font_lookup,
            result=result,
        )
        script = self._build_jsx(
            page=page,
            source_path=source_path,
            psd_path=psd_path,
            page_manifest=page_manifest,
        )
        with open(script_path, "w", encoding="utf-8-sig") as handle:
            handle.write(script)
        result.script_paths.append(script_path)

        if script_only:
            page_manifest["script_only"] = True
            return page_manifest

        if progress_callback:
            progress_callback(
                {
                    "stage": "psd_export_photoshop",
                    "message": f"Photoshop is generating PSD page {page_number}/{total_pages}: {page.index:04d}.",
                    "page_id": page.page_id,
                    "page_index": page.index,
                    "page_number": page_number,
                    "page_count": total_pages,
                    **_output_progress_counts(
                        result,
                        total_pages,
                        script_only=False,
                        active_page_in_progress=True,
                    ),
                }
            )
        generated, warning = _run_photoshop_script(
            script_path,
            psd_path,
            photoshop_location,
            should_cancel=should_cancel,
            progress_callback=progress_callback,
            progress_payload={
                "message": f"Photoshop is generating PSD page {page_number}/{total_pages}: {page.index:04d}.",
                "page_id": page.page_id,
                "page_index": page.index,
                "page_number": page_number,
                "page_count": total_pages,
                **_output_progress_counts(
                    result,
                    total_pages,
                    script_only=False,
                    active_page_in_progress=True,
                ),
            },
        )
        if generated and psd_path.exists() and psd_path.stat().st_size > 0:
            result.psd_paths.append(psd_path)
            page_manifest["psd_generated"] = True
        else:
            _append_warning_once(result, warning or f"Photoshop did not produce a PSD file for page {page.index:04d}.")
            page_manifest["psd_generated"] = False
            page_manifest["script_only"] = True
        return page_manifest

    def _page_manifest(
        self,
        *,
        session: MangaProjectSession,
        page: MangaPage,
        source_path: Path,
        psd_path: Path,
        script_path: Path,
        layout_plans: dict[str, dict[str, object]],
        font_lookup: dict[str, FontCatalogEntry],
        result: PsdExportResult,
    ) -> dict[str, object]:
        layers: list[dict[str, object]] = [
            {"type": "image", "name": f"original/{page.page_id}", "path": str(source_path), "locked": True}
        ]
        inpainted_path = _path_for_layer(session, page, "inpainted")
        rendered_path = _path_for_layer(session, page, "rendered")
        if inpainted_path is not None:
            layers.append({"type": "image", "group": "Base", "name": f"inpainted/{page.page_id}", "path": str(inpainted_path)})
        if rendered_path is not None:
            layers.append(
                {
                    "type": "image",
                    "group": "Base",
                    "name": f"rendered-preview/{page.page_id}",
                    "path": str(rendered_path),
                    "visible": False,
                }
            )
        for mask_name, layer_prefix in (
            ("segment", "diagnostics/mask-segment"),
            ("bubble", "diagnostics/mask-bubble"),
            ("brush", "diagnostics/mask-brush"),
            ("restore", "diagnostics/mask-restore"),
        ):
            mask_path = _path_for_mask(session, page, mask_name)
            if mask_path is not None:
                layers.append(
                    {
                        "type": "image",
                        "group": "Diagnostics",
                        "name": f"{layer_prefix}/{page.page_id}",
                        "path": str(mask_path),
                        "visible": False,
                        "diagnostic": True,
                    }
                )

        for order, block in enumerate(page.text_blocks, start=1):
            layout_plan = layout_plans.get(block.block_id)
            text, used_source_fallback = _text_for_layer(block, layout_plan)
            if not text:
                continue
            font_entry = _resolve_font_entry(block, font_lookup)
            if font_entry is None:
                missing = {
                    "page_id": page.page_id,
                    "block_id": block.block_id,
                    "requested": str(block.style.font_id or block.style.font_family or block.font_prediction),
                }
                result.missing_fonts.append(missing)
                _append_warning_once(
                    result,
                    f"Missing PSD font for page {page.index:04d} block {block.block_id}: {missing['requested']}",
                )
            x1, y1, x2, y2, direction, font_size, line_spacing = _layer_position(block, layout_plan)
            text_layer = {
                "type": "text",
                "group": "Text",
                "name": f"text/{order:03d}_{block.block_id}",
                "block_id": block.block_id,
                "order": order,
                "text": text,
                "used_source_fallback": used_source_fallback,
                "bbox": [x1, y1, x2, y2],
                "rotation": int(block.rotation or 0),
                "direction": direction,
                "font_size": font_size,
                "line_spacing": line_spacing,
                "fill": block.style.fill,
                "stroke_color": block.style.stroke_color,
                "stroke_width": block.style.stroke_width,
                "font": _font_manifest(block, font_entry),
                "flags": list(block.flags),
                "source_metrics": dict(block.source_metrics),
            }
            runs = _layout_runs(layout_plan)
            if runs:
                text_layer["layout_runs"] = runs
            layers.append(text_layer)

        return {
            "page_id": page.page_id,
            "index": page.index,
            "width": page.width,
            "height": page.height,
            "source_path": str(source_path),
            "psd_path": str(psd_path),
            "script_path": str(script_path),
            "layout_artifact_path": str(_page_artifact_path(session, page, "renderResults.json")),
            "layout_plan_count": len(layout_plans),
            "layers": layers,
        }

    def _build_jsx(
        self,
        *,
        page: MangaPage,
        source_path: Path,
        psd_path: Path,
        page_manifest: dict[str, object],
    ) -> str:
        lines: list[str] = [
            "#target photoshop",
            "app.preferences.rulerUnits = Units.PIXELS;",
            "app.preferences.typeUnits = TypeUnits.PIXELS;",
            "",
            "function findFontPostScriptName(fontName) {",
            "  if (!fontName) return null;",
            "  var lowerName = fontName.toLowerCase();",
            "  for (var i = 0; i < app.fonts.length; i++) {",
            "    var font = app.fonts[i];",
            "    var ps = String(font.postScriptName || '').toLowerCase();",
            "    var name = String(font.name || '').toLowerCase();",
            "    var family = String(font.family || '').toLowerCase();",
            "    if (ps === lowerName || name === lowerName || family === lowerName) return font.postScriptName;",
            "  }",
            "  for (var j = 0; j < app.fonts.length; j++) {",
            "    var fuzzy = app.fonts[j];",
            "    var haystack = (String(fuzzy.postScriptName || '') + ' ' + String(fuzzy.name || '') + ' ' + String(fuzzy.family || '')).toLowerCase();",
            "    if (haystack.indexOf(lowerName) >= 0) return fuzzy.postScriptName;",
            "  }",
            "  return null;",
            "}",
            "",
            "function addImageLayer(doc, pathText, layerName, visible) {",
            "  var file = new File(pathText);",
            "  if (!file.exists) { $.writeln('Missing layer image: ' + pathText); return; }",
            "  var imageDoc = app.open(file);",
            "  imageDoc.activeLayer.duplicate(doc, ElementPlacement.PLACEATBEGINNING);",
            "  imageDoc.close(SaveOptions.DONOTSAVECHANGES);",
            "  app.activeDocument = doc;",
            "  doc.activeLayer.name = layerName;",
            "  doc.activeLayer.visible = visible;",
            "}",
            "",
            "function applyTextLayerStroke(layer, size, red, green, blue) {",
            "  if (!layer || size <= 0) return;",
            "  app.activeDocument.activeLayer = layer;",
            "  var desc = new ActionDescriptor();",
            "  var ref = new ActionReference();",
            "  ref.putProperty(charIDToTypeID('Prpr'), charIDToTypeID('Lefx'));",
            "  ref.putEnumerated(charIDToTypeID('Lyr '), charIDToTypeID('Ordn'), charIDToTypeID('Trgt'));",
            "  desc.putReference(charIDToTypeID('null'), ref);",
            "  var effects = new ActionDescriptor();",
            "  effects.putUnitDouble(charIDToTypeID('Scl '), charIDToTypeID('#Prc'), 100.0);",
            "  var stroke = new ActionDescriptor();",
            "  stroke.putBoolean(charIDToTypeID('enab'), true);",
            "  stroke.putEnumerated(charIDToTypeID('Styl'), charIDToTypeID('FStl'), charIDToTypeID('OutF'));",
            "  stroke.putEnumerated(charIDToTypeID('PntT'), charIDToTypeID('FrFl'), charIDToTypeID('SClr'));",
            "  stroke.putEnumerated(charIDToTypeID('Md  '), charIDToTypeID('BlnM'), charIDToTypeID('Nrml'));",
            "  stroke.putUnitDouble(charIDToTypeID('Opct'), charIDToTypeID('#Prc'), 100.0);",
            "  stroke.putUnitDouble(charIDToTypeID('Sz  '), charIDToTypeID('#Pxl'), size);",
            "  var color = new ActionDescriptor();",
            "  color.putDouble(charIDToTypeID('Rd  '), red);",
            "  color.putDouble(charIDToTypeID('Grn '), green);",
            "  color.putDouble(charIDToTypeID('Bl  '), blue);",
            "  stroke.putObject(charIDToTypeID('Clr '), charIDToTypeID('RGBC'), color);",
            "  effects.putObject(charIDToTypeID('FrFX'), charIDToTypeID('FrFX'), stroke);",
            "  desc.putObject(charIDToTypeID('T   '), charIDToTypeID('Lefx'), effects);",
            "  executeAction(charIDToTypeID('setd'), desc, DialogModes.NO);",
            "}",
            "",
            f"var inputFile = new File({_js(_jsx_path(source_path))});",
            "var doc = app.open(inputFile);",
            "try { if (doc.mode != DocumentMode.RGB) doc.changeMode(ChangeMode.RGB); } catch (modeError) {}",
            "var originalLayer = null;",
            "try { originalLayer = doc.backgroundLayer; } catch (bgError) {}",
            "if (!originalLayer && doc.layers.length > 0) originalLayer = doc.layers[doc.layers.length - 1];",
            f"if (originalLayer) {{ originalLayer.name = {_js(f'original/{page.page_id}')}; try {{ originalLayer.allLocked = true; }} catch (lockError) {{}} }}",
        ]

        for layer in page_manifest.get("layers", []):
            if not isinstance(layer, dict) or layer.get("type") != "image":
                continue
            if str(layer.get("name", "")).startswith("original/"):
                continue
            layer_path = Path(str(layer.get("path", "")))
            lines.append(
                f"addImageLayer(doc, {_js(_jsx_path(layer_path))}, {_js(layer.get('name', 'image'))}, {'true' if layer.get('visible', True) else 'false'});"
            )

        text_layers = [
            layer
            for layer in page_manifest.get("layers", [])
            if isinstance(layer, dict) and layer.get("type") == "text"
        ]
        for index, layer in enumerate(text_layers, start=1):
            lines.extend(self._text_layer_jsx(index, layer))

        lines.extend(
            [
                f"var psdFile = new File({_js(_jsx_path(psd_path))});",
                "if (psdFile.parent && !psdFile.parent.exists) psdFile.parent.create();",
                "var psdOptions = new PhotoshopSaveOptions();",
                "psdOptions.embedColorProfile = true;",
                "psdOptions.alphaChannels = true;",
                "psdOptions.layers = true;",
                "doc.saveAs(psdFile, psdOptions, true);",
                "doc.close(SaveOptions.DONOTSAVECHANGES);",
                "",
            ]
        )
        return "\n".join(lines)

    def _text_layer_jsx(self, index: int, layer: dict[str, object]) -> list[str]:
        x1, y1, x2, _y2 = [int(value) for value in list(layer.get("bbox", [0, 0, 0, 0]))[:4]]
        direction = str(layer.get("direction") or "horizontal")
        font_size = max(1, int(layer.get("font_size") or 24))
        line_spacing = max(0.1, float(layer.get("line_spacing") or 1.0))
        layout_runs = _layer_layout_runs(layer)
        if direction == "vertical":
            anchor = _vertical_anchor_from_runs(layout_runs, font_size)
            if anchor is None:
                anchor = (x2 - int(font_size * 0.65), y1)
            position_x, position_y = anchor
            justification = "Justification.LEFT"
            ps_direction = "Direction.VERTICAL"
        else:
            anchor = _horizontal_anchor_from_runs(layout_runs, font_size)
            if anchor is None:
                anchor = (x1, y1 + int(font_size * 0.86))
            position_x, position_y = anchor
            justification = "Justification.LEFT"
            ps_direction = "Direction.HORIZONTAL"

        font = layer.get("font") if isinstance(layer.get("font"), dict) else {}
        font_name = str(
            (font or {}).get("postscript_name")
            or (font or {}).get("display_name")
            or (font or {}).get("requested")
            or ""
        )
        color_r, color_g, color_b = _parse_hex_color(str(layer.get("fill") or "#111111"))
        rotation = int(layer.get("rotation") or 0)
        layer_name = str(layer.get("name") or f"text/{index:03d}")
        text = str(layer.get("text") or "")
        leading = font_size * line_spacing

        lines = [
            "",
            f"var textLayer{index} = doc.artLayers.add();",
            f"textLayer{index}.kind = LayerKind.TEXT;",
            f"textLayer{index}.name = {_js(layer_name)};",
            f"var textItem{index} = textLayer{index}.textItem;",
            f"textItem{index}.direction = {ps_direction};",
            f"textItem{index}.justification = {justification};",
            f"textItem{index}.position = [{position_x}, {position_y}];",
            f"textItem{index}.contents = {_js(text)};",
            f"textItem{index}.size = new UnitValue({font_size}, 'px');",
            f"textItem{index}.useAutoLeading = false;",
            f"textItem{index}.leading = new UnitValue({leading:.2f}, 'px');",
            f"var textColor{index} = new SolidColor();",
            f"textColor{index}.rgb.red = {color_r};",
            f"textColor{index}.rgb.green = {color_g};",
            f"textColor{index}.rgb.blue = {color_b};",
            f"textItem{index}.color = textColor{index};",
        ]
        if font_name:
            lines.extend(
                [
                    f"var requestedFont{index} = {_js(font_name)};",
                    f"var fontPS{index} = findFontPostScriptName(requestedFont{index});",
                    f"if (fontPS{index}) {{",
                    f"  try {{ textItem{index}.font = fontPS{index}; }} catch (fontError{index}) {{ $.writeln('Failed to set font: ' + requestedFont{index}); }}",
                    "} else {",
                    f"  $.writeln('Font not found, using Photoshop default: ' + requestedFont{index});",
                    "}",
                ]
            )
        if rotation:
            lines.append(f"textLayer{index}.rotate({rotation}, AnchorPosition.MIDDLECENTER);")
        stroke_width = max(0, int(layer.get("stroke_width") or 0))
        if stroke_width > 0:
            stroke_r, stroke_g, stroke_b = _parse_hex_color(str(layer.get("stroke_color") or "#ffffff"))
            lines.append(
                f"try {{ applyTextLayerStroke(textLayer{index}, {stroke_width}, {stroke_r}, {stroke_g}, {stroke_b}); }} "
                f"catch (strokeError{index}) {{ $.writeln('Failed to apply text stroke: ' + {_js(layer_name)}); }}"
            )
        return lines
