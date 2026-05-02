from __future__ import annotations

import os
import shutil
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from PIL import Image, ImageDraw

from ModuleFolders.MangaCore.api.schemas import BrushMaskStrokeRequest, RestoreMaskStrokeRequest
from ModuleFolders.MangaCore.constants import DEFAULT_MASK_PATHS
from ModuleFolders.MangaCore.io.persistence import MangaProjectPersistence
from ModuleFolders.MangaCore.ops.apply import capture_page_assets_operation
from ModuleFolders.MangaCore.pipeline.engines.inpaint import InpaintEngine, InpaintResult
from ModuleFolders.MangaCore.pipeline.engines.render import RenderEngine, RenderResult
from ModuleFolders.MangaCore.pipeline.qualityGate import (
    final_page_path,
    load_quality_gate,
    page_blocked_from_final,
    quality_gate_path,
)
from ModuleFolders.MangaCore.project.session import MangaProjectSession, SessionRegistry

router = APIRouter(prefix="/api/manga", tags=["manga"])


def _get_session_or_404(project_id: str) -> MangaProjectSession:
    session = SessionRegistry.get(project_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Manga project is not open: {project_id}")
    return session


def _safe_project_asset(session: MangaProjectSession, relative_path: str) -> str:
    target = os.path.realpath(session.project_path / relative_path)
    root = os.path.realpath(session.project_path)
    if not target.startswith(root):
        raise HTTPException(status_code=403, detail="Asset path escapes manga project root.")
    if not os.path.exists(target):
        raise HTTPException(status_code=404, detail=f"Asset not found: {relative_path}")
    return target


def _asset_version(session: MangaProjectSession, relative_path: str) -> int:
    target = session.project_path / relative_path
    if not target.exists():
        return 0
    return int(target.stat().st_mtime_ns)


def _ensure_restore_mask_path(session: MangaProjectSession, page) -> str:
    if getattr(page.masks, "restore", ""):
        restore_relative_path = page.masks.restore
    else:
        page_key = f"{page.index:04d}"
        restore_relative_path = str(os.path.join("pages", page_key, DEFAULT_MASK_PATHS["restore"])).replace("\\", "/")
        page.masks.restore = restore_relative_path
    restore_path = session.project_path / restore_relative_path
    if not restore_path.exists() and page.width > 0 and page.height > 0:
        restore_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("L", (page.width, page.height), 0).save(restore_path, format="PNG")
    return page.masks.restore


def _load_or_create_mask(mask_path: str, size: tuple[int, int]) -> Image.Image:
    if os.path.exists(mask_path):
        with Image.open(mask_path) as existing:
            mask = existing.convert("L")
            if mask.size != size:
                mask = mask.resize(size, resample=Image.Resampling.NEAREST)
            return mask
    return Image.new("L", size, 0)


def _stroke_points(request_points, width: int, height: int) -> list[tuple[int, int]]:
    return [
        (
            max(0, min(width, int(round(point.x)))),
            max(0, min(height, int(round(point.y)))),
        )
        for point in request_points
    ]


def _draw_mask_stroke(mask: Image.Image, points: list[tuple[int, int]], *, radius: int, fill: int) -> None:
    draw = ImageDraw.Draw(mask)
    if len(points) == 1:
        x, y = points[0]
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)
        return

    draw.line(points, fill=fill, width=radius * 2)
    for x, y in points:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)


def _final_page_asset_ref(page) -> dict[str, object]:
    return {"root": "output", "path": f"final/pages/{page.index:04d}.png"}


def _page_artifact_asset_ref(page, filename: str) -> dict[str, object]:
    return {"root": "project", "path": f"pages/{page.index:04d}/{filename}"}


def _project_asset_ref(relative_path: str) -> dict[str, object]:
    return {"root": "project", "path": relative_path}


def _brush_stroke_asset_refs(page) -> list[dict[str, object]]:
    return [
        _project_asset_ref(page.masks.brush),
        _project_asset_ref(page.layers.inpainted),
        _project_asset_ref(page.layers.rendered),
        _page_artifact_asset_ref(page, "inpaintResults.json"),
        _page_artifact_asset_ref(page, "renderResults.json"),
        _final_page_asset_ref(page),
    ]


def _restore_stroke_asset_refs(page) -> list[dict[str, object]]:
    return [
        _project_asset_ref(page.masks.restore),
        _project_asset_ref(page.layers.rendered),
        _final_page_asset_ref(page),
    ]


def _quality_gate_payload(session: MangaProjectSession, project_id: str, page) -> dict[str, object]:
    gate = load_quality_gate(session, page)
    blocked, _reasons = page_blocked_from_final(session, page)
    issues = gate.issues if gate else []
    blocking_issues = [issue for issue in issues if issue.blocks_final]
    artifact_relative_path = f"pages/{page.index:04d}/qualityGate.json"
    artifact_path = quality_gate_path(session, page)
    artifact_exists = artifact_path.exists()
    final_path = final_page_path(session, page)
    return {
        "exists": gate is not None and artifact_exists,
        "ok": gate.ok if gate else True,
        "final_allowed": gate.final_allowed if gate else True,
        "blocked_from_final": blocked,
        "issue_count": len(blocking_issues),
        "issues": [issue.to_dict() for issue in issues],
        "metrics": dict(gate.metrics) if gate else {},
        "stage_modes": dict(gate.stage_modes) if gate else {},
        "artifact_path": artifact_relative_path if artifact_exists else "",
        "artifact_url": (
            f"/api/manga/projects/{project_id}/assets/{artifact_relative_path}?v={_asset_version(session, artifact_relative_path)}"
            if artifact_exists
            else ""
        ),
        "draft_rendered_path": page.layers.rendered,
        "draft_rendered_url": f"/api/manga/projects/{project_id}/assets/{page.layers.rendered}?v={_asset_version(session, page.layers.rendered)}",
        "final_page_path": f"final/pages/{page.index:04d}.png",
        "final_page_exists": final_path.exists(),
    }


def _record_page_asset_history(
    session: MangaProjectSession,
    page_id: str,
    before_op,
    asset_refs: list[dict[str, object]],
) -> int:
    after_op = capture_page_assets_operation(session, page_id, asset_refs)
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    record = session.history.push(forward_ops=[after_op], inverse_ops=[before_op], timestamp=timestamp)
    session.manifest.updated_at = record.timestamp
    MangaProjectPersistence.save_session(session)
    return record.seq


def _sync_rendered_to_final(session: MangaProjectSession, page) -> None:
    rendered_path = session.project_path / page.layers.rendered
    if not rendered_path.exists():
        return
    final_path = session.output_root / "final" / "pages" / f"{page.index:04d}.png"
    final_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(rendered_path, final_path)


def _apply_restore_mask_to_rendered(session: MangaProjectSession, page) -> None:
    restore_relative_path = _ensure_restore_mask_path(session, page)
    restore_path = session.project_path / restore_relative_path
    source_path = session.project_path / page.layers.source
    rendered_path = session.project_path / page.layers.rendered
    if not restore_path.exists() or not source_path.exists() or not rendered_path.exists():
        return

    with Image.open(rendered_path) as rendered_image:
        rendered = rendered_image.convert("RGBA")
    with Image.open(restore_path) as mask_image:
        restore_mask = mask_image.convert("L")
        if restore_mask.size != rendered.size:
            restore_mask = restore_mask.resize(rendered.size, resample=Image.Resampling.NEAREST)
    if not restore_mask.getbbox():
        rendered.save(rendered_path, format="PNG")
        return
    with Image.open(source_path) as source_image:
        source = source_image.convert("RGBA")
        if source.size != rendered.size:
            source = source.resize(rendered.size, resample=Image.Resampling.BICUBIC)
    Image.composite(source, rendered, restore_mask).save(rendered_path, format="PNG")


def _refresh_page_inpaint_and_render(session: MangaProjectSession, page) -> tuple[InpaintResult, RenderResult]:
    snapshot = session.config_snapshot if isinstance(getattr(session, "config_snapshot", None), dict) else {}
    inpaint_engine = InpaintEngine()
    inpaint_engine.configure(snapshot.get("manga_inpaint_engine"))
    inpaint_result = inpaint_engine.run(
        source_path=session.project_path / page.layers.source,
        segment_mask_path=session.project_path / page.masks.segment,
        brush_mask_path=session.project_path / page.masks.brush,
        output_path=session.project_path / page.layers.inpainted,
    )
    MangaProjectPersistence.write_page_artifact(session, page, "inpaintResults.json", inpaint_result.to_dict())

    render_result = RenderEngine().run_page(session, page)
    MangaProjectPersistence.write_page_artifact(session, page, "renderResults.json", render_result.to_dict())
    page.last_pipeline_stage = "page_rendering"
    return inpaint_result, render_result


def _mark_page_edited(session: MangaProjectSession, page) -> None:
    page.status = "edited"
    session.manifest.updated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    MangaProjectPersistence.save_session(session)


@router.get("/projects/{project_id}/pages/{page_id}")
def get_page(project_id: str, page_id: str) -> dict[str, object]:
    session = _get_session_or_404(project_id)
    page = session.pages.get(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")

    return {
        "page_id": page.page_id,
        "index": page.index,
        "width": page.width,
        "height": page.height,
        "status": page.status,
        "layers": {
            "source_url": f"/api/manga/projects/{project_id}/assets/{page.layers.source}?v={_asset_version(session, page.layers.source)}",
            "overlay_text_url": f"/api/manga/projects/{project_id}/assets/{page.layers.overlay_text}?v={_asset_version(session, page.layers.overlay_text)}",
            "inpainted_url": f"/api/manga/projects/{project_id}/assets/{page.layers.inpainted}?v={_asset_version(session, page.layers.inpainted)}",
            "rendered_url": f"/api/manga/projects/{project_id}/assets/{page.layers.rendered}?v={_asset_version(session, page.layers.rendered)}",
        },
        "masks": {
            "segment_url": f"/api/manga/projects/{project_id}/assets/{page.masks.segment}?v={_asset_version(session, page.masks.segment)}",
            "bubble_url": f"/api/manga/projects/{project_id}/assets/{page.masks.bubble}?v={_asset_version(session, page.masks.bubble)}",
            "brush_url": f"/api/manga/projects/{project_id}/assets/{page.masks.brush}?v={_asset_version(session, page.masks.brush)}",
            "restore_url": f"/api/manga/projects/{project_id}/assets/{_ensure_restore_mask_path(session, page)}?v={_asset_version(session, page.masks.restore)}",
        },
        "blocks": [block.to_dict() for block in page.text_blocks],
        "quality_gate": _quality_gate_payload(session, project_id, page),
    }


@router.get("/projects/{project_id}/pages/{page_id}/thumbnail")
def get_page_thumbnail(project_id: str, page_id: str):
    session = _get_session_or_404(project_id)
    page = session.pages.get(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")
    return FileResponse(_safe_project_asset(session, page.thumbnail_path))


@router.get("/projects/{project_id}/assets/{asset_path:path}")
def get_project_asset(project_id: str, asset_path: str):
    session = _get_session_or_404(project_id)
    return FileResponse(_safe_project_asset(session, asset_path))


@router.post("/projects/{project_id}/pages/{page_id}/brush-mask/strokes")
def apply_brush_mask_stroke(project_id: str, page_id: str, request: BrushMaskStrokeRequest) -> dict[str, object]:
    session = _get_session_or_404(project_id)
    page = session.pages.get(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")
    if not request.points:
        raise HTTPException(status_code=400, detail="Brush stroke requires at least one point.")

    asset_refs = _brush_stroke_asset_refs(page)
    before_op = capture_page_assets_operation(session, page_id, asset_refs)
    brush_mask_path = session.project_path / page.masks.brush
    brush_mask_path.parent.mkdir(parents=True, exist_ok=True)
    mask = _load_or_create_mask(str(brush_mask_path), (page.width, page.height))
    radius = max(1, min(256, int(request.radius)))
    points = _stroke_points(request.points, page.width, page.height)
    _draw_mask_stroke(mask, points, radius=radius, fill=255)

    mask.save(brush_mask_path, format="PNG")
    inpaint_result, render_result = _refresh_page_inpaint_and_render(session, page)
    _mark_page_edited(session, page)
    history_seq = _record_page_asset_history(session, page_id, before_op, asset_refs)

    version = _asset_version(session, page.masks.brush)
    inpainted_version = _asset_version(session, page.layers.inpainted)
    rendered_version = _asset_version(session, page.layers.rendered)
    return {
        "ok": True,
        "mode": request.mode,
        "radius": radius,
        "point_count": len(points),
        "mask_pixels": inpaint_result.mask_pixels,
        "inpaint_runtime_engine_id": inpaint_result.runtime_engine_id,
        "render_runtime_engine_id": render_result.runtime_engine_id,
        "brush_url": f"/api/manga/projects/{project_id}/assets/{page.masks.brush}?v={version}",
        "inpainted_url": f"/api/manga/projects/{project_id}/assets/{page.layers.inpainted}?v={inpainted_version}",
        "rendered_url": f"/api/manga/projects/{project_id}/assets/{page.layers.rendered}?v={rendered_version}",
        "history_seq": history_seq,
        "updated_at": session.manifest.updated_at,
    }


@router.post("/projects/{project_id}/pages/{page_id}/restore-mask/strokes")
def apply_restore_mask_stroke(project_id: str, page_id: str, request: RestoreMaskStrokeRequest) -> dict[str, object]:
    session = _get_session_or_404(project_id)
    page = session.pages.get(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")
    if not request.points:
        raise HTTPException(status_code=400, detail="Restore stroke requires at least one point.")

    restore_relative_path = _ensure_restore_mask_path(session, page)
    asset_refs = _restore_stroke_asset_refs(page)
    before_op = capture_page_assets_operation(session, page_id, asset_refs)
    restore_mask_path = session.project_path / restore_relative_path
    restore_mask_path.parent.mkdir(parents=True, exist_ok=True)
    mask = _load_or_create_mask(str(restore_mask_path), (page.width, page.height))
    radius = max(1, min(256, int(request.radius)))
    points = _stroke_points(request.points, page.width, page.height)
    _draw_mask_stroke(mask, points, radius=radius, fill=255)
    mask.save(restore_mask_path, format="PNG")
    _apply_restore_mask_to_rendered(session, page)
    _sync_rendered_to_final(session, page)
    _mark_page_edited(session, page)
    history_seq = _record_page_asset_history(session, page_id, before_op, asset_refs)

    restore_version = _asset_version(session, restore_relative_path)
    rendered_version = _asset_version(session, page.layers.rendered)
    return {
        "ok": True,
        "mode": request.mode,
        "radius": radius,
        "point_count": len(points),
        "restore_url": f"/api/manga/projects/{project_id}/assets/{restore_relative_path}?v={restore_version}",
        "rendered_url": f"/api/manga/projects/{project_id}/assets/{page.layers.rendered}?v={rendered_version}",
        "history_seq": history_seq,
        "updated_at": session.manifest.updated_at,
    }
